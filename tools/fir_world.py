#!/usr/bin/env python3
"""fir_world.py: split a captured frame's clip transforms into one camera and per-object world matrices, export glTF.

    python fir_world.py capture.fir [--gltf out.gltf [--merge]] [--frame N]

1. Every draw of the scene pass is run through its vertex shader (fir_frame.place); draws whose last linear map into
   clip space takes three atoms (an object-space position) give a 4x4 matrix M (clip from object).
2. The camera's view-projection VP is the most common such matrix among draws whose atoms are the captured position
   itself (the world geometry, already in world space). It is decomposed into a projection (focal lengths, near plane)
   and a view (right, up, forward, position); the decomposition is checked to be a rotation.
3. Every other draw's object-to-world matrix is W = VP^-1 M. Rigid ones (rotation times uniform scale) are objects
   placed in the world; the rest are reported.
4. With --gltf: meshes in object space (the atoms' per-vertex values), deduplicated, one node per draw with its W, and a
   camera node with the recovered view and field of view. glTF is right-handed and Y-up; a left-handed capture world is
   mirrored in X so the picture is not.
"""
import base64
import hashlib
import json
import math
import os
import struct
import sys
from collections import Counter

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fir_read as fr  # noqa: E402
from fir_frame import load_vs_code, place  # noqa: E402
from fir_geometry import load_shader_layouts  # noqa: E402


def scene_range(frame):
    """(first, last) draw seq of the scene pass: the longest stretch without a resolve, ended by its resolve."""
    rs = sorted(e[1]['seq'] for e in frame['events'] if e[0] == 'resolve')
    if not rs:
        return -1, 1 << 30
    gaps = [(b - a, a, b) for a, b in zip([-1] + rs, rs)]
    _, a, b = max(gaps)
    return a, b


def decompose(vp):
    """VP -> projection and view, assuming no skew or off-centre (checked): returns dict or raises ValueError."""
    xr, yr, zr, wr = vp
    f = wr[:3]
    fn = np.linalg.norm(f)
    fwd = f / fn
    fx = np.linalg.norm(xr[:3] - np.dot(xr[:3], fwd) * fwd)
    fy = np.linalg.norm(yr[:3] - np.dot(yr[:3], fwd) * fwd)
    right = xr[:3] / fx
    up = yr[:3] / fy
    R = np.stack([right, up, fwd])
    ortho = float(np.abs(R @ R.T - np.eye(3)).max())
    # camera position: x, y and w rows vanish there
    A = np.stack([xr[:3], yr[:3], wr[:3]])
    pos = np.linalg.solve(A, -np.array([xr[3], yr[3], wr[3]]))
    # depth row: z = a * w_view + b  (z_ndc = a + b / w); near plane where z = 0
    a = float(np.dot(zr[:3], fwd) / fn)
    b = float(zr[3] + np.dot(zr[:3], pos))
    near = -b / a if a else float('nan')
    return {'fx': float(fx / fn), 'fy': float(fy / fn), 'right': right, 'up': up, 'forward': fwd, 'position': pos,
            'ortho_error': ortho, 'near': near, 'depth_a': a, 'yfov_deg': math.degrees(2 * math.atan(fn / fy)),
            'aspect': float(fy / fx), 'w_scale': float(fn)}


