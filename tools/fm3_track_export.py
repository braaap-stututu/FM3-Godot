#!/usr/bin/env python3
"""fm3_track_export.py: a whole FM3 track from its own files as glTF, for the viewer.

    python fm3_track_export.py <extracted bin.zip dir> <out.gltf> [--camera-from world.gltf] [--texmap capmap_dir]
                               [--pvs <track>_NN.pvs]

--pvs: textures from the game's own files for every mesh. The .pvs model table lists each model's texture-table
entries (texture file id + atlas rectangle); the model file's shaders (names end in their texture count) take blocks
of the non-atlas entries in order, and the first of a block is the base texture (85 % right against a captured frame);
the atlas entry is the lightmap: a whole texture when _0x<id>.bix exists, otherwise the rectangle (applied to UV1, or UV0
without one) in the <track>.stx.bin atlas whose id is the largest atlas id <= the entry's id. .bix base levels decode with
tools/fm3_tex.py. Props (model space) are placed by the .pvs instances of that ribbon (layout): world = F (R^T p + pos)
with F = diag(1, 1, -1) and R the instance's 3x3 (origin instances carry R = F, i.e. identity); each instance's own
lightmap entry overrides the model's. Model files without instances are world-space track pieces and are drawn as is.

Track model files (.rmb.bin, tools/fm3_track.py) hold world-space vertices for the track itself (Ladera: all 1,914
files have an identity header matrix and their vertices are what the GPU draws). Meshes are merged per material (and
lightmap). --texmap: textures per material and lightmap placements per mesh, learned from a captured frame
(fir_world.py --material-map, then tools/fm3_track_texmap.py writing <capmap_dir>/track_materials.json); other materials
get stand-in colours by name. --camera-from copies the camera and sun nodes from a fir_world.py export.
"""
import glob
import json
import os
import shutil
import struct
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fm3_track  # noqa: E402
import fm3_tex  # noqa: E402
import fm3_pvs  # noqa: E402
import fm3_families  # noqa: E402
import fm3_car  # noqa: E402
import fm3_carbin  # noqa: E402
import fir_read as fr  # noqa: E402
import fir_frame  # noqa: E402
import re  # noqa: E402
from fir_world import smooth_normals  # noqa: E402

COLOURS = [  # (substring of the lower-case material name, base colour)
    ('rdline', (0.85, 0.85, 0.82)), ('line', (0.85, 0.85, 0.82)), ('kerb', (0.75, 0.2, 0.15)), ('curb', (0.75, 0.2, 0.15)),
    ('road', (0.22, 0.22, 0.22)), ('asphalt', (0.22, 0.22, 0.22)), ('pit', (0.3, 0.3, 0.3)),
    ('grass', (0.28, 0.38, 0.16)), ('veg', (0.2, 0.32, 0.12)), ('tree', (0.18, 0.28, 0.1)), ('bush', (0.2, 0.3, 0.12)),
    ('rock', (0.48, 0.46, 0.43)), ('terr', (0.45, 0.4, 0.32)), ('dirt', (0.45, 0.37, 0.27)), ('sand', (0.65, 0.58, 0.45)),
    ('gravel', (0.55, 0.52, 0.47)), ('barr', (0.7, 0.7, 0.7)), ('wall', (0.65, 0.63, 0.6)), ('facility', (0.7, 0.68, 0.64)),
    ('build', (0.7, 0.68, 0.64)), ('roof', (0.5, 0.5, 0.52)), ('glass', (0.2, 0.25, 0.3)), ('water', (0.15, 0.3, 0.4)),
]


def colour_for(name):
    n = (name or '').lower()
    for key, c in COLOURS:
        if key in n:
            return c
    return (0.6, 0.6, 0.6)


def apply_uv(chan, a, b, me):
    if chan == 'world':
        return (np.c_[me['positions'], np.ones(len(me['positions']))] @ np.array(a).T).astype(np.float32)
    uv = me.get(chan)
    if uv is None:
        return None
    return (uv * np.array(a) + np.array(b)).astype(np.float32)


CARBIN_DIRS = []  # --carbins DIR[;DIR]: whole cars from their .carbin files instead of the captured draws
# --car-matrices <json> (2026-11-23): the game's car body matrices on the grid (tools/live_listen.py --save-cars, from
# FM3_LIVE): carbin car space goes to the world as F (p M) exactly (0.1 mm on the fitted cars), so every car is placed
# by its matrix, also the far ones whose captured low-detail draws are not in the carbin (no fit possible).
CAR_MATRICES = []
CAR_MATRIX_WHEELS = []  # per CAR_MATRICES entry: its four wheels' matrices as drawn (game space, row vectors) or []
WHEEL_DIRS = []  # --wheel-files DIR: <dir>/<car>/ = the car's stock wheel zip (Media\\Wheels\\<car>.zip, DLC packs)
WHEELS_BUILT = set()  # cars whose wheels were built from their wheel carbin (their captured wheel draws are dropped)
CAR_FILE_DIRS = []  # --car-files DIR[;DIR]: <dir>/<car>/ = the car zip's contents (_lod0, _cockpit, textures, ...)
LAMP_MATERIALS = ('tail_light', 'reverse_light', 'head_light', 'brake_light', 'signal', 'reflector', 'textured_reflector',
                  'white_brake')
CARMATS = {}  # car mesh node name -> its glass material's parameters (the game's shader settings), <out>_carmaterials.json
NEEDLES = {}  # node name -> gauge needle data (cockpit gauges), written beside the glTF as <out>_needles.json
CAR_GEOM = {}  # car -> (placed vertices sample): build_cars' cars, to drop their captured low-detail duplicates


CAR_FLAT = {k: v for k, v in json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'profiles', 'fm3',
                                                         'car_materials.json'))).items() if isinstance(v, dict) and not v.get('keep')}


