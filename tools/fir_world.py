#!/usr/bin/env python3
"""fir_world.py: split a captured frame's clip transforms into one camera and per-object world matrices, export glTF.

    python fir_world.py capture.fir [--gltf out.gltf] [--frame N]

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
    for p in scene:
        mi = p[4]
        if mi is None:
            shape['no linear map'] += 1
            continue
        atoms, m = mi
        if len(atoms) != 3:
            shape[f'{len(atoms)} atoms'] += 1
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
        write_gltf(out, objs, cam, mats)
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


def materials(cap, path, objs):
    """Per draw: the base texture and its UVs. The pixel shader runs per vertex on the interpolators the vertex
    shader wrote (fir_vs pixel mode) up to its first 2D texture fetch: that fetch's slot is the base texture, its
    coordinates the UVs. Returns {id(placed record): (uv (n, 2), texture data dict, hash key)}."""
    from fir_frame import f32
    import fir_vs
    from fir_xenos import Fail
    ps_code = load_vs_code(path, pixel=True)
    out, why = {}, Counter()
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
        try:
            with np.errstate(all='ignore'):
                res = fir_vs.run(code, consts, bools, None, nv, loops, pixel_inputs=pin)
        except Fail as e:
            why['pixel shader: ' + str(e)] += 1
            continue
        if not res:
            why['no texture fetch'] += 1
            continue
        # The base texture: the first 2D fetch whose texture came from memory (decoded by the tap). Render targets the
        # game made earlier in the frame (shadow maps, reflections) are not decoded and are skipped.
        pick = None
        for slot, dim, coords in res:
            if dim != 1 or coords is None:
                continue
            t = next((t for t in d['texs'] if t[0] == slot), None)
            tex = cap.data.get((3, t[8], t[9])) if t else None
            if tex and tex['w'] and len(tex['bytes']) >= tex['w'] * tex['h'] * 4:
                pick = (slot, coords, t, tex)
                break
        if pick is None:
            why['no decoded 2D texture'] += 1
            continue
        slot, coords, t, tex = pick
        out[id(p)] = (coords[:, :2].astype(np.float32), tex, f'{t[9]:016x}{t[8]:016x}')
        why['textured'] += 1
    for k, v in why.most_common():
        print(f'  materials: {k}: {v}')
    return out


def write_gltf(out, objs, cam, mats=None):
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
    images, textures, materials_, mat_ids = [], [], [], {}
    tex_dir = os.path.splitext(out)[0] + '_tex'

    def material_index(tex, key):
        if key not in mat_ids:
            os.makedirs(tex_dir, exist_ok=True)
            name = f'{key[:16]}_{tex["w"]}x{tex["h"]}.png'
            fr.write_png(os.path.join(tex_dir, name), tex['w'], tex['h'], tex['bytes'][:tex['w'] * tex['h'] * 4])
            images.append({'uri': os.path.basename(tex_dir) + '/' + name})
            textures.append({'source': len(images) - 1, 'sampler': 0})
            materials_.append({'pbrMetallicRoughness': {'baseColorTexture': {'index': len(textures) - 1}, 'metallicFactor': 0.0,
                                                        'roughnessFactor': 1.0}, 'doubleSided': True})
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
        uv = mat[0] if mat is not None and np.all(np.isfinite(mat[0])) else None
        h = hashlib.blake2b(P.tobytes() + tris.tobytes() + (uv.tobytes() if uv is not None else b'') +
                            (mat[2].encode() if uv is not None else b''), digest_size=12).hexdigest()
        if h not in mesh_ids:
            pv = add_view(P.tobytes(), 34962)
            accessors.append({'bufferView': pv, 'componentType': 5126, 'count': len(P), 'type': 'VEC3',
                              'min': P.min(axis=0).tolist(), 'max': P.max(axis=0).tolist()})
            prim = {'attributes': {'POSITION': len(accessors) - 1}}
            if uv is not None:
                accessors.append({'bufferView': add_view(uv.tobytes(), 34962), 'componentType': 5126, 'count': len(uv), 'type': 'VEC2'})
                prim['attributes']['TEXCOORD_0'] = len(accessors) - 1
                prim['material'] = material_index(mat[1], mat[2])
            iv = add_view(tris.ravel().tobytes(), 34963)
            accessors.append({'bufferView': iv, 'componentType': 5125, 'count': int(tris.size), 'type': 'SCALAR'})
            prim['indices'] = len(accessors) - 1
            meshes.append({'primitives': [prim]})
            mesh_ids[h] = len(meshes) - 1
        checks.append((per_vert, Wg, P))
        nodes.append({'mesh': mesh_ids[h], 'matrix': Wg.T.ravel().tolist(), 'name': f"draw{d['seq']}"})
    C = np.eye(4)
    C[:3, 0], C[:3, 1], C[:3, 2], C[:3, 3] = right, up, -fwd, pos
    nodes.append({'camera': 0, 'matrix': C.T.ravel().tolist(), 'name': 'capture_camera'})
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
            **({'images': images, 'textures': textures, 'materials': materials_, 'samplers': [{'wrapS': 10497, 'wrapT': 10497}]}
               if images else {}),
            'buffers': [{'byteLength': len(blob), 'uri': os.path.basename(os.path.splitext(out)[0]) + '.bin'}]}
    with open(os.path.splitext(out)[0] + '.bin', 'wb') as f:
        f.write(blob)
    with open(out, 'w') as f:
        json.dump(gltf, f)
    print(f'glTF written: {out} ({len(meshes)} meshes, {len(nodes) - 1} placed draws, {len(materials_)} textured materials, {len(blob) / 1e6:.1f} MB)')


if __name__ == '__main__':
    sys.exit(main())
