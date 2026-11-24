/* Criminal Girls Invite Only (PC, steam_criminal.exe x86) — Korean extras loaded as a proxy xinput1_3.dll.
 * The game imports XInput by ordinal 2 (XInputGetState) and 4 (XInputGetCapabilities); we forward every export to
 * the system DLL. At load time we patch the game's code in memory (the exe file stays untouched):
 * cheats (same places as the Vita EBOOT work, see P:\AI\cg-battle-subs\pc\진행.md).
 * Freestanding: no CRT; kernel32 only. */
typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;
typedef int BOOL;
#define WINAPI __stdcall
#define IMP __declspec(dllimport)

IMP void *WINAPI GetModuleHandleA(const char *);
IMP void *WINAPI LoadLibraryA(const char *);
IMP void *WINAPI GetProcAddress(void *, const char *);
IMP BOOL WINAPI VirtualProtect(void *, u32, u32, u32 *);
IMP u32 WINAPI GetSystemDirectoryA(char *, u32);
IMP u32 WINAPI GetModuleFileNameA(void *, char *, u32);
IMP void *WINAPI CreateFileA(const char *, u32, u32, void *, u32, u32, void *);
IMP BOOL WINAPI ReadFile(void *, void *, u32, u32 *, void *);
IMP BOOL WINAPI WriteFile(void *, const void *, u32, u32 *, void *);
IMP BOOL WINAPI CloseHandle(void *);
IMP BOOL WINAPI FlushInstructionCache(void *, const void *, u32);
IMP void *WINAPI GetCurrentProcess(void);
IMP void WINAPI OutputDebugStringA(const char *);
IMP u32 WINAPI GetFileAttributesA(const char *);
IMP void *WINAPI VirtualAlloc(void *, u32, u32, u32);

void *memcpy(void *d, const void *s, u32 n)
{
    u8 *a = d;
    const u8 *b = s;
    while (n--)
        *a++ = *b++;
    return d;
}
void *memset(void *d, int c, u32 n)
{
    u8 *a = d;
    while (n--)
        *a++ = (u8)c;
    return d;
}

/* ---------------------------------------------------------------- options (same file format as the Vita build) */
#define OPT_N 16
/* [0] 무적 [1] MP [2] 경험치 배율-1 [3] 돈 배율-1 [4] 인카운터 끔 [5] 이동 속도 [6] 전투 속도 [7] CG·회상 개방
 * [8] 전투 말풍선 [9] 주제가 가사 [10] Mod+Decensor */
volatile u8 OPT_V[OPT_N] = {0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 0, 0, 0, 0, 0};
#define OPT_MAGIC 0x4B4F5054u
static char opt_path[300];
char KOR_DIR[300]; /* ...\SaveDataFolder\ */

static void opt_path_init(void)
{
    u32 n = GetModuleFileNameA(0, opt_path, 260); /* ...\steam_criminal.exe */
    while (n && opt_path[n - 1] != '\\')
        n--;
    const char *dir = "SaveDataFolder\\", *tail = "kor_options.bin";
    for (u32 i = 0; dir[i]; i++)
        opt_path[n++] = dir[i];
    for (u32 i = 0; i < n; i++)
        KOR_DIR[i] = opt_path[i];
    KOR_DIR[n] = 0;
    for (u32 i = 0; tail[i]; i++)
        opt_path[n++] = tail[i];
    opt_path[n] = 0;
}

void opt_load(void)
{
    void *h = CreateFileA(opt_path, 0x80000000u /* GENERIC_READ */, 1, 0, 3 /* OPEN_EXISTING */, 0, 0);
    if (h == (void *)-1)
        return;
    u32 buf[1 + OPT_N / 4], got = 0;
    ReadFile(h, buf, sizeof buf, &got, 0);
    CloseHandle(h);
    if (got == sizeof buf && buf[0] == OPT_MAGIC)
        for (u32 i = 0; i < OPT_N; i++)
            OPT_V[i] = ((u8 *)&buf[1])[i];
}

void opt_save(void)
{
    u32 buf[1 + OPT_N / 4], put = 0;
    buf[0] = OPT_MAGIC;
    for (u32 i = 0; i < OPT_N; i++)
        ((u8 *)&buf[1])[i] = OPT_V[i];
    void *h = CreateFileA(opt_path, 0x40000000u /* GENERIC_WRITE */, 0, 0, 2 /* CREATE_ALWAYS */, 0, 0);
    if (h == (void *)-1)
        return;
    WriteFile(h, buf, sizeof buf, &put, 0);
    CloseHandle(h);
}