def rigid(W):
    R = W[:3, :3]
    det = np.linalg.det(R)
    if abs(det) < 1e-9:
        return None
    s = abs(det) ** (1 / 3)
    err = float(np.abs(R.T @ R / (s * s) - np.eye(3)).max())
    bottom = float(np.abs(W[3] - np.array([0, 0, 0, 1])).max())
    return s, err, bottom, det


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    path = sys.argv[1]
    cap = fr.Capture(path)
    load_shader_layouts(cap, path)
    code = load_vs_code(path)
    frame = cap.frames[0]
    if '--frame' in sys.argv:
        want = int(sys.argv[sys.argv.index('--frame') + 1])
        frame = next(f for f in cap.frames if f['index'] == want)
    with np.errstate(all='ignore'):
        draws, placed, why, kinds = place(cap, path, code, frame, keep_atoms=True)
    lo, hi = scene_range(frame)
    scene = [p for p in placed if lo < p[0]['seq'] < hi]
    print(f"frame {frame['index']}: scene pass draws {lo + 1}..{hi - 1}: {sum(1 for d in draws if lo < d['seq'] < hi)} draws, "
          f"{len(scene)} placed")
    mats = []
    shape = Counter()
    world_only = []  # draws without a 3-atom map: exported in world space from their clip positions
    for p in scene:
        mi = p[4]
        if mi is None:
            shape['no linear map'] += 1
            world_only.append(p)
            continue
        atoms, m = mi
        if len(atoms) != 3:
            shape[f'{len(atoms)} atoms'] += 1
            world_only.append(p)
            continue
        M = np.array([[r[0], r[1], r[2], r[3]] for r in m], dtype=np.float64)
        mats.append((p, atoms, M))
    shape['3 atoms (object position)'] = len(mats)
    for k, v in shape.most_common():
        print(f'  last linear map over {k}: {v}')
    ref = Counter()
    for p, atoms, M in mats:
        if all(a[0] == 'in' for a in atoms) and [a[1] for a in atoms] == [0, 1, 2]:
            ref[tuple(np.round(M, 3).ravel())] += 1
    if not ref:
        print('no world-space draws to take the camera from')
        return 1
    key, nref = ref.most_common(1)[0]
    VP = next(M for p, atoms, M in mats if tuple(np.round(M, 3).ravel()) == key)
    cam = decompose(VP)
    print(f"camera from {nref} world-space draws: yfov {cam['yfov_deg']:.2f} deg, aspect {cam['aspect']:.4f}, near {cam['near']:.3f}, "
          f"rotation error {cam['ortho_error']:.2e}")
    print(f"  position {np.round(cam['position'], 3).tolist()}, forward {np.round(cam['forward'], 4).tolist()}, "
          f"up (clip y) {np.round(cam['up'], 4).tolist()}")
    # World matrices from the x, y and w rows only (w is the linear view depth): W = [VP_x; VP_y; VP_w; e4]^-1 [M_x; M_y; M_w; e4].
    # A shader may write its own depth (z): such a draw still projects right, so its z row is only checked, not used.
    e4 = np.array([0.0, 0.0, 0.0, 1.0])
    VPi = np.linalg.inv(np.stack([VP[0], VP[1], VP[3], e4]))
    objs, verdict, targets = [], Counter(), Counter()
    depth_own = 0
    for p, atoms, M in mats:
        W = VPi @ np.stack([M[0], M[1], M[3], e4])
        if np.abs(VP[2] @ W - M[2]).max() > 1e-3 * max(1.0, np.abs(M[2]).max()):
            depth_own += 1  # a sky dome or other far-plane trick: not part of the world's geometry
            continue
        r = rigid(W)
        if r is None:
            verdict['singular'] += 1
            continue
        s, err, bottom, det = r
        if bottom > 1e-3:
            verdict['projective (not the same camera)'] += 1
            continue
        if err > 0.02:
            verdict['not rigid (shear or non-uniform scale)'] += 1
            if '--rigid-only' not in sys.argv:
                objs.append((p, atoms, W))  # still placeable, just not a rigid transform
            continue
        verdict['rigid' + (' (mirrored object: FM3 car bodies)' if det < 0 else '')] += 1
        targets[(det < 0, hex(p[1].get(0x2001, 0)), hex(p[1].get(0x2205, 0) & 7))] += 1
        objs.append((p, atoms, W))
    for k, v in verdict.most_common():
        print(f'  object-to-world: {k}: {v}')
    objs = drop_reflections(objs)
    # Draws whose last linear map is not over an object position (skinned, morphed, or decompressed through several
    # registers): each vertex's world position from its clip position through the camera (x, y and w rows), W = I.
    A3 = np.stack([VP[0], VP[1], VP[3]])
    A3i = np.linalg.inv(A3[:, :3])
    n_world = n_own = 0
    for p in world_only:
        pv, vindex = p[3], p[6]
        if any(v is None for v in vindex) or any(c is None for c in pv):
            continue
        C = np.array(pv, dtype=np.float64)
        if not np.all(np.isfinite(C)):
            continue
        Pw = (A3i @ (C[:, [0, 1, 3]] - A3[:, 3]).T).T
        z_pred = Pw @ VP[2, :3] + VP[2, 3]
        if np.abs(z_pred - C[:, 2]).max() > 1e-3 * max(1.0, np.abs(C[:, 2]).max()):
            n_own += 1  # own depth (sky): not world geometry
            continue
        WORLD_POS[id(p)] = Pw
        objs.append((p, 'world', np.eye(4)))
        n_world += 1
    print(f'  exported in world space from clip positions: {n_world} draws ({n_own} with their own depth left out)')
    print(f'  draws writing their own depth (z row not the camera one; left out): {depth_own}')
    if '--groups' in sys.argv:  # seq lists per group, for fir_frame.py --seqs
        base = sys.argv[sys.argv.index('--groups') + 1]
        refseqs = [p[0]['seq'] for p, atoms, M in mats if tuple(np.round(M, 3).ravel()) == key]
        mir = [p[0]['seq'] for p, atoms, M in mats if (r := rigid(VPi @ np.stack([M[0], M[1], M[3], e4]))) and r[3] < 0]
        keep = [o[0][0]['seq'] for o in objs]
        for name, l in (('ref', refseqs), ('mirrored', mir), ('kept', keep)):
            with open(f'{base}-{name}.txt', 'w') as f:
                f.write(' '.join(map(str, l)))
    if '--targets' in sys.argv:
        for k, v in sorted(targets.items()):
            print(f'  mirrored={k[0]} RB_COLOR_INFO={k[1]} cull/face bits={k[2]}: {v}')
    if '--seqs' in sys.argv:
        want = set(map(int, open(sys.argv[sys.argv.index('--seqs') + 1]).read().split()))
        objs = [o for o in objs if o[0][0]['seq'] in want]
    if '--gltf' in sys.argv:
        out = sys.argv[sys.argv.index('--gltf') + 1]
        mats = materials(cap, path, objs)
        write_gltf(out, objs, cam, mats, merge='--merge' in sys.argv, sun=sun_direction(objs))
    return 0


