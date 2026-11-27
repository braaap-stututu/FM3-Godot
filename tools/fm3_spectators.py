r"""FM3's 3D spectators as glTF (2026-11-26): Media\Spectators\models\<Name>_{Sit,Stand}.skinbin with their textures
(spectators.xml: two per model). Static, in the models' own pose (Sit models are seated, Stand ones standing): the
animations (anims\*.anim.bin, QUAT_BITSTREAM) are not decoded yet (PLAN-NEXT.md 2).

    python tools/fm3_spectators.py <FM3-files\game\Media\Spectators> <out dir> [--row]

Writes <out>/<Name>_<Pose>_<k>.gltf (+ .bin, textures <Name>_<k>.png) for every model, pose and texture, the finest
level of detail only, and spectators.json (figure index -> file names, in spectators.xml's model order, which the
.crowd files' figure numbers index). --row also writes all_sit.gltf: every seated variant in a row (a quick look).

.skinbin (big-endian): words (1, 7) (1, 7) (1, first count), 7 (start, count) u16 pairs = the levels of detail over one
index list, at 0x50 the vertex count, at 0x54 the vertices (36 bytes: u32 1, position 3 x f32, normal 3 x f32, uv
2 x u16 (uv = u / 65536), bone 0, bone 1, weight 0, weight 1 as u8), then u32 1, u32 index count, u16 indices.
"""
import base64
import json
import os
import re
import struct
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fm3_tex  # noqa: E402
import fir_read as fr  # noqa: E402

VTX = np.dtype([('tag', '>u4'), ('p', '>f4', 3), ('n', '>f4', 3), ('uv', '>i2', 2), ('b', 'u1', 4)])


def _uv(raw):
    """uv from the 16-bit pair read as unsigned: u = raw / 65536 (checked on all 14 seated figures: faces, shirts and shoes
    in place; FM3_SPEC_UV=<mode> for tests: 0 signed + 0.5, 1 the same v flipped, 2 wrapped, 4 unsigned v flipped)."""
    mode = int(os.environ.get('FM3_SPEC_UV', '3'))
    uv = raw.astype(np.float32) / 65536.0 + 0.5
    if mode == 1:
        uv[:, 1] = 1.0 - uv[:, 1]
    if mode == 2:
        uv = (raw.astype(np.float32) / 32768.0) % 1.0
    if mode in (3, 4):
        uv = raw.astype(np.int32).astype(np.uint16).astype(np.float32) / 65536.0  # (as unsigned)
        if mode == 4:
            uv[:, 1] = 1.0 - uv[:, 1]
    return uv


def read_skinbin(path, lod=0):
    d = open(path, 'rb').read()
    first = struct.unpack_from('>I', d, 20)[0]
    lods = [(0, first)] + [struct.unpack_from('>HH', d, 28 + 8 * i) for i in range(6)]
    n = struct.unpack_from('>I', d, 0x50)[0]
    v = np.frombuffer(d[0x54:0x54 + n * 36], VTX)
    o = 0x54 + n * 36
    ni = struct.unpack_from('>I', d, o + 4)[0]
    idx = np.frombuffer(d[o + 8:o + 8 + 2 * ni], '>u2').astype(np.uint32)
    s, c = lods[lod]
    tri = idx[s:s + c]
    return {'pos': v['p'].astype(np.float32), 'nrm': v['n'].astype(np.float32),
            'uv': _uv(v['uv']), 'idx': tri, 'lods': lods,
            # (skinning, as TEXCOORD_1: x = bone 0 + weight 0 / 2, y = bone 1 (weight 1 = 1 - weight 0: the two sum to 255):
            # the viewer's crowd shader animates with the game's baked animations, tools/fm3_crowd_anim.py)
            'skin': np.stack([v['b'][:, 0].astype(np.float32) + v['b'][:, 2].astype(np.float32) / 255.0 * 0.5,
                              v['b'][:, 1].astype(np.float32)], axis=1)}