/* ---------------------------------------------------------------- patching */
u32 KOR_DELTA; /* runtime image base - 0x400000 (ASLR) */
#define DELTA KOR_DELTA
volatile u32 KOR_TICK; /* frames (task-update calls) */
extern volatile u32 KOR_TESTPAD;
#define RVA(va) ((u32)(va) + DELTA)
/* read by the asm stubs */
u32 RET_REWARD, RET_HP[6], RET_MP, ENC_FIELD_PTR, RET_ENC_CONT, RET_ENC_SKIP;
u32 GAL1_HIT, GAL1_MISS, GAL2_HIT, GAL2_MISS, GAL3_HIT, GAL3_MISS, SCENE_HIT, SCENE_MISS;
/* bit set of hooks that went in (debug: read with a memory probe) */
volatile u32 KOR_HOOKS = 0, KOR_MAGIC = 0x4B4F5248u; /* 'HROK' */

static int same(const u8 *p, const u8 *e, u32 n)
{
    for (u32 i = 0; i < n; i++)
        if (p[i] != e[i])
            return 0;
    return 1;
}

static void write_code(u8 *p, const u8 *bytes, u32 n)
{
    u32 old;
    VirtualProtect(p, n, 0x40 /* PAGE_EXECUTE_READWRITE */, &old);
    for (u32 i = 0; i < n; i++)
        p[i] = bytes[i];
    VirtualProtect(p, n, old, &old);
    FlushInstructionCache(GetCurrentProcess(), p, n);
}

/* jmp rel32 to stub at va (n bytes replaced, rest nop) if the original bytes match */
static int hook_jmp(u32 bit, u32 va, const u8 *expect, u32 n, void *stub)
{
    u8 *p = (u8 *)RVA(va);
    if (!same(p, expect, n))
        return 0;
    u8 b[16];
    b[0] = 0xE9;
    u32 rel = (u32)stub - (u32)(p + 5);
    memcpy(b + 1, &rel, 4);
    for (u32 i = 5; i < n; i++)
        b[i] = 0x90;
    write_code(p, b, n);
    KOR_HOOKS |= 1u << bit;
    return 1;
}

/* E8/E9 rel32 at va that must point at target_va -> fn (same opcode) */
int redirect_call(u32 bit, u32 va, u32 target_va, void *fn)
{
    u8 *c = (u8 *)RVA(va);
    u32 rel;
    if (c[0] != 0xE8 && c[0] != 0xE9)
        return 0;
    memcpy(&rel, c + 1, 4);
    if ((u32)(c + 5) + rel != RVA(target_va))
        return 0;
    u8 b[5] = {c[0]};
    u32 nrel = (u32)fn - (u32)(c + 5);
    memcpy(b + 1, &nrel, 4);
    write_code(c, b, 5);
    KOR_HOOKS |= 1u << bit;
    return 1;
}

/* call fn(frame) at the entry of the function at va, then run its first n bytes (no relative branches, checked
 * against expect) and continue. frame = pushad block: [0] edi [1] esi [2] ebp [3] esp [4] ebx [5] edx [6] ecx
 * [7] eax [8] return address [9..] stack arguments. */
int prehook(u32 bit, u32 va, const u8 *expect, u32 n, void(__cdecl *fn)(u32 *))
{
    static u8 *pool;
    static u32 used;
    u8 *p = (u8 *)RVA(va);
    if (n < 5 || n > 12 || !same(p, expect, n))
        return 0;
    if (!pool)
        pool = VirtualAlloc(0, 4096, 0x3000, 0x40);
    if (!pool || used + 48 > 4096)
        return 0;
    u8 *q = pool + used, *s = q;
    *q++ = 0x60;                        /* pushad */
    *q++ = 0x54;                        /* push esp */
    *q++ = 0xB8;                        /* mov eax, fn */
    memcpy(q, &fn, 4), q += 4;
    *q++ = 0xFF, *q++ = 0xD0;           /* call eax */
    *q++ = 0x83, *q++ = 0xC4, *q++ = 4; /* add esp, 4 */
    *q++ = 0x61;                        /* popad */
    for (u32 i = 0; i < n; i++)
        *q++ = p[i];
    *q++ = 0xE9;
    u32 back = (u32)(p + n) - (u32)(q + 4);
    memcpy(q, &back, 4), q += 4;
    used += (u32)(q - s + 15) & ~15u;
    u8 j[12];
    j[0] = 0xE9;
    u32 rel = (u32)s - (u32)(p + 5);
    memcpy(j + 1, &rel, 4);
    for (u32 i = 5; i < n; i++)
        j[i] = 0x90;
    write_code(p, j, n);
    KOR_HOOKS |= 1u << bit;
    return 1;
}