def drop_reflections(objs):
    """FM3 draws a planar reflection (the stands mirrored in the track) into the scene target itself: the same meshes
    again through one world mirror R. World-space geometry (atoms = the captured position) drawn there has W = R
    exactly, so R is the most common mirrored W among those draws. Then every draw whose R^-1 W is a W some other draw
    of the same geometry has (or, for world-space geometry, is the identity) is a reflected copy and is left out."""
    votes, mats = Counter(), {}
    for p, atoms, W in objs:
        if all(a[0] == 'in' for a in atoms) and np.linalg.det(W[:3, :3]) < -0.5:
            k = tuple(np.round(W, 2).ravel())
            votes[k] += 1
            mats[k] = W
    if not votes or votes.most_common(1)[0][1] < 3:
        print('  reflection pass: none found')
        return objs
    k, n = votes.most_common(1)[0]
    R = mats[k]
    Ri = np.linalg.inv(R)
    by_gid = {}
    for o in objs:
        by_gid.setdefault(o[0][7], []).append(o)
    drop = set()
    for group in by_gid.values():
        for b in group:
            Wb = Ri @ b[2]
            tol = 1e-2 * max(1.0, np.abs(b[2]).max())
            if any(a is not b and np.abs(a[2] - Wb).max() < tol for a in group) or                     (all(t[0] == 'in' for t in b[1]) and np.abs(Wb - np.eye(4)).max() < tol):
                drop.add(id(b))
    nrm = R[:3, :3] @ np.array([0.0, 1.0, 0.0])
    print(f'  reflection pass: mirror R from {n} world-space draws (maps +y to {np.round(nrm, 3).tolist()}, '
          f'offset {np.round(R[:3, 3], 2).tolist()}); {len(drop)} reflected draws left out')
    return [o for o in objs if id(o) not in drop]


WORLD_POS = {}  # id(placed record) -> world positions, for draws exported in world space
STAND_IN = 0.5  # the value a render-target texel reads as in the per-vertex pixel shader run
RULES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'profiles', 'fm3', 'materials.json')
_RAW = json.load(open(RULES_PATH)) if os.path.exists(RULES_PATH) else {}
RULES = {k: v for k, v in _RAW.items() if not k.startswith('_')}
LIGHTMAP_SLOT = _RAW.get('_lightmap_slot')
SUN_CONSTS = _RAW.get('_sun_const', [])


def alpha_mode(regs, ps_code=None):
    """The draw's coverage from its render state and pixel shader: 'BLEND' (source-alpha blending), 'MASK' (alpha
    test, alpha to coverage, or a kill in the pixel shader), else False. RB_COLORCONTROL 0x2202: bits 0-2 alpha function
    (7 always), bit 3 alpha test, bit 4 alpha to coverage. RB_BLENDCONTROL0 0x2201: colour source factor bits 0-4,
    destination bits 8-12 (Xenos factors: 0 zero, 1 one, 6 source alpha, 7 one minus source alpha)."""
    cc, bc = regs.get(0x2202, 0), regs.get(0x2201, 0x10001)
    src, dst = bc & 0x1F, (bc >> 8) & 0x1F
    if src == 6 or dst == 7:
        return 'BLEND'
    if ((cc >> 3) & 1 and (cc & 7) != 7) or (cc >> 4) & 1:
        return 'MASK'
    if ps_code is not None and shader_kills(ps_code):
        return 'MASK'
    return False


_KILLS = {}


def shader_kills(code):
    """Whether a pixel shader has a kill instruction (vector kill_* 24-27, scalar kills_* 35-39)."""
    key = id(code)
    if key not in _KILLS:
        from fir_xenos import bits, decode_alu, parse
        words, cfs = parse(code, full=True)
        found = False
        for lo, hi in cfs:
            if (hi >> 12) & 15 not in (1, 2, 3, 4, 5, 6, 13, 14):
                continue
            addr, count, seq = lo & 0xFFF, (lo >> 12) & 7, (lo >> 16) & 0xFFF
            for k in range(count):
                if (seq >> (2 * k)) & 1:
                    continue
                a = decode_alu(words[(addr + k) * 3:(addr + k) * 3 + 3])
                if 24 <= a['vop'] <= 27 or 35 <= a['sop'] <= 39:
                    found = True
        _KILLS[key] = found
    return _KILLS[key]


def alpha_share(tex):
    """The share of texels with alpha below one half."""
    a = np.frombuffer(tex['bytes'][:tex['w'] * tex['h'] * 4], np.uint8).reshape(-1, 4)[::31, 3]
    return float((a < 128).mean())


