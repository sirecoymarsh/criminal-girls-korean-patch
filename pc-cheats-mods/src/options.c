/* PC settings screen, volume page: 치트 / 모드 rows "connected" under the three volume rows, and their
 * sub-screens (same design and option slots as the Vita build, P:\AI\cg-battle-subs\src\options.c).
 *
 * The PC port draws this page with its own widget system (settings object S, page [S+8] == 0):
 *   [S+0x2538] widget "OPTION": 41 parts, 480x272 units, vertices baked by the update 0x4fb290 each frame
 *              0..9 lace / EXIT ribbon / help frame / TEST+NEXT buttons, 10..27 six panel strips (3 parts each,
 *              10 top strip with border .. 25 bottom strip with border), 28 right arrow, 29 left arrow,
 *              30/32/34 cursor glow lower strip, 31/33/35 upper strip, 38..40 VOICE/SE/BGM label images
 *   [S+0x253c+4i] widget "OP_VOL" i = 0..2 (volume pips; x 120, y 80 + 42.5 i)
 *   [S+0x2534] help text box, [S+4] cursor 0..2
 * Draw 0x4f05d0, input 0x4ee150 (thiscall S, repeat, trigger, result*), both reached from 0x4ee0e0 / 0x4ee100.
 * A part is skipped by the renderer 0x4fbac0 when byte [p+0xb] != 0; vertices [p+0x44] (24 bytes, x y ...),
 * grid [p+0x54] (w*h cells of 6 vertices) or a 4-vertex strip.
 *
 * Main page: the volume rows move up two strips (42 units), strips 3..5 stay where they were and become the
 * VOICE bar strip, 치트 and 모드. Rows 3 / 4 keep the game cursor on 2; their highlight is the lower glow half
 * (a complete one-strip frame). Sub-screens list the items on the same strips. */
typedef unsigned int u32;
typedef unsigned char u8;

extern volatile u8 OPT_V[16];
extern u32 KOR_DELTA;
extern volatile u32 KOR_TICK;
void opt_save(void);
int redirect_call(u32 bit, u32 va, u32 target_va, void *fn);
int decensor_available(void);

extern const char OS_LBL_CHEAT[], OS_LBL_MOD[], OS_HELP_CHEAT[], OS_HELP_MOD[], OS_ON[], OS_OFF[], OS_BASE[],
    OS_TIMES[], OS_C0[], OS_C1[], OS_C2[], OS_C3[], OS_C4[], OS_C5[], OS_C6[], OS_C7[], OS_CH0[], OS_CH1[],
    OS_CH2[], OS_CH3[], OS_CH4[], OS_CH5[], OS_CH6[], OS_CH7[], OS_M0[], OS_M1[], OS_M2[], OS_MH0[], OS_MH1[],
    OS_MH2[];

#define R(va) ((u32)(va) + KOR_DELTA)
typedef void *(__fastcall *text_create_t)(u32 cap, u32 lines);
typedef void(__fastcall *box_fn)(void *box);
typedef void(__fastcall *text_set_t)(void *box, const char *s);
typedef void(__fastcall *pg_input_t)(u8 *S, void *edx, u32 rep, u32 trg, u32 *res);
typedef void(__fastcall *wfn_t)(u8 *w);
typedef void(__fastcall *w_anim_t)(u8 *w, void *edx, u32 anim, u32 unused);
#define text_create ((text_create_t)R(0x4b6c00))
#define text_clear ((box_fn)R(0x4b7700))
#define text_set ((text_set_t)R(0x4b6fe0))
#define text_draw ((box_fn)R(0x4b6f20))
#define w_update ((wfn_t)R(0x4fb290))
#define w_render ((wfn_t)R(0x4fbac0))
#define w_anim ((w_anim_t)R(0x4fb1c0)) /* 0x3e8 selected row colours, 0x3e7 normal */
#define pg0_input ((pg_input_t)R(0x4ee150))
#define MOUSE_X (*(volatile float *)R(0x5e6c60)) /* mouse object 0x5e6c40 (+0x20 x, +0x24 y: 960x544 px) */
#define MOUSE_Y (*(volatile float *)R(0x5e6c64))
#define MOUSE_MOVED (*(volatile u8 *)R(0x5e6cbc))
#define MOUSE_BTN (*(volatile u32 *)R(0x5e6c78)) /* bit 1: click */

