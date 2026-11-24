/* Test helper: in-process screenshot of the game's back buffer (no screen grab, so no other window can be caught).
 * steam_criminal.exe imports d3d9!Direct3DCreate9 by name: we wrap it, then IDirect3D9::CreateDevice (vtable 16),
 * then IDirect3DDevice9::Present (vtable 17). Every 15 presents we look for SaveDataFolder\kor_shot.req; if it is
 * there the back buffer is written to SaveDataFolder\kor_shot.bmp and the request file deleted. */
typedef unsigned int u32;
typedef unsigned char u8;
typedef int BOOL;
typedef long HRESULT;
#define WINAPI __stdcall
#define IMP __declspec(dllimport)
IMP void *WINAPI GetModuleHandleA(const char *);
IMP BOOL WINAPI VirtualProtect(void *, u32, u32, u32 *);
IMP void *WINAPI CreateFileA(const char *, u32, u32, void *, u32, u32, void *);
IMP BOOL WINAPI WriteFile(void *, const void *, u32, u32 *, void *);
IMP BOOL WINAPI CloseHandle(void *);
IMP u32 WINAPI GetFileAttributesA(const char *);
IMP BOOL WINAPI DeleteFileA(const char *);

extern char KOR_DIR[]; /* ...\SaveDataFolder\ (hook.c) */
static char req_path[300], bmp_path[300];

typedef void *(WINAPI *create9_t)(u32);
typedef HRESULT(WINAPI *createdev_t)(void *, u32, u32, void *, u32, void *, void **);
typedef HRESULT(WINAPI *present_t)(void *, const void *, const void *, void *, const void *);
static create9_t real_create9;
static createdev_t real_createdev;
static present_t real_present;
static u32 frames;
volatile u32 KOR_CAP_STATE; /* 1 inline hook in, 2 create9 seen, 4 createdev seen, 8 present seen */
volatile u32 KOR_CNT[4];
volatile u32 KOR_CAPDBG[6]; /* step reached, last hr, format, multisample, width, height */     /* diagnostics: [0] device Present, [1] EndScene, [2] swap chain Present */

static void put_vtbl(void **vt, u32 idx, void *fn, void **orig)
{
    u32 old;
    if (*orig)
        return;
    *orig = vt[idx];
    VirtualProtect(&vt[idx], 4, 0x04 /* PAGE_READWRITE */, &old);
    vt[idx] = fn;
    VirtualProtect(&vt[idx], 4, old, &old);
}

#define VT(obj) (*(void ***)(obj))
#define CALL(obj, idx, type) ((type)VT(obj)[idx])

typedef struct {
    u32 Format, Type, Usage, Pool, MultiSampleType, MultiSampleQuality, Width, Height;
} SURFDESC;
typedef struct {
    int Pitch;
    void *pBits;
} LOCKED;