def looks_like_normal_map(tex):
    """Tangent-space normal maps: blue-dominant around (128, 128, 255), or two-channel ones (DXT5nm style: R = B,
    G well above them)."""
    a = np.frombuffer(tex['bytes'][:tex['w'] * tex['h'] * 4], np.uint8).reshape(-1, 4)[::97].astype(np.float64)
    r, g, b, _ = a.mean(0)
    if b > 200 and abs(r - 128) < 30 and abs(g - 128) < 30:
        return True
    return abs(r - b) < 10 and g - r > 25


def materials(cap, path, objs):
    """Per draw: the base texture and its UVs. The pixel shader runs per vertex on the interpolators the vertex
    shader wrote (fir_vs pixel mode) up to its first 2D texture fetch: that fetch's slot is the base texture, its
    coordinates the UVs. Returns {id(placed record): (uv (n, 2), texture data dict, hash key)}."""
    from fir_frame import f32
    import fir_vs
    from fir_xenos import Fail
    ps_code = load_vs_code(path, pixel=True)
    out, why = {}, Counter()
    tex_cache = {}
    for p, atoms, W in objs:
        d, regs, g, per_vert, mi, atom_vals, vindex, gid, exports, nv = p
        code = ps_code.get(d['ps'])
        if code is None:
            why['pixel shader missing'] += 1
            continue
        pin = {}
        for reg, comps in exports.items():
            if reg < 16:
                pin[reg] = np.stack([np.zeros(nv) if v is None or v.n is None else
                                     np.broadcast_to(np.asarray(v.n, dtype=np.float64), (nv,)) for v in comps], axis=1)
        consts = {i: f32(regs[0x4400 + i]) for i in range(1024) if 0x4400 + i in regs}
        bools = {0x4900 + i: regs.get(0x4900 + i, 0) for i in range(8)}
        loops = {i: regs.get(0x4908 + i, 0) for i in range(32)}
        texs = {t[0]: t for t in d['texs']}

        def sample(slot, dim, coords, texs=texs):
            """Nearest-texel sampling of decoded 2D textures (wrap); stand-ins for render targets and the rest."""
            t = texs.get(slot)
            tex = cap.data.get((3, t[8], t[9])) if t else None
            if dim == 1 and tex and coords is not None and tex['w'] and len(tex['bytes']) >= tex['w'] * tex['h'] * 4:
                img = tex_cache.get(id(tex))
                if img is None:
                    img = tex_cache[id(tex)] = np.frombuffer(tex['bytes'][:tex['w'] * tex['h'] * 4], np.uint8).reshape(
                        tex['h'], tex['w'], 4).astype(np.float64) / 255.0
                x = np.floor(np.nan_to_num(coords[:, 0]) * tex['w']).astype(np.int64) % tex['w']
                y = np.floor(np.nan_to_num(coords[:, 1]) * tex['h']).astype(np.int64) % tex['h']
                return img[y, x]
            fmt = (t[3] & 0x3F) if t else -1
            # Render targets have no data here: a shadow map (formats 25, 36) reads far (lit), anything else neutral.
            v = 1.0 if fmt in (25, 36) else STAND_IN
            return np.full((nv, 4), v)

        try:
            with np.errstate(all='ignore'):
                mach = fir_vs.run(code, consts, bools, None, nv, loops, pixel_inputs=pin, sample=sample)
        except Fail as e:
            why['pixel shader: ' + str(e)] += 1
            continue
        res = mach.tfetches
        color = mach.color
        if not res and not RULES.get(f"{d['ps']:016x}"):
            # No texture at all: the colour is the shader's arithmetic. Its output at the vertices (median, clamped) is
            # the best estimate of the surface colour (it includes FM3's lighting, roughly neutral at noon).
            if color is not None and np.isfinite(color[:, :3]).all():
                c = np.clip(np.median(color[:, :3], axis=0), 0.0, 1.0)
                out[id(p)] = {'uv': None, 'image': None, 'key': None, 'factor': c.tolist() + [1.0], 'blend': False,
                              'color': color, 'lightmap': None}
                why['no texture fetch: colour from the shader output'] += 1
            else:
                why['no texture fetch'] += 1
            continue
        fetch_at = {slot: coords for slot, dim, coords in res if dim == 1 and coords is not None}

        def decoded(slot):
            t = texs.get(slot)
            tex = cap.data.get((3, t[8], t[9])) if t else None
            if tex and tex['w'] and len(tex['bytes']) >= tex['w'] * tex['h'] * 4:
                return t, tex
            return None, None

        lightmap = None
        if LIGHTMAP_SLOT is not None and LIGHTMAP_SLOT in fetch_at:
            lt, ltex = decoded(LIGHTMAP_SLOT)
            if ltex is not None:
                lightmap = (fetch_at[LIGHTMAP_SLOT][:, :2].astype(np.float32), ltex, f'{lt[9]:016x}{lt[8]:016x}')
        rule = RULES.get(f"{d['ps']:016x}")
        if rule and rule.get('drop'):
            out[id(p)] = {'drop': True}
            why['rule: ' + rule['name'] + ' (left out)'] += 1
            continue
        if rule:
            # A profile rule (profiles/fm3/materials.json): albedo colour, texture and coverage by role.
            colour = np.array(rule.get('color', [1.0, 1.0, 1.0]), dtype=np.float64)
            if 'color_const' in rule:
                colour = np.array([consts.get(rule['color_const'] * 4 + k, 0.0) for k in range(3)])
            slot = rule.get('texture', rule.get('alpha_texture'))
            t, tex = decoded(slot) if slot is not None else (None, None)
            if slot is not None and (tex is None or slot not in fetch_at):
                why['rule: texture missing'] += 1
                t = tex = None
            mat = {'uv': fetch_at[slot][:, :2].astype(np.float32) if tex else None, 'factor': [1.0, 1.0, 1.0, 1.0],
                   'blend': 'alpha_texture' in rule, 'image': None, 'key': None, 'color': color, 'unlit': rule.get('unlit', False),
                   'roughness': rule.get('roughness', 1.0), 'metallic': rule.get('metallic', 0.0)}
            if tex is None:
                mat['factor'] = colour.tolist() + [float(rule.get('alpha', 1.0))]
                mat['blend'] = mat['blend'] or 'alpha' in rule
            else:
                img = np.frombuffer(tex['bytes'][:tex['w'] * tex['h'] * 4], np.uint8).reshape(tex['h'], tex['w'], 4).astype(np.float64) / 255
                if 'alpha_texture' in rule and 'under' in rule:
                    a_ = img[:, :, rule.get('alpha_channel', 3)][:, :, None]
                    base_c = np.array(rule['under'], dtype=np.float64)
                    img = np.concatenate([base_c * (1 - a_) + colour * a_, np.ones_like(a_)], axis=2)
                    mat['blend'] = False
                elif 'alpha_texture' in rule:
                    a_ = img[:, :, rule.get('alpha_channel', 3)]
                    img = np.concatenate([np.broadcast_to(colour, img.shape[:2] + (3,)), a_[:, :, None]], axis=2)
                elif rule.get('texture_mode') == 'over_alpha':
                    al = img[:, :, 3:4]
                    img = np.concatenate([colour * (1 - al) + img[:, :, :3] * al, np.ones_like(al)], axis=2)
                else:  # multiply
                    img = np.concatenate([img[:, :, :3] * colour, np.ones(img.shape[:2] + (1,))], axis=2)
                mat['image'] = {'w': tex['w'], 'h': tex['h'], 'bytes': (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8).tobytes()}
                mat['key'] = f"{t[9]:016x}{t[8]:016x}_{rule['name'].replace(' ', '_')}_{''.join(f'{int(v * 255):02x}' for v in colour)}"
            mat['lightmap'] = lightmap
            out[id(p)] = mat
            why['rule: ' + rule['name']] += 1
            continue
        # The base texture: the first 2D fetch whose texture came from memory (decoded by the tap) and does not look like
        # a normal map. Render targets the game made earlier in the frame (shadow maps, reflections) are not decoded. For
        # a cut-out or blended draw, a texture whose alpha actually has a pattern wins (fences, foliage, trusses).
        mode = alpha_mode(regs, code)
        cands = []
        for slot, dim, coords in res:
            if dim != 1 or coords is None:
                continue
            t, tex = decoded(slot)
            if tex is not None and not looks_like_normal_map(tex):
                cands.append((slot, coords, t, tex))
        pick = cands[0] if cands else None
        if mode and cands:
            with_alpha = [c for c in cands if 0.05 < alpha_share(c[3]) < 0.995]
            if with_alpha:
                pick = with_alpha[0]
        if pick is None and not res:
            # No texture at all: the colour is the shader's arithmetic. Its output at the vertices (median, clamped) is
            # the best estimate of the surface colour (it includes FM3's lighting, roughly neutral at noon).
            if color is not None and np.isfinite(color[:, :3]).all():
                c = np.clip(np.median(color[:, :3], axis=0), 0.0, 1.0)
                out[id(p)] = {'uv': None, 'image': None, 'key': None, 'factor': c.tolist() + [1.0], 'blend': False,
                              'color': color, 'lightmap': None}
                why['no texture fetch: colour from the shader output'] += 1
                continue
        if pick is None:
            if mode and res:
                out[id(p)] = {'drop': True}  # a blended or cut-out effect whose textures are not available
                why['blended/cut-out with no usable texture (left out)'] += 1
                continue
            why['no decoded 2D texture'] += 1
            continue
        slot, coords, t, tex = pick
        out[id(p)] = {'uv': coords[:, :2].astype(np.float32), 'image': tex, 'key': f'{t[9]:016x}{t[8]:016x}',
                      'factor': [1.0, 1.0, 1.0, 1.0], 'blend': mode, 'color': color,
                      'lightmap': lightmap if lightmap is not None and slot != LIGHTMAP_SLOT else None}
        why['textured'] += 1
    for k, v in why.most_common():
        print(f'  materials: {k}: {v}')
    return out


