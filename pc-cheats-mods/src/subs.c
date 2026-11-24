/* PC battle voice subtitles (speech bubbles) — port of the Vita build (P:\AI\cg-battle-subs\src\subs.c).
 *
 * Voice: the common player 0x464aa0(ecx = channel, edx = Ogg data, [esp+4] = size) — hooked at its entry.
 *        Key = (size, FNV-1a of the first 4096 bytes), table pc_subs_table.c (tools\gen_pc_subs.py).
 * Speaker: the battle voice dispatcher 0x431ca0(ecx = character id, [esp+4] = voice id, [esp+8] flag) — the
 *        character's place = its index among the party units of the battle manager [0x5c8234] (+0x28 unit
 *        pointers; unit +0x18 side 1 = party, +0x28 character id). Corners as on the Vita: 0 TL 1 TR 2 BL 3 BR.
 * Draw: after the frame's task update (hook.c opt_update), inside 0x4cd280(1)..(0) (the text boxes' 480x272 2D
 *        projection): quad 0x503170 with a white texture, then the game's text boxes.
 * Look (user's choice on the Vita, 11-22): translucent black box (alpha A8) + white text, size 22 px. */
typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;

extern u32 KOR_DELTA;
extern volatile u32 KOR_TICK;
extern volatile u8 OPT_V[16];
int prehook(u32 bit, u32 va, const u8 *expect, u32 n, void(__cdecl *fn)(u32 *));
int redirect_call(u32 bit, u32 va, u32 target_va, void *fn);
#define R(va) ((u32)(va) + KOR_DELTA)

struct sub { u32 size, hash; const char *text; u16 ms; u8 chr, pad; };
extern const struct sub SUBS[];
extern const u32 SUBS_N;

/* asm thunks (stubs.S) and the addresses they call */
u32 KOR_FN_QUAD, KOR_FN_LAYOUT, KOR_FN_XFORM;
void kor_quad(void **tex_slot, u32 abgr, float x, float y, float z, float w, float h, u32 blend);
void kor_layout(void *box);
void kor_xform(float x, float y, float z, float sx, float sy);

typedef void *(__fastcall *text_create_t)(u32 cap, u32 lines);
typedef void(__fastcall *box_fn)(void *box);
typedef void(__fastcall *text_set_t)(void *box, const char *s);
#define text_create ((text_create_t)R(0x4b6c00))
#define text_clear ((box_fn)R(0x4b7700))
#define text_set ((text_set_t)R(0x4b6fe0))
#define text_draw ((box_fn)R(0x4b6f20))
typedef void(__fastcall *screen2d_t)(u32 on);
#define screen_2d ((screen2d_t)R(0x4cd280))
#define RENDER_READY (*(volatile u8 *)(*(u32 *)R(0x5e533c) + 0x24))

/* tunables (units 480x272; colours ABGR) — live-adjustable with probe.py setf/seti */
volatile float KOR_BUB[16] = {
    11.0f,  /* [0] glyph size */
    4.0f,   /* [1] padding */
    98.0f,  /* [2] left anchor x */
    382.0f, /* [3] right anchor x (bubble ends here) */
    35.0f,  /* [4] top row y */
    175.0f, /* [5] bottom row y */
    13.0f,  /* [6] fallback line size */
    235.0f, /* [7] fallback line y */
    3.0f,   /* [8] line gap */
    -201.0f, /* [9] quad z (glyphs are drawn at z -200, 0x564e5c; just behind them, as on the Vita) */
    0.0f,    /* [10] test: draw an empty text box first */
    0.5f,    /* [11] half-width advance / size (spaces, ASCII, punctuation) — the Vita build's text_setsize gives w/2 */
    0.5f,    /* [12] double strike: second pass this many units to the right (0 = off) — user's pick 11-23 (시안 나) */
    0.0f,    /* [13] generation: changing it re-sets every bubble text (sizes apply when a text is set) */
    0.82f,   /* [14] glyph ink height / size (measured 11-23: 24 px of a 11-unit line at 1280x720) — the text is moved
              *      down by half the unused line height so the box has equal room above and below */
    0.0f};