extern void stub_reward(void);
extern void stub_hp1(void), stub_hp2(void), stub_hp3(void), stub_hp4(void), stub_hp5(void), stub_hp6(void);
extern void stub_mp(void), stub_encfn(void), stub_encin(void);
extern void stub_gal1(void), stub_gal2(void), stub_gal3(void), stub_scene(void);
void opt_update(void);
void subs_draw(void);
void capture_install(void);
void census_install(void);
void testinput_install(void);
void options_install(void);
void subs_install(void);
void decensor_install(void);

/* ---------------------------------------------------------------- speed (이동 속도 / 전투 속도)
 * frame function 0x4f5ab0: pad poll 0x50dd60 (pads 0x5f5ef8, 2 x 0x28: +0 held, +4 pressed, +8 repeat), then the
 * task update 0x4c7bb0 called from 0x4f5bc2. Extra task passes see no new presses or repeats. gd = [0x5c954c],
 * gd+0x20098 bit 22 = in battle. */
static void (*task_update)(void);
static u32 speed_acc;

void opt_update(void)
{
    KOR_TICK++;
    task_update();
    volatile u32 *pad = (volatile u32 *)RVA(0x5f5ef8);
    u8 *gd = *(u8 **)RVA(0x5c954c);
    u32 in_battle = gd && (*(volatile u32 *)(gd + 0x20098) & 0x400000u);
    static const u8 MOVE_H[4] = {2, 3, 4, 6}, BATTLE_H[4] = {2, 4, 6, 8};
    u32 h = 2;
    if (in_battle)
        h = BATTLE_H[OPT_V[6] & 3u];
    else if (OPT_V[5] && ((pad[0] | pad[10]) & 0xF00000F0u))
        h = MOVE_H[OPT_V[5] & 3u];
    if (h <= 2u) {
        speed_acc = 0;
    } else {
        speed_acc += h - 2u;
        while (speed_acc >= 2u) {
            speed_acc -= 2u;
            pad[1] = pad[2] = 0;
            pad[11] = pad[12] = 0;
            task_update();
        }
    }
}

/* test pad in game button bits (Vita layout: 0x10 up 0x20 right 0x40 down 0x80 left, 0x2000 confirm, 0x4000 cancel) */
volatile u32 KOR_PAD_BUTTONS;
static void (*pad_poll)(void);
static u32 test_prev;
static void test_pad_poll(void)
{
    pad_poll();
    volatile u32 *pad = (volatile u32 *)RVA(0x5f5ef8);
    u32 v = KOR_PAD_BUTTONS, t = v & ~test_prev;
    pad[0] |= v;
    pad[1] |= t;
    pad[2] |= t;
    test_prev = v;
}

