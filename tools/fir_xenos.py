"""fir_xenos.py: Xenos vertex shader microcode, enough to find a draw's object-to-clip transform.

Ported from ReGPU src/gpu/ucode.cpp (Parse, DecodeAlu, DecodeSource, DecodeFetch) for the parts needed here. The
evaluator walks the exec clauses in order and tracks every register component as a linear form over the position
fetch's input (x, y, z, 1) with numeric coefficients taken from the draw's constants. oPos (export 62) then gives a
4x5 matrix: clip = M * (x, y, z, w, 1). Anything non-linear in the position, relative constant addressing, loops and
calls return None with the reason.
"""
import struct

VECTOR_OPS = ["add", "mul", "max", "min", "seq", "sgt", "sge", "sne", "frc", "trunc", "floor", "mad", "cndeq", "cndge", "cndgt",
              "dp4", "dp3", "dp2add", "cube", "max4", "setp_eq_push", "setp_ne_push", "setp_gt_push", "setp_ge_push", "kill_eq",
              "kill_gt", "kill_ge", "kill_ne", "dst", "maxa", "?30", "?31"]
CF_EXEC = {1, 2, 3, 4, 5, 6, 13, 14}
CF_END = {2, 4, 6, 14}
ALU_CONSTANTS, BOOL_CONSTANTS = 0x4000, 0x4900


def bits(v, lo, n):
    return (v >> lo) & ((1 << n) - 1)


def parse(code_be_words, full=False):
    """ucode::Parse: host-order words and the CF list (stops at the first end unless full: then the whole CF area)."""
    words = list(code_be_words)  # the capture stores the microcode as ReGPU holds it: big-endian dwords
    words = [struct.unpack('>I', struct.pack('<I', w))[0] for w in words]
    cfs, cf_end, triple = [], len(words) // 3, 0
    while triple < cf_end and triple * 3 + 2 < len(words):
        w = words[triple * 3:triple * 3 + 3]
        pair = [(w[0], w[1] & 0xFFFF), ((w[1] >> 16) | ((w[2] << 16) & 0xFFFFFFFF), w[2] >> 16)]
        ended = False
        for lo, hi in pair:
            op = (hi >> 12) & 0xF
            cfs.append((lo, hi))
            if op in CF_EXEC and ((lo >> 12) & 7):
                cf_end = min(cf_end, lo & 0xFFF)
            if op in CF_END:
                ended = True
        if ended and not full:
            break
        triple += 1
    return words, cfs


def decode_source(reg, is_temp, swizzle, negate, abs_constants):
    s = {'const': not is_temp, 'neg': negate}
    if is_temp:
        s['reg'], s['abs'] = reg & 0x3F, bool(reg & 0x80)
    else:
        s['reg'], s['abs'] = reg, abs_constants
    s['swz'] = [((swizzle >> (2 * c)) + c) & 3 for c in range(4)]
    s['rel'] = 0
    return s


def decode_alu(w):
    a = {'vdest': bits(w[0], 0, 6), 'sdest': bits(w[0], 8, 6), 'export': bool(bits(w[0], 15, 1)), 'vmask': bits(w[0], 16, 4),
         'smask': bits(w[0], 20, 4), 'sop': bits(w[0], 26, 6), 'vop': bits(w[2], 24, 5), 'pred': bool(bits(w[1], 28, 1)), 'pred_cond': bool(bits(w[1], 27, 1)),
         'sdest_rel': bool(bits(w[0], 14, 1))}
    abs_c = bool(bits(w[0], 7, 1))
    swz = [bits(w[1], 16, 8), bits(w[1], 8, 8), bits(w[1], 0, 8)]
    neg = [bool(bits(w[1], 26, 1)), bool(bits(w[1], 25, 1)), bool(bits(w[1], 24, 1))]
    reg = [bits(w[2], 16, 8), bits(w[2], 8, 8), bits(w[2], 0, 8)]
    temp = [bool(bits(w[2], 31, 1)), bool(bits(w[2], 30, 1)), bool(bits(w[2], 29, 1))]
    addr_abs = bool(bits(w[1], 29, 1))
    const_rel = [bool(bits(w[1], 31, 1)), bool(bits(w[1], 30, 1))]
    op = a['vop']
    arity = 3 if op in (11, 12, 13, 14, 17) else 1 if op in (8, 9, 10, 19) else 2
    slot, srcs = 0, []
    for i in range(3):
        s = decode_source(reg[i], temp[i], swz[i], neg[i], abs_c)
        if (i < arity or i == 2) and not temp[i] and slot < 2:
            if const_rel[slot]:
                s['rel'] = 1 if addr_abs else 2
            slot += 1
        srcs.append(s)
    a['src'] = srcs
    a['s3_reg'], a['s3_temp'], a['s3_swz'] = reg[2], temp[2], swz[2]
    a['arity'] = arity
    return a


