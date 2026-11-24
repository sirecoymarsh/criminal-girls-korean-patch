/* Mod + Decensor on PC: data\kor_decensor.dat (pc/tools/make_pc_decensor.py, from the Vita "CGIO - Mod + Decensor")
 * laid over the game's archive data_jp.dat / data_en.dat. Read at game start; OPT_V[10] (설정 > 모드) decides.
 *
 * Archive object [0x5e5468]: +0x12d4b4 file header (PS3FS_V1, u64 count at +0x12d4bc), +0x12d4c4 table (64-byte
 * entries: name[40], u64 0, u64 size at +0x30, u64 offset at +0x38; sorted bytewise, binary search 0x50a050),
 * +0x12d4c8 three FILE* of the same file (one per reader). Load 0x507480: reads the header and the table, then at
 * 0x5076f0 resolves pending requests and starts the reader thread 0x509ed0. Every archive read is
 * fseek(FILE*, low dword of the offset, SEEK_SET) then fread (IAT 0x539220 / 0x539144). The table block comes from
 * 0x4f2260 (header [p-0x10] raw, [p-0xc] size, [p-8] align, byte [p-4] 1 = VirtualAlloc) and is freed by 0x4f2360.
 *
 * At 0x5076f0 the overlay goes into the table: its files point past the end of the real file (VBASE + offset in the
 * overlay; new names are inserted in order). Our fseek/fread serve seeks to >= VBASE on the three archive FILE*s from
 * the overlay, and copy the patches (anm0000.fad: the pink fog texture made transparent) over normal reads. */
typedef unsigned int u32;
typedef unsigned char u8;
typedef int BOOL;
#define WINAPI __stdcall
#define IMP __declspec(dllimport)

IMP void *WINAPI CreateFileA(const char *, u32, u32, void *, u32, u32, void *);
IMP BOOL WINAPI ReadFile(void *, void *, u32, u32 *, void *);
IMP BOOL WINAPI CloseHandle(void *);
IMP u32 WINAPI SetFilePointer(void *, long, long *, u32);
IMP void *WINAPI VirtualAlloc(void *, u32, u32, u32);
IMP BOOL WINAPI VirtualProtect(void *, u32, u32, u32 *);
IMP u32 WINAPI GetModuleFileNameA(void *, char *, u32);
IMP u32 WINAPI GetFileAttributesA(const char *);

extern volatile u8 OPT_V[16];
extern u32 KOR_DELTA;
extern volatile u32 KOR_HOOKS;
int prehook(u32 bit, u32 va, const u8 *expect, u32 n, void(__cdecl *fn)(u32 *));
void *memcpy(void *, const void *, u32);
void *memset(void *, int, u32);
#define R(va) ((u32)(va) + KOR_DELTA)

#define VBASE 0x78000000u /* above data_en.dat (0x7468xxxx) and data_jp.dat, below 2 GB (32-bit fseek) */
#define MAXF 1024u
#define MAXP 4u
#define INVALID ((void *)-1)

struct ofile {
    char name[48];
    u32 size, off;
};
struct opatch {
    char name[48];
    u32 esize, rel, len, off;
};

static char path[300];
static struct ofile *F;
static u32 NF, NP, OVL_SIZE, loaded;
static struct opatch P[MAXP];
static u32 PABS[MAXP];
static u8 PON[MAXP];
static void *H[3]; /* the overlay, one handle per archive FILE* (each FILE* is used by one reader at a time) */
static volatile u32 VON[3], VPOS[3];
static volatile u32 ACTIVE;
/* debug (memory probe): state, files placed, new names, patches on, overlay reads, patch copies */
volatile u32 KOR_DCN[6];

static int(__cdecl *real_fseek)(void *, long, int);
static u32(__cdecl *real_fread)(void *, u32, u32, void *);
static long(__cdecl *real_ftell)(void *);

static void path_init(void)
{
    if (path[0])
        return;
    u32 n = GetModuleFileNameA(0, path, 260);
    while (n && path[n - 1] != '\\')
        n--;
    const char *t = "data\\kor_decensor.dat";
    for (u32 i = 0; t[i]; i++)
        path[n++] = t[i];
    path[n] = 0;
}

int decensor_available(void)
{
    path_init();
    return GetFileAttributesA(path) != 0xFFFFFFFFu;
}

static int name_ok(const char *s)
{
    for (u32 i = 0; i < 40; i++)
        if (!s[i])
            return i > 0;
    return 0;
}