static void install(void)
{
    DELTA = (u32)GetModuleHandleA(0) - 0x400000u;
    static const u8 E_REWARD[14] = {0x6a, 0x00, 0x01, 0x87, 0x60, 0x01, 0x00, 0x00, 0x01, 0x8f, 0x5c, 0x01, 0x00, 0x00};
    static const u8 E_HP1[6] = {0x29, 0xb7, 0xdc, 0, 0, 0}, E_HP2[6] = {0x29, 0x86, 0xdc, 0, 0, 0},
                    E_HP3[6] = {0x29, 0x87, 0xdc, 0, 0, 0}, E_MP[6] = {0x29, 0x87, 0xe4, 0, 0, 0};
    static const u8 E_ENCIN[13] = {0x83, 0xb8, 0x68, 0x01, 0, 0, 0, 0x0f, 0x85, 0xa0, 0x03, 0, 0};
    static const u8 E_GAL1[6] = {0x85, 0x4c, 0x86, 0x08, 0x75, 0x08}, E_GAL2[6] = {0x85, 0x54, 0x88, 0x08, 0x74, 0x08},
                    E_GAL3[6] = {0x85, 0x54, 0xb0, 0x08, 0x74, 0x0d}, E_SCENE[5] = {0x83, 0x39, 0x01, 0x75, 0x04};

    RET_REWARD = RVA(0x423ed9);
    hook_jmp(0, 0x423ecb, E_REWARD, 14, stub_reward);
    static const u32 HPVA[6] = {0x41e737, 0x41eec4, 0x41fecb, 0x4211e6, 0x42f69e, 0x42f75c};
    static const u8 *const HPE[6] = {E_HP1, E_HP2, E_HP3, E_HP2, E_HP2, E_HP2};
    void (*const HPS[6])(void) = {stub_hp1, stub_hp2, stub_hp3, stub_hp4, stub_hp5, stub_hp6};
    for (u32 i = 0; i < 6; i++) {
        RET_HP[i] = RVA(HPVA[i] + 6);
        hook_jmp(1 + i, HPVA[i], HPE[i], 6, HPS[i]);
    }
    RET_MP = RVA(0x41f829);
    hook_jmp(7, 0x41f823, E_MP, 6, stub_mp);
    /* encounter: the check function (its first mov eax,[0x667324] is relocated: expect the moved address) */
    ENC_FIELD_PTR = RVA(0x667324);
    u8 e_encfn[5] = {0xa1, 0, 0, 0, 0};
    memcpy(e_encfn + 1, &ENC_FIELD_PTR, 4);
    hook_jmp(8, 0x4d42b0, e_encfn, 5, stub_encfn);
    RET_ENC_CONT = RVA(0x4dc704);
    RET_ENC_SKIP = RVA(0x4dcaa4);
    hook_jmp(9, 0x4dc6f7, E_ENCIN, 13, stub_encin);
    /* galleries */
    GAL1_HIT = RVA(0x4e62ca), GAL1_MISS = RVA(0x4e62c2);
    hook_jmp(10, 0x4e62bc, E_GAL1, 6, stub_gal1);
    GAL2_HIT = RVA(0x4e7147), GAL2_MISS = RVA(0x4e714f);
    hook_jmp(11, 0x4e7141, E_GAL2, 6, stub_gal2);
    GAL3_HIT = RVA(0x4e7389), GAL3_MISS = RVA(0x4e7396);
    hook_jmp(12, 0x4e7383, E_GAL3, 6, stub_gal3);
    SCENE_HIT = RVA(0x4e64aa), SCENE_MISS = RVA(0x4e64ae);
    hook_jmp(13, 0x4e64a5, E_SCENE, 5, stub_scene);
    /* test copy only: the window procedure pauses the game on WM_ACTIVATEAPP(FALSE)
     * (0x4f5d63 test eax,eax / setne al -> active flag 0x68753e); keep it "active" so a background test runs */
    if (KOR_TESTPAD) {
        static const u8 E_ACT[5] = {0x85, 0xc0, 0x0f, 0x95, 0xc0}, N_ACT[5] = {0xb0, 0x01, 0x90, 0x90, 0x90};
        u8 *a = (u8 *)RVA(0x4f5d63);
        if (same(a, E_ACT, 5)) {
            write_code(a, N_ACT, 5);
            KOR_HOOKS |= 1u << 15;
        }
    }
    /* test copy only: after the pad poll (0x4f5ace call 0x50dd60) add KOR_PAD_BUTTONS (game button bits) to pad 0 */
    if (KOR_TESTPAD) {
        u8 *c = (u8 *)RVA(0x4f5ace);
        u32 rel;
        memcpy(&rel, c + 1, 4);
        if (c[0] == 0xE8 && (u32)(c + 5) + rel == RVA(0x50dd60)) {
            pad_poll = (void (*)(void))RVA(0x50dd60);
            u8 b[5] = {0xE8};
            u32 nrel = (u32)test_pad_poll - (u32)(c + 5);
            memcpy(b + 1, &nrel, 4);
            write_code(c, b, 5);
            KOR_HOOKS |= 1u << 16;
        }
    }
    /* speed: redirect the call to the task update */
    u8 *call = (u8 *)RVA(0x4f5bc2);
    if (call[0] == 0xE8) {
        u32 rel;
        memcpy(&rel, call + 1, 4);
        u32 target = (u32)(call + 5) + rel;
        if (target == RVA(0x4c7bb0)) {
            task_update = (void (*)(void))target;
            u8 b[5] = {0xE8};
            u32 nrel = (u32)opt_update - (u32)(call + 5);
            memcpy(b + 1, &nrel, 4);
            write_code(call, b, 5);
            KOR_HOOKS |= 1u << 14;
        }
    }
    /* settings: 치트 / 모드 rows on the volume page (options.c) */
    options_install();
    /* battle voice subtitles (subs.c) */
    subs_install();
    /* Mod + Decensor: data\kor_decensor.dat over the archive (decensor.c) */
    decensor_install();
}