#define B_UP 0x10u
#define B_RIGHT 0x20u
#define B_DOWN 0x40u
#define B_LEFT 0x80u
#define B_NEXT 0x01u
#define B_OK 0x2000u
#define B_CANCEL 0x4000u
#define SHIFT (-42.0f) /* two strips, in 480x272 units */

/* text (units, colours ARGB); live-tunable from the test tools: [0] glyph w [1] glyph h [2] half-width advance
 * [3] line height [4] item name x [5] value column x [6] value column width */
volatile float KOR_TXT[8] = {10.0f, 11.0f, 7.0f, 14.0f, 121.0f, 232.0f, 40.0f, 0.0f};
#define TS KOR_TXT[1]
#define NAME_X KOR_TXT[4]
#define VAL_X KOR_TXT[5]
#define VAL_W KOR_TXT[6]
#define LBL_X 123.0f /* left edge of the BGM / SE / VOICE label images */
#define WHITE 0xFFFFFFFFu
#define YELLOW 0xFF80E6FFu /* colours are ABGR (as on the Vita): FFE680 */
#define GREY 0xFFA8A8A8u
/* ABGR */

/* debug words (read with probe.py) */
volatile u32 KOR_OPTDBG[12] = {0x5054504Fu}; /* 'OPTP' [1] input calls [2] renders [3] ext [4] sub [5] sel [6] geo fails [7] S */

struct item {
    const char *name, *help;
    u8 slot, kind; /* kind 0 toggle, 1 multiplier 1..20, 2 move speed, 3 battle speed */
};
static const struct item CHEATS[8] = {
    {OS_C0, OS_CH0, 0, 0}, {OS_C1, OS_CH1, 1, 0}, {OS_C2, OS_CH2, 2, 1}, {OS_C3, OS_CH3, 3, 1},
    {OS_C4, OS_CH4, 4, 0}, {OS_C5, OS_CH5, 5, 2}, {OS_C6, OS_CH6, 6, 3}, {OS_C7, OS_CH7, 7, 0},
};
static const struct item MODS[3] = {{OS_M0, OS_MH0, 8, 0}, {OS_M1, OS_MH1, 9, 0}, {OS_M2, OS_MH2, 10, 0}};
static const char *const SPEED_MOVE[4] = {0, "1.5", "2", "3"};
static const char *const SPEED_BATTLE[4] = {0, "2", "3", "4"};

static struct {
    u8 *S;
    u32 tick;   /* KOR_TICK of the last input call */
    u32 ext;    /* row 0..4 (3 치트, 4 모드) */
    u32 sub;    /* 0 main page, 1 cheats, 2 mods */
    u32 sel;
    u32 dirty;
    /* geometry from the last render (units) */
    float s4top, s5top, s5bot, top0;
    void *lbl[2], *name[8], *val[8];
    const char *name_txt[8];
    char val_txt[8][16];
    const struct item *val_item[8];
    u8 val_last[8];
} O = {.s4top = 140.5f, .s5top = 161.5f, .s5bot = 188.0f, .top0 = 12.5f};
int _fltused; /* MSVC float marker (no CRT) */

static const struct item *items(u32 sub, u32 *n)
{
    if (sub == 1u) {
        *n = 8;
        return CHEATS;
    }
    *n = decensor_available() ? 3 : 2; /* Mod + Decensor only with data\kor_decensor.dat (decensor.c) */
    return MODS;
}

static u32 value_max(const struct item *it) { return it->kind == 0u ? 1u : it->kind == 1u ? 19u : 3u; }

static char *put_str(char *p, const char *s)
{
    while (*s)
        *p++ = *s++;
    return p;
}

static const char *value_text(const struct item *it, u32 k)
{
    u32 v = OPT_V[it->slot];
    if (it->kind == 0u)
        return v ? OS_ON : OS_OFF;
    if (v == 0u)
        return OS_BASE;
    char *p = O.val_txt[k];
    if (it->kind == 1u) {
        u32 m = v + 1u;
        if (m >= 10u)
            *p++ = (char)('0' + m / 10u);
        *p++ = (char)('0' + m % 10u);
    } else {
        p = put_str(p, it->kind == 2u ? SPEED_MOVE[v & 3u] : SPEED_BATTLE[v & 3u]);
    }
    p = put_str(p, OS_TIMES);
    *p = 0;
    return O.val_txt[k];
}