/* 1 = overlay tables in memory */
static int ovl_load(void)
{
    if (loaded)
        return loaded == 1u;
    loaded = 2;
    path_init();
    void *h = CreateFileA(path, 0x80000000u, 1, 0, 3, 0, 0);
    if (h == INVALID)
        return 0;
    u32 head[4], got = 0, ok = 0;
    OVL_SIZE = SetFilePointer(h, 0, 0, 2 /* FILE_END */);
    SetFilePointer(h, 0, 0, 0);
    if (ReadFile(h, head, 16, &got, 0) && got == 16 && head[0] == 0x4E43444Bu /* KDCN */ && head[1] == 0x33303030u
        /* 0003 */ && head[2] && head[2] <= MAXF && head[3] <= MAXP) {
        NF = head[2], NP = head[3];
        F = VirtualAlloc(0, NF * sizeof(struct ofile), 0x3000, 4);
        if (F && ReadFile(h, F, NF * sizeof(struct ofile), &got, 0) && got == NF * sizeof(struct ofile) &&
            (!NP || (ReadFile(h, P, NP * sizeof(struct opatch), &got, 0) && got == NP * sizeof(struct opatch)))) {
            ok = 1;
            for (u32 i = 0; i < NF; i++)
                if (!name_ok(F[i].name) || F[i].off > OVL_SIZE || F[i].size > OVL_SIZE - F[i].off)
                    ok = 0;
            for (u32 i = 0; i < NP; i++)
                if (!name_ok(P[i].name) || P[i].off > OVL_SIZE || P[i].len > OVL_SIZE - P[i].off ||
                    P[i].rel > P[i].esize || P[i].len > P[i].esize - P[i].rel)
                    ok = 0;
        }
    }
    CloseHandle(h);
    if (ok)
        loaded = 1;
    return ok;
}

static int cmp(const char *a, const char *b)
{
    for (;; a++, b++) {
        u8 x = (u8)*a, y = (u8)*b;
        if (x != y)
            return x < y ? -1 : 1;
        if (!x)
            return 0;
    }
}

/* index of name, or -(insert position) - 1 */
static int find(const u8 *t, u32 n, const char *name)
{
    u32 lo = 0, hi = n;
    while (lo < hi) {
        u32 mid = (lo + hi) / 2;
        int c = cmp(name, (const char *)(t + mid * 64u));
        if (!c)
            return (int)mid;
        if (c < 0)
            hi = mid;
        else
            lo = mid + 1;
    }
    return -(int)lo - 1;
}

static int slot(void *f)
{
    u8 *obj = *(u8 **)R(0x5e5468);
    if (!obj || !f)
        return -1;
    for (int i = 0; i < 3; i++)
        if (*(void **)(obj + 0x12d4c8 + 4 * i) == f)
            return i;
    return -1;
}

static u32 ovl_read(int s, u32 off, void *buf, u32 n)
{
    if (off >= OVL_SIZE)
        return 0;
    if (n > OVL_SIZE - off)
        n = OVL_SIZE - off;
    u32 got = 0;
    if (SetFilePointer(H[s], (long)off, 0, 0) != off || !ReadFile(H[s], buf, n, &got, 0))
        return 0;
    return got;
}

static int __cdecl my_fseek(void *f, long off, int org)
{
    int s = ACTIVE ? slot(f) : -1;
    if (s >= 0) {
        if (org == 0 && (u32)off >= VBASE) {
            VPOS[s] = (u32)off - VBASE;
            VON[s] = 1;
            return 0;
        }
        VON[s] = 0;
    }
    return real_fseek(f, off, org);
}

static u32 __cdecl my_fread(void *buf, u32 size, u32 count, void *f)
{
    int s = ACTIVE ? slot(f) : -1;
    if (s < 0 || !size)
        return real_fread(buf, size, count, f);
    if (VON[s]) {
        u32 got = ovl_read(s, VPOS[s], buf, size * count);
        VPOS[s] += got;
        KOR_DCN[4]++;
        return got / size;
    }
    if (!KOR_DCN[3])
        return real_fread(buf, size, count, f);
    long pos = real_ftell(f);
    u32 r = real_fread(buf, size, count, f), got = r * size;
    if (pos >= 0)
        for (u32 i = 0; i < NP; i++) {
            if (!PON[i])
                continue;
            u32 a = (u32)pos, b = a + got, pa = PABS[i], pb = pa + P[i].len;
            u32 st = a > pa ? a : pa, en = b < pb ? b : pb;
            if (st < en) {
                ovl_read(s, P[i].off + (st - pa), (u8 *)buf + (st - a), en - st);
                KOR_DCN[5]++;
            }
        }
    return r;
}

/* 0x507539 (load: old reader thread stopped, each archive FILE* closed and about to be reopened; runs 3 times):
 * nothing of the old overlay state may leak into this load */
static void __cdecl on_load(u32 *fr)
{
    (void)fr;
    ACTIVE = 0;
    for (int i = 0; i < 3; i++)
        VON[i] = 0;
    for (u32 i = 0; i < MAXP; i++)
        PON[i] = 0;
    KOR_DCN[3] = 0;
}