def smooth_normals(P, tris):
    """Area-weighted vertex normals (float32, unit length; up for unused vertices)."""
    p = P.astype(np.float64)
    fn = np.cross(p[tris[:, 1]] - p[tris[:, 0]], p[tris[:, 2]] - p[tris[:, 0]])
    n = np.zeros_like(p)
    for k in range(3):
        np.add.at(n, tris[:, k], fn)
    ln = np.linalg.norm(n, axis=1)
    n[ln < 1e-12] = (0.0, 1.0, 0.0)
    ln[ln < 1e-12] = 1.0
    return (n / ln[:, None]).astype(np.float32)


def sun_direction(objs):
    """The direction to the sun in the capture's world: the most common unit vector among the profile's sun constants."""
    from fir_frame import f32
    votes, vec = Counter(), {}
    for p, atoms, W in objs:
        regs = p[1]
        for c in SUN_CONSTS:
            v = np.array([f32(regs.get(0x4400 + c * 4 + k, 0)) for k in range(3)])
            if 0.98 < np.linalg.norm(v) < 1.02:
                k = tuple(np.round(v, 3))
                votes[k] += 1
                vec[k] = v
    if not votes:
        return None
    k, n = votes.most_common(1)[0]
    print(f'  sun: direction {list(k)} ({n} votes; elevation {np.degrees(np.arcsin(k[1])):.1f} deg)')
    return vec[k] / np.linalg.norm(vec[k])