/* ---------------------------------------------------------------- widget parts */
static u32 nparts(u8 *w) { return *(u32 *)(w + 0xc8); }
static u8 *part(u8 *w, u32 i) { return (*(u8 ***)(w + 0xcc))[i]; }
static u32 part_nv(u8 *p)
{
    u32 *g = *(u32 **)(p + 0x54);
    return g ? g[0] * g[1] * 6u : 4u;
}
static float *part_v(u8 *p) { return *(float **)(p + 0x44); }
static float part_top(u8 *p)
{
    float *v = part_v(p), m = 1e9f;
    if (!v)
        return 0.0f;
    for (u32 k = 0, n = part_nv(p); k < n; k++)
        if (v[k * 6 + 1] < m)
            m = v[k * 6 + 1];
    return m;
}
static float part_bot(u8 *p)
{
    float *v = part_v(p), m = -1e9f;
    if (!v)
        return 0.0f;
    for (u32 k = 0, n = part_nv(p); k < n; k++)
        if (v[k * 6 + 1] > m)
            m = v[k * 6 + 1];
    return m;
}
/* The renderer only records a pointer to a part's vertices (0x4fffe0) and draws at the end of the frame, so a
 * moved part gets its own copy from this ring (several frames deep) instead of an in-place edit. */
#define VPOOL 1024u /* 4-vertex quads */
static float vpool[VPOOL][24];
static u32 vpool_next;
static float *part_moved(u8 *p, float dy)
{
    float *v = part_v(p);
    if (!v || dy == 0.0f || part_nv(p) != 4u)
        return 0;
    float *c = vpool[vpool_next++ % VPOOL];
    for (u32 k = 0; k < 24; k++)
        c[k] = v[k];
    for (u32 k = 0; k < 4; k++)
        c[k * 6 + 1] += dy;
    return c;
}

#define BIT(i) (1ull << (i))
#define M_FRAME 0x3FFull                        /* 0..9 */
#define M_S(k) (7ull << (10 + 3 * (k)))          /* strip k: 3 parts */
#define M_RARROW BIT(28)
#define M_LARROW BIT(29)
#define M_GLOW (0x3Full << 30)
#define M_GLOW_LOW (BIT(30) | BIT(32) | BIT(34))
#define M_LABELS (BIT(38) | BIT(39) | BIT(40))

/* render only the parts in mask, moved by dy */
static void pass(u8 *w, unsigned long long mask, float dy)
{
    u32 n = nparts(w);
    u8 keep[64];
    float *vkeep[64];
    for (u32 i = 0; i < n; i++) {
        u8 *p = part(w, i);
        keep[i] = p[0xb];
        vkeep[i] = part_v(p);
        if (mask & BIT(i)) {
            float *c = part_moved(p, dy);
            if (c)
                *(float **)(p + 0x44) = c;
        } else {
            p[0xb] = 1;
        }
    }
    w_render(w);
    for (u32 i = 0; i < n; i++) {
        u8 *p = part(w, i);
        p[0xb] = keep[i];
        *(float **)(p + 0x44) = vkeep[i];
    }
}

/* the part layout this code expects (else the page is drawn as the game does) */
static int geo_ok(u8 *w)
{
    if (nparts(w) != 41u)
        return 0;
    for (u32 i = 10; i < 36; i++)
        if (!part_v(part(w, i)) || *(u32 *)(part(w, i) + 0x54))
            return 0;
    float t0 = part_top(part(w, 10)), t3 = part_top(part(w, 19)), t4 = part_top(part(w, 22)), t5 = part_top(part(w, 25));
    return t0 < t3 && t3 < t4 && t4 < t5 && t5 - t4 > 15.0f && t5 - t4 < 30.0f;
}

static int active(void)
{
    return O.S && *(u32 *)(O.S + 8) == 0u && KOR_TICK - O.tick < 4u;
}

/* sub-screen item k: strip top (units) */
static float item_top(u32 k) { return k == 0u ? O.top0 : O.top0 + 23.0f + 21.0f * (float)(k - 1u); }
static float item_mid(u32 k) { return item_top(k) + (k == 0u ? 2.0f : 0.0f) + 11.0f; }