/* SaveDataFolder\kor_hook.log: "hooks XXXXXXXX base XXXXXXXX" (which patches went in) */
static void hook_log(void)
{
    char p[300], line[64];
    u32 n = 0;
    for (; opt_path[n]; n++)
        p[n] = opt_path[n];
    while (n && p[n - 1] != '\\')
        n--;
    const char *f = "kor_hook.log";
    for (u32 i = 0; f[i]; i++)
        p[n++] = f[i];
    p[n] = 0;
    static const char HEX[] = "0123456789ABCDEF";
    const char *a = "hooks ", *b = " base ";
    u32 k = 0;
    for (u32 i = 0; a[i]; i++)
        line[k++] = a[i];
    for (int s = 28; s >= 0; s -= 4)
        line[k++] = HEX[(KOR_HOOKS >> s) & 15];
    for (u32 i = 0; b[i]; i++)
        line[k++] = b[i];
    for (int s = 28; s >= 0; s -= 4)
        line[k++] = HEX[((0x400000u + DELTA) >> s) & 15];
    line[k++] = '\r', line[k++] = '\n';
    void *h = CreateFileA(p, 0x40000000u, 1, 0, 2, 0, 0);
    if (h == (void *)-1)
        return;
    u32 put;
    WriteFile(h, line, k, &put, 0);
    CloseHandle(h);
}

/* ---------------------------------------------------------------- XInput forwarding */
static void *real;
static void *rx(const char *name)
{
    if (!real) {
        char p[300];
        static const char *const names[3] = {"\\xinput1_3.dll", "\\xinput1_4.dll", "\\xinput9_1_0.dll"};
        for (u32 k = 0; k < 3 && !real; k++) {
            u32 n = GetSystemDirectoryA(p, 260);
            for (u32 i = 0; names[k][i]; i++)
                p[n++] = names[k][i];
            p[n] = 0;
            real = LoadLibraryA(p);
        }
        if (!real)
            return 0;
    }
    return GetProcAddress(real, name);
}
#define NOT_CONNECTED 1167u
/* test pad (only when SaveDataFolder\kor_testpad exists at start): pad 0 reports KOR_PAD_BUTTONS, written by
 * the test tool with WriteProcessMemory — input without focus or key messages */
volatile u32 KOR_TESTPAD;
u32 WINAPI XInputGetState(u32 i, void *s)
{
    u32(WINAPI * f)(u32, void *) = rx("XInputGetState");
    return f ? f(i, s) : NOT_CONNECTED;
}
u32 WINAPI XInputSetState(u32 i, void *v)
{
    u32(WINAPI * f)(u32, void *) = rx("XInputSetState");
    return f ? f(i, v) : NOT_CONNECTED;
}
u32 WINAPI XInputGetCapabilities(u32 i, u32 fl, void *c)
{
    u32(WINAPI * f)(u32, u32, void *) = rx("XInputGetCapabilities");
    return f ? f(i, fl, c) : NOT_CONNECTED;
}
void WINAPI XInputEnable(BOOL e)
{
    void(WINAPI * f)(BOOL) = rx("XInputEnable");
    if (f)
        f(e);
}
u32 WINAPI XInputGetDSoundAudioDeviceGuids(u32 i, void *a, void *b)
{
    u32(WINAPI * f)(u32, void *, void *) = rx("XInputGetDSoundAudioDeviceGuids");
    return f ? f(i, a, b) : NOT_CONNECTED;
}
u32 WINAPI XInputGetBatteryInformation(u32 i, u8 t, void *b)
{
    u32(WINAPI * f)(u32, u8, void *) = rx("XInputGetBatteryInformation");
    return f ? f(i, t, b) : NOT_CONNECTED;
}
u32 WINAPI XInputGetKeystroke(u32 i, u32 r, void *k)
{
    u32(WINAPI * f)(u32, u32, void *) = rx("XInputGetKeystroke");
    return f ? f(i, r, k) : NOT_CONNECTED;
}

BOOL WINAPI DllMain(void *inst, u32 reason, void *res)
{
    (void)inst, (void)res;
    if (reason == 1 /* DLL_PROCESS_ATTACH */) {
        opt_path_init();
        {
            char t[300];
            u32 n = 0;
            for (; KOR_DIR[n]; n++)
                t[n] = KOR_DIR[n];
            const char *f = "kor_testpad";
            for (u32 i = 0; f[i]; i++)
                t[n++] = f[i];
            t[n] = 0;
            KOR_TESTPAD = GetFileAttributesA(t) != 0xFFFFFFFFu;
        }
        opt_load();
        install();
        capture_install();
        if (KOR_TESTPAD) {
            census_install();
            testinput_install();
        }
        OutputDebugStringA("cg kor hook: installed\n");
        hook_log();
    }
    return 1;
}
