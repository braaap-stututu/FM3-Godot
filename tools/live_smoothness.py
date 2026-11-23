"""How smooth the live viewer's motion was: reads world_view.gd --live-log <csv> (time, camera xyz, followed car xyz).

    python tools/live_smoothness.py [--window S] <csv> [<csv> ...]

--window S also reports every S seconds of the run on its own line.

Per file, over the frames where the camera moved overall (the race running):
  frozen frames     viewer frames that show no camera motion (the same game frame twice: judder)
  speed jitter      |speed(i) - speed(i-1)| / mean speed, median and p95 (steady motion: near 0)
  car shake         change of the car-to-camera offset per viewer frame, cm (median, p95)
"""
import sys

import numpy as np


def load(path):
    # (whole lines only: the viewer may be stopped in the middle of one)
    rows = [l.split(',') for l in open(path).read().splitlines()]
    return np.array([[float(x) for x in r] for r in rows if len(r) == 7 and all(r)], dtype=np.float64).reshape(-1, 7)


def report(path, d=None):
    if d is None:
        d = load(path)
    if len(d) < 30:
        print(f'{path}: {len(d)} frames, too few')
        return
    t, cam, car = d[:, 0], d[:, 1:4], d[:, 4:7]
    step = np.linalg.norm(np.diff(cam, axis=0), axis=1)
    dt = np.diff(t)
    speed = step / np.maximum(dt, 1e-6)
    moving = speed > 1.0  # m/s (frames of a running race)
    # keep the stretch where the race runs (from the first to the last moving frame)
    idx = np.nonzero(moving)[0]
    if len(idx) < 30:
        print(f'{path}: the camera hardly moved')
        return
    a, b = idx[0], idx[-1]
    sp, st, dtt = speed[a:b + 1], step[a:b + 1], dt[a:b + 1]
    frozen = int(np.sum(st < 1e-5))
    mean = float(np.mean(sp))
    jit = np.abs(np.diff(sp)) / mean * 100
    off = car[a:b + 2] - cam[a:b + 2]
    shake = np.linalg.norm(np.diff(off, axis=0), axis=1) * 100
    print(f'{path}: {b - a + 1} frames at {1 / np.median(dtt):.0f} fps, mean speed {mean:.1f} m/s; frozen frames {frozen} '
          f'({100 * frozen / (b - a + 1):.1f}%); speed jitter median {np.median(jit):.1f}%, p95 {np.percentile(jit, 95):.1f}%; '
          f'car shake median {np.median(shake):.2f} cm, p95 {np.percentile(shake, 95):.2f} cm')


args = sys.argv[1:]
window = 0.0
if args[:1] == ['--window']:
    window, args = float(args[1]), args[2:]
for p in args:
    report(p)
    if window > 0:
        d = load(p)
        t0 = d[0, 0]
        k = 0
        while t0 + k * window < d[-1, 0]:
            part = d[(d[:, 0] >= t0 + k * window) & (d[:, 0] < t0 + (k + 1) * window)]
            report(f'  {k * window:4.0f}-{(k + 1) * window:3.0f} s', part)
            k += 1
