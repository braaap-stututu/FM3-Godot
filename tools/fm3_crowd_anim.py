r"""fm3_crowd_anim.py: the crowd's animations for the viewer (2026-11-27; LIVE.md "The crowd's animations").

    python tools/fm3_crowd_anim.py <Godot\work\crowd_anim\crowdbuf.bin> <FM3-files\game\Media\Spectators> <out\spectators>

The game bakes every crowd animation of its spectators.xml at the race load (each sampled through its QUAT_BITSTREAM
codec, sub_82AABED0) into one vertex buffer that its crowd vertex shader (6ee601730a7f9f87) reads as fetch 94; dumped
from a running game by tools/research/crowd_anim_dump.ps1. Layout (checked: the sizes add up to the byte): the
skeletons in spectators.xml order (Sitting: 12 bones, Standing: 17), within each its animations in order, each frame
(30 a second, the record's frame count) one entry per bone; an entry = 3 dwords, each an 11:11:10 signed normalized
vector (fm3_carbin.unpack111110): rotation rows r0, r1 and the translation t; the bone's skinning transform relative
to the bind pose: p' = r0 p.x + r1 p.y + (r0 x r1) p.z + (2 t.x, 3.5 t.y, 2 t.z) (the shader's constants c255.x and
c254.w), blended over the vertex's two bones by its weights. A person's draw sets c10.w = its animation's first entry
and c10.x = the current frame's (e.g. the photographer's Stand_Idle_Photo at 62035: the camera raised to the face).

Writes <out>/crowd_anim.bin (float32 RGB, 3 texels an entry: r0, r1, t x (2, 3.5, 2), rows of 2048 texels) and
<out>/crowd_anim.json: {"width", "height", "anims": {name: [first entry, frames, bones]}, "classes": {class:
{"skeleton", "idle": [names], "cheer": [names]}}}.
"""
import json
import os
import re
import struct
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fm3_carbin  # noqa: E402

WIDTH = 2048


def anim_record(path):
    c = open(path, 'rb').read()
    r = c[c.find(b'animation\x00'):]
    bones, frames = struct.unpack('>HH', r[32:36])
    return bones, frames


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    buf, spec, out = sys.argv[1:4]
    xml = open(os.path.join(spec, 'spectators.xml'), encoding='utf-8-sig').read()
    w = np.frombuffer(open(buf, 'rb').read(), '>u4')
    e = fm3_carbin.unpack111110(w).reshape(-1, 3, 3).astype(np.float32)
    anims = {}
    o = 0
    for sk, body in re.findall(r'<skeleton name="([^"]+)"[^>]*>(.*?)</skeleton>', xml, re.S):
        for name in re.findall(r'filename="([^"]+)"', body):
            bones, frames = anim_record(os.path.join(spec, 'anims', name + '.anim.bin'))
            anims[name] = [o, frames, bones]
            o += frames * bones
    if o != len(e):
        raise SystemExit(f'the buffer holds {len(e)} entries, the animations {o}: another layout')
    classes = {}
    for cl, body in re.findall(r'<crowdclass name="([^"]+)">(.*?)</crowdclass>', xml, re.S):
        classes[cl] = {'skeleton': re.search(r'<skeleton name="([^"]+)"', body).group(1),
                       'idle': re.findall(r'<idle name="([^"]+)"', body), 'cheer': re.findall(r'<cheer name="([^"]+)"', body)}
    e[:, 2] *= np.array([2.0, 3.5, 2.0], np.float32)
    flat = e.reshape(-1, 3)
    h = (len(flat) + WIDTH - 1) // WIDTH
    tex = np.zeros((h * WIDTH, 3), np.float32)
    tex[:len(flat)] = flat
    os.makedirs(out, exist_ok=True)
    tex.astype('<f4').tofile(os.path.join(out, 'crowd_anim.bin'))
    with open(os.path.join(out, 'crowd_anim.json'), 'w', newline='\n') as f:
        json.dump({'width': WIDTH, 'height': h, 'anims': anims, 'classes': classes}, f, indent=1)
    print(f'{len(anims)} animations, {len(e)} entries -> {WIDTH} x {h} texels')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