def build_cars(ref, rbin, caps, capdir, copy_mat, add_view, accessors, meshes, nodes, materials_out, images=None,
               textures=None, tex_out=None):
    """Every car of the capture rebuilt from its .carbin (fm3_car.py): the stock parts (the captured variants, mirrored
    to the other side, else 'a'), placed by a rigid fit of the car's captured draws (carbin car space -> world), with
    the materials the capture gave each material name (UV0 is the captured texture coordinate). Returns the car names
    built (their captured body draws are then left out; wheels stay captured)."""
    fl = os.path.join(capdir, 'fetches.json') if capdir else None
    recs = dict(caps)
    if fl and os.path.exists(fl):
        for r in json.load(open(fl)):
            recs.setdefault(r['seq'], r)

    def world_of(n):
        p = ref['meshes'][n['mesh']]['primitives'][0]
        a = ref['accessors'][p['attributes']['POSITION']]
        v = ref['bufferViews'][a['bufferView']]
        P = np.frombuffer(rbin, np.float32, a['count'] * 3, v.get('byteOffset', 0) + a.get('byteOffset', 0)).reshape(-1, 3)
        M = np.array(n.get('matrix', np.eye(4).ravel())).reshape(4, 4).T
        return P.astype(np.float64) @ M[:3, :3].T + M[:3, 3], p.get('material')
    xds_tex, xds_mat = {}, {}

    def xds_texture(zdir, stem, opaque=False):
        """glTF texture index of <zdir>/<stem>.xds decoded to a PNG in tex_out (once), or None. opaque: alpha set to
        255 (a '_rgb' copy, for materials that use the colour where the alpha is 0: Godot's import fills fully
        transparent pixels with their neighbours' colour, the cockpit gauges' dark faces came out white)."""
        key = (zdir, stem, opaque)
        if key not in xds_tex:
            src = os.path.join(zdir, stem + '.xds')
            img = fm3_tex.load_xds(src) if os.path.exists(src) else None
            if img is None:
                xds_tex[key] = None
            else:
                os.makedirs(tex_out, exist_ok=True)
                name = f'car_{os.path.basename(zdir)}_{stem}{"_rgb" if opaque else ""}.png'
                if opaque:
                    img = img.copy()
                    img[..., 3] = 255
                fr.write_png(os.path.join(tex_out, name), img.shape[1], img.shape[0], np.ascontiguousarray(img).tobytes())
                images.append({'uri': os.path.basename(tex_out) + '/' + name})
                textures.append({'source': len(images) - 1, 'sampler': 0})
                xds_tex[key] = len(textures) - 1
        return xds_tex[key]

    def xds_material(zdir, stem, mname, cutout=False, opaque=False):
        key = (zdir, stem, mname, cutout, opaque)
        if key not in xds_mat:
            ti = xds_texture(zdir, stem, opaque)
            if ti is None:
                xds_mat[key] = None
            else:
                materials_out.append({'name': f'{mname}_{stem}', 'doubleSided': True, 'pbrMetallicRoughness': {
                    'baseColorTexture': {'index': ti}, 'metallicFactor': 0.0, 'roughnessFactor': 0.6},
                    **({'alphaMode': 'MASK', 'alphaCutoff': 0.5} if cutout else {})})
                xds_mat[key] = ('index', len(materials_out) - 1)
        return xds_mat[key]
    if images is None:
        xds_material = None  # noqa: F811 (no texture lists to add to)

    per_car = {}
    for n in ref['nodes']:
        mo = re.match(r'draw(\d+) ([a-z0-9_]+)\.([a-z0-9_]+)$', n.get('name', ''))
        if mo and 'mesh' in n:
            per_car.setdefault(mo.group(2), []).append((int(mo.group(1)), mo.group(3), n))
    built = set()
    for car, draws in per_car.items():
        path = next((os.path.join(d, car + '.carbin') for d in CARBIN_DIRS
                     if os.path.exists(os.path.join(d, car + '.carbin'))), None)
        if path is None:
            continue
        secs = fm3_car.parse(open(path, 'rb').read())
        by_ib = {}
        for si, sec in enumerate(secs):
            for sub in sec['subs']:
                by_ib.setdefault(sub['ib_hex'], (si, sub))
        X, Y, captured, mat_of = [], [], set(), {}
        for seq, matname, n in draws:
            r = recs.get(seq)
            hit = by_ib.get(r['ib']) if r else None
            if hit is None:
                continue
            si, sub = hit
            sec = secs[si]
            W, mat = world_of(n)
            vi = np.array(r['vindex'])
            if sec['offset'] is None or len(vi) != len(W) or vi.max() >= len(sec['local']):
                continue
            captured.add(sec['name'])
            if mat is not None:
                mat_of.setdefault((sec['name'], sub['material']), mat)
                votes = mat_of.setdefault(('*', sub['material']), {})
                votes[mat] = votes.get(mat, 0) + len(vi)
            if sec['name'].startswith(('headlight', 'trunk', 'hood', 'door')):
                continue  # (movable parts: not used for the fit)
            X.append(sec['local'][vi] + sec['offset'])
            Y.append(W)
        # The car's matrix (--car-matrices): the one nearest the centre of all its captured draws (within 4 m).
        placed_by = None
        best_wheels = []
        if CAR_MATRICES:
            centre = np.concatenate([world_of(n)[0] for _, _, n in draws]).mean(0)
            Fz = np.diag([1.0, 1.0, -1.0])
            best = min(CAR_MATRICES, key=lambda M: np.linalg.norm(Fz @ M[3, :3] - centre))
            best_wheels = next((w for M, w in zip(CAR_MATRICES, CAR_MATRIX_WHEELS) if M is best), [])
            if np.linalg.norm(Fz @ best[3, :3] - centre) < 4.0:
                R, t, err = Fz @ best[:3, :3].T, Fz @ best[3, :3], 0.0
                good = list(range(len(X)))
                placed_by = 'its game matrix'
        if placed_by is None:
            if not X:
                continue
            # robust: fit on the largest captured piece, keep the pieces it explains within 2 cm (some parts sit animated
            # or damage-deformed in the frame), refit on those
            good, err = [], 1.0
            for seed in sorted(range(len(X)), key=lambda i: -len(X[i]))[:12]:  # the seed piece that explains most pieces
                if len(X[seed]) < 4:
                    continue
                R, t, e = fm3_car.kabsch(X[seed], Y[seed])
                g_ = [i for i in range(len(X)) if np.abs(X[i] @ R.T + t - Y[i]).max() < 0.02]
                if sum(len(X[i]) for i in g_) > sum(len(X[i]) for i in good):
                    good, err = g_, e
            if not good:
                print(f'  {car}: largest captured piece is not rigid in the carbin ({err:.3f} m), kept the captured draws')
                continue
            R, t, err = fm3_car.kabsch(np.concatenate([X[i] for i in good]), np.concatenate([Y[i] for i in good]))
            if err > 0.05 or len(good) < max(3, len(X) // 3):
                print(f'  {car}: carbin fit error {err:.3f} m, kept the captured draws')
                continue
            placed_by = f'fit {err * 1000:.1f} mm over {len(good)} of {len(X)} captured pieces'
        elif X:
            fit_err = max(float(np.abs(X[i] @ R.T + t - Y[i]).max()) for i in range(len(X)))
            placed_by += f' (its {len(X)} matched captured pieces within {fit_err * 1000:.1f} mm)'
        keep = fm3_car.stock_parts(secs, captured)
        # the car's paint: the captured material with a metallic-roughness texture (fir_world writes one only for paint)
        paint = None
        for (sn, mn), v in mat_of.items():
            if sn == '*':
                for mi_, cnt_ in v.items():
                    if 'metallicRoughnessTexture' in ref['materials'][mi_].get('pbrMetallicRoughness', {}):
                        paint = mi_
        if paint is None:
            # A far car's paint is drawn by low-detail draws that match no carbin part: the asset match named them after
            # whatever carbin material they resembled (the PT Cruiser's body LOD as 'emblem', the Beetle's as 'frame'),
            # or not at all. The paint shader gives itself away: fir_world writes a metallic-roughness texture only for
            # paint. So: the paint material of this car's own captured draws, then of the unnamed ones in its box, by
            # vertex count.
            Rinv = np.linalg.inv(R)
            votes = {}
            cand = [n for _, _, n in draws] + [n for n in ref['nodes'] if 'mesh' in n and re.match(r'draw\d+$', n.get('name', ''))]
            for n in cand:
                Wn, mn = world_of(n)
                if mn is None or 'metallicRoughnessTexture' not in ref['materials'][mn].get('pbrMetallicRoughness', {}):
                    continue
                loc = (Wn - t) @ Rinv.T
                if np.all(np.abs(loc[:, 0]) < 1.3) and np.all(np.abs(loc[:, 2]) < 3.0) and np.all(np.abs(loc[:, 1]) < 2.0):
                    votes[mn] = votes.get(mn, 0) + len(Wn)
            if votes:
                paint = max(votes, key=votes.get)
                print(f'  {car}: paint from {votes[paint]} captured low-detail paint-shader vertices on it')
        # The geometry (PLAN-CARS phase 2, 2026-11-23): the car's high-detail <car>_lod0.carbin (its zip contents in a
        # --car-files folder), read structurally (fm3_carbin.py), with the main file's LOD 1 only for the parts LOD 0
        # lacks (cabin, seats, mirrors, hood, windscreen and side glass), never both for one part; the file's own normals.
        # Without the zip: the main file's LOD 1 as before (fm3_car.py), normals recomputed.
        geo, geo_from = secs, 'main file LOD 1'
        zdir = next((os.path.join(d, car) for d in CAR_FILE_DIRS if os.path.exists(os.path.join(d, car, car + '_lod0.carbin'))), None)
        if zdir:
            l0 = fm3_carbin.sections(fm3_carbin.parse(open(os.path.join(zdir, car + '_lod0.carbin'), 'rb').read()), 0)
            have = {s['name'] for s in l0}
            l1 = [s for s in fm3_carbin.sections(fm3_carbin.parse(open(path, 'rb').read()), 1) if s['name'] not in have]
            for s in l0:
                s['lod'] = 0
            for s in l1:
                s['lod'] = 1
            geo = l0 + l1
            geo_from = f'LOD 0 ({len(l0)} parts) + main file LOD 1 for {len(l1)} parts it lacks'
        groups = {}
        unmapped = {}  # material names with no material (glTF default: white): reported
        for sec in geo:
            if sec['name'] not in keep or sec['offset'] is None or sec['name'] == 'wheel':
                continue
            P = (sec['local'] + sec['offset']) @ R.T + t
            Nf = None
            if sec.get('normal') is not None:
                Nf = sec['normal'] @ R.T
                Nf /= np.maximum(np.linalg.norm(Nf, axis=1, keepdims=True), 1e-9)
            for sub in sec['subs']:
                tris = fm3_car.triangles(sub['indices'], sub['prim'], restart=sub.get('restart', 0xFFFF))
                if not len(tris) or tris.max() >= len(P):
                    print(f'  {car}: {sec["name"]}.{sub["material"]}: indices past its {len(P)} vertices, left out')
                    continue
                mname = sub['material'][:-5] if sub['material'].endswith('_lod0') else sub['material']
                m_ = mat_of.get((sec['name'], mname))
                if mname.startswith('mirror'):
                    m_ = ('flat', 'window')  # (mirror glass: dark opaque glass, glass_params' MIRROR_GLASS)
                if m_ is None and ('*', mname) in mat_of:
                    v_ = mat_of[('*', mname)]
                    m_ = max(v_, key=v_.get)  # the material most of this name's captured vertices had
                if m_ is None and mname in ('body', 'body_2') and paint is not None:
                    m_ = paint
                if m_ is None and mname in CAR_FLAT:
                    m_ = ('flat', mname)
                if m_ is None and zdir and xds_material is not None:
                    # The car's own texture (PLAN-CARS phase 3, first step): lamps on lights[_lod0].xds, the rest on
                    # nodamage[_lod0].xds (the baseSampler's 'nodamage'); _lod0 files for LOD 0 meshes.
                    lamp = mname.startswith(('head_light', 'tail_light', 'reverse_light', 'brake_light', 'signal'))
                    m_ = xds_material(zdir, ('lights' if lamp else 'nodamage') + ('_lod0' if sec.get('lod') == 0 else ''),
                                      mname, cutout=mname in ('emblem', 'badge'))
                if m_ is None:
                    unmapped[mname] = unmapped.get(mname, 0) + len(tris)
                # baked brightness (vertex byte 20, as the cockpit's): dark cabin seen through the glass, dark underside
                # and exhaust; used by plain materials only (paint and glass have their own shaders)
                lit = None
                # (not the lamps: they sit in the housings' dark cavities, but the game shows their reflectors bright
                # through the lenses)
                if sec.get('light') is not None and not mname.startswith(LAMP_MATERIALS):
                    lit = np.clip(sec['light'] / 107.0, 0.0, 1.0) ** 2.2
                groups.setdefault((mname, m_), []).append((P, tris, sec['uv0'], Nf, lit))
        mirrored = np.linalg.det(R) < 0
        normal_agree = []

        def emit(groups, prefix):
          for (matname, matidx), parts in groups.items():
            Pc = np.concatenate([q[0] for q in parts]).astype(np.float32)
            Uc = np.concatenate([q[2] for q in parts]).astype(np.float32)
            off, tl = 0, []
            for q in parts:
                tl.append((q[1][:, ::-1] if mirrored else q[1]) + off)
                off += len(q[0])
            T = np.concatenate(tl).astype(np.uint32)
            N = smooth_normals(Pc, T)
            if all(q[3] is not None for q in parts):
                # The file's normals (11:11:10 at byte 16): |cos| 0.965 per vertex against normals rebuilt from the
                # geometry on the CR-X's LOD 0, and pointing outwards; used as they are. (Rebuilt normals take their
                # sign from the strip winding, which alternates: no reference for the sign.)
                Nfile = np.concatenate([q[3] for q in parts])
                normal_agree.append(float(np.mean(np.abs(np.sum(Nfile * N, axis=1)))))
                N = Nfile
            prim = {'attributes': {}}
            attrs = [('POSITION', Pc, 'VEC3'), ('NORMAL', N.astype(np.float32), 'VEC3'), ('TEXCOORD_0', Uc, 'VEC2')]
            if all(len(q) > 4 and q[4] is not None for q in parts):
                lit = np.concatenate([q[4] for q in parts]).astype(np.float32)
                attrs.append(('COLOR_0', np.stack([lit, lit, lit, np.ones_like(lit)], axis=1), 'VEC4'))
            for attr, arr, typ in attrs:
                acc = {'bufferView': add_view(np.ascontiguousarray(arr).tobytes(), 34962), 'componentType': 5126,
                       'count': len(arr), 'type': typ}
                if attr == 'POSITION':
                    acc.update(min=Pc.min(0).tolist(), max=Pc.max(0).tolist())
                accessors.append(acc)
                prim['attributes'][attr] = len(accessors) - 1
            accessors.append({'bufferView': add_view(T.tobytes(), 34963), 'componentType': 5125, 'count': int(T.size),
                              'type': 'SCALAR'})
            prim['indices'] = len(accessors) - 1
            if isinstance(matidx, tuple) and matidx[0] == 'index':
                prim['material'] = matidx[1]  # (a car texture material, already in materials_out)
            elif isinstance(matidx, tuple):
                r_ = CAR_FLAT[matidx[1]]
                materials_out.append({'name': matidx[1], 'doubleSided': True, 'pbrMetallicRoughness': {
                    'baseColorFactor': list(r_.get('color', [0.5, 0.5, 0.5])) + [float(r_.get('alpha', 1.0))],
                    'metallicFactor': r_.get('metallic', 0.0), 'roughnessFactor': r_.get('roughness', 1.0)},
                    **({'alphaMode': 'BLEND'} if r_.get('alpha', 1.0) < 1.0 else {})})
                prim['material'] = len(materials_out) - 1
            elif matidx is not None:
                prim['material'] = copy_mat(matidx)
            meshes.append({'name': f'{car}.{matname}', 'primitives': [prim]})
            nodes.append({'mesh': len(meshes) - 1, 'name': f'{prefix}{car}_{matname}_{len(meshes) - 1}'})
        first_node = len(nodes)
        emit(groups, 'carbin_')
        # The cockpit (PLAN-CARS phase 4, 2026-11-23): <car>_cockpit.carbin, the in-car model (cabin with gauges,
        # seats, steering wheel, A-pillars, hood, mirrors, windscreen) in the same car space; nodes 'cockpit_<car>_...',
        # which the viewer shows instead of the car's body when the game's camera is a first-person one. Cabin
        # materials on the car's interior_lod0.xds (CockpitInteriorHiSampler), the outside pieces on nodamage_lod0,
        # paint and glass as on the body. (The race cage is an option, left out.)
        ckpath = os.path.join(zdir, car + '_cockpit.carbin') if zdir else None
        cockpit_parts = 0
        if ckpath and os.path.exists(ckpath) and xds_material is not None:
            cgroups = {}
            csecs = fm3_carbin.sections(fm3_carbin.parse(open(ckpath, 'rb').read()), 0)
            byname = {sec['name']: sec for sec in csecs}
            ticks = gauge_ticks(os.path.join(zdir, 'carattribs.xml'))
            for sec in csecs:
                # (gauge needles come as <gauge>_min / _mid / _max parts, the same needle at parameter 0, 0.5 and 1;
                # the game shows one and turns it: _min is kept, as its own node, with its rotation (needle_turn))
                if sec['name'].endswith(('race', '_mid', '_max')):
                    continue
                needle = None
                if sec['name'] == 'steering_wheel':
                    needle = steering_turn((sec['local'] + sec['offset']) @ R.T + t,
                                           [(q['local'] + q['offset']) @ R.T + t for q in csecs
                                            if q['name'] in ('seatL', 'seatR')])
                    if needle is not None:
                        needle.update(gauge='steering', car=car)
                        turns = car_attrib(os.path.join(zdir, 'carattribs.xml'), 'SteeringWheelAngleOverride')
                        if turns:
                            needle['game_deg'] = 360.0 * turns  # (the CR-X's 0.206 = 74 deg; its in-car pictures: ~73)
                elif sec['name'].endswith('_min'):
                    gname = sec['name'][:-4]
                    mid, mx = byname.get(gname + '_mid'), byname.get(gname + '_max')
                    if mid is not None and mx is not None:
                        world = lambda q: (q['local'] + q['offset']) @ R.T + t  # noqa: E731
                        needle = needle_turn(world(sec), world(mid), world(mx))
                        if needle is not None:
                            needle.update(gauge=gname, car=car, ticks=ticks.get(gname, []))
                cockpit_parts += 1
                P = (sec['local'] + sec['offset']) @ R.T + t
                Nf = None
                if sec.get('normal') is not None:
                    Nf = sec['normal'] @ R.T
                    Nf /= np.maximum(np.linalg.norm(Nf, axis=1, keepdims=True), 1e-9)
                outside = sec['name'] in ('a_pillar', 'hooda', 'mirrorL', 'mirrorR')
                for sub in sec['subs']:
                    tris = fm3_car.triangles(sub['indices'], sub['prim'], restart=sub.get('restart', 0xFFFF))
                    if not len(tris) or tris.max() >= len(P):
                        continue
                    mname = sub['material']
                    if mname == 'glass' and sec['name'] == 'interior':
                        continue  # (the gauges' clear cover: through the window-glass shader it blacked the dials out)
                    if mname in ('body', 'body_2') and paint is not None:
                        m_ = paint
                    elif mname in CAR_FLAT and CAR_FLAT[mname].get('glass'):
                        m_ = ('flat', mname)
                    elif mname.startswith('mirror'):
                        m_ = ('flat', 'window')  # (the game's mirrors are render targets: dark reflective glass here)
                    else:
                        m_ = xds_material(zdir, 'nodamage_lod0' if outside else 'interior_lod0', 'cockpit_' + mname,
                                          cutout=mname in ('emblem', 'badge'),
                                          opaque='gauge' in mname)  # (dark faces, white markings, alpha 0)
                    # baked brightness (vertex byte 20) as a vertex colour: 107 = open sky (the hood's highest); linear
                    lit = None
                    if sec.get('light') is not None and not mname.startswith('gauge'):  # (gauges glow: GaugeEmissiveScale)
                        lit = np.clip(sec['light'] / 107.0, 0.0, 1.0) ** 2.2
                    gkey = 'cockpit_' + mname + (f'-{sec["name"]}' if needle is not None else '')
                    cgroups.setdefault((gkey, m_), []).append((P, tris, sec['uv0'], Nf, lit))
                    if needle is not None:
                        NEEDLES[gkey] = needle
            first = len(nodes)
            emit(cgroups, 'cockpit_')
            for nd in nodes[first:]:
                # (node names: cockpit_<car>_cockpit_<material>-<part>_<mesh>: the needle data under the node's name)
                key = next((k for k in NEEDLES if isinstance(NEEDLES[k], dict) and NEEDLES[k].get('car') == car
                            and nd['name'].startswith(f'cockpit_{car}_{k}_')), None)
                if key is not None:
                    NEEDLES[nd['name']] = NEEDLES.pop(key)
        # The game's glass parameters per mesh node (exterior and cockpit), for the viewer's glass shader
        settings = car_settings(zdir)
        for nd in nodes[first_node:]:
            nm = nd['name']
            for pre in ('carbin_' + car + '_', 'cockpit_' + car + '_cockpit_'):
                if nm.startswith(pre):
                    mname = nm[len(pre):].rsplit('_', 1)[0].split('-')[0]
                    gp = cockpit_glass_params(settings, mname) if pre.startswith('cockpit') else glass_params(settings, mname)
                    if gp is not None:
                        CARMATS[nm] = gp
                    break
        wheel_note = build_wheels(car, best_wheels, ref, copy_mat, xds_material, emit, zdir) if best_wheels else ''
        built.add(car)
        allp = np.concatenate([q[0] for parts in groups.values() for q in parts])
        CAR_GEOM[car] = allp[np.linspace(0, len(allp) - 1, min(6000, len(allp))).astype(int)]
        print(f'  {car}: {len(keep)} parts from the carbin ({geo_from}), placed by {placed_by}'
              + (f'; cockpit {cockpit_parts} parts' if cockpit_parts else '') + wheel_note
              + (f'; file normals vs rebuilt: mean |cos| {np.mean(normal_agree):.3f}' if normal_agree else '')
              + (f'; NO MATERIAL (white): {", ".join(f"{k} ({v} tris)" for k, v in sorted(unmapped.items()))}' if unmapped else ''))
    return built


def build_wheels(car, wheels, ref, copy_mat, xds_material, emit, zdir=None):
    """A car's four wheels from its stock wheel carbin (PLAN-CARS phase 2): LOD 0 (rims, spokes, the blurred rim; FM3's
    LOD 0 has no tyre) plus the tyre of LOD 1, each placed by the wheel's matrix as the game draws it (spin and steering
    included; world = F (p W) as the body). Materials: the captured wheel draws' by material name, else the wheel zip's
    textures (wheel_lod0.xds; the blurred rim wheel0_lod0.xds), the tyre a flat rubber. Nodes 'wheel_<car>_<k>_<material>_n'
    (the viewer follows each wheel's matrix and switches rim / blurred rim by speed)."""
    wdir = next((os.path.join(d, car) for d in WHEEL_DIRS if os.path.isdir(os.path.join(d, car))), None)
    path = None
    if wdir:
        for root_, _, files in os.walk(wdir):
            for f_ in files:
                if f_.lower() == car + '.carbin':
                    path = os.path.join(root_, f_)
    if not path or len(wheels) != 4:
        return ''
    tex_dir = os.path.dirname(path)
    w = fm3_carbin.parse(open(path, 'rb').read())
    secs = [(s, False) for s in fm3_carbin.sections(w, 0)]
    secs += [(dict(s, subs=[u for u in s['subs'] if u['material'] in ('tire', 'tread', 'sidewall')]), True)
             for s in fm3_carbin.sections(w, 1)]
    # the captured wheel draws' materials by name (their textures as the game bound them)
    cap = {}
    for n in ref['nodes']:
        mo = re.match(r'draw\d+ wheel:([a-z0-9_]+)\.([A-Za-z0-9_]+)$', n.get('name', ''))
        if mo and mo.group(1) == car and 'mesh' in n:
            p0 = ref['meshes'][n['mesh']]['primitives'][0]
            if 'material' in p0:
                cap.setdefault(mo.group(2), p0['material'])
    Fz = np.diag([1.0, 1.0, -1.0])
    groups = {}
    for k, W in enumerate(wheels):
        R = Fz @ W[:3, :3].T
        t = Fz @ W[3, :3]
        # The wheel model's spoke face is at its -x; the four matrices all keep x along the car's +x (no mirror,
        # determinant +1), so on the car's right side the game must mirror the model elsewhere: mirrored here (checked
        # on the CR-X: the spoke face outboard on both sides). Order: 0 LF, 1 RF, 2 RR, 3 LR.
        side = np.diag([-1.0, 1.0, 1.0]) if k in (1, 2) else np.eye(3)
        for sec, lod1 in secs:
            P = ((sec['local'] + sec['offset']) @ side) @ R.T + t
            Nf = None
            if sec.get('normal') is not None:
                Nf = (sec['normal'] @ side) @ R.T
                Nf /= np.maximum(np.linalg.norm(Nf, axis=1, keepdims=True), 1e-9)
            for sub in sec['subs']:
                tris = fm3_car.triangles(sub['indices'], sub['prim'], restart=sub.get('restart', 0xFFFF))
                if not len(tris) or tris.max() >= len(P):
                    continue
                mname = sub['material']
                # (the wheel zip's own textures, not the captured draws' materials: those came as the track's blend
                # family or paint, past the viewer's rim handling: light grey spokes)
                if mname in ('tire', 'tread', 'sidewall'):
                    m_ = ('flat', 'tire')
                elif xds_material is not None:
                    m_ = xds_material(tex_dir, 'wheel0_lod0' if 'blur' in mname else 'wheel_lod0', 'wheel_' + mname,
                                      cutout='blur' in mname)
                else:
                    m_ = None
                lit = None if sec.get('light') is None else np.clip(sec['light'] / 107.0, 0.0, 1.0) ** 2.2
                groups.setdefault((f'{k}_{mname}', m_), []).append((P, tris, sec['uv0'], Nf, lit))
    emit(groups, 'wheel_')
    WHEELS_BUILT.add(car)
    # Brakes from the car zip (<car>_rotor{lf,rf,rr,lr}.carbin, _caliper..: each corner its own model, centred on the
    # wheel, axle along x): the rotor turns with the wheel (its matrix as drawn); the caliper does not spin: placed in
    # the wheel's frame without the spin (axle from the wheel matrix, up from the car's), nodes 'brake_..caliper..' that
    # the viewer moves with the body. Flat materials (no brake textures in the zips).
    nb = 0
    if zdir:
        corner = ['lf', 'rf', 'rr', 'lr']
        bgroups = {}
        for k, W in enumerate(wheels):
            R = Fz @ W[:3, :3].T
            t = Fz @ W[3, :3]
            x = W[0, :3] / np.linalg.norm(W[0, :3])
            up = np.array([0.0, 1.0, 0.0])
            y = up - x * float(up @ x)
            y /= np.linalg.norm(y)
            z = np.cross(x, y)
            Rc = Fz @ np.stack([x, y, z]).T
            for kind, Rk in (('rotor', R), ('caliper', Rc)):
                f_ = os.path.join(zdir, f'{car}_{kind}{corner[k]}.carbin')
                if not os.path.exists(f_):
                    continue
                b = fm3_carbin.parse(open(f_, 'rb').read())
                for sec in fm3_carbin.sections(b, 0) or fm3_carbin.sections(b, 1):
                    P = (sec['local'] + sec['offset']) @ Rk.T + t
                    Nf = None
                    if sec.get('normal') is not None:
                        Nf = sec['normal'] @ Rk.T
                        Nf /= np.maximum(np.linalg.norm(Nf, axis=1, keepdims=True), 1e-9)
                    for sub in sec['subs']:
                        tris = fm3_car.triangles(sub['indices'], sub['prim'], restart=sub.get('restart', 0xFFFF))
                        if not len(tris) or tris.max() >= len(P):
                            continue
                        mn = sub['material']
                        m_ = ('flat', mn) if mn in CAR_FLAT else ('flat', 'black')
                        bgroups.setdefault((f'{k}_{kind}_{mn}', m_), []).append((P, tris, sec['uv0'], Nf))
                        nb += 1
        if bgroups:
            emit(bgroups, 'brake_')
    return f'; wheels from {os.path.basename(path)} ({len(cap)} captured materials)' + (f', {nb} brake meshes' if nb else '')


def on_rebuilt_car(W):
    """True when a captured draw's vertices lie on a car rebuilt from its carbin (median distance under 3 cm): one of
    that car's own low-detail pieces, now duplicated by the carbin. Drivers and people sit further from the body."""
    if not CAR_GEOM or not len(W):
        return False
    c = W.mean(0)
    sample = W[np.linspace(0, len(W) - 1, min(60, len(W))).astype(int)]
    for P in CAR_GEOM.values():
        if np.linalg.norm(P.mean(0) - c) > 4.0:
            continue
        d = np.array([np.min(np.linalg.norm(P - q, axis=1)) for q in sample])
        if np.median(d) < 0.03:
            return True
    return False


def import_dynamic(ref_path, capdir, src, add_view, accessors, materials, images, textures, meshes, nodes, tex_out):
    """Copy the capture export's dynamic objects into this glTF: cars (nodes named after their car, fir_world.py's asset
    match) and every captured draw whose vertex data is not in the track's files (people, drivers, the crowd, flags)."""
    ref = json.load(open(ref_path))
    rbin = open(os.path.join(os.path.dirname(ref_path), ref['buffers'][0]['uri']), 'rb').read()
    caps = {c['seq']: c for c in json.load(open(os.path.join(capdir, 'materials.json')))} if capdir else {}
    blob = b''.join(open(f, 'rb').read() for f in glob.glob(os.path.join(src, '*.rmb.bin')))
    ref_dir = os.path.dirname(ref_path)
    acc_map, mat_map, tex_map = {}, {}, {}

    def copy_acc(i):
        if i not in acc_map:
            a = dict(ref['accessors'][i])
            v = ref['bufferViews'][a['bufferView']]
            n = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}[a['type']]
            size = {5126: 4, 5125: 4, 5123: 2, 5121: 1}[a['componentType']]
            start = v.get('byteOffset', 0) + a.pop('byteOffset', 0)
            data = rbin[start:start + a['count'] * n * size]
            a['bufferView'] = add_view(data, v.get('target', 34962))
            accessors.append(a)
            acc_map[i] = len(accessors) - 1
        return acc_map[i]

    def copy_tex(t):
        if t not in tex_map:
            uri = ref['images'][ref['textures'][t]['source']]['uri']
            dst = os.path.join(tex_out, 'cap_' + os.path.basename(uri))
            os.makedirs(tex_out, exist_ok=True)
            src_ = os.path.join(ref_dir, uri)
            # (copied again when the capture export rewrote it: its names come from texture addresses, not the colours
            # composited in, so an old copy would otherwise stay, as the paint colours did until 2026-11-23)
            if not os.path.exists(dst) or os.path.getmtime(src_) > os.path.getmtime(dst):
                shutil.copyfile(src_, dst)
            images.append({'uri': os.path.basename(tex_out) + '/' + os.path.basename(dst)})
            textures.append({'source': len(images) - 1, 'sampler': 0})
            tex_map[t] = len(textures) - 1
        return tex_map[t]

    def copy_mat(i):
        if i not in mat_map:
            m = json.loads(json.dumps(ref['materials'][i]))
            pbr = m.get('pbrMetallicRoughness', {})
            for k in ('baseColorTexture', 'metallicRoughnessTexture'):
                if k in pbr:
                    pbr[k]['index'] = copy_tex(pbr[k]['index'])
            for k in ('occlusionTexture', 'normalTexture', 'emissiveTexture'):
                if k in m:
                    m[k]['index'] = copy_tex(m[k]['index'])
            materials.append(m)
            mat_map[i] = len(materials) - 1
        return mat_map[i]

    built = build_cars(ref, rbin, caps, capdir, copy_mat, add_view, accessors, meshes, nodes, materials, images, textures,
                       tex_out) if CARBIN_DIRS else set()
    count = len(built)
    dropped_dup = 0
    for n in ref['nodes']:
        if 'mesh' not in n:
            continue
        mo = re.match(r'draw(\d+)(.*)', n.get('name', ''))
        if not mo:
            continue
        car = bool(mo.group(2).strip())
        if car and mo.group(2).strip().split('.')[0] in built:
            continue  # rebuilt whole from its .carbin
        if car and mo.group(2).strip().startswith('wheel:') and mo.group(2).strip()[6:].split('.')[0] in WHEELS_BUILT:
            continue  # its wheels rebuilt from the wheel carbin
        rec = caps.get(int(mo.group(1)))
        if not car and (rec is None or blob.find(bytes.fromhex(rec['vb_head'])[:32]) >= 0):
            continue
        if not car and CAR_GEOM:
            p0 = ref['meshes'][n['mesh']]['primitives'][0]
            a0 = ref['accessors'][p0['attributes']['POSITION']]
            v0 = ref['bufferViews'][a0['bufferView']]
            P0 = np.frombuffer(rbin, np.float32, a0['count'] * 3, v0.get('byteOffset', 0) + a0.get('byteOffset', 0)).reshape(-1, 3)
            M0 = np.array(n.get('matrix', np.eye(4).ravel())).reshape(4, 4).T
            if on_rebuilt_car(P0.astype(np.float64) @ M0[:3, :3].T + M0[:3, 3]):
                dropped_dup += 1
                continue  # a rebuilt car's own low-detail piece
        prims = []
        for p in ref['meshes'][n['mesh']]['primitives']:
            q = {'attributes': {k: copy_acc(v) for k, v in p['attributes'].items()}}
            if 'indices' in p:
                q['indices'] = copy_acc(p['indices'])
            if 'material' in p:
                q['material'] = copy_mat(p['material'])
            if 'mode' in p:
                q['mode'] = p['mode']
            prims.append(q)
        meshes.append({'name': n.get('name'), 'primitives': prims})
        nd = {'mesh': len(meshes) - 1, 'name': n.get('name', '').replace(' ', '_').replace(':', '_')}
        for k in ('matrix', 'translation', 'rotation', 'scale'):
            if k in n:
                nd[k] = n[k]
        nodes.append(nd)
        count += 1
    if dropped_dup:
        print(f'  {dropped_dup} captured low-detail car pieces left out (their cars are rebuilt from the carbin)')
    return count


