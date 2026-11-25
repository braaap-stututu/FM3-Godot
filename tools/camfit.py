"""The game's camera in the followed car's frame, from tools/camrec.py recordings (2026-11-25).

    python tools/camfit.py <view.npz> [...]

Per recording: the camera class (vtable), and over time the camera position in the car's frame (x right, y up, z the
car's forward axis as its matrix gives it), its distance and height, the yaw of the camera's view against the car's
heading (how far a chase camera swings out in corners), the FOV against speed. The car followed = the car nearest the
camera. FM3's world matrices are row vectors: rows 0-2 the car's axes, row 3 its position; the view matrix maps world
to camera (p_cam = p_world V).
"""
import sys

import numpy as np


def cam_pose(v):
    right, up, fwd = v[:3, 0], v[:3, 1], v[:3, 2]
    c = -(right * v[3, 0] + up * v[3, 1] + fwd * v[3, 2])
    return c, right, up, fwd


def main():
    for path in sys.argv[1:]:
        d = np.load(path)
        ct, cv, fov, vt = d['cam_t'], d['cam_v'], d['cam_fov'], d['cam_vt']
        cars = [(d['car%d_t' % i], d['car%d_m' % i]) for i in range(len(d['car_ids']))]
        if not len(ct) or not cars:
            print(path, 'empty')
            continue
        c0 = cam_pose(cv[len(cv) // 2])[0]
        near = min(range(len(cars)), key=lambda i: np.linalg.norm(cars[i][1][len(cars[i][1]) // 2][3, :3] - c0))
        tt, mm = cars[near]
        rows = []
        for k in range(len(ct)):
            j = int(np.clip(np.searchsorted(tt, ct[k]), 1, len(tt) - 1))
            j = j if abs(tt[j] - ct[k]) < abs(tt[j - 1] - ct[k]) else j - 1
            m = mm[j]
            ax = m[:3, :3]  # rows: the car's x, y, z axes in the world
            pos = m[3, :3]
            c, right, up, fwd = cam_pose(cv[k])
            local = ax @ (c - pos) / np.maximum(np.linalg.norm(ax, axis=1) ** 2, 1e-9)
            look = ax @ fwd / np.maximum(np.linalg.norm(ax, axis=1), 1e-9)
            speed = 0.0
            if 0 < j < len(tt) - 1:
                speed = np.linalg.norm(mm[j + 1][3, :3] - mm[j - 1][3, :3]) / max(tt[j + 1] - tt[j - 1], 1e-6)
            rows.append((ct[k], *local, np.degrees(np.arctan2(look[0], look[2])), np.degrees(np.arcsin(np.clip(look[1], -1, 1))),
                         fov[k], speed))
        r = np.array(rows)
        vts = sorted(set('%08X' % x for x in vt))
        print('== %s: camera classes %s, %d samples, car %d' % (path, vts, len(r), near))
        for name, i in (('x (right)', 1), ('y (up)', 2), ('z (forward)', 3), ('view yaw vs car', 4), ('view pitch', 5),
                        ('fov', 6), ('speed m/s', 7)):
            print('   %-16s median %8.3f  p5 %8.3f  p95 %8.3f' % (name, np.median(r[:, i]), np.percentile(r[:, i], 5),
                                                                np.percentile(r[:, i], 95)))
        dist = np.hypot(r[:, 1], r[:, 3])
        print('   %-16s median %8.3f  p5 %8.3f  p95 %8.3f' % ('distance (xz)', np.median(dist), np.percentile(dist, 5),
                                                            np.percentile(dist, 95)))
        np.save(path.replace('.npz', '_local.npy'), r)


if __name__ == '__main__':
    main()