/* 0x5076f0 (table read, requests not yet resolved): edi = archive object */
static void __cdecl on_table(u32 *fr)
{
    u8 *obj = (u8 *)fr[0];
    KOR_DCN[0] = 1;
    if (!OPT_V[10] || !(KOR_HOOKS & (1u << 29)) || !ovl_load())
        return;
    KOR_DCN[0] = 2;
    u8 *t = *(u8 **)(obj + 0x12d4c4);
    u32 n = *(u32 *)(obj + 0x12d4bc);
    if (!t || !n || *(u32 *)(obj + 0x12d4c0))
        return;
    for (u32 i = 0; i < n; i++) { /* the real file must end below VBASE */
        const u8 *e = t + i * 64u;
        u32 sz = *(const u32 *)(e + 0x30), off = *(const u32 *)(e + 0x38);
        if (*(const u32 *)(e + 0x34) || *(const u32 *)(e + 0x3c) || off >= VBASE || sz > VBASE - off)
            return;
    }
    KOR_DCN[0] = 3;
    for (int i = 0; i < 3; i++)
        if (!H[i] && (H[i] = CreateFileA(path, 0x80000000u, 1, 0, 3, 0, 0)) == INVALID) {
            H[i] = 0;
            return;
        }
    u32 add = 0;
    for (u32 i = 0; i < NF; i++)
        if (find(t, n, F[i].name) < 0)
            add++;
    u8 *nt = t;
    u32 cnt = n;
    if (add) {
        u32 bytes = 16u + (n + add) * 64u;
        u8 *base = VirtualAlloc(0, bytes, 0x3000, 4);
        if (!base)
            return;
        nt = base + 16;
        *(u32 *)(nt - 16) = (u32)base;
        *(u32 *)(nt - 12) = bytes;
        *(u32 *)(nt - 8) = 16;
        nt[-4] = 1; /* freed with VirtualFree by the game (0x4f2360) */
        memcpy(nt, t, n * 64u);
        for (u32 i = 0; i < NF; i++) {
            int k = find(nt, cnt, F[i].name);
            if (k >= 0)
                continue;
            u32 at = (u32)(-k - 1);
            for (u32 j = cnt; j > at; j--)
                memcpy(nt + j * 64u, nt + (j - 1) * 64u, 64);
            memset(nt + at * 64u, 0, 64);
            memcpy(nt + at * 64u, F[i].name, 40);
            cnt++;
        }
    }
    u32 placed = 0;
    for (u32 i = 0; i < NF; i++) {
        int k = find(nt, cnt, F[i].name);
        if (k < 0)
            continue;
        u8 *e = nt + (u32)k * 64u;
        memset(e + 0x28, 0, 0x18);
        *(u32 *)(e + 0x30) = F[i].size;
        *(u32 *)(e + 0x38) = VBASE + F[i].off;
        placed++;
    }
    for (u32 i = 0; i < NP; i++) {
        int k = find(nt, cnt, P[i].name);
        PON[i] = 0;
        if (k < 0)
            continue;
        const u8 *e = nt + (u32)k * 64u;
        if (*(const u32 *)(e + 0x30) != P[i].esize || *(const u32 *)(e + 0x38) >= VBASE)
            continue; /* a different build of that file: leave it */
        PABS[i] = *(const u32 *)(e + 0x38) + P[i].rel;
        PON[i] = 1;
        KOR_DCN[3]++;
    }
    if (add) {
        *(u8 **)(obj + 0x12d4c4) = nt;
        *(u32 *)(obj + 0x12d4bc) = cnt;
        ((void(__fastcall *)(void *))R(0x4f2360))(t);
    }
    KOR_DCN[1] = placed;
    KOR_DCN[2] = add;
    KOR_DCN[0] = 4;
    ACTIVE = 1;
}

static int iat_swap(u32 va, void *fn, void **orig)
{
    void **slotp = (void **)R(va);
    u32 old;
    if (!VirtualProtect(slotp, 4, 4 /* PAGE_READWRITE */, &old))
        return 0;
    *orig = *slotp;
    *slotp = fn;
    VirtualProtect(slotp, 4, old, &old);
    return 1;
}

void decensor_install(void)
{
    static const u8 E_LOAD[10] = {0xc7, 0x87, 0xac, 0xd4, 0x12, 0, 0, 0, 0, 0};  /* mov [edi+0x12d4ac], 0 */
    static const u8 E_TABLE[10] = {0xc7, 0x87, 0xd4, 0xd4, 0x12, 0x00, 7, 0, 0, 0}; /* mov [edi+0x12d4d4], 7 */
    real_ftell = *(long(__cdecl **)(void *))R(0x539150);
    if (!prehook(27, 0x507539, E_LOAD, 10, on_load))
        return;
    if (!prehook(28, 0x5076f0, E_TABLE, 10, on_table))
        return;
    if (iat_swap(0x539220, (void *)my_fseek, (void **)&real_fseek) &&
        iat_swap(0x539144, (void *)my_fread, (void **)&real_fread))
        KOR_HOOKS |= 1u << 29;
}