static void __fastcall my_opt_render(u8 *w)
{
    KOR_OPTDBG[2]++;
    if (!active() || w != *(u8 **)(O.S + 0x2538) || !geo_ok(w)) {
        if (active())
            KOR_OPTDBG[6]++;
        w_render(w);
        return;
    }
    float t4 = part_top(part(w, 22)), t5 = part_top(part(w, 25));
    O.s4top = t4;
    O.s5top = t5;
    O.s5bot = part_bot(part(w, 25));
    O.top0 = part_top(part(w, 10)) + SHIFT;
    float glow = part_top(part(w, 30)), amid = (part_top(part(w, 28)) + part_bot(part(w, 28))) * 0.5f;
    if (O.sub == 0u) {
        /* strips 3..5 are taller than their pitch: each one's lower border is covered by the next strip, so
         * the moved strips go first and the three that stay are drawn over them */
        pass(w, M_FRAME, 0.0f);
        pass(w, M_S(0) | M_S(1) | M_S(2) | M_S(3) | M_S(4), SHIFT);
        pass(w, M_S(3) | M_S(4) | M_S(5), 0.0f);
        unsigned long long m = M_LABELS;
        if (O.ext < 3u)
            m |= M_RARROW | M_LARROW | M_GLOW;
        pass(w, m, SHIFT);
        if (O.ext >= 3u) {
            float top = O.ext == 3u ? t4 : t5;
            pass(w, M_GLOW_LOW, top - 0.5f - glow);
            pass(w, M_RARROW, top + 11.0f - amid);
        }
        return;
    }
    u32 n;
    items(O.sub, &n);
    pass(w, M_FRAME, 0.0f);
    float s0 = part_top(part(w, 10)), s1 = part_top(part(w, 13));
    for (u32 k = 0; k < n; k++) {
        if (k == 0u)
            pass(w, M_S(0), item_top(0) - s0);
        else if (k + 1u == n)
            pass(w, M_S(5), item_top(k) - t5);
        else
            pass(w, M_S(1), item_top(k) - s1);
    }
    u32 k = O.sel;
    pass(w, M_GLOW_LOW, item_top(k) + (k == 0u ? 1.5f : -0.5f) - glow);
    pass(w, M_RARROW | M_LARROW, item_mid(k) - amid);
}

/* volume pips: moved with their rows; hidden on the sub-screens */
static void __fastcall my_row_update(u8 *w)
{
    if (active()) {
        if (O.sub)
            return;
        for (u32 i = 0; i < 3; i++)
            if (w == *(u8 **)(O.S + 0x253c + 4 * i)) {
                *(float *)(w + 0x3c) = 80.0f + 42.5f * (float)i + SHIFT;
                if (i == 2u && O.ext >= 3u) { /* game cursor parked on 2: show the VOICE pips unselected */
                    u32 frame = *(u32 *)(w + 0x1c);
                    u8 vis = w[0x2c];
                    w_anim(w, 0, 0x3e7, 0);
                    *(u32 *)(w + 0x1c) = frame;
                    w[0x2c] = vis;
                }
            }
    }
    w_update(w);
}

static void __fastcall my_row_render(u8 *w)
{
    if (active() && O.sub)
        return;
    w_render(w);
}

/* ---------------------------------------------------------------- texts */
static void *box_get(void **slot)
{
    if (!*slot)
        *slot = text_create(0x80, 2);
    return *slot;
}

static void set_text(void *box, const char *s)
{
    text_clear(box);
    float *f = (float *)box;
    f[0x48 / 4] = KOR_TXT[0];
    f[0x4c / 4] = KOR_TXT[1];
    f[0x50 / 4] = KOR_TXT[2];
    f[0x54 / 4] = KOR_TXT[3];
    f[0x68 / 4] = 0.0f; /* as the game's help box: no type-out, the whole line at once */
    f[0x6c / 4] = 0.0f;
    f[0x70 / 4] = 0.0f;
    text_set(box, s);
}

/* x, y = text top-left (units); w > 0: centred in [x, x + w) */
static void put(void *box, float x, float y, float w, u32 colour)
{
    float *f = (float *)box;
    f[0x48 / 4] = KOR_TXT[0];
    f[0x4c / 4] = KOR_TXT[1];
    f[0x50 / 4] = KOR_TXT[2];
    f[0x54 / 4] = KOR_TXT[3];
    f[0x2c / 4] = x;
    f[0x30 / 4] = y;
    if (w > 0.0f) {
        f[0x34 / 4] = w;
        *(volatile u32 *)box |= 0x10u;
    } else {
        f[0x34 / 4] = 480.0f;
        *(volatile u32 *)box &= ~0x10u;
    }
    ((volatile u32 *)box)[0x3c / 4] = colour;
    *(volatile u32 *)box |= 1u; /* re-layout */
    text_draw(box);
}