def car_attrib(path, name):
    """A float <name value="..."/> of carattribs.xml, or None."""
    if not os.path.exists(path):
        return None
    import xml.etree.ElementTree as ET
    e = ET.parse(path).getroot().find(name)
    return float(e.get('value')) if e is not None and e.get('value') else None


def shader_settings(path):
    """An FM3 ShaderSettings XML (Media\\Cars\\ShaderSettings\\Normal.xml, every car material's parameters; or a car
    zip's shadersettings.xml, its overrides): {material: {param: float or [r, g, b, a]}}."""
    out = {}
    if not path or not os.path.exists(path):
        return out
    import xml.etree.ElementTree as ET
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return out
    for m in root:
        d = {}
        for e in m:
            if e.get('value') is not None:
                d[e.tag] = float(e.get('value'))
            elif e.get('r') is not None:
                d[e.tag] = [float(e.get(k, 0)) for k in 'rgba']
        out[m.tag] = d
    return out


_GLOBAL_SETTINGS = {}


def car_settings(zdir):
    """The game's material parameters for one car: Media\\Cars\\ShaderSettings\\Normal.xml (copied to
    <car files>/../shadersettings/, game data) with the car's own shadersettings.xml over it."""
    if not _GLOBAL_SETTINGS and CAR_FILE_DIRS:
        _GLOBAL_SETTINGS.update(shader_settings(os.path.join(os.path.dirname(os.path.abspath(CAR_FILE_DIRS[0])),
                                                             'shadersettings', 'Normal.xml')) or {'': {}})
    merged = {k: dict(v) for k, v in _GLOBAL_SETTINGS.items()}
    for k, v in shader_settings(os.path.join(zdir, 'shadersettings.xml') if zdir else None).items():
        merged.setdefault(k, {}).update(v)
    return merged