static void capture(void *dev)
{
    void *bb = 0, *rt = 0, *off = 0;
    HRESULT hr;
    KOR_CAPDBG[0] = 1;
    if ((hr = CALL(dev, 18, HRESULT(WINAPI *)(void *, u32, u32, u32, void **))(dev, 0, 0, 0, &bb)) < 0 || !bb) {
        KOR_CAPDBG[1] = (u32)hr;
        return;
    }
    SURFDESC d;
    CALL(bb, 12, HRESULT(WINAPI *)(void *, SURFDESC *))(bb, &d);
    KOR_CAPDBG[0] = 2, KOR_CAPDBG[2] = d.Format, KOR_CAPDBG[3] = d.MultiSampleType, KOR_CAPDBG[4] = d.Width, KOR_CAPDBG[5] = d.Height;
    void *src = bb;
    if (d.MultiSampleType) { /* resolve first */
        if (CALL(dev, 28, HRESULT(WINAPI *)(void *, u32, u32, u32, u32, u32, BOOL, void **, void *))(
                dev, d.Width, d.Height, d.Format, 0, 0, 0, &rt, 0) >= 0) {
            CALL(dev, 34, HRESULT(WINAPI *)(void *, void *, const void *, void *, const void *, u32))(dev, bb, 0, rt, 0, 0);
            src = rt;
        }
    }
    hr = CALL(dev, 36, HRESULT(WINAPI *)(void *, u32, u32, u32, u32, void **, void *))(
        dev, d.Width, d.Height, d.Format, 2 /* D3DPOOL_SYSTEMMEM */, &off, 0);
    KOR_CAPDBG[1] = (u32)hr;
    if (hr >= 0)
        KOR_CAPDBG[1] = (u32)(hr = CALL(dev, 32, HRESULT(WINAPI *)(void *, void *, void *))(dev, src, off)) | 0x10000000u;
    if (hr >= 0) {
        LOCKED lr;
        if ((d.Format == 21 || d.Format == 22) &&
            CALL(off, 13, HRESULT(WINAPI *)(void *, LOCKED *, const void *, u32))(off, &lr, 0, 0x10 /* READONLY */) >= 0) {
            KOR_CAPDBG[0] = 3;
            void *h = CreateFileA(bmp_path, 0x40000000u, 0, 0, 2, 0, 0);
            if (h != (void *)-1) {
                KOR_CAPDBG[0] = 4;
                u32 w = d.Width, hh = d.Height, img = w * hh * 4, put;
                u8 hdr[54] = {'B', 'M'};
                u32 v;
                v = 54 + img, *(u32 *)(void *)(hdr + 2) = v;
                *(u32 *)(void *)(hdr + 10) = 54;
                *(u32 *)(void *)(hdr + 14) = 40;
                *(u32 *)(void *)(hdr + 18) = w;
                *(u32 *)(void *)(hdr + 22) = (u32)(-(int)hh); /* top-down */
                hdr[26] = 1, hdr[28] = 32;
                *(u32 *)(void *)(hdr + 34) = img;
                WriteFile(h, hdr, 54, &put, 0);
                for (u32 y = 0; y < hh; y++)
                    WriteFile(h, (u8 *)lr.pBits + y * (u32)lr.Pitch, w * 4, &put, 0);
                CloseHandle(h);
            }
            CALL(off, 14, HRESULT(WINAPI *)(void *))(off);
        }
    }
    if (off)
        CALL(off, 2, u32(WINAPI *)(void *))(off);
    if (rt)
        CALL(rt, 2, u32(WINAPI *)(void *))(rt);
    CALL(bb, 2, u32(WINAPI *)(void *))(bb);
}

/* per-frame callback for other modules (subtitles later) */
void (*kor_on_present)(void *dev);

static HRESULT WINAPI my_present(void *dev, const void *a, const void *b, void *c, const void *e)
{
    KOR_CAP_STATE |= 8;
    KOR_CNT[0]++;
    if (kor_on_present)
        kor_on_present(dev);
    if (++frames % 15u == 0u && GetFileAttributesA(req_path) != 0xFFFFFFFFu) {
        capture(dev);
        DeleteFileA(req_path);
    }
    return real_present(dev, a, b, c, e);
}

typedef HRESULT(WINAPI *endscene_t)(void *);
typedef HRESULT(WINAPI *scpresent_t)(void *, const void *, const void *, void *, const void *, u32);
static endscene_t real_endscene;
static scpresent_t real_scpresent;
static void *last_dev;

static HRESULT WINAPI my_endscene(void *dev)
{
    KOR_CNT[1]++;
    last_dev = dev;
    return real_endscene(dev);
}

static HRESULT WINAPI my_scpresent(void *sc, const void *a, const void *b, void *c, const void *e, u32 f)
{
    KOR_CNT[2]++;
    if (last_dev && KOR_CNT[2] % 15u == 0u && GetFileAttributesA(req_path) != 0xFFFFFFFFu) {
        capture(last_dev);
        DeleteFileA(req_path);
    }
    return real_scpresent(sc, a, b, c, e, f);
}

extern volatile u32 KOR_TESTPAD;
volatile u32 KOR_PP[3]; /* what the game asked for: Windowed, width, height */
void *KOR_DEVICE; /* the game's IDirect3DDevice9 (subs.c makes its white texture with it) */
typedef HRESULT(WINAPI *reset_t)(void *, void *);
static reset_t real_reset;
static HRESULT WINAPI my_reset(void *dev, void *pp)
{
    u32 *p = pp;
    KOR_PP[0] = p[8] | 0x100u;
    if (KOR_TESTPAD)
        p[8] = 1, p[12] = 0;
    return real_reset(dev, pp);
}

