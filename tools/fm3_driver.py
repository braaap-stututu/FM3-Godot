r"""fm3_driver.py: the in-car driver's arms and hands as glTF (2026-11-27; PLAN-NEXT 3).

    python tools/fm3_driver.py <FM3-files\game\Media\Cars\Driver> <out dir> [--no-vflip]

Media\Cars\Driver\Driver.skinbin is the first-person driver (arms, hands, legs: 1,156 vertices, 13 bones; the game's
13-track animations sampled on the grid are this skeleton's): the crowd's 36-byte vertex layout (fm3_spectators.py)
behind a one-level header (words 1, 1, 1, 1, 1, index count, 1, 1, vertex count at 0x20, vertices at 0x24, then u32 1,
u32 index count, u16 indices). Its bones by their vertices: 5 = the left hand, 8 = the right hand (at the wheel, ~0.4 m
apart), 4 / 7 the forearms, 9-12 legs and feet. Written in the car library's raw car space handedness (x mirrored, as
the library's: the driver sits at +x like the cars' steering wheels; triangles reversed to keep them outside), in three
nodes: driver_arms, driver_hand_l, driver_hand_r (a triangle goes with the hand when its vertices are mostly that hand's
bone), plus driver.png (Driver.xds) and driver.json: the hands' midpoint and spacing, for the viewer to put them on the
car's steering wheel (world_view.gd _attach_driver; the Granny animations stay to do: Oodle1-compressed).
"""
import json
import os
import struct
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fir_read as fr  # noqa: E402
import fm3_spectators as sp  # noqa: E402
import fm3_tex  # noqa: E402

HAND_L, HAND_R = 5, 8


def main():
    src, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    d = open(os.path.join(src, 'Driver.skinbin'), 'rb').read()
    n = struct.unpack_from('>I', d, 0x20)[0]
    v = np.frombuffer(d[0x24:0x24 + n * 36], sp.VTX)
    o = 0x24 + n * 36
    ni = struct.unpack_from('>I', d, o + 4)[0]
    idx = np.frombuffer(d[o + 8:o + 8 + 2 * ni], '>u2').astype(np.uint32).reshape(-1, 3)
    P = v['p'].astype(np.float32) * np.array([-1, 1, 1], np.float32)
    N = v['n'].astype(np.float32) * np.array([-1, 1, 1], np.float32)
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)
    U = sp._uv(v['uv'])
    if '--no-vflip' not in sys.argv:
        # (v runs the other way than the crowd's: flipped, the hands get the gloves (black, light fingers, red logo) and
        # the in-car view against the game's 18.8 -> 18.0; unflipped they wore the suit's striped sleeves)
        U[:, 1] = 1.0 - U[:, 1]
    b = v['b'].astype(np.int32)
    w0, w1 = b[:, 2] / 255.0, b[:, 3] / 255.0
    hand = np.zeros(n, np.int32)
    for k, bone in ((1, HAND_L), (2, HAND_R)):
        w = np.where(b[:, 0] == bone, w0, 0.0) + np.where(b[:, 1] == bone, w1, 0.0)
        hand[w >= 0.5] = k
    tris = idx[:, ::-1]  # (mirrored: reversed winding)
    tri_hand = np.array([np.bincount(hand[t], minlength=3).argmax() for t in tris])
    parts = {'driver_arms': tris[tri_hand == 0], 'driver_hand_l': tris[tri_hand == 1], 'driver_hand_r': tris[tri_hand == 2]}
    img = fm3_tex.load_xds(os.path.join(src, 'Driver.xds'))
    fr.write_png(os.path.join(out, 'driver.png'), img.shape[1], img.shape[0], np.ascontiguousarray(img).tobytes())
    blob = bytearray()
    views, accs, meshes, nodes = [], [], [], []

    def view(bts, target):
        while len(blob) % 4:
            blob.append(0)
        views.append({'buffer': 0, 'byteOffset': len(blob), 'byteLength': len(bts), 'target': target})
        blob.extend(bts)
        return len(views) - 1

    a0 = 0
    accs.append({'bufferView': view(P.tobytes(), 34962), 'componentType': 5126, 'count': n, 'type': 'VEC3',
                 'min': P.min(0).tolist(), 'max': P.max(0).tolist()})
    accs.append({'bufferView': view(N.tobytes(), 34962), 'componentType': 5126, 'count': n, 'type': 'VEC3'})
    accs.append({'bufferView': view(U.astype(np.float32).tobytes(), 34962), 'componentType': 5126, 'count': n, 'type': 'VEC2'})
    for name, t in parts.items():
        accs.append({'bufferView': view(t.astype(np.uint32).tobytes(), 34963), 'componentType': 5125, 'count': int(t.size),
                     'type': 'SCALAR'})
        meshes.append({'name': name, 'primitives': [{'attributes': {'POSITION': a0, 'NORMAL': a0 + 1, 'TEXCOORD_0': a0 + 2},
                                                     'indices': len(accs) - 1, 'material': 0}]})
        nodes.append({'mesh': len(meshes) - 1, 'name': name})
    g = {'asset': {'version': '2.0', 'generator': 'fm3_driver.py'}, 'scene': 0, 'scenes': [{'nodes': list(range(len(nodes)))}],
         'nodes': nodes, 'meshes': meshes, 'accessors': accs, 'bufferViews': views,
         'materials': [{'name': 'driver', 'doubleSided': False, 'pbrMetallicRoughness': {'baseColorTexture': {'index': 0},
                                                                                         'metallicFactor': 0.0, 'roughnessFactor': 0.8}}],
         'textures': [{'source': 0}], 'images': [{'uri': 'driver.png'}],
         'buffers': [{'byteLength': len(blob), 'uri': 'driver.bin'}]}
    open(os.path.join(out, 'driver.bin'), 'wb').write(bytes(blob))
    open(os.path.join(out, 'driver.gltf'), 'w', newline='\n').write(json.dumps(g))
    hl = P[hand == 1].mean(0)
    hr = P[hand == 2].mean(0)
    info = {'hand_l': hl.tolist(), 'hand_r': hr.tolist(), 'mid': ((hl + hr) / 2).tolist(),
            'spacing': float(np.linalg.norm(hl - hr)), 'triangles': {k: int(len(t)) for k, t in parts.items()}}
    open(os.path.join(out, 'driver.json'), 'w', newline='\n').write(json.dumps(info, indent=1))
    print(json.dumps(info))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