volatile u32 KOR_BUBC[8] = {0xA8000000u /* fill */, 0xFFFFFFFFu /* text */, 0 /* blend */, 0 /* demo: 1 = sample bubbles */,
                            0 /* [4] order rotation */, 0 /* [5] outer 2D pair */,
                            0 /* [6] 0 quad+text per bubble, 1 all quads then texts, 2 texts only */,
                            1 /* [7] 1: 2D start 0x4d5240 before each text — needed in battle: without it only the
                                   * first text box of a frame shows once a quad came between (11-23 test) */};
/* debug: [0] 'SUBP' [1] voice calls [2] Ogg calls [3] matches [4] dispatcher calls [5] last size [6] last hash
 *        [7] last char [8] last corner [9] draws [10] bubbles shown [11] last voice id */
volatile u32 KOR_SUBDBG[12] = {0x50425553u};

static struct {
    u32 disp_chr, disp_tick, disp_corner;
    u32 last_tick;
} S = {0xFF, 0, 0xFF, 0};

static const char *last_text; /* test freeze (KOR_BUBC[3] == 3): keep the last line up */
static u32 last_corner;
struct bub {
    void *box;
    const char *text, *shown;
    u32 left; /* frames */
    float x, y, w, h;
};
static struct bub B[5]; /* 0..3 corners, 4 fallback (bottom centre) */

static u32 fnv(const u8 *p, u32 n)
{
    u32 h = 2166136261u;
    for (u32 i = 0; i < n; i++) {
        h ^= p[i];
        h *= 16777619u;
    }
    return h;
}

static const struct sub *find_sub(u32 size, u32 hash)
{
    u32 lo = 0, hi = SUBS_N;
    while (lo < hi) {
        u32 mid = (lo + hi) >> 1;
        const struct sub *e = &SUBS[mid];
        if (e->hash < hash || (e->hash == hash && e->size < size))
            lo = mid + 1;
        else
            hi = mid;
    }
    if (lo < SUBS_N && SUBS[lo].hash == hash && SUBS[lo].size == size)
        return &SUBS[lo];
    return 0;
}

/* party slot of a character in the running battle (0..3), 0xFF if none */
static u32 party_slot(u32 chr)
{
    u8 *bm = *(u8 **)R(0x5c8234);
    if (!bm)
        return 0xFF;
    u32 slot = 0;
    for (u32 k = 0; k < 16; k++) {
        u8 *u = *(u8 **)(bm + 0x28 + 4 * k);
        if (!u || u[0x18] != 1)
            continue;
        if (*(u32 *)(u + 0x28) == chr)
            return slot < 4 ? slot : 0xFF;
        slot++;
    }
    return 0xFF;
}

static void __cdecl on_dispatch(u32 *f)
{
    KOR_SUBDBG[4]++;
    S.disp_chr = f[6] & 0xFF;
    S.disp_tick = KOR_TICK;
    S.disp_corner = party_slot(S.disp_chr);
    KOR_SUBDBG[7] = S.disp_chr;
    KOR_SUBDBG[8] = S.disp_corner;
    KOR_SUBDBG[11] = f[9];
}

static void __cdecl on_voice(u32 *f)
{
    KOR_SUBDBG[1]++;
    const u8 *p = (const u8 *)f[5];
    u32 size = f[9];
    if (!p || size < 0x40u || size > 0x2000000u || *(const u32 *)p != 0x5367674Fu) /* 'OggS' */
        return;
    KOR_SUBDBG[2]++;
    u32 h = fnv(p, size < 4096u ? size : 4096u);
    KOR_SUBDBG[5] = size;
    KOR_SUBDBG[6] = h;
    const struct sub *e = find_sub(size, h);
    if (!e)
        return;
    KOR_SUBDBG[3]++;
    u32 frames = ((u32)e->ms + 600u) * 60u / 1000u;
    u32 c = 4;
    if (e->chr == S.disp_chr && KOR_TICK - S.disp_tick <= 4u && S.disp_corner < 4u)
        c = S.disp_corner;
    B[c].text = e->text;
    B[c].left = frames;
    last_text = e->text;
    last_corner = c;
    KOR_SUBDBG[10]++;
}

