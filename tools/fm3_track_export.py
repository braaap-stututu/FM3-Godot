#!/usr/bin/env python3
"""fm3_track_export.py: a whole FM3 track from its own files as glTF (geometry, per-material meshes), for the viewer.

    python fm3_track_export.py <extracted bin.zip dir> <out.gltf> [--camera-from world.gltf]

Track model files (.rmb.bin, tools/fm3_track.py) hold world-space vertices for the track itself (Ladera: all 1,914
files have an identity header matrix and their vertices are what the GPU draws). Meshes are merged per material name;
colours are stand-ins by name (textures: next step). --camera-from copies the camera and sun nodes from a
fir_world.py export, so the viewer starts at the captured view.
"""
import json
import glob
import math
import os
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


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    src, out = sys.argv[1], sys.argv[2]
    groups = {}
    nfiles = 0
    for path in sorted(glob.glob(os.path.join(src, '*.rmb.bin'))):
        data = open(path, 'rb').read()
        model = fm3_track.parse(data)
        nfiles += 1
        for me in model['meshes']:
            if me['indices'] is None:
                continue
            tris = np.array(fm3_track.strip_to_triangles(me['indices']), dtype=np.int64)
            if not len(tris):
                continue
            P = me['positions'].astype(np.float32)
            if not np.all(np.isfinite(P)):
                continue
            groups.setdefault(me['material'] or 'unnamed', []).append((P, tris))
    bin_parts, views, accessors, meshes, nodes, materials = [], [], [], [], [], []
    offset = 0

    def add_view(data, target):
        nonlocal offset
        pad = (-len(data)) % 4
        bin_parts.append(data + b'\0' * pad)
        views.append({'buffer': 0, 'byteOffset': offset, 'byteLength': len(data), 'target': target})
        offset += len(data) + pad
        return len(views) - 1

    nv = nt = 0
    for name, parts in sorted(groups.items()):
        P = np.concatenate([p for p, _ in parts])
        base, tl = 0, []
        for p, t in parts:
            tl.append(t + base)
            base += len(p)
        T = np.concatenate(tl).astype(np.uint32)
        N = smooth_normals(P, T)
        materials.append({'name': name, 'pbrMetallicRoughness': {'baseColorFactor': list(colour_for(name)) + [1.0],
                                                                 'metallicFactor': 0.0, 'roughnessFactor': 1.0}, 'doubleSided': True})
        accessors.append({'bufferView': add_view(P.tobytes(), 34962), 'componentType': 5126, 'count': len(P), 'type': 'VEC3',
                          'min': P.min(0).tolist(), 'max': P.max(0).tolist()})
        accessors.append({'bufferView': add_view(N.tobytes(), 34962), 'componentType': 5126, 'count': len(N), 'type': 'VEC3'})
        accessors.append({'bufferView': add_view(T.tobytes(), 34963), 'componentType': 5125, 'count': int(T.size), 'type': 'SCALAR'})
        meshes.append({'name': name, 'primitives': [{'attributes': {'POSITION': len(accessors) - 3, 'NORMAL': len(accessors) - 2},
                                                     'indices': len(accessors) - 1, 'material': len(materials) - 1}]})
        nodes.append({'mesh': len(meshes) - 1, 'name': name})
        nv += len(P)
        nt += len(T) // 3
    gltf = {'asset': {'version': '2.0', 'generator': 'frame-ir fm3_track_export.py'}, 'scene': 0, 'nodes': nodes,
            'meshes': meshes, 'materials': materials, 'accessors': accessors, 'bufferViews': views}
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
    print(f'{nfiles} model files -> {len(meshes)} materials, {nv} vertices, {nt} triangles, {len(blob) / 1e6:.0f} MB: {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
