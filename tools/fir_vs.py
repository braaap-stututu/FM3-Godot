"""fir_vs.py: run a Xenos vertex shader over a draw's vertices, numerically and symbolically at once.

Every register component carries two things:
- its value for each vertex (a numpy array, or a plain float when it is the same for all of them), and
- a linear form over "atoms": the position fetch's components ('in', c) and any value the shader computed
  non-linearly (a fresh atom per instruction, register and component, whose per-vertex values are known).

At the end, oPos (export 62) gives the clip position of every vertex (the ground truth for an overlay) and, as linear
forms, the shader's last linear map into clip space. When those forms only use ('in', c) atoms, the map is the draw's
object-to-clip matrix over the captured positions; otherwise it is the matrix over whatever the shader computed first
(a decompressed or animated position), and those atoms' per-vertex values are the object-space positions it maps.

Ported from ReGPU src/gpu/ucode.cpp (decoding) and hlsl.cpp (op semantics, ScalarCode). Not handled: loops and calls,
relative constant addressing (skinning, instancing), texture fetches in the vertex shader: those raise Fail.
"""
import numpy as np

from fir_xenos import BOOL_CONSTANTS, CF_END, CF_EXEC, Fail, bits, decode_alu, parse

CONST = None  # the form key of the constant term


class V:
    __slots__ = ('n', 'f')

    def __init__(self, n, f):
        self.n, self.f = n, f  # n: float or ndarray (None = unknown); f: dict atom -> coefficient (None = no form)


def num(x):
    return V(float(x), {CONST: float(x)})


def is_const(v):
    return v.f is not None and all(k is CONST for k in v.f)


def f_add(a, b, sb=1.0):
    if a.f is None or b.f is None:
        return None
    r = dict(a.f)
    for k, c in b.f.items():
        r[k] = r.get(k, 0.0) + sb * c
    return r


def f_scale(a, k):
    return None if a.f is None else {x: c * k for x, c in a.f.items()}


def cval(v):
    return v.f.get(CONST, 0.0)


class Machine:
    def __init__(self, n_verts):
        self.n = n_verts
        self.atoms = {}  # atom -> per-vertex values
        self.regs = {}

    def fresh(self, key, n):
        """A computed value: constant if it is the same for every vertex, else an atom."""
        if n is None:
            return V(None, None)
        if isinstance(n, float) or np.ndim(n) == 0:
            return num(float(n))
        if n.size and np.all(n == n.flat[0]):
            return num(float(n.flat[0]))
        self.atoms[key] = n
        return V(n, {key: 1.0})

    def reg(self, r):
        return self.regs.setdefault(r, [num(0.0)] * 4)


def _bin(a, b, fn):
    if a.n is None or b.n is None:
        return None
    with np.errstate(all='ignore'):
        return fn(a.n, b.n)