static u32 count_lines(const char *s)
{
    u32 n = 1;
    for (; *s; s++)
        if (*s == '\n')
            n++;
    return n;
}

/* A 4x4 white D3D texture inside a copy of a live game texture object (renderer 0x4f7ba0 binds [tex+0x70];
 * +8 is the reference count — kept high so the game never frees it). Template: the key-icon texture [0x5e6bac]. */
extern void *KOR_DEVICE;
void *memcpy(void *, const void *, u32);
#define VCALL(obj, idx, type) ((type)((*(void ***)(obj))[idx]))
typedef long(__stdcall *create_tex_t)(void *, u32, u32, u32, u32, u32, u32, void **, void *);
typedef long(__stdcall *lock_t)(void *, u32, void *, void *, u32);
typedef long(__stdcall *unlock_t)(void *, u32);
static u8 white_obj[0x200];
static void *white_tex; /* what kor_quad's slot points at */
static u32 white_state;  /* 0 not yet, 1 ready, 2 failed */
static void *white(void)
{
    if (white_state)
        return white_state == 1u ? white_tex : 0;
    u8 *tpl = *(u8 **)R(0x5e6bac);
    if (!tpl || !KOR_DEVICE)
        return 0;
    void *tex = 0;
    if (VCALL(KOR_DEVICE, 23, create_tex_t)(KOR_DEVICE, 4, 4, 1, 0, 21 /* A8R8G8B8 */, 1 /* MANAGED */, &tex, 0) < 0 || !tex) {
        white_state = 2;
        return 0;
    }
    struct { int pitch; u8 *bits; } lr;
    if (VCALL(tex, 19, lock_t)(tex, 0, &lr, 0, 0) >= 0) {
        for (u32 y = 0; y < 4; y++)
            for (u32 x = 0; x < 4; x++)
                ((u32 *)(lr.bits + y * (u32)lr.pitch))[x] = 0xFFFFFFFFu;
        VCALL(tex, 20, unlock_t)(tex, 0);
    }
    memcpy(white_obj, tpl, sizeof white_obj);
    *(u32 *)(white_obj + 8) = 0x10000000u;
    *(void **)(white_obj + 0x70) = tex;
    *(void **)(white_obj + 0x78) = 0;
    white_tex = white_obj;
    white_state = 1;
    return white_tex;
}

