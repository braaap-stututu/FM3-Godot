r"""fm3_effects.py: the game's tyre smoke and tread mark textures for the viewer (2026-11-27; LIVE.md "Tyre smoke").

    python tools/fm3_effects.py <FM3-files\game\Media> <out\effects>

Writes smoke.png (Effects\smoke.dds: a 256 x 256 atlas, the tyre smoke in its top-left quarter as particles.xml's
tire_smoke uses it, dust / grass / dirt in the others) and treadmark.png (Treadmark.dds, 128 x 512), both plain DXT5
DDS files (little-endian, untiled), decoded by fm3_tex.
"""
import os
import struct
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fir_read as fr  # noqa: E402
import fm3_tex  # noqa: E402


def dds_rgba(path):
    d = open(path, 'rb').read()
    if d[:4] != b'DDS ' or d[84:88] != b'DXT5':
        raise SystemExit(f'{path}: not a DXT5 DDS')
    h, w = struct.unpack('<II', d[12:20])
    fmt = [k for k, v in fm3_tex.FORMATS.items() if v[2] == 'dxt5'][0]
    return fm3_tex.decode(d[128:], w, h, fmt, 0, tiled=False)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    media, out = sys.argv[1:3]
    os.makedirs(out, exist_ok=True)
    for src, name in ((os.path.join(media, 'Effects', 'smoke.dds'), 'smoke.png'), (os.path.join(media, 'Treadmark.dds'), 'treadmark.png')):
        img = dds_rgba(src)
        fr.write_png(os.path.join(out, name), img.shape[1], img.shape[0], np.ascontiguousarray(img).tobytes())
        print(name, img.shape)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