def run(code_words, consts, bools, fetch, n_verts):
    """fetch(fetch_fields) -> (n_verts, 4) array of the fetched components. Returns (clip rows: list of 4 V, Machine)."""
    words, cfs = parse(code_words)
    m = Machine(n_verts)
    ps = num(0.0)
    pred = None  # per-vertex predicate (bool array or bool)
    out = {}
    pos_fetch_done = False
    prev_full = None

    def read(s):
        if s['const']:
            if s['rel']:
                raise Fail('relative constant addressing')
            base = s['reg'] * 4
            comps = [num(consts.get(base + s['swz'][c], 0.0)) for c in range(4)]
        else:
            r = m.reg(s['reg'])
            comps = [r[s['swz'][c]] for c in range(4)]
        if s['abs']:
            comps = [num(abs(cval(x))) if is_const(x) else V(None if x.n is None else np.abs(x.n), None) for x in comps]
        if s['neg']:
            comps = [V(None if x.n is None else -x.n, f_scale(x, -1.0)) for x in comps]
        return comps

    def finish(key, n, f=None):
        """A result: its linear form when the op is linear (f), else a fresh atom."""
        if f is not None and n is not None:
            if all(k is CONST for k in f):
                return num(f.get(CONST, 0.0))
            return V(n, f)
        return m.fresh(key, n)

    for lo, hi in cfs:
        op = (hi >> 12) & 0xF
        if op in (7, 8, 9, 10, 11):
            raise Fail('loops, calls or jumps')
        if op not in CF_EXEC:
            continue
        clause_pred = None
        if op in (3, 4):
            b = (lo >> 16) & 0xFF
            word = bools.get(BOOL_CONSTANTS + (b >> 5), 0)
            if bool((word >> (b & 31)) & 1) != bool((hi >> 10) & 1):
                continue
        elif op in (5, 6):
            clause_pred = bool((hi >> 10) & 1)
        addr, count, seq = lo & 0xFFF, (lo >> 12) & 7, (lo >> 16) & 0xFFF
        for k in range(count):
            i = addr + k
            if (i + 1) * 3 > len(words):
                break
            w = words[i * 3:i * 3 + 3]
            if (seq >> (2 * k)) & 1:
                opc = bits(w[0], 0, 5)
                if opc != 0:
                    raise Fail('texture fetch in the vertex shader')
                fld = {'const': bits(w[0], 20, 5) * 3 + bits(w[0], 25, 2), 'signed': bool(bits(w[1], 12, 1)),
                       'norm': bits(w[1], 13, 1) == 0, 'format': bits(w[1], 16, 6), 'mini': bool(bits(w[1], 30, 1)),
                       'exp': (bits(w[1], 24, 6) ^ 32) - 32, 'stride': bits(w[2], 0, 8), 'offset': bits(w[2], 8, 23)}
                if fld['mini']:
                    if prev_full is None:
                        raise Fail('mini fetch first')
                    fld['stride'] = prev_full['stride']
                else:
                    prev_full = fld
                data = fetch(fld)
                dest = bits(w[0], 12, 6)
                dswz = bits(w[1], 0, 12)
                old = m.reg(dest)
                new = []
                is_pos = not pos_fetch_done and not fld['mini']
                for c in range(4):
                    sel = (dswz >> (3 * c)) & 7
                    if sel < 4:
                        col = None if data is None else data[:, sel]
                        if is_pos and col is not None:
                            m.atoms[('in', sel)] = col
                            new.append(V(col, {('in', sel): 1.0}))
                        else:
                            new.append(m.fresh(('f', i, c), col))
                    elif sel == 4:
                        new.append(num(0.0))
                    elif sel == 5:
                        new.append(num(1.0))
                    else:
                        new.append(old[c])
                m.regs[dest] = new
                if is_pos:
                    pos_fetch_done = True
                continue
            a = decode_alu(w)
            vop, sop = a['vop'], a['sop']
            A, B, C = (read(a['src'][j]) for j in range(3))
            res = [None] * 4
            for c in range(4):
                x, y, z = A[c], B[c], C[c]
                key = ('v', i, c)
                if vop == 0:
                    res[c] = finish(key, _bin(x, y, np.add), f_add(x, y))
                elif vop == 1:
                    f = f_scale(y, cval(x)) if is_const(x) else f_scale(x, cval(y)) if is_const(y) else None
                    res[c] = finish(key, _bin(x, y, np.multiply), f)
                elif vop in (2, 3):
                    if a['src'][0] == a['src'][1]:
                        res[c] = x
                    else:
                        res[c] = finish(key, _bin(x, y, np.maximum if vop == 2 else np.minimum))
                elif vop in (4, 5, 6, 7):
                    fn = {4: np.equal, 5: np.greater, 6: np.greater_equal, 7: np.not_equal}[vop]
                    res[c] = finish(key, _bin(x, y, lambda p, q: fn(p, q).astype(np.float64) if isinstance(fn(p, q), np.ndarray) else float(fn(p, q))))
                elif vop in (8, 9, 10):
                    fn = {8: lambda p: p - np.floor(p), 9: np.trunc, 10: np.floor}[vop]
                    res[c] = finish(key, None if x.n is None else fn(x.n))
                elif vop == 11:
                    f = None
                    if is_const(x):
                        f = f_add(V(None, f_scale(y, cval(x))), z)
                    elif is_const(y):
                        f = f_add(V(None, f_scale(x, cval(y))), z)
                    n = None if x.n is None or y.n is None or z.n is None else x.n * y.n + z.n
                    res[c] = finish(key, n, f)
                elif vop in (12, 13, 14):
                    if x.n is None or y.n is None or z.n is None:
                        res[c] = V(None, None)
                    else:
                        cond = {12: np.equal, 13: np.greater_equal, 14: np.greater}[vop](x.n, 0.0)
                        if np.all(cond):
                            res[c] = y
                        elif not np.any(cond):
                            res[c] = z
                        else:
                            res[c] = finish(key, np.where(cond, y.n, z.n))
            if vop in (15, 16, 17):
                terms = [(A[c], B[c]) for c in range(4 if vop == 15 else 3 if vop == 16 else 2)]
                f, n = {CONST: 0.0}, 0.0
                for x, y in terms:
                    t = f_scale(y, cval(x)) if is_const(x) else f_scale(x, cval(y)) if is_const(y) else None
                    f = None if f is None or t is None else f_add(V(None, f), V(None, t))
                    n = None if n is None or x.n is None or y.n is None else n + x.n * y.n
                if vop == 17:
                    f = None if f is None else f_add(V(None, f), C[2])
                    n = None if n is None or C[2].n is None else n + C[2].n
                r = finish(('v', i, 0), n, f)
                res = [r] * 4
            elif vop == 18 or vop >= 19:
                if vop == 19:  # max4
                    n = None if any(A[c].n is None for c in range(4)) else np.maximum(np.maximum(A[0].n, A[1].n), np.maximum(A[2].n, A[3].n))
                    res = [finish(('v', i, 0), n)] * 4
                elif vop == 28:  # dst
                    res = [num(1.0), finish(('v', i, 1), _bin(A[1], B[1], np.multiply)), A[2], B[3]]
                elif vop == 29:
                    raise Fail('address register (maxa)')
                else:
                    res = [V(None, None)] * 4  # setp_*_push, kill_*, cube: no position meaning
            # Scalar half: src3's .w (sA) and .x (sB).
            S = read(a['src'][2])
            sA, sB = S[3], S[0]
            key = ('s', i)
            sres = V(None, None)
            if sop == 50:
                sres = ps
            elif sop == 0:
                sres = finish(key, _bin(sA, sB, np.add), f_add(sA, sB))
            elif sop == 1:
                sres = finish(key, _bin(sA, ps, np.add), f_add(sA, ps))
            elif sop in (2, 3, 4):
                y = sB if sop == 2 else ps
                f = f_scale(y, cval(sA)) if is_const(sA) else f_scale(sA, cval(y)) if is_const(y) else None
                sres = finish(key, _bin(sA, y, np.multiply), f)
            elif sop in (5, 6):
                sres = sA if a['src'][2]['swz'][3] == a['src'][2]['swz'][0] else finish(key, _bin(sA, sB, np.maximum if sop == 5 else np.minimum))
            elif sop in (7, 8, 9, 10):
                fn = {7: np.equal, 8: np.greater, 9: np.greater_equal, 10: np.not_equal}[sop]
                sres = finish(key, None if sA.n is None else np.asarray(fn(sA.n, 0.0), dtype=np.float64))
            elif sop in (11, 12, 13):
                fn = {11: lambda p: p - np.floor(p), 12: np.trunc, 13: np.floor}[sop]
                sres = finish(key, None if sA.n is None else fn(np.asarray(sA.n, dtype=np.float64)))
            elif sop in (14, 15, 16, 17, 18, 19, 20, 21, 22, 40, 48, 49):
                if sA.n is not None:
                    with np.errstate(all='ignore'):
                        x = np.asarray(sA.n, dtype=np.float64)
                        n = {14: np.exp2, 15: np.log2, 16: np.log2, 17: lambda p: 1.0 / p, 18: lambda p: 1.0 / p, 19: lambda p: 1.0 / p,
                             20: lambda p: p ** -0.5, 21: lambda p: p ** -0.5, 22: lambda p: p ** -0.5, 40: np.sqrt, 48: np.sin, 49: np.cos}[sop](x)
                        if sop in (18, 21):
                            n = np.where(np.isinf(n), 0.0, n)
                        if sop in (17, 20):
                            n = np.clip(n, -3.4e38, 3.4e38)
                        if sop == 15:
                            n = np.where(np.isneginf(n), -3.4e38, n)
                    sres = finish(key, n)
            elif sop in (23, 24):
                raise Fail('address register (maxas)')
            elif sop in (25, 26):
                y = sB if sop == 25 else ps
                sres = finish(key, _bin(sA, y, np.subtract), f_add(sA, y, -1.0))
            elif sop in (27, 28, 29, 30):
                if sA.n is not None:
                    fn = {27: np.equal, 28: np.not_equal, 29: np.greater, 30: np.greater_equal}[sop]
                    pred = fn(sA.n, 0.0)
                    sres = finish(key, np.where(pred, 0.0, 1.0) if isinstance(pred, np.ndarray) else (0.0 if pred else 1.0))
                else:
                    pred = None
            elif 42 <= sop <= 47:
                raw_swz, raw_reg = a['s3_swz'], a['s3_reg']
                temp = (sop & 1) | (int(a['s3_temp']) << 1) | (raw_swz & 0x3C)
                ca = num(consts.get(raw_reg * 4 + (((raw_swz >> 6) + 3) & 3), 0.0))
                tb = m.reg(temp & 63)[raw_swz & 3]
                if a['src'][2]['neg']:
                    ca = num(-cval(ca))
                    tb = V(None if tb.n is None else -tb.n, f_scale(tb, -1.0))
                if sop <= 43:
                    sres = finish(key, _bin(ca, tb, np.multiply), f_scale(tb, cval(ca)))
                else:
                    sg = 1.0 if sop <= 45 else -1.0
                    sres = finish(key, _bin(ca, tb, lambda p, q: p + sg * q), f_add(ca, tb, sg))
            # Predication: the instruction's own, or the clause's.
            cond = a['pred_cond'] if a['pred'] else clause_pred
            if a['pred'] or clause_pred is not None:
                if pred is None:
                    raise Fail('predicate unknown')
                take = pred == cond
                if np.ndim(take) and not (np.all(take) or not np.any(take)):
                    raise Fail('predicate differs between vertices')
                if not np.all(take):
                    continue  # nothing written
            ps = sres
            vm, sm = a['vmask'], a['smask']
            if a['export']:
                if a['vdest'] == 62:
                    for c in range(4):
                        if (vm >> c) & 1:
                            out[c] = res[c]
                        if (sm >> c) & 1:
                            out[c] = sres
                continue
            if vm:
                r = m.reg(a['vdest'])[:]
                for c in range(4):
                    if (vm >> c) & 1:
                        r[c] = res[c]
                m.regs[a['vdest']] = r
            if sm:
                if a['sdest_rel']:
                    raise Fail('relative register write')
                r = m.reg(a['sdest'])[:]
                for c in range(4):
                    if (sm >> c) & 1:
                        r[c] = sres
                m.regs[a['sdest']] = r
        if op in CF_END:
            break
    rows = [out.get(c) for c in range(4)]
    if any(r is None or r.n is None for r in rows):
        raise Fail('oPos not computed')
    return rows, m


def clip_positions(rows, n):
    return np.stack([np.broadcast_to(np.asarray(r.n, dtype=np.float64), (n,)) for r in rows], axis=1)


def matrix(rows):
    """The last linear map into clip space: (atoms, 4 x (len(atoms) + 1) matrix) or None when a row has no form."""
    if any(r.f is None for r in rows):
        return None
    atoms = sorted({k for r in rows for k in r.f if k is not CONST}, key=repr)
    mat = [[r.f.get(k, 0.0) for k in atoms] + [r.f.get(CONST, 0.0)] for r in rows]
    return atoms, mat