#define begin_2d ((void (*)(void))R(0x4d5240))
#define record_state ((u32(*)(void))R(0x4cd0e0)) /* returns the state record */
static void bubble_draw(u32 c, u32 phase) /* phase bit 0 quad, bit 1 text */
{
    struct bub *b = &B[c];
    if (!b->text)
        return;
    if (!b->box) {
        b->box = text_create(0x80, 4);
        if (!b->box)
            return;
    }
    float size = c < 4u ? KOR_BUB[0] : KOR_BUB[6];
    float *f = (float *)b->box;
    if (b->shown != b->text) {
        text_clear(b->box);
        f[0x48 / 4] = size;
        f[0x4c / 4] = size;
        f[0x50 / 4] = size * KOR_BUB[11];
        f[0x54 / 4] = size + KOR_BUB[8];
        f[0x68 / 4] = 0.0f; /* whole line at once */
        f[0x6c / 4] = 0.0f;
        f[0x70 / 4] = 0.0f;
        text_set(b->box, b->text);
        f[0x2c / 4] = 0.0f;
        f[0x30 / 4] = 0.0f;
        f[0x34 / 4] = 480.0f;
        *(volatile u32 *)b->box &= ~0x10u;
        kor_layout(b->box); /* measure: widest line at +0x58 */
        *(volatile u32 *)b->box &= ~1u;
        float w = f[0x58 / 4];
        if (w < 4.0f || w > 470.0f)
            w = 150.0f;
        float h = (float)count_lines(b->text) * (size + KOR_BUB[8]);
        float x;
        if (c == 4u)
            x = (480.0f - w) * 0.5f;
        else
            x = (c & 1u) ? KOR_BUB[3] - w : KOR_BUB[2];
        if (x < 3.0f)
            x = 3.0f;
        if (x + w > 477.0f)
            x = 477.0f - w;
        b->x = x;
        b->y = c == 4u ? KOR_BUB[7] : (c < 2u ? KOR_BUB[4] : KOR_BUB[5]);
        b->w = w;
        b->h = h;
        b->shown = b->text;
    }
    float pad = KOR_BUB[1];
    /* only the quad goes inside its own 2D pair: a text box draw makes its own pair, and text boxes inside one
     * shared outer pair lose all but the first box's glyphs in battle (11-23) */
    if ((phase & 1u) && KOR_BUBC[7])
        begin_2d(); /* the game starts every UI element with this; a quad recorded without it vanished in battle */
    if ((phase & 1u) && !KOR_BUBC[5])
        screen_2d(1);
    if (phase & 1u) {
        /* what a text box draw sets before its glyph quads (0x4b6f20 / 0x4b6ab8): draw mode 1 (alpha blend; 2D start
         * leaves 0, under which the black box vanished), then record the state into the list as the game's own
         * quads do (0x461d3a) */
        *(volatile u32 *)R(0x6874fc) |= 0x10u;
        *(volatile u32 *)R(0x5e5328) = 0;
        *(volatile u32 *)R(0x5c97fc) = 1;
        /* the recorded state's address goes with the quad (last argument), as the glyph draw does
         * (0x4b6b2a -> 0x457cb0 -> 0x503170 -> command +0x2c); with 0 the quad took whatever state the
         * previous command left — in battle often one under which the black box vanished */
        u32 st = record_state();
        if (white())
            kor_quad(&white_tex, KOR_BUBC[0], b->x - pad, b->y - pad, KOR_BUB[9], b->w + 2.0f * pad,
                     b->h + 2.0f * pad, KOR_BUBC[2] ? KOR_BUBC[2] : st);
    }
    if ((phase & 1u) && !KOR_BUBC[5])
        screen_2d(0);
    if (!(phase & 2u))
        return;
    if (KOR_BUBC[7])
        begin_2d();
    if (KOR_BUBC[5])
        *(volatile u32 *)b->box &= ~4u;
    else
        *(volatile u32 *)b->box |= 4u;
    float size_now = c < 4u ? KOR_BUB[0] : KOR_BUB[6];
    float ty = b->y + ((size_now + KOR_BUB[8]) - size_now * KOR_BUB[14]) * 0.5f; /* centre the ink in the box */
    f[0x2c / 4] = b->x;
    f[0x30 / 4] = ty;
    f[0x34 / 4] = b->w;
    *(volatile u32 *)b->box |= 0x10u | 1u; /* centred, re-layout */
    ((volatile u32 *)b->box)[0x3c / 4] = KOR_BUBC[1];
    text_draw(b->box);
    if (KOR_BUB[12] != 0.0f) { /* bolder: the same line again a fraction to the right */
        if (KOR_BUBC[7])
            begin_2d();
        f[0x2c / 4] = b->x + KOR_BUB[12];
        *(volatile u32 *)b->box |= 1u;
        text_draw(b->box);
    }
}

extern const char OS_M0[], OS_MH0[]; /* demo texts */

