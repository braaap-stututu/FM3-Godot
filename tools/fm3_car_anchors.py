"""fm3_car_anchors.py: each library car's driver anchors as <car>_anchors.json (2026-11-27; PLAN-NEXT 3).

    python tools/fm3_car_anchors.py <car files dir> <car library dir> [car ...]

The main .carbin's header block after the exhaust emitters (0x1AC bytes, fm3_carbin.parse skips it) starts with the
in-car driver's anchors in the library's raw car space (checked on the CR-X and the Mazda 3 against their cockpit
steering wheels), each a 0 then x, y, z: the wheel's centre, its axis (the cockpit steering needle's axis within a
degree or two), the two hands' grips, then two more (the seat? and a direction; not used yet). The viewer
(world_view.gd _attach_driver) puts the driver's hands (tools/fm3_driver.py) on the grips.
"""
import json
import os
import struct
import sys


def anchors(path):
    data = open(path, 'rb').read()
    kind, w4 = struct.unpack_from('>II', data, 0)
    o = 8
    if w4 != 0xD:
        o += 0x100 if kind == 1 else 20
    o += 8
    em = struct.unpack_from('>I', data, o)[0]
    if em > 64:
        return None
    o += 4 + 140 * em
    f = struct.unpack_from('>24f', data, o)
    q = [[round(x, 5) for x in f[i + 1:i + 4]] for i in range(0, 24, 4)]  # (each: a 0, then x, y, z)
    g1, g2 = sorted((q[2], q[3]), key=lambda p: -p[0])  # (+x is the car's left in the library's space)
    return {'wheel': q[0], 'axis': q[1], 'grip_l': g1, 'grip_r': g2, 'other': q[4:6]}


def main():
    a = sys.argv[1:]
    if len(a) < 2:
        print(__doc__)
        return 2
    cdir, lib = a[:2]
    cars = a[2:] or sorted(os.path.splitext(f)[0] for f in os.listdir(lib) if f.endswith('.gltf'))
    n = 0
    for car in cars:
        p = os.path.join(cdir, car, car + '.carbin')
        if not os.path.exists(p):
            continue
        an = anchors(p)
        if an is None:
            continue
        with open(os.path.join(lib, car + '_anchors.json'), 'w', newline='\\n'.encode().decode('unicode_escape')) as f:
            json.dump(an, f, indent=1)
        n += 1
    print(f'{n} cars')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