/* KOR_TXT[7] is a generation number: changing it re-sets every text (sizes apply when a text is set) */
static float txt_gen;
static u32 labels_done;
static void txt_refresh(void)
{
    if (KOR_TXT[7] == txt_gen)
        return;
    txt_gen = KOR_TXT[7];
    labels_done = 0;
    for (u32 k = 0; k < 8; k++)
        O.name_txt[k] = 0, O.val_item[k] = 0;
}

static void main_labels(void)
{
    static const char *const L[2] = {OS_LBL_CHEAT, OS_LBL_MOD};
    u32 done = labels_done;
    for (u32 r = 0; r < 2; r++) {
        void *b = box_get(&O.lbl[r]);
        if (!b)
            return;
        if (!(done & (1u << r))) {
            set_text(b, L[r]);
            done |= 1u << r;
            labels_done = done;
        }
        float y = (r ? O.s5top : O.s4top) + 11.0f - TS * 0.5f;
        put(b, LBL_X, y, 0.0f, WHITE);
        put(b, LBL_X + 0.5f, y, 0.0f, WHITE); /* double strike: closer to the bold row label images */
    }
}

static void sub_texts(void)
{
    u32 n;
    const struct item *it = items(O.sub, &n);
    for (u32 k = 0; k < n; k++) {
        void *nb = box_get(&O.name[k]), *vb = box_get(&O.val[k]);
        if (!nb || !vb)
            return;
        if (O.name_txt[k] != it[k].name) {
            set_text(nb, it[k].name);
            O.name_txt[k] = it[k].name;
        }
        u8 v = OPT_V[it[k].slot];
        if (O.val_item[k] != &it[k] || O.val_last[k] != v) {
            set_text(vb, value_text(&it[k], k));
            O.val_item[k] = &it[k];
            O.val_last[k] = v;
        }
        float y = item_mid(k) - TS * 0.5f;
        put(nb, NAME_X, y, 0.0f, WHITE);
        put(vb, VAL_X, y, VAL_W, v ? YELLOW : GREY);
    }
}

static void __fastcall my_help_draw(void *box)
{
    text_draw(box);
    if (!active())
        return;
    txt_refresh();
    if (O.sub)
        sub_texts();
    else
        main_labels();
}

/* ---------------------------------------------------------------- input */
static const char *help_line(void)
{
    if (O.sub) {
        u32 n;
        const struct item *it = items(O.sub, &n);
        return it[O.sel < n ? O.sel : 0].help;
    }
    return O.ext == 3u ? OS_HELP_CHEAT : O.ext == 4u ? OS_HELP_MOD : 0;
}

static void enter_sub(void)
{
    O.sub = O.ext == 3u ? 1u : 2u;
    O.sel = 0;
}

static void leave_sub(void)
{
    O.ext = O.sub == 1u ? 3u : 4u;
    O.sub = 0;
    if (O.dirty) {
        opt_save();
        O.dirty = 0;
    }
}

static void change(const struct item *t, u32 rep, u32 trg)
{
    u32 v = OPT_V[t->slot], mx = value_max(t);
    if (rep & B_RIGHT)
        v = v < mx ? v + 1u : (t->kind == 0u ? 0u : mx);
    else if (rep & B_LEFT)
        v = v > 0u ? v - 1u : (t->kind == 0u ? mx : 0u);
    else if (trg & B_OK)
        v = v < mx ? v + 1u : 0u;
    else
        return;
    if (v != OPT_V[t->slot]) {
        OPT_V[t->slot] = (u8)v;
        O.dirty = 1;
    }
}

