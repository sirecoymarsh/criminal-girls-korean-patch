/* Test-copy diagnostics: who calls the game's draw primitives (only when SaveDataFolder\kor_census exists).
 * Each target's first instructions (no relative branches) are copied into a trampoline:
 *   pushad / push esp / push id / call census_rec / add esp,8 / popad / <orig bytes> / jmp back
 * census_rec keeps unique (id, return address) pairs with a hit count and the last ecx/edx.
 * Read with tools\census.py; writing KOR_CENSUS_RESET = 1 clears the table at the next hit. */
typedef unsigned int u32;
typedef unsigned char u8;
#define IMP __declspec(dllimport)
#define WINAPI __stdcall
IMP void *WINAPI VirtualAlloc(void *, u32, u32, u32);
IMP u32 WINAPI GetFileAttributesA(const char *);
IMP void *WINAPI GetModuleHandleA(const char *);
IMP int WINAPI VirtualProtect(void *, u32, u32, u32 *);
IMP int WINAPI FlushInstructionCache(void *, const void *, u32);
IMP void *WINAPI GetCurrentProcess(void);
extern char KOR_DIR[300];

#define CN 1024
struct cen { u32 id, ret, count, ecx, edx, esi; };
volatile struct cen KOR_CENSUS[CN];
volatile u32 KOR_CENSUS_N, KOR_CENSUS_RESET, KOR_CENSUS_ON;

static void __cdecl census_rec(u32 id, u32 *f)
{
    if (KOR_CENSUS_RESET) {
        KOR_CENSUS_N = 0;
        KOR_CENSUS_RESET = 0;
    }
    u32 ret = f[8], n = KOR_CENSUS_N;
    /* id 8 (quad): report the texture object (*ecx) in the esi column — never write into f (popad restores it) */
    u32 esi = (id == 8u && f[6] > 0x10000u) ? *(u32 *)f[6] : f[1];
    for (u32 i = 0; i < n; i++)
        if (KOR_CENSUS[i].ret == ret && KOR_CENSUS[i].id == id) {
            KOR_CENSUS[i].count++;
            KOR_CENSUS[i].ecx = f[6], KOR_CENSUS[i].edx = f[5], KOR_CENSUS[i].esi = esi;
            return;
        }
    if (n < CN) {
        KOR_CENSUS[n].id = id, KOR_CENSUS[n].ret = ret, KOR_CENSUS[n].count = 1;
        KOR_CENSUS[n].ecx = f[6], KOR_CENSUS[n].edx = f[5], KOR_CENSUS[n].esi = esi;
        KOR_CENSUS_N = n + 1;
    }
}

struct tgt { u32 va, n; u8 b[8]; };
static const struct tgt T[] = {
    {0x4d57f0, 6, {0x55, 0x8b, 0xec, 0x83, 0xec, 0x08}}, /* 0 element draw (ecx layout, edx element) */
    {0x4b6f20, 5, {0x53, 0x8b, 0xd9, 0x56, 0x57}},       /* 1 text box draw */
    {0x4fb290, 6, {0x55, 0x8b, 0xec, 0x83, 0xe4, 0xf8}}, /* 2 widget draw */
    {0x4ad420, 5, {0x55, 0x8b, 0xec, 0x6a, 0xff}},       /* 3 */
    {0x4ad2d0, 5, {0x55, 0x8b, 0xec, 0x6a, 0xff}},       /* 4 */
    {0x4d5fe0, 5, {0x55, 0x8b, 0xec, 0x6a, 0xff}},       /* 5 */
    {0x4db3f0, 6, {0x55, 0x8b, 0xec, 0x83, 0xec, 0x1c}}, /* 6 */
    {0x4fbac0, 6, {0x55, 0x8b, 0xec, 0x83, 0xe4, 0xf8}}, /* 7 */
    {0x503170, 6, {0x55, 0x8b, 0xec, 0x83, 0xec, 0x10}}, /* 8 quad (ecx = texture slot: esi field = texture object) */
};

void census_install(void)
{
    char t[300];
    u32 n = 0;
    for (; KOR_DIR[n]; n++)
        t[n] = KOR_DIR[n];
    const char *f = "kor_census";
    for (u32 i = 0; f[i]; i++)
        t[n++] = f[i];
    t[n] = 0;
    if (GetFileAttributesA(t) == 0xFFFFFFFFu)
        return;
    u32 delta = (u32)GetModuleHandleA(0) - 0x400000u;
    u8 *mem = VirtualAlloc(0, 4096, 0x3000, 0x40);
    if (!mem)
        return;
    u8 *q = mem;
    for (u32 k = 0; k < sizeof T / sizeof T[0]; k++) {
        u8 *p = (u8 *)(T[k].va + delta);
        u32 ok = 1;
        for (u32 i = 0; i < T[k].n; i++)
            if (p[i] != T[k].b[i])
                ok = 0;
        if (!ok)
            continue;
        u8 *s = q;
        *q++ = 0x60;                       /* pushad */
        *q++ = 0x54;                       /* push esp */
        *q++ = 0x68;                       /* push id */
        *(u32 *)q = k, q += 4;
        *q++ = 0xB8;                       /* mov eax, census_rec */
        *(u32 *)q = (u32)census_rec, q += 4;
        *q++ = 0xFF, *q++ = 0xD0;          /* call eax */
        *q++ = 0x83, *q++ = 0xC4, *q++ = 8; /* add esp, 8 */
        *q++ = 0x61;                       /* popad */
        for (u32 i = 0; i < T[k].n; i++)
            *q++ = p[i];
        *q++ = 0xE9;
        *(u32 *)q = (u32)(p + T[k].n) - (u32)(q + 4), q += 4;
        u8 j[8];
        j[0] = 0xE9;
        *(u32 *)(j + 1) = (u32)s - (u32)(p + 5);
        for (u32 i = 5; i < T[k].n; i++)
            j[i] = 0x90;
        u32 old;
        VirtualProtect(p, T[k].n, 0x40, &old);
        for (u32 i = 0; i < T[k].n; i++)
            p[i] = j[i];
        VirtualProtect(p, T[k].n, old, &old);
        FlushInstructionCache(GetCurrentProcess(), p, T[k].n);
        KOR_CENSUS_ON |= 1u << k;
    }
}
