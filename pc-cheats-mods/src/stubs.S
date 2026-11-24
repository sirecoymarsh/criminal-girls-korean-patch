/* x86 cheat stubs (i686 windows, intel syntax). Patched game code jumps here; we jump back through variables
 * the installer filled with ASLR-moved addresses. OPT_V: [0] 무적 [1] MP [2] 경험치-1 [3] 돈-1 [4] 인카운터 끔 [7] CG·회상 */
        .intel_syntax noprefix
        .text

/* reward sum 0x423ecb: eax = enemy EXP, ecx = enemy OP, edi = battle manager; edx (enemy) is live after */
        .globl _stub_reward
_stub_reward:
        push    edx
        movzx   edx, byte ptr [_OPT_V + 2]
        inc     edx
        imul    eax, edx
        movzx   edx, byte ptr [_OPT_V + 3]
        inc     edx
        imul    ecx, edx
        pop     edx
        push    0
        add     dword ptr [edi + 0x160], eax
        add     dword ptr [edi + 0x15c], ecx
        jmp     dword ptr [_RET_REWARD]

/* HP damage: sub dword ptr [UNIT + 0xdc], DMG; party (byte [UNIT+0x18] == 1) skips it while 무적 is on */
.macro HP name, unit, dmg, idx
        .globl _\name
_\name:
        cmp     byte ptr [_OPT_V], 0
        je      1f
        cmp     byte ptr [\unit + 0x18], 1
        je      2f
1:      sub     dword ptr [\unit + 0xdc], \dmg
2:      jmp     dword ptr [_RET_HP + 4 * \idx]
.endm
        HP stub_hp1, edi, esi, 0
        HP stub_hp2, esi, eax, 1
        HP stub_hp3, edi, eax, 2
        HP stub_hp4, esi, eax, 3
        HP stub_hp5, esi, eax, 4
        HP stub_hp6, esi, eax, 5

/* skill MP cost 0x41f823: sub dword ptr [edi + 0xe4], eax */
        .globl _stub_mp
_stub_mp:
        cmp     byte ptr [_OPT_V + 1], 0
        je      1f
        cmp     byte ptr [edi + 0x18], 1
        je      2f
1:      sub     dword ptr [edi + 0xe4], eax
2:      jmp     dword ptr [_RET_MP]

/* encounter check function 0x4d42b0: al = ([[0x667324]+0x168] == 0); 0 while 인카운터 끔 */
        .globl _stub_encfn
_stub_encfn:
        cmp     byte ptr [_OPT_V + 4], 0
        jne     1f
        mov     eax, dword ptr [_ENC_FIELD_PTR]
        mov     eax, dword ptr [eax]
        cmp     dword ptr [eax + 0x168], 0
        sete    al
        ret
1:      xor     eax, eax
        ret

/* inlined check in the field scene 0x4dc6f7: cmp [eax+0x168],0 / jne skip */
        .globl _stub_encin
_stub_encin:
        cmp     byte ptr [_OPT_V + 4], 0
        jne     1f
        cmp     dword ptr [eax + 0x168], 0
        jne     1f
        jmp     dword ptr [_RET_ENC_CONT]
1:      jmp     dword ptr [_RET_ENC_SKIP]

/* galleries: bit tests on the system data (+8 bits = pictures); "open" while CG·회상 개방 is on */
        .globl _stub_gal1
_stub_gal1:                                     /* test [esi+eax*4+8], ecx / jne HIT */
        cmp     byte ptr [_OPT_V + 7], 0
        jne     1f
        test    dword ptr [esi + eax*4 + 8], ecx
        jne     1f
        jmp     dword ptr [_GAL1_MISS]
1:      jmp     dword ptr [_GAL1_HIT]

        .globl _stub_gal2
_stub_gal2:                                     /* test [eax+ecx*4+8], edx / je MISS */
        cmp     byte ptr [_OPT_V + 7], 0
        jne     1f
        test    dword ptr [eax + ecx*4 + 8], edx
        jne     1f
        jmp     dword ptr [_GAL2_MISS]
1:      jmp     dword ptr [_GAL2_HIT]

        .globl _stub_gal3
_stub_gal3:                                     /* test [eax+esi*4+8], edx / je MISS */
        cmp     byte ptr [_OPT_V + 7], 0
        jne     1f
        test    dword ptr [eax + esi*4 + 8], edx
        jne     1f
        jmp     dword ptr [_GAL3_MISS]
1:      jmp     dword ptr [_GAL3_HIT]

/* scene gallery words (1 = open), eax = slot 0..7: every character has 5 scenes (slots 0..4) */
        .globl _stub_scene
_stub_scene:
        cmp     byte ptr [_OPT_V + 7], 0
        je      1f
        cmp     eax, 5
        jb      2f
1:      cmp     dword ptr [ecx], 1
        jne     3f
2:      jmp     dword ptr [_SCENE_HIT]
3:      jmp     dword ptr [_SCENE_MISS]

/* ---- calls into game functions that take float arguments in xmm registers (addresses set at install) ---- */
/* void kor_quad(void **tex_slot, u32 abgr, float x, float y, float z, float w, float h, u32 blend)
 * -> 0x503170: ecx = texture slot, edx = colour, xmm1 = x, xmm2 = y, xmm3 = z,
 *    stack: w, h, u0, v0, u1, v1, 0, blend (caller cleans 0x20) */
        .globl _kor_quad
_kor_quad:
        push    ebp
        mov     ebp, esp
        push    dword ptr [ebp + 0x24]        /* blend */
        push    0
        push    0x3f800000                    /* v1 */
        push    0x3f800000                    /* u1 */
        push    0                             /* v0 */
        push    0                             /* u0 */
        push    dword ptr [ebp + 0x20]        /* h */
        push    dword ptr [ebp + 0x1c]        /* w */
        mov     ecx, dword ptr [ebp + 8]
        mov     edx, dword ptr [ebp + 0xc]
        movss   xmm1, dword ptr [ebp + 0x10]
        movss   xmm2, dword ptr [ebp + 0x14]
        movss   xmm3, dword ptr [ebp + 0x18]
        call    dword ptr [_KOR_FN_QUAD]
        add     esp, 0x20
        pop     ebp
        ret

/* void kor_layout(void *box) -> 0x4b64c0: ecx = box, dl = 0, xmm1 = 0 (what the text draw runs when dirty) */
        .globl _kor_layout
_kor_layout:
        push    ebx
        push    esi
        push    edi
        mov     ecx, dword ptr [esp + 0x10]
        xor     edx, edx
        xorps   xmm1, xmm1
        call    dword ptr [_KOR_FN_LAYOUT]
        pop     edi
        pop     esi
        pop     ebx
        ret

/* void kor_xform(float x, float y, float z, float sx, float sy) -> 0x4d53b0: xmm0..xmm3 = x y z sx, stack sy */
        .globl _kor_xform
_kor_xform:
        push    ebp
        mov     ebp, esp
        movss   xmm0, dword ptr [ebp + 8]
        movss   xmm1, dword ptr [ebp + 0xc]
        movss   xmm2, dword ptr [ebp + 0x10]
        movss   xmm3, dword ptr [ebp + 0x14]
        push    dword ptr [ebp + 0x18]
        call    dword ptr [_KOR_FN_XFORM]
        add     esp, 4
        pop     ebp
        ret