/* the page's input: keys first (as on the Vita), then the mouse */
static void __fastcall my_pg0_input(u8 *S, void *edx, u32 rep, u32 trg, u32 *res)
{
    (void)edx;
    KOR_OPTDBG[1]++;
    int *cur = (int *)(S + 4);
    if (S != O.S || KOR_TICK - O.tick > 3u) { /* page (re)opened */
        O.S = S;
        O.sub = 0;
        O.ext = (u32)*cur;
        O.dirty = 0;
    }
    O.tick = KOR_TICK;
    float mx = MOUSE_X * 0.5f, my = MOUSE_Y * 0.5f, keep_y = MOUSE_Y;
    int in_x = mx >= 94.5f && mx < 306.0f;
    u32 click = (MOUSE_BTN >> 1) & 1u, moved = MOUSE_MOVED;
    u32 grep = rep, gtrg = trg; /* what the game still gets */

    if (O.sub) {
        u32 n;
        const struct item *it = items(O.sub, &n);
        grep = gtrg = 0;
        if (trg & B_CANCEL) {
            leave_sub();
        } else if (rep & B_UP) {
            O.sel = O.sel ? O.sel - 1u : n - 1u;
        } else if (rep & B_DOWN) {
            O.sel = O.sel + 1u < n ? O.sel + 1u : 0u;
        } else {
            change(&it[O.sel], rep, trg);
        }
        if (O.sub && (moved || click)) {
            int hit = -1;
            if (in_x && my >= item_top(0) && my < item_top(n - 1u) + 26.5f)
                for (u32 k = 0; k < n; k++)
                    if (my >= item_top(k) + (k ? 0.0f : 2.0f) && my < item_top(k) + (k ? 21.0f : 23.0f) + (k + 1u == n ? 2.0f : 0.0f))
                        hit = (int)k;
            if (hit >= 0 && moved)
                O.sel = (u32)hit;
            if (click) {
                if (hit >= 0)
                    change(&it[O.sel], 0, B_OK);
                else
                    leave_sub();
            }
        }
        MOUSE_Y = -8000.0f;
    } else {
        if (O.ext < 3u || *cur != 2)
            O.ext = (u32)*cur;
        if (rep & B_UP) {
            if (O.ext == 3u) {
                *cur = 3; /* game: 3 - 1 = 2, its cursor sound and help line */
                O.ext = 2;
            } else if (O.ext == 4u) {
                O.ext = 3;
                grep &= ~B_UP;
            } else if (O.ext == 0u) {
                O.ext = 4;
                *cur = 2;
                grep &= ~B_UP;
            }
        } else if (rep & B_DOWN) {
            if (O.ext == 2u) {
                O.ext = 3;
                grep &= ~B_DOWN;
            } else if (O.ext == 3u) {
                O.ext = 4;
                grep &= ~B_DOWN;
            } else if (O.ext == 4u) {
                O.ext = 0; /* game: 2 + 1 wraps to 0 */
            }
        } else if (O.ext >= 3u && ((rep & B_RIGHT) || (trg & B_OK))) {
            enter_sub();
            grep &= ~(B_RIGHT | B_LEFT);
            gtrg &= ~B_OK;
        } else if (O.ext >= 3u) {
            grep &= ~(B_RIGHT | B_LEFT);
            gtrg &= ~B_OK;
        }
        /* mouse: the volume rows are drawn 84 px higher; the new rows are ours */
        if (in_x && my >= O.top0 && my < O.s4top) {
            MOUSE_Y = keep_y + 84.0f;
        } else if (in_x && my >= O.s4top && my < O.s5bot) {
            u32 r = my < O.s5top ? 3u : 4u;
            if (moved && O.sub == 0u) {
                O.ext = r;
                *cur = 2;
            }
            if (click && O.sub == 0u) {
                O.ext = r;
                *cur = 2;
                enter_sub();
            }
            MOUSE_Y = -8000.0f;
        }
    }
    pg0_input(S, 0, grep, gtrg, res);
    MOUSE_Y = keep_y;
    if (O.sub == 0u && O.ext < 3u)
        O.ext = (u32)*cur; /* the game may have moved it (mouse hover, wrap) */
    const char *h = help_line();
    void *hb = *(void **)(S + 0x2534);
    if (h && hb) {
        text_clear(hb);
        text_set(hb, h);
    }
    KOR_OPTDBG[3] = O.ext;
    KOR_OPTDBG[4] = O.sub;
    KOR_OPTDBG[5] = O.sel;
    KOR_OPTDBG[7] = (u32)S;
}

void options_install(void)
{
    redirect_call(17, 0x4ee096, 0x4ee150, (void *)my_pg0_input);
    redirect_call(18, 0x4f0747, 0x4fbac0, (void *)my_opt_render);
    redirect_call(19, 0x4f0805, 0x4fb290, (void *)my_row_update);
    redirect_call(20, 0x4f080c, 0x4fbac0, (void *)my_row_render);
    redirect_call(21, 0x4f0843, 0x4b6f20, (void *)my_help_draw);
}
