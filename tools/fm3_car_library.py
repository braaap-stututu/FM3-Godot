"""fm3_car_library.py: every car as its own glTF from the game's files, no capture (PLAN-CARS phase 5 / LIVE.md stage A
item 5: cars attached by the stream's identity, on any track).

    python tools/fm3_car_library.py <car files dir> <wheel files dir> <gamedb.slt> <out dir> [car ...]

<car files dir>/<car>/ = the car zip's contents (fm3_track_export.py --car-files), <wheel files dir>/<car>/ = its
stock wheel zip (--wheel-files). Writes per car <out>/<car>.gltf (+ .bin, <car>_tex/):
  - body: <car>_lod0.carbin, the main file's LOD 1 for the parts LOD 0 lacks (its 'race' / damage variants left out as
    in build_cars), in RAW car space (the viewer places the car's node with its streamed matrix: world = F (p M));
    nodes carbin_<car>_<material>_<n> as the grid export names them;
  - cockpit: cockpit_<car>_cockpit_<material>[-<part>]_<n> (needles and the steering wheel as their own nodes);
  - wheels: wheel_<car>_<k>_<material>_<n> in WHEEL space (k = 0 LF, 1 RF, 2 RR, 3 LR; the right side mirrored), rotors
    brake_<car>_<k>_rotor_<material>_<n>; the viewer places them with the streamed wheel matrices;
  - materials: the car zip's .xds textures (nodamage / lights / interior), car_materials.json's flat ones, and the paint:
    nodamage_lod0 x the colour (white here: the viewer sets the database colour from FM3N), with a metallic-roughness
    texture so the viewer gives it the paint shader;
  - <car>_colors.json: the database's Combo_Colors for the car {Sequence: [r, g, b, metallic]} (sRGB 0..1),
    <car>_carmaterials.json (glass parameters by node), <car>_needles.json (needle / steering turns, car space).
"""
import json
import os
import re
import sqlite3
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fir_read as fr  # noqa: E402
import fm3_car  # noqa: E402
import fm3_carbin  # noqa: E402
import fm3_tex  # noqa: E402
import fm3_track_export as tx  # noqa: E402
from fir_world import smooth_normals  # noqa: E402

# the lights texture's materials: the lamps and the reflectors (the CR-X's 'reflector' is the red CR-X VTEC panel between its
# tail lights, on lights_lod0; from nodamage it came out white)
LAMPS = tx.LAMP_MATERIALS