GLASS_PARAMS = {'GlassColor': 'glass_color', 'GlassMaxOpacity': 'max_opacity', 'FresnelMin': 'fresnel_min',
                'FresnelMax': 'fresnel_max', 'FresnelScale': 'fresnel_scale', 'FresnelPower': 'fresnel_power',
                'CubeScale': 'cube_scale', 'SpecularAmount': 'spec_amount', 'SpecularPower': 'spec_power',
                'SpecularColor': 'spec_color'}
# The game's mirrors are render targets (what is behind): here a dark, opaque, reflective glass.
MIRROR_GLASS = {'glass_color': [0.01, 0.012, 0.015, 1.0], 'max_opacity': 1.0, 'fresnel_min': 0.3, 'fresnel_max': 1.0,
                'fresnel_power': 1.5, 'spec_amount': 0.0}


def glass_params(settings, mname):
    """The glass shader's parameters for a car material from the game's settings (only materials with a GlassColor),
    or the mirror stand-in; None otherwise."""
    if mname.startswith('mirror'):
        return dict(MIRROR_GLASS)
    g = settings.get(mname) or settings.get(mname[:-5] if mname.endswith('_lod0') else mname)
    if not g or 'GlassColor' not in g:
        return None
    return {GLASS_PARAMS[k]: v for k, v in g.items() if k in GLASS_PARAMS}