def write_gltf(out, objs, cam, mats=None, merge=False, sun=None):
    # FM3's scene target reaches the screen rotated 180 deg: clip x is screen-left and clip y screen-down.
    right, up, fwd = -cam['right'], -cam['up'], cam['forward']
    S = np.eye(4)
    if np.linalg.det(np.stack([right, up, fwd])) > 0:  # x right, y up, z forward: left-handed -> mirror X
        S[0, 0] = -1.0
    s3 = S[:3, :3]
    right, up, fwd, pos = s3 @ right, s3 @ up, s3 @ fwd, s3 @ cam['position']
    bin_parts, views, accessors, meshes, nodes = [], [], [], [], []
    mesh_ids = {}
    offset = 0
    checks = []
    groups = {}  # merge mode: material index -> [(world positions, normals, uvs, triangles)]
    images, textures, materials_, mat_ids, img_ids = [], [], [], {}, {}
    tex_dir = os.path.splitext(out)[0] + '_tex'

    def image_index(tex, key):
        if key not in img_ids:
            os.makedirs(tex_dir, exist_ok=True)
            name = f'{key[:24]}_{len(images)}.png'
            fr.write_png(os.path.join(tex_dir, name), tex['w'], tex['h'], tex['bytes'][:tex['w'] * tex['h'] * 4])
            images.append({'uri': os.path.basename(tex_dir) + '/' + name})
            textures.append({'source': len(images) - 1, 'sampler': 0})
            img_ids[key] = len(textures) - 1
        return img_ids[key]

    def material_index(mat, lm=None):
        key = (mat['key'] or 'none') + str(mat['factor']) + str(mat['blend']) + str(mat.get('unlit')) + (lm[2] if lm else '') + str(mat.get('roughness'))
        if key not in mat_ids:
            pbr = {'baseColorFactor': mat['factor'], 'metallicFactor': mat.get('metallic', 0.0), 'roughnessFactor': mat.get('roughness', 1.0)}
            if mat['image'] is not None:
                pbr['baseColorTexture'] = {'index': image_index(mat['image'], mat['key'])}
            occ = {'occlusionTexture': {'index': image_index(lm[1], 'lm' + lm[2]), 'texCoord': 1}} if lm else {}
            mode = mat['blend'] if isinstance(mat['blend'], str) else ('BLEND' if mat['blend'] else None)
            materials_.append({'pbrMetallicRoughness': pbr, 'doubleSided': True, **occ,
                               **({'alphaMode': mode} if mode else {}), **({'alphaCutoff': 0.5} if mode == 'MASK' else {}),
                               **({'extensions': {'KHR_materials_unlit': {}}} if mat.get('unlit') else {})})
            mat_ids[key] = len(materials_) - 1
        return mat_ids[key]

    def add_view(data, target):
        nonlocal offset
        pad = (-len(data)) % 4
        bin_parts.append(data + b'\0' * pad)
        views.append({'buffer': 0, 'byteOffset': offset, 'byteLength': len(data), 'target': target})
        offset += len(data) + pad
        return len(views) - 1

    for p, atoms, W in objs:
        d, regs, g, per_vert, mi, atom_vals, vindex, gid = p[:8]
        if any(v is None for v in vindex):
            continue
        if atoms == 'world':
            cols = [WORLD_POS[id(p)][:, k] for k in range(3)]
        else:
            cols = [np.broadcast_to(np.asarray(atom_vals[a], dtype=np.float64), (len(vindex),)) for a in atoms]
        # Node matrices keep a positive determinant (Godot's glTF import loses a mirror in a node matrix): world =
        # S W P = (S W F) (F P), with F mirroring X when that makes det(S W F) positive. A mirror in F flips the winding.
        Wg = S @ W
        F = np.eye(4)
        if np.linalg.det(Wg[:3, :3]) < 0:
            F[0, 0] = -1.0
        P = np.stack(cols, axis=1) @ F[:3, :3]
        P = P.astype(np.float32)
        tris = np.array(g['triangles'], dtype=np.uint32)
        if F[0, 0] < 0 and len(tris):
            tris = tris[:, [0, 2, 1]]
        Wg = Wg @ F
        if not np.all(np.isfinite(P)) or not len(tris):
            continue
        mat = (mats or {}).get(id(p))
        if mat is not None and mat.get('drop'):
            continue
        if merge:
            uvm = mat['uv'] if mat is not None and mat['uv'] is not None and mat['image'] is not None and np.all(np.isfinite(mat['uv'])) else None
            lmm = mat.get('lightmap') if mat is not None else None
            if lmm is not None and not np.all(np.isfinite(lmm[0])):
                lmm = None
            mi_ = material_index(mat, lmm) if mat is not None and (uvm is not None or mat['image'] is None) else -1
            Pw = (Wg[:3, :3] @ P.astype(np.float64).T).T + Wg[:3, 3]
            Nw = smooth_normals(P, tris).astype(np.float64) @ np.linalg.inv(Wg[:3, :3])
            Nw /= np.maximum(np.linalg.norm(Nw, axis=1, keepdims=True), 1e-12)
            groups.setdefault(mi_, []).append((Pw.astype(np.float32), Nw.astype(np.float32),
                                               uvm if uvm is not None else np.zeros((len(P), 2), np.float32), tris,
                                               lmm[0] if lmm is not None else np.zeros((len(P), 2), np.float32)))
            checks.append((per_vert, np.eye(4), Pw.astype(np.float32)))
            continue
        uv = mat['uv'] if mat is not None and mat['uv'] is not None and np.all(np.isfinite(mat['uv'])) else None
        mkey = (mat['key'] or '') + str(mat['factor']) + (mat['lightmap'][2] if mat.get('lightmap') else '') if mat is not None else ''
        h = hashlib.blake2b(P.tobytes() + tris.tobytes() + (uv.tobytes() if uv is not None else b'') + mkey.encode(),
                            digest_size=12).hexdigest()
        if h not in mesh_ids:
            pv = add_view(P.tobytes(), 34962)
            accessors.append({'bufferView': pv, 'componentType': 5126, 'count': len(P), 'type': 'VEC3',
                              'min': P.min(axis=0).tolist(), 'max': P.max(axis=0).tolist()})
            prim = {'attributes': {'POSITION': len(accessors) - 1}}
            N = smooth_normals(P, tris)
            accessors.append({'bufferView': add_view(N.tobytes(), 34962), 'componentType': 5126, 'count': len(N), 'type': 'VEC3'})
            prim['attributes']['NORMAL'] = len(accessors) - 1
            if mat is not None and (uv is not None or mat['image'] is None):
                if uv is not None and mat['image'] is not None:
                    accessors.append({'bufferView': add_view(uv.tobytes(), 34962), 'componentType': 5126, 'count': len(uv), 'type': 'VEC2'})
                    prim['attributes']['TEXCOORD_0'] = len(accessors) - 1
                lm = mat.get('lightmap')
                if lm is not None and np.all(np.isfinite(lm[0])):
                    accessors.append({'bufferView': add_view(lm[0].tobytes(), 34962), 'componentType': 5126, 'count': len(lm[0]), 'type': 'VEC2'})
                    prim['attributes']['TEXCOORD_1'] = len(accessors) - 1
                else:
                    lm = None
                prim['material'] = material_index(mat, lm)
            iv = add_view(tris.ravel().tobytes(), 34963)
            accessors.append({'bufferView': iv, 'componentType': 5125, 'count': int(tris.size), 'type': 'SCALAR'})
            prim['indices'] = len(accessors) - 1
            meshes.append({'primitives': [prim]})
            mesh_ids[h] = len(meshes) - 1
        checks.append((per_vert, Wg, P))
        nodes.append({'mesh': mesh_ids[h], 'matrix': Wg.T.ravel().tolist(), 'name': f"draw{d['seq']}"})
    for mi_, parts in groups.items():
        # One mesh per material, vertices in world space (fewer draw calls for a renderer without automatic batching).
        Pm = np.concatenate([q[0] for q in parts])
        Nm = np.concatenate([q[1] for q in parts])
        Um = np.concatenate([q[2] for q in parts])
        base, tl = 0, []
        for q in parts:
            tl.append(q[3].astype(np.uint32) + base)
            base += len(q[0])
        Tm = np.concatenate(tl)
        accessors.append({'bufferView': add_view(Pm.tobytes(), 34962), 'componentType': 5126, 'count': len(Pm), 'type': 'VEC3',
                          'min': Pm.min(axis=0).tolist(), 'max': Pm.max(axis=0).tolist()})
        prim = {'attributes': {'POSITION': len(accessors) - 1}}
        accessors.append({'bufferView': add_view(Nm.tobytes(), 34962), 'componentType': 5126, 'count': len(Nm), 'type': 'VEC3'})
        prim['attributes']['NORMAL'] = len(accessors) - 1
        if mi_ >= 0:
            if 'baseColorTexture' in materials_[mi_]['pbrMetallicRoughness']:
                accessors.append({'bufferView': add_view(Um.tobytes(), 34962), 'componentType': 5126, 'count': len(Um), 'type': 'VEC2'})
                prim['attributes']['TEXCOORD_0'] = len(accessors) - 1
            if 'occlusionTexture' in materials_[mi_]:
                L2 = np.ascontiguousarray(np.concatenate([q[4] for q in parts]))
                accessors.append({'bufferView': add_view(L2.tobytes(), 34962), 'componentType': 5126, 'count': len(L2), 'type': 'VEC2'})
                prim['attributes']['TEXCOORD_1'] = len(accessors) - 1
            prim['material'] = mi_
        accessors.append({'bufferView': add_view(Tm.ravel().tobytes(), 34963), 'componentType': 5125, 'count': int(Tm.size), 'type': 'SCALAR'})
        prim['indices'] = len(accessors) - 1
        meshes.append({'primitives': [prim]})
        nodes.append({'mesh': len(meshes) - 1, 'name': f'merged_material_{mi_}'})
    C = np.eye(4)
    C[:3, 0], C[:3, 1], C[:3, 2], C[:3, 3] = right, up, -fwd, pos
    nodes.append({'camera': 0, 'matrix': C.T.ravel().tolist(), 'name': 'capture_camera'})
    if sun is not None:
        # A glTF directional light shines along its node's -Z: +Z points at the sun.
        z = s3 @ sun
        x = np.cross([0.0, 1.0, 0.0], z)
        x /= np.linalg.norm(x)
        y = np.cross(z, x)
        L = np.eye(4)
        L[:3, 0], L[:3, 1], L[:3, 2] = x, y, z
        nodes.append({'extensions': {'KHR_lights_punctual': {'light': 0}}, 'matrix': L.T.ravel().tolist(), 'name': 'sun'})
    # Self-check: each node's first vertex through the glTF camera against the capture's clip position (scene rotated 180 deg).
    V = np.linalg.inv(C)
    fy = 1 / math.tan(math.radians(cam['yfov_deg']) / 2)
    fx = fy / cam['aspect']
    errs = []
    for per_vert, Wg_, P_ in checks:
        c = per_vert[0]
        if c is None or c[3] <= 1e-6:
            continue
        v = V @ (Wg_ @ np.append(P_[0], 1.0))
        if v[2] >= 0:
            continue
        errs.append(max(abs(fx * v[0] / -v[2] + c[0] / c[3]), abs(fy * v[1] / -v[2] + c[1] / c[3])))
    if errs:
        e = np.array(errs)
        print(f'self-check through the glTF camera: median error {np.median(e):.2e} NDC, {np.mean(e < 1e-3) * 100:.1f}% under 1e-3')
    blob = b''.join(bin_parts)
    gltf = {'asset': {'version': '2.0', 'generator': 'frame-ir fir_world.py'},
            'scene': 0, 'scenes': [{'nodes': list(range(len(nodes)))}], 'nodes': nodes, 'meshes': meshes,
            'cameras': [{'type': 'perspective', 'perspective': {'yfov': math.radians(cam['yfov_deg']), 'aspectRatio': cam['aspect'],
                                                                'znear': max(cam['near'], 0.01)}}],
            'accessors': accessors, 'bufferViews': views,
            **({'materials': materials_} if materials_ else {}),
            'extensionsUsed': (['KHR_materials_unlit'] if any('extensions' in m for m in materials_) else []) +
                              (['KHR_lights_punctual'] if sun is not None else []),
            **({'extensions': {'KHR_lights_punctual': {'lights': [{'type': 'directional', 'color': [1.0, 0.95, 0.86], 'intensity': 3.0, 'name': 'sun'}]}}}
               if sun is not None else {}),
            **({'images': images, 'textures': textures, 'samplers': [{'wrapS': 10497, 'wrapT': 10497}]} if images else {}),
            'buffers': [{'byteLength': len(blob), 'uri': os.path.basename(os.path.splitext(out)[0]) + '.bin'}]}
    with open(os.path.splitext(out)[0] + '.bin', 'wb') as f:
        f.write(blob)
    with open(out, 'w') as f:
        json.dump(gltf, f)
    print(f'glTF written: {out} ({len(meshes)} meshes, {len(nodes) - 1} placed draws, {len(materials_)} materials, {len(blob) / 1e6:.1f} MB)')


if __name__ == '__main__':
    sys.exit(main())
