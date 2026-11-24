/* Test copy only (SaveDataFolder\kor_testpad): the game reads the keyboard and mouse globally (raw input with
 * background delivery, GetAsyncKeyState, GetCursorPos), so a test game behind the user's windows reacted to the
 * user's own typing and clicks. Here its USER32 imports are redirected:
 *   GetAsyncKeyState -> 0 (except injected mouse buttons), GetRawInputData -> header type made unknown,
 *   GetCursorPos/ScreenToClient -> the injected point KOR_MOUSE[0..1] (client pixels; default far outside). */
typedef unsigned int u32;
typedef int BOOL;
#define WINAPI __stdcall
#define IMP __declspec(dllimport)
IMP BOOL WINAPI VirtualProtect(void *, u32, u32, u32 *);
IMP void *WINAPI GetModuleHandleA(const char *);

volatile int KOR_MOUSE[3] = {-4000, -4000, 0}; /* x, y (client px), buttons bit0 left bit1 right */
volatile u32 KOR_INPUT_ISOLATED;

static u32(WINAPI *real_rid)(void *, u32, void *, u32 *, u32);

volatile int KOR_VKEYS[4]; /* virtual-key codes the test tool holds down */
static short WINAPI my_gaks(int vk)
{
    for (u32 i = 0; i < 4; i++)
        if (KOR_VKEYS[i] && KOR_VKEYS[i] == vk)
            return (short)0x8001;
    if (vk == 1 && (KOR_MOUSE[2] & 1))
        return (short)0x8000;
    if (vk == 2 && (KOR_MOUSE[2] & 2))
        return (short)0x8000;
    return 0;
}

#define RID_MAGIC ((void *)0x4B4F5200) /* WM_INPUT posted by the test tool: a mouse event at KOR_MOUSE */
static u32 WINAPI my_rid(void *h, u32 cmd, void *data, u32 *size, u32 hdr)
{
    if (h == RID_MAGIC) {
        if (!data) {
            *size = 0x28;
            return 0;
        }
        for (u32 i = 0; i < 0x28u && i < *size; i++)
            ((unsigned char *)data)[i] = 0; /* dwType 0 = RIM_TYPEMOUSE */
        return 0x28;
    }
    u32 r = real_rid(h, cmd, data, size, hdr);
    if (data && r != 0xFFFFFFFFu && r >= 4u)
        *(u32 *)data = 0x7F; /* RAWINPUTHEADER.dwType: no keyboard / mouse / HID */
    return r;
}

static BOOL WINAPI my_gcp(int *pt)
{
    pt[0] = KOR_MOUSE[0];
    pt[1] = KOR_MOUSE[1];
    return 1;
}

static BOOL WINAPI my_s2c(void *hwnd, int *pt)
{
    (void)hwnd, (void)pt; /* the injected point is already in client pixels */
    return 1;
}

static void put(u32 slot, void *fn, void **save)
{
    void **p = (void **)slot;
    u32 old;
    VirtualProtect(p, 4, 0x04, &old);
    if (save)
        *save = *p;
    *p = fn;
    VirtualProtect(p, 4, old, &old);
}

/* window mouse messages (WM_MOUSEMOVE .. WM_MOUSEHWHEEL) reach the game's handler 0x4ff2c0 (stdcall hwnd, msg,
 * wParam, lParam) from the window procedure (0x4f5d29). Only the test tool's own messages pass: they carry 0x4000
 * in wParam (removed before the game sees it). */
static u32 mouse_handler;
static u32 WINAPI my_mouse(void *hwnd, u32 msg, u32 wp, u32 lp)
{
    if (msg >= 0x200u && msg <= 0x20Eu) {
        if (!(wp & 0x4000u))
            return 0;
        wp &= ~0x4000u;
    }
    return ((u32(WINAPI *)(void *, u32, u32, u32))mouse_handler)(hwnd, msg, wp, lp);
}
int redirect_call(u32 bit, u32 va, u32 target_va, void *fn);

void testinput_install(void)
{
    u32 d = (u32)GetModuleHandleA(0) - 0x400000u;
    put(0x5392bc + d, (void *)my_gaks, 0);
    put(0x5392d0 + d, (void *)my_rid, (void **)&real_rid);
    put(0x5392d4 + d, (void *)my_gcp, 0);
    put(0x5392cc + d, (void *)my_s2c, 0);
    mouse_handler = 0x4ff2c0 + d;
    if (redirect_call(23, 0x4f5d29, 0x4ff2c0, (void *)my_mouse))
        KOR_INPUT_ISOLATED = 3;
    else
        KOR_INPUT_ISOLATED = 1;
}
