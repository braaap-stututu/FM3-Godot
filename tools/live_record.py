"""Record FM3's live stream (camera + cars) and report how smooth it is (LIVE.md, "Smoothness").

    python tools/live_record.py [--port 7342] [--seconds 5] [--csv out.csv]

Per stream: packet intervals (median, p99, gaps > 10 ms) and steps that go backwards along the direction of travel.
For the camera against the car it follows (the nearest car): how much the camera-to-car offset jumps from packet to
packet, which shows as the car shaking on screen when the two are not from the same game step.
"""
import argparse
import socket
import struct
import time

import numpy as np

CAM = '<4sIII16ffId'
CAR = '<4sIII16f2Id'


def stats(name, t, p):
    t = np.asarray(t)
    p = np.asarray(p)
    if len(t) < 3:
        print(f'{name}: {len(t)} packets')
        return
    dt = np.diff(t) * 1000
    step = np.diff(p, axis=0)
    speed = np.linalg.norm(step, axis=1) / np.maximum(np.diff(t), 1e-6)
    travel = p[-1] - p[0]
    back = 0
    if np.linalg.norm(travel) > 1:
        d = travel / np.linalg.norm(travel)
        back = int(np.sum(step @ d < -1e-4))
    print(f'{name}: {len(t)} packets, {len(t) / (t[-1] - t[0]):.0f}/s; interval median {np.median(dt):.2f} ms, p99 '
          f'{np.percentile(dt, 99):.2f} ms, max {dt.max():.1f} ms, gaps > 10 ms: {int(np.sum(dt > 10))}; repeats '
          f'(no movement) {int(np.sum(np.linalg.norm(step, axis=1) < 1e-6))}; backwards steps {back}; speed median '
          f'{np.median(speed):.1f} m/s')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=7342)
    ap.add_argument('--seconds', type=float, default=5.0)
    a = ap.parse_args()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 << 20)
    s.bind(('127.0.0.1', a.port))
    s.settimeout(0.25)
    cam_t, cam_p, cam_seq = [], [], []
    drawn_t, drawn_p = [], []
    cars = {}
    end = time.time() + a.seconds
    while time.time() < end:
        try:
            data, _ = s.recvfrom(256)
        except socket.timeout:
            continue
        if len(data) != 96:
            continue
        if data[:4] in (b'FM3C', b'FM3V'):
            _, _, seq, director, *rest = struct.unpack(CAM, data)
            v = np.array(rest[:16]).reshape(4, 4)
            c = -(v[:3, 0] * v[3, 0] + v[:3, 1] * v[3, 1] + v[:3, 2] * v[3, 2])
            if data[:4] == b'FM3V':
                drawn_t.append(rest[18])
                drawn_p.append(c)
                continue
            cam_t.append(rest[18])
            cam_p.append(c)
            cam_seq.append(seq)
        elif data[:4] == b'FM3K':
            _, _, seq, car, *rest = struct.unpack(CAR, data)
            cars.setdefault(car, ([], []))
            cars[car][0].append(rest[-1])
            cars[car][1].append(rest[12:15])
    if not cam_t:
        print('no camera packets (FM3_LIVE on? game running and not paused?)')
        return 1
    stats('camera (hand-off, FM3C)', cam_t, cam_p)
    if drawn_t:
        stats('camera (drawn, FM3V)', drawn_t, drawn_p)
    for car, (t, p) in cars.items():
        stats(f'car {car:08X}', t, p)
    # The car the camera follows: the nearest at the start.
    cam_t, cam_p = np.asarray(cam_t), np.asarray(cam_p)
    best = min(cars, key=lambda k: float(np.linalg.norm(np.asarray(cars[k][1])[0] - cam_p[0])))
    ct, cp = np.asarray(cars[best][0]), np.asarray(cars[best][1])
    # Frame pacing (2026-11-23): per drawn game frame, how far the followed car moved. Steady driving moves it about the
    # same distance each frame if the game steps a fixed time per frame; dividing by the timestamps' spacing instead
    # shows whether the timestamps (taken on the render thread when the frame is built) wobble more than the motion.
    if len(drawn_t) > 30:
        dtn = np.asarray(drawn_t)
        uniq = np.unique(ct)  # car packet times; per drawn frame take the car packet right after each FM3V
        k = np.clip(np.searchsorted(ct, dtn), 0, len(ct) - 1)
        pos = cp[k]
        step = np.linalg.norm(np.diff(pos, axis=0), axis=1)
        gap = np.diff(dtn)
        ok = (step > 1e-4) & (gap > 0)
        if ok.sum() > 20:
            s, g = step[ok], gap[ok]
            per_frame = np.abs(np.diff(s)) / np.mean(s) * 100
            per_time = np.abs(np.diff(s / g)) / np.mean(s / g) * 100
            print(f'pacing over {ok.sum()} moving frames: frame interval median {np.median(g) * 1000:.2f} ms, sd '
                  f'{np.std(g) * 1000:.2f} ms, min {g.min() * 1000:.2f}, max {g.max() * 1000:.2f}; car step per frame '
                  f'change median {np.median(per_frame):.1f}% p95 {np.percentile(per_frame, 95):.1f}%; speed by '
                  f'timestamp change median {np.median(per_time):.1f}% p95 {np.percentile(per_time, 95):.1f}%')
    for name, tt, pp in (('hand-off camera', cam_t, cam_p), ('drawn camera', np.asarray(drawn_t), np.asarray(drawn_p))):
        if len(tt) < 3:
            continue
        # For each camera packet, the latest car packet at or before it (what a viewer taking "the newest of each" shows).
        # (the nearest car packet in time: one frame's packets go out together, the drawn camera with its first car)
        hi = np.clip(np.searchsorted(ct, tt), 1, len(ct) - 1)
        idx = np.where(np.abs(ct[hi] - tt) < np.abs(ct[hi - 1] - tt), hi, hi - 1)
        ok = np.ones(len(tt), dtype=bool)
        off = cp[idx[ok]] - pp[ok]
        jump = np.linalg.norm(np.diff(off, axis=0), axis=1) * 100
        print(f'{name} vs followed car {best:08X}: offset jump per packet median {np.median(jump):.2f} cm, p95 '
              f'{np.percentile(jump, 95):.2f} cm, max {jump.max():.2f} cm')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
