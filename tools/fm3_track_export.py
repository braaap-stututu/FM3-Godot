#!/usr/bin/env python3
"""fm3_track_export.py: a whole FM3 track from its own files as glTF, for the viewer.

    python fm3_track_export.py <extracted bin.zip dir> <out.gltf> [--camera-from world.gltf] [--texmap capmap_dir]

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
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fm3_track  # noqa: E402
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


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    src, out = sys.argv[1], sys.argv[2]
    texmap, lmmap, capdir = {}, {}, None
    if '--texmap' in sys.argv:
        capdir = sys.argv[sys.argv.index('--texmap') + 1]
        tm = json.load(open(os.path.join(capdir, 'track_materials.json')))
        texmap = {k: v for k, v in tm['materials'].items() if v['err'] < 0.02}
        lmmap = {k: v for k, v in tm['lightmaps'].items() if v.get('lm_err', 1) < 0.02}
    tex_out = os.path.splitext(out)[0] + '_tex'

    groups = {}
    nfiles = textured = lit = 0
    for path in sorted(glob.glob(os.path.join(src, '*.rmb.bin'))):
        data = open(path, 'rb').read()
        model = fm3_track.parse(data)
        nfiles += 1
        for me in model['meshes']:
            if me['indices'] is None:
                continue
            tris = np.array(fm3_track.triangles(me), dtype=np.int64)
            if not len(tris):
                continue
            P = me['positions'].astype(np.float32)
            if not np.all(np.isfinite(P)):
                continue
            name = me['material'] or 'unnamed'
            rec = texmap.get(name)
            uv = apply_uv(rec['chan'], rec['a'], rec['b'], me) if rec else None
            lmr = lmmap.get(f"{os.path.basename(path)}@{me['index_offset']}")
            luv = apply_uv(lmr['lm_chan'], lmr['lm_a'], lmr['lm_b'], me) if (lmr and uv is not None) else None
            key = (name, rec['base'] if uv is not None else None, lmr['lightmap'] if luv is not None else None)
            textured += uv is not None
            lit += luv is not None
            groups.setdefault(key, []).append((P, tris, uv, luv, rec if uv is not None else None))

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

    def image(png):
        if png not in img_ids:
            os.makedirs(tex_out, exist_ok=True)
            shutil.copyfile(os.path.join(capdir, png), os.path.join(tex_out, png))
            images.append({'uri': os.path.basename(tex_out) + '/' + png})
            textures.append({'source': len(images) - 1, 'sampler': 0})
            img_ids[png] = len(textures) - 1
        return img_ids[png]

    nv = nt = 0
    for (name, base, lm), parts in sorted(groups.items(), key=lambda kv: str(kv[0])):
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
        mat = {'name': name, 'pbrMetallicRoughness': pbr, 'doubleSided': True}
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
            pbr['baseColorTexture'] = {'index': image(base)}
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
        materials.append(mat)
        accessors.append({'bufferView': add_view(T.tobytes(), 34963), 'componentType': 5125, 'count': int(T.size), 'type': 'SCALAR'})
        prim['indices'] = len(accessors) - 1
        prim['material'] = len(materials) - 1
        meshes.append({'name': name, 'primitives': [prim]})
        nodes.append({'mesh': len(meshes) - 1, 'name': name})
        nv += len(P)
        nt += len(T)
    print(f'meshes textured from the capture: {textured}, with lightmaps: {lit}')

    gltf = {'asset': {'version': '2.0', 'generator': 'frame-ir fm3_track_export.py'}, 'scene': 0, 'nodes': nodes,
            'meshes': meshes, 'materials': materials, 'accessors': accessors, 'bufferViews': views}
    if images:
        gltf.update(images=images, textures=textures, samplers=[{'wrapS': 10497, 'wrapT': 10497}])
    if '--camera-from' in sys.argv:
        ref = json.load(open(sys.argv[sys.argv.index('--camera-from') + 1]))
        for n in ref['nodes']:
            if 'camera' in n or n.get('name') == 'sun':
                nodes.append(dict(n))
        gltf['cameras'] = ref.get('cameras', [])
        if 'KHR_lights_punctual' in ref.get('extensions', {}):
            gltf['extensions'] = {'KHR_lights_punctual': ref['extensions']['KHR_lights_punctual']}
            gltf['extensionsUsed'] = ['KHR_lights_punctual']
    gltf['scenes'] = [{'nodes': list(range(len(nodes)))}]
    blob = b''.join(bin_parts)
    gltf['buffers'] = [{'byteLength': len(blob), 'uri': os.path.basename(os.path.splitext(out)[0]) + '.bin'}]
    with open(os.path.splitext(out)[0] + '.bin', 'wb') as f:
        f.write(blob)
    with open(out, 'w') as f:
        json.dump(gltf, f)
    print(f'{nfiles} model files -> {len(meshes)} meshes, {nv} vertices, {nt} triangles, {len(blob) / 1e6:.0f} MB: {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