class Gltf:
    def __init__(self, tex_dir):
        self.nodes, self.meshes, self.materials, self.accessors, self.views = [], [], [], [], []
        self.images, self.textures, self.parts, self.offset = [], [], [], 0
        self.tex_dir = tex_dir
        self.tex_ids, self.mat_ids = {}, {}

    def view(self, data, target):
        pad = (-len(data)) % 4
        self.parts.append(data + b'\0' * pad)
        self.views.append({'buffer': 0, 'byteOffset': self.offset, 'byteLength': len(data), 'target': target})
        self.offset += len(data) + pad
        return len(self.views) - 1

    def acc(self, arr, kind, target=34962, minmax=False):
        a = {'bufferView': self.view(np.ascontiguousarray(arr).tobytes(), target),
             'componentType': 5125 if arr.dtype == np.uint32 else 5126, 'count': int(len(arr) if kind != 'SCALAR' else arr.size),
             'type': kind}
        if minmax:
            a.update(min=arr.min(0).tolist(), max=arr.max(0).tolist())
        self.accessors.append(a)
        return len(self.accessors) - 1

    def texture(self, img, name):
        if name not in self.tex_ids:
            os.makedirs(self.tex_dir, exist_ok=True)
            fr.write_png(os.path.join(self.tex_dir, name), img.shape[1], img.shape[0], np.ascontiguousarray(img).tobytes())
            self.images.append({'uri': os.path.basename(self.tex_dir) + '/' + name})
            self.textures.append({'source': len(self.images) - 1, 'sampler': 0})
            self.tex_ids[name] = len(self.textures) - 1
        return self.tex_ids[name]

    def material(self, key, mat):
        if key not in self.mat_ids:
            self.materials.append(mat)
            self.mat_ids[key] = len(self.materials) - 1
        return self.mat_ids[key]

    def mesh(self, node_name, P, T, U, N, lit, mat, flip=False):
        if not len(T):
            return
        # Raw car space, the file's winding (counter-clockwise = outside: its normals agree with the rebuilt ones on
        # 99.8% of the Mazda's paint vertices); flip reverses the triangles where the caller mirrored the vertices (the
        # right-side wheels). The viewer places the meshes with the streamed matrices as they are, mirrored or not
        # (Godot culls a mirrored node's faces itself). (Until 2026-11-24 the glTF mirror F was baked in here, triangles
        # reversed, and the viewer added x F to the matrix: the grid's car matrices are proper rotations, so the nodes
        # came out mirrored over reversed triangles and Godot drew the cars' back faces: a dark band across the Mazda's
        # trunk, its paint 41 against the captured copy's 55; the rest of the gap was the viewer's colour, world_view.gd
        # _vec4.)
        if flip:
            T = T[:, ::-1]
        P = P.astype(np.float32)
        prim = {'attributes': {'POSITION': self.acc(P, 'VEC3', minmax=True)}, 'material': mat}
        if N is None:
            N = smooth_normals(P, T)
        else:
            # (the file's 11:11:10 normals are not unit length: shorter ones lit the library cars too darkly)
            N = N / np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)
        prim['attributes']['NORMAL'] = self.acc(N.astype(np.float32), 'VEC3')
        prim['attributes']['TEXCOORD_0'] = self.acc(U.astype(np.float32), 'VEC2')
        if lit is not None:
            lit = lit.astype(np.float32)
            prim['attributes']['COLOR_0'] = self.acc(np.stack([lit, lit, lit, np.ones_like(lit)], axis=1), 'VEC4')
        prim['indices'] = self.acc(T.astype(np.uint32).ravel(), 'SCALAR', 34963)
        self.meshes.append({'name': node_name, 'primitives': [prim]})
        self.nodes.append({'mesh': len(self.meshes) - 1, 'name': f'{node_name}_{len(self.meshes) - 1}'})

    def write(self, out):
        blob = b''.join(self.parts)
        g = {'asset': {'version': '2.0', 'generator': 'fm3_car_library.py'}, 'scene': 0,
             'scenes': [{'nodes': list(range(len(self.nodes)))}], 'nodes': self.nodes, 'meshes': self.meshes,
             'materials': self.materials, 'accessors': self.accessors, 'bufferViews': self.views,
             'buffers': [{'byteLength': len(blob), 'uri': os.path.basename(os.path.splitext(out)[0]) + '.bin'}]}
        if self.images:
            g.update(images=self.images, textures=self.textures, samplers=[{'wrapS': 10497, 'wrapT': 10497}])
        with open(os.path.splitext(out)[0] + '.bin', 'wb') as f:
            f.write(blob)
        with open(out, 'w') as f:
            json.dump(g, f)


def car_colors(db, media):
    """{Sequence: [r, g, b, metallic]} for a car (Data_Car.MediaName, any case) from Combo_Colors."""
    if not db or not os.path.exists(db):
        return {}
    c = sqlite3.connect('file:' + db + '?mode=ro', uri=True)
    row = c.execute('select Id from Data_Car where lower(MediaName) = lower(?)', (media,)).fetchone()
    if not row:
        return {}
    out = {}
    for seq, rgb, met in c.execute('select Sequence, RGB, Metallic from Combo_Colors where Ordinal = ? order by Sequence', (row[0],)):
        out[int(seq)] = [((rgb >> 16) & 255) / 255.0, ((rgb >> 8) & 255) / 255.0, (rgb & 255) / 255.0, int(met)]
    return out