def cockpit_glass_params(settings, mname):
    """The glass shader's parameters for a cockpit mesh. The cockpit's own windows ('window', 'glass': the glass the
    driver looks through) take ShaderSettings' cockpit_glass, which has a specular highlight only (no GlassColor,
    Fresnel or opacity): clear glass with highlights. With the exterior window's settings (dark, alpha >= 0.4) the
    in-car view of the capture-free CrownJewel was ~60% of the game's brightness through the windscreen (sky 123 vs
    209, 2026-11-24)."""
    if ('cockpit_' + mname) in settings:
        return glass_params(settings, 'cockpit_' + mname)
    g = settings.get('cockpit_glass')
    if g is not None and (mname.startswith('window') or mname == 'glass'):
        p = {GLASS_PARAMS[k]: v for k, v in g.items() if k in GLASS_PARAMS}
        p.update(fresnel_min=0.0, fresnel_max=0.0, max_opacity=0.0, glass_color=[0.0, 0.0, 0.0, 0.0])
        return p
    return glass_params(settings, mname)


def gauge_ticks(path):
    """carattribs.xml's <Gauges>: {'speed' | 'tach' | 'fuel' | 'boost': [[param, value], ...]}; param 0..1 is the needle
    from its _min to its _max part, value in the game's units (speed m/s, tach rpm)."""
    out = {}
    if not os.path.exists(path):
        return out
    import xml.etree.ElementTree as ET
    g = ET.parse(path).getroot().find('Gauges')
    for e in (list(g) if g is not None else []):
        out[e.tag.lower()] = [[float(k.get('Param')), float(k.get('Value'))] for k in e.findall('TickMark')]
    return out


def steering_turn(P, seats):
    """The cockpit steering wheel's turn: pivot = the middle of its bounds, axis = the normal of its plane (the
    smallest spread of its vertices) pointing towards the nearer seat (the driver); turning right is clockwise seen from
    there, a negative angle about this axis. None without seats."""
    if len(P) < 8 or not seats:
        return None
    pivot = (P.min(0) + P.max(0)) / 2
    _, _, Vt = np.linalg.svd(P - P.mean(0), full_matrices=False)
    axis = Vt[2]
    seat = min((q.mean(0) for q in seats), key=lambda c: float(np.linalg.norm(c - pivot)))
    if float((seat - pivot) @ axis) < 0:
        axis = -axis
    return {'pivot': pivot.tolist(), 'axis': axis.tolist()}