/* once per task-update pass (the speed cheat runs several per frame: timers use KOR_TICK, so they advance once) */
void subs_draw(void)
{
    u32 dt = KOR_TICK - S.last_tick;
    S.last_tick = KOR_TICK;
    if (dt > 30u)
        dt = 30u;
    static float gen;
    if (KOR_BUB[13] != gen) {
        gen = KOR_BUB[13];
        for (u32 c = 0; c < 5; c++)
            B[c].shown = 0;
    }
    if (KOR_BUBC[3] == 3u && last_text) { /* test: freeze the last real line */
        B[last_corner].text = last_text;
        B[last_corner].left = 60;
    } else if (KOR_BUBC[3]) { /* test: sample bubbles in all corners */
        static const char *const D[2] = {OS_M0, OS_MH0};
        for (u32 c = 0; c < 5; c++) {
            if (KOR_BUBC[3] == 2u && c) /* 2: only the top-left one */
                break;
            B[c].text = D[c & 1u];
            B[c].left = 60;
        }
    }
    u32 any = 0;
    for (u32 c = 0; c < 5; c++) {
        if (!B[c].text)
            continue;
        if (B[c].left > dt) {
            B[c].left -= dt;
            any = 1;
        } else {
            B[c].text = 0;
        }
    }
    if (!OPT_V[8]) { /* 모드 > 전투 음성 말풍선 끔 */
        for (u32 c = 0; c < 5; c++)
            B[c].text = 0;
        return;
    }
    if (!any || !*(u32 *)R(0x5e533c) || !RENDER_READY)
        return;
    KOR_SUBDBG[9]++;
    /* Draws recorded during the task update (layer 4) take the current global matrices; in the field and in battle
     * those are the 3D camera. The game's text boxes wrap their glyphs in 0x4cd280(1) .. 0x4cd280(0), which sets a
     * 480x272 2D projection (nested-counted) and restores it — the quads go inside the same pair. */
    u32 outer = KOR_BUBC[5]; /* 1: text boxes without their own 2D switch (flag 4 off), one pair around all */
    if (outer)
        screen_2d(1);
    if (KOR_BUB[10] != 0.0f) { /* test: draw an (empty-looking) text box first; quads after a text box showed */
        static void *primer;
        if (!primer) {
            primer = text_create(0x80, 1);
            if (primer) {
                float *pf = (float *)primer;
                pf[0x68 / 4] = pf[0x6c / 4] = pf[0x70 / 4] = 0.0f;
                text_set(primer, " ");
            }
        }
        if (primer) {
            begin_2d();
            text_draw(primer);
        }
    }
    u32 mode = KOR_BUBC[6];
    for (u32 i = 0; i < 5; i++)
        bubble_draw((i + KOR_BUBC[4]) % 5u, mode == 0u ? 3u : mode == 1u ? 1u : 0u);
    if (mode)
        for (u32 i = 0; i < 5; i++)
            bubble_draw((i + KOR_BUBC[4]) % 5u, 2u);
    if (outer)
        screen_2d(0);
}

/* inside the task update 0x4c7bb0: after the tasks ran (0x4c7c8b call 0x4c74e0) and before the layers are
 * flushed (0x4cd640 x4, which also emits the text glyph batches) */
typedef void (*vfn_t)(void);
static void my_run_tasks(void)
{
    ((vfn_t)R(0x4c74e0))();
    subs_draw();
}

void subs_install(void)
{
    if (redirect_call(26, 0x4c7c8b, 0x4c74e0, (void *)my_run_tasks))
        KOR_SUBDBG[0] = 0x50425553u;
    KOR_FN_QUAD = R(0x503170);
    KOR_FN_LAYOUT = R(0x4b64c0);
    KOR_FN_XFORM = R(0x4d53b0);
    static const u8 E_VOICE[6] = {0x55, 0x8b, 0xec, 0x83, 0xe4, 0xf8};
    static const u8 E_DISP[6] = {0x55, 0x8b, 0xec, 0x83, 0xec, 0x0c};
    prehook(24, 0x464aa0, E_VOICE, 6, on_voice);
    prehook(25, 0x431ca0, E_DISP, 6, on_dispatch);
}