def write_gltf(path, meshes, png_names):
    """meshes: [(mesh dict, texture index, translation)] -> one glTF with one node per mesh."""
    blob = bytearray()
    views, accs, gmeshes, nodes, mats = [], [], [], [], []

    def view(b, target):
        while len(blob) % 4:
            blob.append(0)
        views.append({'buffer': 0, 'byteOffset': len(blob), 'byteLength': len(b), 'target': target})
        blob.extend(b)
        return len(views) - 1

    for k, png in enumerate(png_names):
        mats.append({'name': 'spectator_%d' % k, 'pbrMetallicRoughness': {'baseColorTexture': {'index': k},
                     'metallicFactor': 0.0, 'roughnessFactor': 1.0}, 'doubleSided': True})
    for m, tex, at in meshes:
        P, N, U, I = m['pos'], m['nrm'], m['uv'], m['idx']
        a0 = len(accs)
        accs.append({'bufferView': view(P.tobytes(), 34962), 'componentType': 5126, 'count': len(P), 'type': 'VEC3',
                     'min': P.min(0).tolist(), 'max': P.max(0).tolist()})
        accs.append({'bufferView': view(N.tobytes(), 34962), 'componentType': 5126, 'count': len(N), 'type': 'VEC3'})
        accs.append({'bufferView': view(U.tobytes(), 34962), 'componentType': 5126, 'count': len(U), 'type': 'VEC2'})
        accs.append({'bufferView': view(I.astype(np.uint32).tobytes(), 34963), 'componentType': 5125, 'count': len(I),
                     'type': 'SCALAR'})
        attrs = {'POSITION': a0, 'NORMAL': a0 + 1, 'TEXCOORD_0': a0 + 2}
        if m.get('skin') is not None:
            accs.append({'bufferView': view(np.ascontiguousarray(m['skin']).tobytes(), 34962), 'componentType': 5126,
                         'count': len(P), 'type': 'VEC2'})
            attrs['TEXCOORD_1'] = len(accs) - 1
        gmeshes.append({'primitives': [{'attributes': attrs, 'indices': a0 + 3, 'material': tex}]})
        nodes.append({'mesh': len(gmeshes) - 1, 'translation': list(at)})
    g = {'asset': {'version': '2.0', 'generator': 'fm3_spectators.py'}, 'scene': 0,
         'scenes': [{'nodes': list(range(len(nodes)))}], 'nodes': nodes, 'meshes': gmeshes, 'materials': mats,
         'textures': [{'source': k} for k in range(len(png_names))], 'images': [{'uri': p} for p in png_names],
         'accessors': accs, 'bufferViews': views,
         'buffers': [{'byteLength': len(blob), 'uri': os.path.basename(path)[:-5] + '.bin'}]}
    open(path[:-5] + '.bin', 'wb').write(bytes(blob))
    open(path, 'w', newline='\n').write(json.dumps(g))


def main():
    src, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    xml = open(os.path.join(src, 'spectators.xml'), encoding='utf-8-sig').read()
    models = re.findall(r'<model name="([^"]+)">(.*?)</model>', xml, re.S)
    index = []
    row = []
    for fi, (name, body) in enumerate(models):
        texs = re.findall(r'<texture name="([^"]+)"', body)
        pngs = []
        for k, t in enumerate(texs):
            img = fm3_tex.load_xds(os.path.join(src, 'textures', t))
            png = '%s_%d.png' % (name, k + 1)
            fr.write_png(os.path.join(out, png), img.shape[1], img.shape[0], np.ascontiguousarray(img).tobytes())
            pngs.append(png)
        entry = {'figure': fi, 'name': name}
        for pose in ('Sit', 'Stand'):
            sp = os.path.join(src, 'models', '%s_%s.skinbin' % (name, pose))
            if not os.path.exists(sp):
                continue
            m = read_skinbin(sp)
            files = []
            for k, png in enumerate(pngs):
                gp = '%s_%s_%d.gltf' % (name, pose, k + 1)
                write_gltf(os.path.join(out, gp), [(m, 0, (0, 0, 0))], [png])
                files.append(gp)
                # (and coarser levels for the crowd: thousands of people; level 2 = 448 triangles, level 3 = 156)
                for lv in (2, 3):
                    write_gltf(os.path.join(out, gp[:-5] + '_lod%d.gltf' % lv), [(read_skinbin(sp, lv), 0, (0, 0, 0))], [png])
            entry[pose.lower()] = files
            if pose == 'Sit':
                row.append((m, pngs, fi))
        index.append(entry)
        print('%2d %-12s %s' % (fi, name, ', '.join(k for k in ('sit', 'stand') if k in entry)))
    open(os.path.join(out, 'spectators.json'), 'w', newline='\n').write(json.dumps(index, indent=1))
    if '--row' in sys.argv:
        allp = []
        meshes = []
        for i, (m, pngs, fi) in enumerate(row):
            allp.append(pngs[0])
            meshes.append((m, len(allp) - 1, (i * 0.8, 0, 0)))
        write_gltf(os.path.join(out, 'all_sit.gltf'), meshes, allp)


if __name__ == '__main__':
    main()
