"""Record FM3's drawn camera and the cars from the live stream, for fitting the game's cameras (2026-11-25).

    python tools/camrec.py --seconds 20 --out cams.npz [--port 7342]

Saves per drawn-camera packet (FM3V, the player view = director with the most packets): time, view matrix (4x4, row
vectors, p_cam = p_world V), FOV, the camera class's vtable; and per car (FM3K): time and world matrix (row vectors,
rows 0-2 the car's axes, row 3 its position). tools/camfit.py turns them into car-space camera paths.
"""
import argparse
import collections
import socket
import struct
import time

import numpy as np

CAM = '<4sIII16ffId'
CAR = '<4sIII16f2Id'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=7342)
    ap.add_argument('--seconds', type=float, default=20.0)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8 << 20)
    s.bind(('127.0.0.1', a.port))
    s.settimeout(0.25)
    cams = collections.defaultdict(list)  # director -> [(t, view16, fov, vtable)]
    cars = collections.defaultdict(list)  # car -> [(t, m16)]
    end = time.time() + a.seconds
    while time.time() < end:
        try:
            data, _ = s.recvfrom(512)
        except socket.timeout:
            continue
        if len(data) != 96:
            continue
        if data[:4] == b'FM3V':
            _, _, seq, director, *rest = struct.unpack(CAM, data)
            cams[director].append((rest[18], rest[:16], rest[16], rest[17]))
        elif data[:4] == b'FM3K':
            _, _, seq, car, *rest = struct.unpack(CAR, data)
            cars[car].append((rest[-1], rest[:16]))
    if not cams:
        print('no drawn-camera packets')
        return 1
    d = max(cams, key=lambda k: len(cams[k]))
    c = cams[d]
    out = {'cam_t': np.array([x[0] for x in c]), 'cam_v': np.array([x[1] for x in c]).reshape(-1, 4, 4),
           'cam_fov': np.array([x[2] for x in c]), 'cam_vt': np.array([x[3] for x in c], dtype=np.uint32)}
    ids = sorted(cars)
    out['car_ids'] = np.array(ids, dtype=np.uint64)
    for i, k in enumerate(ids):
        out['car%d_t' % i] = np.array([x[0] for x in cars[k]])
        out['car%d_m' % i] = np.array([x[1] for x in cars[k]]).reshape(-1, 4, 4)
    np.savez(a.out, **out)
    vts = collections.Counter('%08X' % v for v in out['cam_vt'])
    print('director %08X: %d camera packets, %d cars; camera classes %s' % (d, len(c), len(ids), dict(vts)))


if __name__ == '__main__':
    raise SystemExit(main())