def build(car, cdir, wdir, db, outdir):
    zdir = os.path.join(cdir, car)
    lod0 = os.path.join(zdir, car + '_lod0.carbin')
    if not os.path.exists(lod0):
        return f'{car}: no {car}_lod0.carbin'
    g = Gltf(os.path.join(outdir, car + '_tex'))
    xds_cache = {}

    def xds_mat(stem, mname, cutout=False, opaque=False):
        key = ('xds', stem, mname, cutout, opaque)
        if key in g.mat_ids:
            return g.mat_ids[key]
        if stem not in xds_cache:
            p = os.path.join(zdir, stem + '.xds')
            xds_cache[stem] = fm3_tex.load_xds(p) if os.path.exists(p) else None
        img = xds_cache[stem]
        if img is None:
            return flat_mat('black')
        if opaque:
            img = img.copy()
            img[..., 3] = 255
        ti = g.texture(img, f'{stem}{"_rgb" if opaque else ""}.png')
        return g.material(key, {'name': f'{mname}_{stem}', 'doubleSided': True, 'pbrMetallicRoughness': {
            'baseColorTexture': {'index': ti}, 'metallicFactor': 0.0, 'roughnessFactor': 0.6},
            **({'alphaMode': 'MASK', 'alphaCutoff': 0.5} if cutout else {})})

    def flat_mat(name):
        r_ = tx.CAR_FLAT.get(name, tx.CAR_FLAT['black'])
        mat = {'name': name, 'doubleSided': True, 'pbrMetallicRoughness': {
            'baseColorFactor': list(r_.get('color', [0.5, 0.5, 0.5])) + [float(r_.get('alpha', 1.0))],
            'metallicFactor': r_.get('metallic', 0.0), 'roughnessFactor': r_.get('roughness', 1.0)}}
        if r_.get('alpha', 1.0) < 1.0:
            mat['alphaMode'] = 'BLEND'
        return g.material(('flat', name), mat)

    def paint_mat():
        if ('paint',) in g.mat_ids:
            return g.mat_ids[('paint',)]
        p = os.path.join(zdir, 'nodamage_lod0.xds')
        img = fm3_tex.load_xds(p) if os.path.exists(p) else np.full((4, 4, 4), 255, np.uint8)
        # The zip's nodamage is the livery / badge layer over the paint (its alpha; 0 over plain paint). Godot zeroes
        # the colour of fully transparent pixels on loading, which made the library paint black: composited over white
        # here, alpha 255, so the viewer's paint colour x this = the colour on plain paint, the badges over it.
        a_ = img[..., 3:4].astype(np.float32) / 255.0
        over = np.concatenate([np.clip(img[..., :3] * a_ + 255.0 * (1.0 - a_), 0, 255).astype(np.uint8),
                               np.full(img.shape[:2] + (1,), 255, np.uint8)], axis=2)
        ti = g.texture(over, 'paint_over_white.png')
        # (the metallic-roughness texture only marks it as paint for the viewer, as fir_world.py's paint does)
        return g.material(('paint',), {'name': 'paint', 'doubleSided': True, 'pbrMetallicRoughness': {
            'baseColorTexture': {'index': ti}, 'metallicRoughnessTexture': {'index': ti}, 'baseColorFactor': [1, 1, 1, 1],
            'metallicFactor': 0.0, 'roughnessFactor': 1.0}})

    def material_for(mname, lod, cockpit=False, outside=False):
        if mname in ('body', 'body_2'):
            return paint_mat()
        if mname.startswith('mirror'):
            return flat_mat('window')
        if mname in tx.CAR_FLAT and not tx.CAR_FLAT[mname].get('keep'):
            return flat_mat(mname)
        if cockpit:
            return xds_mat('nodamage_lod0' if outside else 'interior_lod0', 'cockpit_' + mname,
                           cutout=mname in ('emblem', 'badge'), opaque='gauge' in mname)
        lamp = mname.startswith(LAMPS)
        return xds_mat(('lights' if lamp else 'nodamage') + ('_lod0' if lod == 0 else ''), mname,
                       cutout=mname in ('emblem', 'badge'))

    def lit_of(sec, mname):
        if sec.get('light') is None or mname.startswith(tx.LAMP_MATERIALS) or mname.startswith('gauge'):
            return None
        return np.clip(sec['light'] / 107.0, 0.0, 1.0) ** 2.2

    def add(prefix, sec, P, Nf, mname, mat, lit, flip=False):
        for sub in sec['subs']:
            if sub['material'] != mname and not (sub['material'].endswith('_lod0') and sub['material'][:-5] == mname):
                continue
            tris = fm3_car.triangles(sub['indices'], sub['prim'], restart=sub.get('restart', 0xFFFF))
            if len(tris) and tris.max() < len(P):
                g.mesh(prefix, P, tris, sec['uv0'], Nf, lit, mat, flip)

    settings = tx.car_settings(zdir)
    carmats, needles = {}, {}
    # body: LOD 0 + main LOD 1 for parts LOD 0 lacks; parts as build_cars keeps them (stock: the 'a' variants and
    # unlettered parts; 'race' / lettered alternates left out)
    l0 = fm3_carbin.sections(fm3_carbin.parse(open(lod0, 'rb').read()), 0)
    main = os.path.join(zdir, car + '.carbin')
    have = {s['name'] for s in l0}
    l1 = []
    if os.path.exists(main):
        l1 = [s for s in fm3_carbin.sections(fm3_carbin.parse(open(main, 'rb').read()), 1) if s['name'] not in have]
    for s in l0:
        s['lod'] = 0
    for s in l1:
        s['lod'] = 1

    def stock(name):
        m = re.match(r'^(.*?)([a-g]|race)$', name)
        return m is None or m.group(2) == 'a'
    nb = 0
    for sec in l0 + l1:
        if sec['name'] == 'wheel' or not stock(sec['name']):
            continue
        P = sec['local'] + sec['offset']
        for mname in sorted({(u['material'][:-5] if u['material'].endswith('_lod0') else u['material']) for u in sec['subs']}):
            node = f'carbin_{car}_{mname}'
            add(node, sec, P, sec.get('normal'), mname, material_for(mname, sec['lod']), lit_of(sec, mname))
            gp = tx.glass_params(settings, mname)
            if gp is not None:
                carmats[f'{node}_{len(g.meshes) - 1}'] = gp
            nb += 1
    # cockpit
    ck = os.path.join(zdir, car + '_cockpit.carbin')
    if os.path.exists(ck):
        csecs = fm3_carbin.sections(fm3_carbin.parse(open(ck, 'rb').read()), 0)
        byname = {s['name']: s for s in csecs}
        ticks = tx.gauge_ticks(os.path.join(zdir, 'carattribs.xml'))
        turns = tx.car_attrib(os.path.join(zdir, 'carattribs.xml'), 'SteeringWheelAngleOverride')
        for sec in csecs:
            if sec['name'].endswith(('race', '_mid', '_max')):
                continue
            P = sec['local'] + sec['offset']
            needle = None
            if sec['name'] == 'steering_wheel':
                needle = tx.steering_turn(P, [q['local'] + q['offset'] for q in csecs if q['name'] in ('seatL', 'seatR')])
                if needle is not None:
                    needle.update(gauge='steering', car=car)
                    if turns:
                        needle['game_deg'] = 360.0 * turns
            elif sec['name'].endswith('_min'):
                gname = sec['name'][:-4]
                mid, mx = byname.get(gname + '_mid'), byname.get(gname + '_max')
                if mid is not None and mx is not None:
                    needle = tx.needle_turn(P, mid['local'] + mid['offset'], mx['local'] + mx['offset'])
                    if needle is not None:
                        needle.update(gauge=gname, car=car, ticks=ticks.get(gname, []))
            outside = sec['name'] in ('a_pillar', 'hooda', 'mirrorL', 'mirrorR')
            for mname in sorted({u['material'] for u in sec['subs']}):
                if mname == 'glass' and sec['name'] == 'interior':
                    continue
                node = f'cockpit_{car}_cockpit_{mname}' + (f'-{sec["name"]}' if needle is not None else '')
                lit = None if mname.startswith('gauge') else lit_of(sec, mname)
                add(node, sec, P, sec.get('normal'), mname, material_for(mname, 0, cockpit=True, outside=outside), lit)
                full = f'{node}_{len(g.meshes) - 1}'
                if needle is not None:
                    needles[full] = needle
                gp = tx.glass_params(settings, ('cockpit_' + mname) if ('cockpit_' + mname) in settings else mname)
                if gp is not None:
                    carmats[full] = gp
    # wheels (wheel space) and rotors
    wpath = None
    for root_, _, files in os.walk(os.path.join(wdir, car)) if wdir else []:
        for f_ in files:
            if f_.lower() == car + '.carbin':
                wpath = os.path.join(root_, f_)
    nw = 0
    if wpath:
        wtex = os.path.dirname(wpath)
        w = fm3_carbin.parse(open(wpath, 'rb').read())
        wsecs = [(s, False) for s in fm3_carbin.sections(w, 0)]
        wsecs += [(dict(s, subs=[u for u in s['subs'] if u['material'] in ('tire', 'tread', 'sidewall')]), True)
                  for s in fm3_carbin.sections(w, 1)]
        wimg = {}

        def wheel_mat(mname):
            if mname in ('tire', 'tread', 'sidewall'):
                return flat_mat('tire')
            stem = 'wheel0_lod0' if 'blur' in mname else 'wheel_lod0'
            key = ('wheel', stem, mname)
            if key not in g.mat_ids:
                if stem not in wimg:
                    p = os.path.join(wtex, stem + '.xds')
                    wimg[stem] = fm3_tex.load_xds(p) if os.path.exists(p) else None
                if wimg[stem] is None:
                    return flat_mat('black')
                ti = g.texture(wimg[stem], f'wheel_{stem}.png')
                g.material(key, {'name': f'wheel_{mname}_{stem}', 'doubleSided': True, 'pbrMetallicRoughness': {
                    'baseColorTexture': {'index': ti}, 'metallicFactor': 0.0, 'roughnessFactor': 0.6},
                    **({'alphaMode': 'MASK', 'alphaCutoff': 0.5} if 'blur' in mname else {})})
            return g.mat_ids[key]
        corner = ['lf', 'rf', 'rr', 'lr']
        for k in range(4):
            side = np.diag([-1.0, 1.0, 1.0]) if k in (1, 2) else np.eye(3)
            for sec, _ in wsecs:
                P = (sec['local'] + sec['offset']) @ side
                Nf = None if sec.get('normal') is None else sec['normal'] @ side
                lit = None if sec.get('light') is None else np.clip(sec['light'] / 107.0, 0.0, 1.0) ** 2.2
                for mname in sorted({u['material'] for u in sec['subs']}):
                    add(f'wheel_{car}_{k}_{mname}', sec, P, Nf, mname, wheel_mat(mname), lit, flip=k in (1, 2))
                    nw += 1
            rp = os.path.join(zdir, f'{car}_rotor{corner[k]}.carbin')
            if os.path.exists(rp):
                b = fm3_carbin.parse(open(rp, 'rb').read())
                for sec in fm3_carbin.sections(b, 0) or fm3_carbin.sections(b, 1):
                    P = sec['local'] + sec['offset']
                    for mname in sorted({u['material'] for u in sec['subs']}):
                        add(f'brake_{car}_{k}_rotor_{mname}', sec, P, sec.get('normal'), mname,
                            flat_mat(mname if mname in tx.CAR_FLAT else 'black'), None)
    out = os.path.join(outdir, car + '.gltf')
    g.write(out)
    for suffix, data in (('_colors.json', car_colors(db, car)), ('_carmaterials.json', carmats), ('_needles.json', needles)):
        with open(os.path.join(outdir, car + suffix), 'w', newline='\n') as f:
            json.dump(data, f, indent=1)
    return f'{car}: {len(g.meshes)} meshes ({nb} body groups, {nw} wheel groups), {len(needles)} needles, ' \
           f'{len(car_colors(db, car))} colours -> {out}'


def main():
    a = sys.argv[1:]
    if len(a) < 4:
        print(__doc__)
        return 2
    cdir, wdir, db, outdir = a[:4]
    tx.CAR_FILE_DIRS[:] = [cdir]
    os.makedirs(outdir, exist_ok=True)
    cars = a[4:] or sorted(d for d in os.listdir(cdir) if os.path.isdir(os.path.join(cdir, d)))
    for car in cars:
        print(build(car, cdir, wdir, db, outdir))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