def needle_turn(a, m, b):
    """A gauge needle's turn from its three poses (vertices of the _min, _mid, _max parts, same order): pivot, unit axis
    and the angles (radians) to _mid and _max about it; None when they are not one rigid rotation."""
    if not (len(a) == len(m) == len(b)) or len(a) < 3:
        return None

    def rigid(A, B):
        ca, cb = A.mean(0), B.mean(0)
        U, _, Vt = np.linalg.svd((A - ca).T @ (B - cb))
        Rm = Vt.T @ np.diag([1, 1, np.sign(np.linalg.det(Vt.T @ U.T))]) @ U.T
        return Rm, cb - Rm @ ca

    def axis_angle(Rm):
        ax = np.array([Rm[2, 1] - Rm[1, 2], Rm[0, 2] - Rm[2, 0], Rm[1, 0] - Rm[0, 1]])
        return ax / max(np.linalg.norm(ax), 1e-12), float(np.arccos(np.clip((np.trace(Rm) - 1) / 2, -1, 1)))
    R1, t1 = rigid(a, m)
    R2, _ = rigid(m, b)
    ax1, an1 = axis_angle(R1)
    ax2, an2 = axis_angle(R2)
    if abs(float(ax1 @ ax2)) < 0.99 or np.abs(a @ R1.T + t1 - m).max() > 1e-3:
        return None
    pivot = np.linalg.lstsq(np.eye(3) - R1, t1, rcond=None)[0]
    pivot += ax1 * float((a.mean(0) - pivot) @ ax1)  # (the point of the axis level with the needle, not the least-norm one)
    return {'pivot': pivot.tolist(), 'axis': ax1.tolist(), 'mid': an1, 'max': an1 + an2 * float(np.sign(ax1 @ ax2))}


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    src, out = sys.argv[1], sys.argv[2]
    texmap, lmmap, texmesh, capdir = {}, {}, {}, None
    if '--texmap' in sys.argv:
        capdir = sys.argv[sys.argv.index('--texmap') + 1]
        tm = json.load(open(os.path.join(capdir, 'track_materials.json')))
        texmap = {k: v for k, v in tm['materials'].items() if v['err'] < 0.02}
        lmmap = {k: v for k, v in tm['lightmaps'].items() if v.get('lm_err', 1) < 0.02}
        texmesh = {k: v for k, v in tm.get('meshes', {}).items() if v['err'] < 0.02}
    tex_out = os.path.splitext(out)[0] + '_tex'
    pv, by_model = None, {}
    F = np.diag([1.0, 1.0, -1.0])
    if '--pvs' in sys.argv:
        pv = fm3_pvs.parse(open(sys.argv[sys.argv.index('--pvs') + 1], 'rb').read())
        for i in pv['instances']:
            by_model.setdefault(i['model'], []).append(i)
    bix_cache = {}

    def bix_png(tid):
        # Decode _0x<tid>.bix (+ _B) to a PNG in tex_out; the file name, or None.
        if tid in bix_cache:
            return bix_cache[tid]
        name = None
        hp = os.path.join(src, '_0x%08X.bix' % tid)
        bp = os.path.join(src, '_0x%08X_B.bix' % tid)
        if os.path.exists(hp) and os.path.exists(bp):
            hdr = fm3_tex.bix_header(open(hp, 'rb').read(64))
            base = open(bp, 'rb').read()
            if hdr and len(base) >= hdr['base']:
                img = fm3_tex.decode(base[:hdr['base']], hdr['w'], hdr['h'], hdr['format'], hdr['endian'])
                if img is not None:
                    os.makedirs(tex_out, exist_ok=True)
                    name = 'bix_%05x.png' % tid
                    fr.write_png(os.path.join(tex_out, name), img.shape[1], img.shape[0], img.tobytes())
        if name is None and stx is not None and tid in stx['stream']:
            # textures without a .bix live only in the stx (77 on Ladera, some full size: the grass tufts' cards)
            img = fm3_tex.decode_stx(stx_data, stx, stx['stream'][tid])
            if img is not None:
                os.makedirs(tex_out, exist_ok=True)
                name = 'stx_%05x.png' % tid
                fr.write_png(os.path.join(tex_out, name), img.shape[1], img.shape[0], img.tobytes())
        bix_cache[tid] = name
        return name

    def red_alpha_png(png):
        # A copy of a decoded texture whose alpha is its red channel (road lines); the file name.
        key = ('red_alpha', png)
        if key not in bix_cache:
            src_ = os.path.join(tex_out, png)
            if not os.path.exists(src_) and capdir and os.path.exists(os.path.join(capdir, png)):
                src_ = os.path.join(capdir, png)  # (a capture texture, not copied yet)
            w_, h_, px_ = fir_frame.read_png(src_)
            a_ = np.frombuffer(bytes(px_), np.uint8).reshape(h_, w_, -1)
            rgba = np.empty((h_, w_, 4), np.uint8)
            rgba[:, :, :3] = a_[:, :, :3]
            rgba[:, :, 3] = a_[:, :, 0]
            name_ = 'ra_' + png
            fr.write_png(os.path.join(tex_out, name_), w_, h_, rgba.tobytes())
            bix_cache[key] = name_
        return bix_cache[key]

    stx_path = glob.glob(os.path.join(src, '*.stx.bin'))
    stx = fm3_tex.load_stx(stx_path[0]) if (pv is not None and stx_path) else None
    stx_data = open(stx_path[0], 'rb').read() if stx else None

    def atlas_png(piece_id):
        # The stx lightmap atlas holding a .pvs atlas entry, as a PNG in tex_out; the file name, or None.
        a = fm3_tex.stx_atlas_of(stx, piece_id) if stx else None
        if a is None:
            return None
        key = ('atlas', a)
        if key not in bix_cache:
            img = fm3_tex.decode_stx(stx_data, stx, stx['atlases'][a])
            name = None
            if img is not None:
                os.makedirs(tex_out, exist_ok=True)
                name = 'lmatlas_%05x.png' % a
                fr.write_png(os.path.join(tex_out, name), img.shape[1], img.shape[0], img.tobytes())
            bix_cache[key] = name
        return bix_cache[key]

    # Sky dome: FM3 centres it on the camera, lowered by SkyboxHeightOffset. Its vertices are written around the camera
    # (the height offset only), its nodes named 'skydome_...' at the camera (--camera-from's, else 0): the viewer keeps
    # them on its camera (world_view.gd), so the sky follows a flying or live camera on every track.
    sky_origin = np.zeros(3)
    sky_height = np.zeros(3)
    shadow_dir = None  # TrackSettings.xml ShadowLightDirection (game space): the sun of a capture-free scene
    if '--camera-from' in sys.argv:
        ref_ = json.load(open(sys.argv[sys.argv.index('--camera-from') + 1]))
        for n_ in ref_['nodes']:
            if 'camera' in n_ and 'matrix' in n_:
                sky_origin = np.array(n_['matrix'][12:15], float)
    if pv is not None:
        ts = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(sys.argv[sys.argv.index('--pvs') + 1]))),
                          'TrackSettings.xml')
        if os.path.exists(ts):
            ts_text = open(ts, errors='replace').read()
            mo = re.search(r'SkyboxHeightOffset value="([-0-9.]+)"', ts_text)
            if mo:
                sky_height = np.array([0.0, float(mo.group(1)), 0.0])
            mo = re.search(r'<ShadowLightDirection x="([-0-9.e]+)" y="([-0-9.e]+)" z="([-0-9.e]+)"', ts_text)
            if mo:
                shadow_dir = np.array([float(mo.group(k)) for k in (1, 2, 3)])
    sky_cam = sky_origin.copy()
    families_used = {}
    groups = {}
    nfiles = textured = lit = from_files = placed = 0
    for path in sorted(glob.glob(os.path.join(src, '*.rmb.bin'))):
        data = open(path, 'rb').read()
        model = fm3_track.parse(data)
        nfiles += 1
        is_sky = os.path.basename(path).endswith('out.sky.rmb.bin')
        if is_sky:
            # The sky dome: 16-byte vertices are position + u16 UV pair; FM3 centres it on the camera, lowered by the
            # track's SkyboxHeightOffset (TrackSettings.xml), and draws it unlit behind everything.
            for me_ in model['meshes']:
                raw_ = np.frombuffer(me_['raw'], np.uint8).reshape(-1, me_['stride'])
                me_['uv0'] = raw_[:, 12:16].copy().view('>u2').reshape(-1, 2) / 65535.0
                me_['normals'] = None
        file_tex, file_lm, mesh_tex, mesh_lm, mesh_mat = {}, None, {}, {}, {}
        mm = re.search(r'out\.(\d+)\.rmb', path)
        if pv is not None and mm and int(mm.group(1)) < len(pv['models']):
            mid = int(mm.group(1))
            entries = [pv['textures'][t] for t in pv['models'][mid]['textures'] if t < len(pv['textures'])]
            plain = [e['id'] for e in entries if e['rect'] == (1.0, 1.0, 0.0, 0.0)]
            atlas = [e for e in entries if e['rect'] != (1.0, 1.0, 0.0, 0.0)]
            shaders = [x.decode() for x in re.findall(rb'shaders\\track\\([a-z0-9_]+)', data)]
            counts = []
            for sh in shaders:
                mt = re.search(r'_(\d)(?:_|$)', sh)
                counts.append(int(mt.group(1)) if mt else 1)
            starts = np.cumsum([0] + counts[:-1]).tolist()
            order = []
            for me_ in model['meshes']:
                if me_['material'] not in order:
                    order.append(me_['material'])
            for k, mat_name in enumerate(order):
                if k < len(starts) and starts[k] < len(plain):
                    file_tex[mat_name] = (plain[starts[k]], shaders[k] if k < len(shaders) else '')
            if atlas:
                file_lm = atlas[0]
            # The file's own material table (fm3_track._parse_materials): slot 0 = base texture, slot 7 = lightmap,
            # both indices into this model's .pvs texture list; overrides the shader-block guess above.
            texl = pv['models'][mid]['textures']
            for me_ in model['meshes']:
                mats_ = model.get('materials')
                if not mats_ or me_.get('material_index', 99999) >= len(mats_):
                    continue
                mt_ = mats_[me_['material_index']]
                sl = mt_['slots']
                shn = shaders[mt_['shader']] if mt_['shader'] < len(shaders) else ''
                mesh_mat[me_['index_offset']] = (shn, mt_, texl)
                if sl and 0 <= sl[0] < len(texl):
                    mesh_tex[me_['index_offset']] = (pv['textures'][texl[sl[0]]]['id'], shn)
                if len(sl) > 7 and 0 <= sl[7] < len(texl):
                    mesh_lm[me_['index_offset']] = pv['textures'][texl[sl[7]]]
        if is_sky and pv is not None and model.get('materials'):
            # The sky dome's textures: its material slots 0..n-1 (one per sky mesh) are the last n of the .pvs texture
            # entries with flags 1, in id order (streamed from the .stx; no .pvs model lists them). Checked on
            # CrownJewel against the captured sky: sky1..4 = ids 3509 / 3510 / 3507 / 3508, mean |diff| 3.5-6 (sky5 the
            # zenith cap, sky6 the landscape below the horizon, both drawn too); AmalfiGP, Suzuka, NewYork and LeMans
            # have 5 such entries for 5 sky meshes.
            n_sky = len(model['materials'])
            ones = sorted(t['id'] for t in pv['textures'] if t['flags'] == 1)
            if len(ones) >= n_sky:
                for me_ in model['meshes']:
                    sl = model['materials'][me_['material_index']]['slots']
                    if sl and 0 <= sl[0] < n_sky:
                        mesh_tex[me_['index_offset']] = (ones[len(ones) - n_sky + sl[0]], 'sky_diff_1')
        # Placements: (3x3, translation, lightmap entry or None); world-space files once, as they are.
        places = [(np.eye(3), np.zeros(3), None)]
        if is_sky:
            places = [(np.eye(3), sky_height, None)]
        if pv is not None and mm and int(mm.group(1)) in by_model:
            places = []
            for ins in by_model[int(mm.group(1))]:
                e = pv['textures'][ins['lightmap']] if ins['lightmap'] < len(pv['textures']) else None
                places.append((F @ ins['rot'].T, F @ np.array(ins['pos']), e if (e and e['rect'][0] < 0.9) else None))
            placed += len(places)
        for me in model['meshes']:
            if me['indices'] is None:
                continue
            tris = np.array(fm3_track.triangles(me), dtype=np.int64)
            if not len(tris):
                continue
            P0 = me['positions']
            if not np.all(np.isfinite(P0)):
                continue
            name = me['material'] or 'unnamed'
            # (files without a material table, AmalfiGP's sea: the shader from the file's shader blocks, file_tex)
            shader_ = (mesh_mat.get(me['index_offset']) or ('',))[0] or (file_tex.get(name) or ('', ''))[1]
            if shader_.startswith('flare_') or (me['name'] or '').startswith('LGHT_'):
                continue  # sun flare (a camera-facing effect) and light volumes/cookies (no material): not drawn as is
            if shader_.startswith('tree_') and me['stride'] == 24:
                # tree card shaders read UV0 at byte 12 (where other layouts keep the normal): 12 of 13 captured draws
                me = dict(me, uv0=fm3_track.uv_pair(me, 12))
            if shader_.startswith('grass_') and me['stride'] == 20:
                # grass tuft cards: UV0 at byte 12 (0..1 across each card), the lightmap at 16
                u12 = fm3_track.uv_pair(me, 12)
                if np.ptp(u12[:, 0]) > 0.9 and np.ptp(u12[:, 1]) > 0.9:
                    me = dict(me, uv0=u12, uv1=fm3_track.uv_pair(me, 16))
            # Captured texture for this very mesh, else the game files' own, else a capture of the same material name.
            rec = texmesh.get(f"{os.path.basename(path)}@{me['index_offset']}")
            uv = apply_uv(rec['chan'], rec['a'], rec['b'], me) if rec else None
            base_png = rec['base'] if uv is not None else None
            ft = mesh_tex.get(me['index_offset']) or file_tex.get(name)
            if uv is None and ft and me.get('uv0') is not None:
                png = bix_png(ft[0])
                if png:
                    sh = ft[1]
                    # grass_* cards are soft decals (flat tuft shadows, upright tufts): alpha-blended; other opac: cut out
                    rec = {'factor': [1, 1, 1, 1], 'blend': 'BLEND' if sh.startswith('grass') else
                           ('MASK' if ('opac' in sh or 'tree' in sh) else False)}
                    if sh.startswith('rdline') and 'opac' in sh:
                        # Road lines (rdline_blnd_spec_opac_3, captured ps 94e08de1): the game blends the line over the
                        # asphalt by a mask texture (material slot 2, the line's own picture: its red channel = the
                        # line texture's grey, ~0.72 in the paint, 0 around it); the line texture's alpha is 255
                        # everywhere. Baked here as the line with alpha = its red channel, blended: cut out opaque,
                        # the CrownJewel grid boxes were 254 (clipped) where the game's are 188. Blended alone they
                        # stayed clipped (the game's line shader lights them less than a plain lightmapped surface), so
                        # a colour factor fitted on the live CrownJewel grid: 0.5 / 0.6 / 0.7 -> start-box line p95
                        # 134 / 159 / 185 (game 188), whole frame 20.3/20.0/18.4, 20.4/20.2/18.5, 20.7/20.4/18.7
                        # (opaque white: 21.2/21.0/19.3); 0.6 between the two measures.
                        png = red_alpha_png(png)
                        rec = {'factor': [0.6, 0.6, 0.6, 1], 'blend': 'BLEND'}
                    uv, base_png = me['uv0'].astype(np.float32), png
                    from_files += 1
            if uv is None and texmap.get(name):
                rec = texmap[name]
                uv = apply_uv(rec['chan'], rec['a'], rec['b'], me)
                base_png = rec['base'] if uv is not None else None
            if base_png and shader_.startswith('rdline') and 'opac' in shader_ and not base_png.startswith('ra_'):
                # (a captured road line too: the same line picture, blended and dimmed as above)
                base_png = red_alpha_png(base_png)
                rec = dict(rec, factor=[0.6, 0.6, 0.6, 1], blend='BLEND')
            # FM3 shader families (fm3_families.py): multi-texture terrain, road, paint, curbs, from the files; they replace
            # the capture's single (composited) texture too, so the area the frame saw looks like the rest of the track.
            fam, fam_ex = None, None
            if shader_.startswith(('lake_', 'ocean_')):
                # Animated reflective water (lake_anim_norm_opac_refl_5; the sea: ocean_anim_norm_refl_5, AmalfiGP, whose
                # base slot holds a small reflection snapshot, pale cyan as a texture): a dark glossy surface reflecting
                # the sky. (The sea's colour not fitted against the game yet.)
                rec = {'factor': [0.06, 0.09, 0.09, 0.92], 'blend': 'BLEND', 'roughness': 0.05, 'water': True}
                uv, base_png = None, None
            mm_ = None if shader_.startswith(('lake_', 'ocean_')) else mesh_mat.get(me['index_offset'])
            if mm_ is not None:
                r_ = fm3_families.recipe(mm_[0], mm_[1]['params'], me['stride'], mm_[1]['slots'])
                captured = texmesh.get(f"{os.path.basename(path)}@{me['index_offset']}") is not None
                if r_ is not None:  # (everywhere, captured or not: no seam where the captured frame's view ends)
                    texl_ = mm_[2]
                    pngs = [bix_png(pv['textures'][texl_[sl]]['id']) if 0 <= sl < len(texl_) else None for sl in r_['slots']]
                    if all(pngs):
                        def uv_src(o, me=me):
                            return me['positions'][:, [0, 2]] if o == 'xz' else fm3_track.uv_pair(me, o)
                        base_png, uv = pngs[0], uv_src(r_['src0']).astype(np.float32)
                        fam = dict(r_, tex=pngs, slots=None)
                        fam_ex = {'uv2': uv_src(r_['src1']).astype(np.float32),
                                  'uv3': (uv_src(r_['mask']) if r_['mask'] is not None else uv_src(r_['src1'])).astype(np.float32),
                                  'col': fm3_track.vertex_colour(me) if r_['vclr'] else None,
                                  'lmsrc': uv_src(r_['lm']) if r_['lm'] is not None else None}
                        rec = {'factor': [1, 1, 1, 1], 'blend': False}
                        families_used[r_['mode']] = families_used.get(r_['mode'], 0) + 1
            for M3, t, inst_lm in places:
                P = (P0 @ M3.T + t).astype(np.float32)
                luv = lm_png = None
                if len(places) == 1 and inst_lm is None:  # captured lightmap fits are per file mesh (world-space)
                    lmr = lmmap.get(f"{os.path.basename(path)}@{me['index_offset']}")
                    luv = apply_uv(lmr['lm_chan'], lmr['lm_a'], lmr['lm_b'], me) if (lmr and uv is not None) else None
                    lm_png = lmr['lightmap'] if luv is not None else None
                lm_e = inst_lm or mesh_lm.get(me['index_offset']) or file_lm
                ft_sh = (mesh_tex.get(me['index_offset']) or file_tex.get(name) or ('', ''))[1]
                if fam is not None:
                    luv = lm_png = None  # (captured lightmap fits are for the single-texture path)
                if luv is None and uv is not None and lm_e is not None and 'nolm' not in ft_sh and name != 'crowds':
                    src_uv = me.get('uv1') if me.get('uv1') is not None else me.get('uv0')
                    if fam_ex is not None and fam_ex['lmsrc'] is not None:
                        src_uv = fam_ex['lmsrc']
                    # An entry with its own .bix is a whole lightmap (rectangle unused); else a slot in an stx atlas.
                    own = bix_png(lm_e['id']) if src_uv is not None else None
                    png = own or (atlas_png(lm_e['id']) if src_uv is not None else None)
                    if own:
                        luv, lm_png = src_uv.astype(np.float32), own
                    elif png:
                        sx, sy, ox, oy = lm_e['rect']
                        luv, lm_png = (src_uv * np.array([sx, sy]) + np.array([ox, oy])).astype(np.float32), png
                key = (name + ('#sky' if is_sky else ''), base_png, lm_png, json.dumps(fam, sort_keys=True) if fam else None)
                textured += uv is not None
                lit += luv is not None
                ex = None
                if fam_ex is not None:
                    ex = dict(fam_ex)
                    if fam['src0'] == 'xz':  # world-space grain: the placed position
                        uv = P[:, [0, 2]].astype(np.float32)
                groups.setdefault(key, []).append((P, tris, uv, luv, rec if (uv is not None or (rec or {}).get('water')) else None, ex))

    bin_parts, views, accessors, meshes, nodes, materials, images, textures = [], [], [], [], [], [], [], []
    img_ids = {}
    offset = 0

    def add_view(data, target):
        nonlocal offset
        pad = (-len(data)) % 4
        bin_parts.append(data + b'\0' * pad)
        views.append({'buffer': 0, 'byteOffset': offset, 'byteLength': len(data), 'target': target})
        offset += len(data) + pad
        return len(views) - 1

    def image(png, sampler=0):
        # (sampler 1 = clamp to edge: the sky dome's panels; with repeat, filtering blended in the opposite edge: a light
        # seam line down the sky where two panels meet)
        if (png, sampler) not in img_ids:
            os.makedirs(tex_out, exist_ok=True)
            if capdir and os.path.exists(os.path.join(capdir, png)):  # (capture textures may change under the same name)
                shutil.copyfile(os.path.join(capdir, png), os.path.join(tex_out, png))
            images.append({'uri': os.path.basename(tex_out) + '/' + png})
            textures.append({'source': len(images) - 1, 'sampler': sampler})
            img_ids[(png, sampler)] = len(textures) - 1
        return img_ids[(png, sampler)]

    # The crowd (the layout's <track>_track_NN.crowd beside its .pvs, PLAN-CARS): header version, cell count, people
    # count (u32 BE); per cell 52 bytes: row start, end, middle (3 floats each), half length, 0, first person, count;
    # per person 16 bytes: u16 figure (low byte 0..14; +256 a second set), 6 zero bytes, the offset from its cell's
    # middle as three half floats, the facing angle as a half float (radians). CrownJewel Ribbon_04: 95 cells, 2627
    # people, every one within a few metres of its cell's row. Drawn as upright cards from the 'crowds' sprite sheet
    # (seven seated figures; the game draws 3D people near the camera and sprites past SpriteDistance): crowd_people.
    crowd_png = next((k[1] for k in groups if k[0] == 'crowds' and k[1]), None)
    crowd_file = None
    if '--pvs' in sys.argv:
        crowd_file = next(iter(glob.glob(os.path.join(os.path.dirname(os.path.abspath(sys.argv[sys.argv.index('--pvs') + 1])),
                                                       '*.crowd'))), None)
    # (not with --dynamic-from: a captured scene has the frame's own people)
    if crowd_file and crowd_png and '--no-crowd' not in sys.argv and '--dynamic-from' not in sys.argv:
        cd = open(crowd_file, 'rb').read()
        _ver, ncell, npeople = struct.unpack('>3I', cd[:12])
        mids = np.zeros((npeople, 3))
        for c in range(ncell):
            v = struct.unpack('>10f3I', cd[12 + 52 * c: 12 + 52 * c + 52])
            mids[v[11]:v[11] + v[12]] = v[6:9]
        R_ = np.frombuffer(cd[12 + 52 * ncell: 12 + 52 * ncell + 16 * npeople], np.uint8).reshape(-1, 16)
        fig = R_[:, 0:2].copy().view('>u2').ravel() & 0xFF
        pos = mids + R_[:, 8:14].copy().view('>f2').reshape(-1, 3).astype(np.float64)
        ang = R_[:, 14:16].copy().view('>f2').ravel().astype(np.float64)
        hw, ht = 0.37, 1.3  # (a seated figure: the sheet's cells are 73 x 128 px)
        right = np.stack([np.cos(ang), np.zeros_like(ang), -np.sin(ang)], 1)
        corners = []
        for sx, sy in ((-1, 0), (1, 0), (1, 1), (-1, 1)):
            corners.append(pos + right * (sx * hw) + np.array([0.0, sy * ht, 0.0]))
        # (no F: the cells lie where the track's own 'crowds' cards are in the glTF, z 96..472 on CrownJewel; with F
        # they landed on the far side of the complex)
        Pq = np.stack(corners, 1).reshape(-1, 3)
        col = fig % 7
        u0, u1 = col / 7.0, (col + 1) / 7.0
        Uq = np.stack([np.stack([u0, np.ones_like(u0)], 1), np.stack([u1, np.ones_like(u0)], 1),
                       np.stack([u1, np.zeros_like(u0)], 1), np.stack([u0, np.zeros_like(u0)], 1)], 1).reshape(-1, 2)
        b4 = np.arange(npeople) * 4
        Tq = np.concatenate([np.stack([b4, b4 + 1, b4 + 2], 1), np.stack([b4, b4 + 2, b4 + 3], 1)])
        groups.setdefault(('crowd_people', crowd_png, None, None), []).append(
            (Pq.astype(np.float32), Tq.astype(np.int64), Uq.astype(np.float32), None,
             {'factor': [1, 1, 1, 1], 'blend': 'MASK'}, None))
        print(f'crowd: {npeople} people in {ncell} cells from {os.path.basename(crowd_file)}')

    nv = nt = 0
    for (name, base, lm, famj), parts in sorted(groups.items(), key=lambda kv: str(kv[0])):
        P = np.concatenate([q[0] for q in parts])
        off, tl = 0, []
        for q in parts:
            tl.append(q[1] + off)
            off += len(q[0])
        T = np.concatenate(tl).astype(np.uint32)
        N = smooth_normals(P, T)
        rec = parts[0][4]
        pbr = {'baseColorFactor': (list(colour_for(name)) + [1.0]) if base is None else list(rec.get('factor', [1, 1, 1, 1])),
               'metallicFactor': 0.0, 'roughnessFactor': 1.0}
        sky = name.endswith('#sky')
        name = name.replace('#sky', '')
        mat = {'name': name, 'pbrMetallicRoughness': pbr, 'doubleSided': True}
        if rec and rec.get('water'):
            pbr.update(baseColorFactor=rec['factor'], roughnessFactor=rec['roughness'])
            mat['alphaMode'] = 'BLEND'
        if sky:
            mat['extensions'] = {'KHR_materials_unlit': {}}
            lm = None
        prim = {'attributes': {}}
        accessors.append({'bufferView': add_view(P.tobytes(), 34962), 'componentType': 5126, 'count': len(P), 'type': 'VEC3',
                          'min': P.min(0).tolist(), 'max': P.max(0).tolist()})
        prim['attributes']['POSITION'] = len(accessors) - 1
        accessors.append({'bufferView': add_view(N.tobytes(), 34962), 'componentType': 5126, 'count': len(N), 'type': 'VEC3'})
        prim['attributes']['NORMAL'] = len(accessors) - 1
        if base is not None:
            U = np.ascontiguousarray(np.concatenate([q[2] for q in parts]).astype(np.float32))
            accessors.append({'bufferView': add_view(U.tobytes(), 34962), 'componentType': 5126, 'count': len(U), 'type': 'VEC2'})
            prim['attributes']['TEXCOORD_0'] = len(accessors) - 1
            pbr['baseColorTexture'] = {'index': image(base, 1 if sky else 0)}
            blend = rec.get('blend')
            if blend in ('MASK', 'BLEND', True):
                mat['alphaMode'] = 'MASK' if blend == 'MASK' else 'BLEND'
                if mat['alphaMode'] == 'MASK':
                    mat['alphaCutoff'] = 0.5
        if lm is not None:
            L = np.ascontiguousarray(np.concatenate([q[3] for q in parts]).astype(np.float32))
            accessors.append({'bufferView': add_view(L.tobytes(), 34962), 'componentType': 5126, 'count': len(L), 'type': 'VEC2'})
            prim['attributes']['TEXCOORD_1'] = len(accessors) - 1
            mat['occlusionTexture'] = {'index': image(lm), 'texCoord': 1}
        if famj:
            fam = json.loads(famj)
            for attr, k in (('TEXCOORD_2', 'uv2'), ('TEXCOORD_3', 'uv3')):
                A = np.ascontiguousarray(np.concatenate([q[5][k] for q in parts]).astype(np.float32))
                accessors.append({'bufferView': add_view(A.tobytes(), 34962), 'componentType': 5126, 'count': len(A),
                                  'type': 'VEC2'})
                prim['attributes'][attr] = len(accessors) - 1
            if fam['vclr']:
                C = np.ascontiguousarray(np.concatenate([q[5]['col'] for q in parts]).astype(np.float32))
                accessors.append({'bufferView': add_view(C.tobytes(), 34962), 'componentType': 5126, 'count': len(C),
                                  'type': 'VEC4'})
                prim['attributes']['COLOR_0'] = len(accessors) - 1
            for png in fam['tex']:
                image(png)
            fam['tex'] = [os.path.basename(tex_out) + '/' + png for png in fam['tex']]
            mat['extras'] = {'fm3': fam}
        materials.append(mat)
        accessors.append({'bufferView': add_view(T.tobytes(), 34963), 'componentType': 5125, 'count': int(T.size), 'type': 'SCALAR'})
        prim['indices'] = len(accessors) - 1
        prim['material'] = len(materials) - 1
        meshes.append({'name': name, 'primitives': [prim]})
        if sky:
            nodes.append({'mesh': len(meshes) - 1, 'name': f'skydome_{name}__{len(meshes) - 1}', 'translation': sky_cam.tolist()})
        else:
            nodes.append({'mesh': len(meshes) - 1, 'name': f'{name}__{len(meshes) - 1}'})  # unique (Godot renames duplicates)
        nv += len(P)
        nt += len(T)
    if pv is not None:
        # the layout's static environment cube (window glass, car paint): envcube_0..5.png next to the textures
        cube_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[sys.argv.index('--pvs') + 1])),
                                 'staticcarcubemap.xpr')
        if not os.path.exists(cube_path):  # (most tracks keep one cube for all layouts, in the track's folder)
            cube_path = os.path.join(os.path.dirname(os.path.dirname(cube_path)), 'staticcarcubemap.xpr')
        faces = fm3_tex.load_xpr_cube(cube_path) if os.path.exists(cube_path) else None
        if faces:
            os.makedirs(tex_out, exist_ok=True)
            for k, img in enumerate(faces):
                img = img.copy()
                img[..., 3] = 255
                fr.write_png(os.path.join(tex_out, 'envcube_%d.png' % k), img.shape[1], img.shape[0], img.tobytes())
    if '--carbins' in sys.argv:
        CARBIN_DIRS.extend(sys.argv[sys.argv.index('--carbins') + 1].split(';'))
    if '--car-files' in sys.argv:
        CAR_FILE_DIRS.extend(sys.argv[sys.argv.index('--car-files') + 1].split(';'))
    if '--car-matrices' in sys.argv:
        for c in json.load(open(sys.argv[sys.argv.index('--car-matrices') + 1]))['cars']:
            CAR_MATRICES.append(np.array(c['matrix'], dtype=np.float64).reshape(4, 4))
            CAR_MATRIX_WHEELS.append([np.array(w, dtype=np.float64).reshape(4, 4) for w in c.get('wheels', [])])
    if '--wheel-files' in sys.argv:
        WHEEL_DIRS.extend(sys.argv[sys.argv.index('--wheel-files') + 1].split(';'))
    if '--dynamic-from' in sys.argv:
        ndyn = import_dynamic(sys.argv[sys.argv.index('--dynamic-from') + 1], capdir, src, add_view, accessors, materials,
                              images, textures, meshes, nodes, tex_out)
        print(f'dynamic objects from the capture (cars, people, crowd): {ndyn} nodes')
    print(f'meshes textured: {textured} ({from_files} from the game files), with lightmaps: {lit}; '
          f'props placed by .pvs instances: {placed}; shader families: {families_used}')

    gltf = {'asset': {'version': '2.0', 'generator': 'frame-ir fm3_track_export.py'}, 'scene': 0, 'nodes': nodes,
            'meshes': meshes, 'materials': materials, 'accessors': accessors, 'bufferViews': views}
    if any('extensions' in m for m in materials):
        gltf['extensionsUsed'] = ['KHR_materials_unlit']
    if images:
        gltf.update(images=images, textures=textures, samplers=[{'wrapS': 10497, 'wrapT': 10497}, {'wrapS': 33071, 'wrapT': 33071}])
    if '--camera-from' in sys.argv:
        ref = json.load(open(sys.argv[sys.argv.index('--camera-from') + 1]))
        for n in ref['nodes']:
            if 'camera' in n or n.get('name') == 'sun':
                nodes.append(dict(n))
        gltf['cameras'] = ref.get('cameras', [])
        if 'KHR_lights_punctual' in ref.get('extensions', {}):
            gltf['extensions'] = {'KHR_lights_punctual': ref['extensions']['KHR_lights_punctual']}
            gltf['extensionsUsed'] = gltf.get('extensionsUsed', []) + ['KHR_lights_punctual']
    else:
        # Capture-free (PLAN-CARS phase 5): a camera from --camera-at x,y,z:tx,ty,tz (glTF space), else above the middle
        # of the track's placed objects (the .pvs instances), looking down at it; the viewer needs one (--fly from it).
        eye = target = None
        if '--camera-at' in sys.argv:
            e_, t_ = sys.argv[sys.argv.index('--camera-at') + 1].split(':')
            eye, target = np.array([float(x) for x in e_.split(',')]), np.array([float(x) for x in t_.split(',')])
        else:
            # the middle of everything exported (the accessors' bounds), seen from above and to the side
            # (the median of the meshes' centres: the sky dome and the horizon planes span kilometres)
            c_ = np.array([(np.array(a_['min']) + np.array(a_['max'])) / 2 for a_ in accessors
                           if 'min' in a_ and len(a_['min']) == 3])
            target = np.median(c_, axis=0)
            spread = np.percentile(np.linalg.norm(c_ - target, axis=1), 60)
            eye = target + np.array([0.0, 0.5, 0.9]) * spread
        if eye is not None:
            fwd = target - eye
            fwd /= np.linalg.norm(fwd)
            right = np.cross(fwd, [0.0, 1.0, 0.0])
            right /= np.linalg.norm(right)
            up = np.cross(right, fwd)
            M_ = np.eye(4)
            M_[:3, 0], M_[:3, 1], M_[:3, 2], M_[:3, 3] = right, up, -fwd, eye
            gltf['cameras'] = [{'type': 'perspective', 'perspective': {'yfov': 0.9250, 'aspectRatio': 16 / 9,
                                                                       'znear': 0.3, 'zfar': 20000.0}}]
            nodes.append({'name': 'capture_camera', 'camera': 0, 'matrix': M_.T.ravel().tolist()})
            print(f'camera at {np.round(eye, 1).tolist()} looking at {np.round(target, 1).tolist()} (no capture)')
        if shadow_dir is not None and np.linalg.norm(shadow_dir) > 1e-6:
            # The sun from TrackSettings.xml's ShadowLightDirection (the direction the light travels, game space), as
            # fir_world.py writes the captured one: the node's +Z points at the sun, game -> glTF by F. CrownJewel's
            # (0.714145, -0.680362, -0.164636) is exactly the captured grid's sun; without it the viewer's default sun
            # lit the capture-free grid from the other side (the silver Mazda's back half as bright: 24.8 vs 45.8).
            z = np.diag([1.0, 1.0, -1.0]) @ (-shadow_dir / np.linalg.norm(shadow_dir))
            x = np.cross([0.0, 1.0, 0.0], z)
            x /= np.linalg.norm(x)
            y = np.cross(z, x)
            L = np.eye(4)
            L[:3, 0], L[:3, 1], L[:3, 2] = x, y, z
            nodes.append({'extensions': {'KHR_lights_punctual': {'light': 0}}, 'matrix': L.T.ravel().tolist(), 'name': 'sun'})
            gltf['extensions'] = {'KHR_lights_punctual': {'lights': [{'type': 'directional', 'color': [1.0, 0.95, 0.86],
                                                                       'intensity': 3.0, 'name': 'sun'}]}}
            gltf['extensionsUsed'] = gltf.get('extensionsUsed', []) + ['KHR_lights_punctual']
            print(f'sun from TrackSettings.xml: ShadowLightDirection {shadow_dir.tolist()}')
    gltf['scenes'] = [{'nodes': list(range(len(nodes)))}]
    blob = b''.join(bin_parts)
    gltf['buffers'] = [{'byteLength': len(blob), 'uri': os.path.basename(os.path.splitext(out)[0]) + '.bin'}]
    with open(os.path.splitext(out)[0] + '.bin', 'wb') as f:
        f.write(blob)
    with open(out, 'w') as f:
        json.dump(gltf, f)
    with open(os.path.splitext(out)[0] + '_needles.json', 'w', newline='\n') as f:
        json.dump(NEEDLES, f, indent=1)
    with open(os.path.splitext(out)[0] + '_carmaterials.json', 'w', newline='\n') as f:
        json.dump(CARMATS, f, indent=1)
    print(f'{nfiles} model files -> {len(meshes)} meshes, {nv} vertices, {nt} triangles, {len(blob) / 1e6:.0f} MB: {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