def decode_vfetch(w):
    return {'opcode': bits(w[0], 0, 5), 'src': bits(w[0], 5, 6), 'dest': bits(w[0], 12, 6), 'dswz': bits(w[1], 0, 12),
            'const': bits(w[0], 20, 5) * 3 + bits(w[0], 25, 2), 'mini': bool(bits(w[1], 30, 1))}


# A linear form over the position input: (cx, cy, cz, cw, c1); a plain number has only c1. None = unknown.
def lin_num(v):
    return (0.0, 0.0, 0.0, 0.0, v)


def is_num(f):
    return f is not None and f[0] == 0.0 and f[1] == 0.0 and f[2] == 0.0 and f[3] == 0.0


def l_add(a, b):
    return None if a is None or b is None else tuple(x + y for x, y in zip(a, b))


def l_scale(a, k):
    return None if a is None else tuple(x * k for x in a)


def l_mul(a, b):
    if a is None or b is None:
        return None
    if is_num(a):
        return l_scale(b, a[4])
    if is_num(b):
        return l_scale(a, b[4])
    return None  # position x position: not linear


class Fail(Exception):
    pass


def evaluate(code_words, consts, bools, trace=None):
    """oPos as rows x, y, z, w of clip space, each (cx, cy, cz, cw, c1) over the position input (x, y, z, w, 1)."""
    words, cfs = parse(code_words)
    regs = {}
    pos_fetch_done = False
    out = {}
    ps = None

    def read(s, allow_unknown=True):
        if s['const']:
            if s['rel']:
                raise Fail('relative constant addressing')
            base = s['reg'] * 4
            vals = [consts.get(base + c, 0.0) for c in range(4)]
            comps = [lin_num(vals[s['swz'][c]]) for c in range(4)]
        else:
            r = regs.get(s['reg'], [None] * 4)
            comps = [r[s['swz'][c]] for c in range(4)]
        if s['abs']:
            comps = [lin_num(abs(x[4])) if is_num(x) else None for x in comps]
        if s['neg']:
            comps = [l_scale(x, -1.0) for x in comps]
        return comps

    for lo, hi in cfs:
        op = (hi >> 12) & 0xF
        if op in (7, 8, 9, 10, 11):
            raise Fail('loops, calls or jumps')
        if op not in CF_EXEC:
            continue
        if op in (3, 4, 13, 14):  # cond exec on a bool constant
            b = (hi >> 2) & 0xFF
            word = bools.get(BOOL_CONSTANTS + (b >> 5), 0)
            if bool((word >> (b & 31)) & 1) != bool((hi >> 10) & 1):
                continue
        addr, count, seq = lo & 0xFFF, (lo >> 12) & 7, (lo >> 16) & 0xFFF
        for k in range(count):
            i = addr + k
            if (i + 1) * 3 > len(words):
                break
            w = words[i * 3:i * 3 + 3]
            if (seq >> (2 * k)) & 1:
                f = decode_vfetch(w)
                if trace is not None:
                    trace.append(f"{i:3d} vfetch r{f['dest']} <- r{f['src']} const {f['const']} swz {f['dswz']:03x}{' mini' if f['mini'] else ''} op {f['opcode']}")
                if f['opcode'] != 0:
                    continue
                old = regs.get(f['dest'], [None] * 4)
                new = []
                for c in range(4):
                    sel = (f['dswz'] >> (3 * c)) & 7
                    if not pos_fetch_done and not f['mini']:
                        new.append(tuple(1.0 if j == sel else 0.0 for j in range(4)) + (0.0,) if sel < 4
                                   else lin_num(0.0) if sel == 4 else lin_num(1.0) if sel == 5 else old[c])
                    else:
                        new.append(None if sel < 4 else lin_num(0.0) if sel == 4 else lin_num(1.0) if sel == 5 else old[c])
                regs[f['dest']] = new
                if not f['mini']:
                    pos_fetch_done = True
                continue
            a = decode_alu(w)
            vop = a['vop']
            if trace is not None:
                def kind(f):
                    return '?' if f is None else 'n' if is_num(f) else 'L'
                srcs = []
                for j in range(3):
                    sj = a['src'][j]
                    try:
                        v = read(sj)
                    except Fail:
                        v = [None] * 4
                    srcs.append(('c' if sj['const'] else 'r') + str(sj['reg']) + '.' + ''.join('xyzw'[q] for q in sj['swz']) + ('*' if sj['rel'] else '') + ':' + ''.join(kind(x) for x in v))
                trace.append(f"{i:3d} {VECTOR_OPS[vop]:6s} {'e' if a['export'] else 'r'}{a['vdest']}.{a['vmask']:x}  s{a['sop']} {a['sdest']}.{a['smask']:x}"
                             f"{' pred' if a['pred'] else ''}  " + ' '.join(srcs))
            src = [read(a['src'][j]) for j in range(3)]
            A, B, C = src
            res = [None] * 4
            if vop == 0:
                res = [l_add(A[c], B[c]) for c in range(4)]
            elif vop == 1:
                res = [l_mul(A[c], B[c]) for c in range(4)]
            elif vop in (2, 3):  # max/min: a move when both operands are the same register and swizzle
                s0, s1 = a['src'][0], a['src'][1]
                if s0 == s1:
                    res = A
                else:
                    res = [lin_num(max(A[c][4], B[c][4]) if vop == 2 else min(A[c][4], B[c][4])) if is_num(A[c]) and is_num(B[c]) else None
                           for c in range(4)]
            elif vop == 11:
                res = [l_add(l_mul(A[c], B[c]), C[c]) for c in range(4)]
            elif vop in (15, 16):
                n = 4 if vop == 15 else 3
                acc = lin_num(0.0)
                for c in range(n):
                    acc = l_add(acc, l_mul(A[c], B[c]))
                res = [acc] * 4
            elif vop == 17:
                acc = l_add(l_add(l_mul(A[0], B[0]), l_mul(A[1], B[1])), C[2])
                res = [acc] * 4
            # (other vector ops: unknown results)
            vm = a['vmask']
            # Scalar half: src3's .w (A) and .x (B), the previous scalar result ps.
            sop = a['sop']
            S = read(a['src'][2]) if sop != 50 else [None] * 4
            sA, sB = S[3], S[0]
            sres = None
            if sop == 50:
                sres = ps
            elif sop == 0:
                sres = l_add(sA, sB)
            elif sop == 1:
                sres = l_add(sA, ps)
            elif sop == 2:
                sres = l_mul(sA, sB)
            elif sop in (3, 4):
                sres = l_mul(sA, ps)
            elif sop in (5, 6):
                sres = sA if sA == sB else (lin_num(max(sA[4], sB[4]) if sop == 5 else min(sA[4], sB[4]))
                                            if is_num(sA) and is_num(sB) else None)
            elif sop == 25:
                sres = l_add(sA, l_scale(sB, -1.0))
            elif sop == 26:
                sres = l_add(sA, l_scale(ps, -1.0))
            elif sop in (17, 18, 19) and is_num(sA) and sA[4] != 0.0:
                sres = lin_num(1.0 / sA[4])
            elif sop in (20, 21, 22) and is_num(sA) and sA[4] > 0.0:
                sres = lin_num(sA[4] ** -0.5)
            elif 42 <= sop <= 47:
                raw_swz, raw_reg = a['s3_swz'], a['s3_reg']
                temp = (sop & 1) | (int(a['s3_temp']) << 1) | (raw_swz & 0x3C)
                if a['src'][2]['rel']:
                    raise Fail('relative constant addressing')
                ca = lin_num(consts.get(raw_reg * 4 + (((raw_swz >> 6) + 3) & 3), 0.0))
                tb = regs.get(temp & 63, [None] * 4)[raw_swz & 3]
                if a['src'][2]['neg']:
                    ca, tb = l_scale(ca, -1.0), l_scale(tb, -1.0)
                sres = l_mul(ca, tb) if sop <= 43 else l_add(ca, tb if sop <= 45 else l_scale(tb, -1.0))
            if a['pred']:
                res, sres = [None] * 4, None
            ps = sres
            sm = a['smask']
            if a['export']:
                if a['vdest'] == 62:
                    for c in range(4):
                        if (vm >> c) & 1:
                            out[c] = res[c]
                        if (sm >> c) & 1:
                            out[c] = sres
            else:
                if vm:
                    r = regs.get(a['vdest'], [None] * 4)[:]
                    for c in range(4):
                        if (vm >> c) & 1:
                            r[c] = res[c]
                    regs[a['vdest']] = r
                if sm:
                    if a['sdest_rel']:
                        raise Fail('relative register write')
                    r = regs.get(a['sdest'], [None] * 4)[:]
                    for c in range(4):
                        if (sm >> c) & 1:
                            r[c] = sres
                    regs[a['sdest']] = r
    rows = [out.get(c) for c in range(4)]
    if any(r is None for r in rows):
        raise Fail('oPos not linear in the position (or not written)')
    return rows
