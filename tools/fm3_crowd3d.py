r"""A layout's spectators for the viewer's 3D crowd (2026-11-26): every person of <track>_track_NN.crowd (FM3-FORMATS
"Crowd") as [figure, texture set, x, y, z, facing angle] in the glTF frame of our track exports (the same positions
fm3_track_export.py draws its crowd cards at), written to <out>_crowd.json beside the scene.

    python tools/fm3_crowd3d.py <...\Ribbon_NN\<track>_track_NN.crowd> <out\world\<scene>.gltf>

The viewer (world_view.gd, FM3_CROWD3D) draws them with tools/fm3_spectators.py's models (out\spectators), one
MultiMesh per figure and texture set, in place of the 'crowd_people' cards.
"""
import json
import os
import re
import struct
import sys

import numpy as np


def people(path):
    cd = open(path, 'rb').read()
    _ver, ncell, npeople = struct.unpack('>3I', cd[:12])
    mids = np.zeros((npeople, 3))
    for c in range(ncell):
        v = struct.unpack('>10f3I', cd[12 + 52 * c: 12 + 52 * c + 52])
        mids[v[11]:v[11] + v[12]] = v[6:9]
    R = np.frombuffer(cd[12 + 52 * ncell: 12 + 52 * ncell + 16 * npeople], np.uint8).reshape(-1, 16)
    word = R[:, 0:2].copy().view('>u2').ravel().astype(np.int64)
    pos = mids + R[:, 8:14].copy().view('>f2').reshape(-1, 3).astype(np.float64)
    ang = R[:, 14:16].copy().view('>f2').ravel().astype(np.float64)
    return [[int(w & 0xFF), int(w >> 8), round(float(p[0]), 3), round(float(p[1]), 3), round(float(p[2]), 3),
             round(float(a), 4)] for w, p, a in zip(word, pos, ang)]


def main():
    out = sys.argv[2][:-5] + '_crowd.json' if sys.argv[2].endswith('.gltf') else sys.argv[2]
    ps = people(sys.argv[1])
    # the distance beyond which the game draws its crowd as sprites (TrackSettings <Crowds SpriteDistance>), metres
    ts = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(sys.argv[1]))), 'TrackSettings.xml')
    m = re.search(r'SpriteDistance="([-0-9.e]+)"', open(ts, errors='replace').read()) if os.path.exists(ts) else None
    sd = float(m.group(1)) if m else 0.0
    json.dump({'people': ps, 'sprite_distance': sd, 'source': sys.argv[1].replace('\\', '/').split('/')[-1]},
              open(out, 'w', newline='\n'))
    print('sprite distance %g m' % sd)
    figs = sorted(set(p[0] for p in ps))
    print('%d people, figures %s, sets %s -> %s' % (len(ps), figs, sorted(set(p[1] for p in ps)), out))


if __name__ == '__main__':
    main()