static HRESULT WINAPI my_createdev(void *d3d, u32 ad, u32 ty, void *wnd, u32 fl, void *pp, void **out)
{
    u32 *p = pp; /* D3DPRESENT_PARAMETERS: [0] w [1] h ... [8] Windowed ... [12] FullScreen_RefreshRateInHz */
    KOR_PP[0] = p[8], KOR_PP[1] = p[0], KOR_PP[2] = p[1];
    if (KOR_TESTPAD) { /* test copy: never take the display (no mode change, no lost device in the background) */
        p[8] = 1;
        p[12] = 0;
    }
    HRESULT r = real_createdev(d3d, ad, ty, wnd, fl, pp, out);
    KOR_CAP_STATE |= 4;
    KOR_CAPDBG[5] = (u32)r;
    KOR_CAPDBG[4] = p[6] | (p[3] << 8) | (p[13] << 16); /* SwapEffect, BackBufferCount, PresentationInterval */
    if (r >= 0 && out && *out) {
        void *dev = *out, *sc = 0;
        KOR_DEVICE = dev;
        put_vtbl(VT(dev), 17, (void *)my_present, (void **)&real_present);
        put_vtbl(VT(dev), 42, (void *)my_endscene, (void **)&real_endscene);
        put_vtbl(VT(dev), 16, (void *)my_reset, (void **)&real_reset);
        if (CALL(dev, 14, HRESULT(WINAPI *)(void *, u32, void **))(dev, 0, &sc) >= 0 && sc) { /* GetSwapChain(0) */
            put_vtbl(VT(sc), 3, (void *)my_scpresent, (void **)&real_scpresent);
            CALL(sc, 2, u32(WINAPI *)(void *))(sc);
        }
    }
    return r;
}

static void *WINAPI my_create9(u32 sdk)
{
    void *d3d = real_create9(sdk);
    KOR_CAP_STATE |= 2;
    if (d3d)
        put_vtbl(VT(d3d), 16, (void *)my_createdev, (void **)&real_createdev);
    return d3d;
}

IMP void *WINAPI LoadLibraryA(const char *);
IMP void *WINAPI GetProcAddress(void *, const char *);
IMP void *WINAPI VirtualAlloc(void *, u32, u32, u32);
IMP BOOL WINAPI FlushInstructionCache(void *, const void *, u32);
IMP void *WINAPI GetCurrentProcess(void);

/* cgD3D9.dll loads d3d9.dll itself: hook d3d9!Direct3DCreate9's standard 5-byte prologue
 * (8B FF mov edi,edi / 55 push ebp / 8B EC mov ebp,esp) with a jmp; trampoline = those 5 bytes + jmp back */
static void inline_create9(void)
{
    u8 *f = GetProcAddress(LoadLibraryA("d3d9.dll"), "Direct3DCreate9");
    if (!f || f[0] != 0x8B || f[1] != 0xFF || f[2] != 0x55 || f[3] != 0x8B || f[4] != 0xEC)
        return;
    u8 *t = VirtualAlloc(0, 16, 0x3000, 0x40);
    if (!t)
        return;
    for (u32 i = 0; i < 5; i++)
        t[i] = f[i];
    t[5] = 0xE9;
    *(u32 *)(void *)(t + 6) = (u32)(f + 5) - (u32)(t + 10);
    if (!real_create9)
        real_create9 = (create9_t)t;
    u32 old;
    VirtualProtect(f, 5, 0x40, &old);
    f[0] = 0xE9;
    *(u32 *)(void *)(f + 1) = (u32)my_create9 - (u32)(f + 5);
    VirtualProtect(f, 5, old, &old);
    FlushInstructionCache(GetCurrentProcess(), f, 5);
    KOR_CAP_STATE |= 1;
}

/* paths + the inline hook on d3d9!Direct3DCreate9 (the exe and cgD3D9.dll both end up there) */
void capture_install(void)
{
    u32 n = 0;
    for (; KOR_DIR[n]; n++)
        req_path[n] = bmp_path[n] = KOR_DIR[n];
    const char *r = "kor_shot.req", *b = "kor_shot.bmp";
    for (u32 i = 0; r[i]; i++)
        req_path[n + i] = r[i], bmp_path[n + i] = b[i];
    inline_create9();
}
