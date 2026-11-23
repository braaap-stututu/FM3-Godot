"""Listen to FM3's live camera stream (FM3_LIVE, FM3-ReGPU recomp src/hooks/live_camera.cpp; LIVE.md).

    python tools/live_listen.py [--port 7342] [--seconds 5] [--compare out/world/grid.gltf]

Prints the directors seen (player view, rear-view mirror, ...) with their packet rate and last camera. With --compare,
converts each director's last camera into glTF space with every combination of axis signs (world mirror sx, sy, sz;
camera right/up signs sr, su: world_view.gd --live-axes) and reports how close each comes to the glTF's camera node
(position in metres, axes as the largest angle in degrees). On the frozen test grid (FM3_GRID_TEST=1) the player view
must match grid.gltf's captured camera.
"""
import argparse
import itertools
import json
import math
import socket
import struct
import time

import numpy as np

FMT = '<4sIII16ffId'  # magic, version, seq, director, view[16], fov, camera vtable, time (96 bytes)


def camera_axes(view):
    """Camera position and right/up/forward in the game world from its view matrix (row vectors, p_cam = p_world V)."""
    v = np.array(view, dtype=np.float64).reshape(4, 4)
    right, up, fwd = v[:3, 0], v[:3, 1], v[:3, 2]
    c = -(right * v[3, 0] + up * v[3, 1] + fwd * v[3, 2])
    return c, right, up, fwd


def to_gltf(view, axes):
    """The same conversion as world_view.gd live_transform: basis columns x, y, z and origin in glTF space."""
    sx, sy, sz, sr, su = axes
    c, right, up, fwd = camera_axes(view)
    s = np.array([sx, sy, sz])
    return np.stack([s * right * sr, s * up * su, -(s * fwd)], axis=1), s * c


def gltf_camera(path):
    """World transform (3x3, origin) of the first node with a camera, parents included."""
    g = json.load(open(path))
    nodes = g['nodes']
    parent = {}
    for i, n in enumerate(nodes):
        for ch in n.get('children', []):
            parent[ch] = i

    def local(n):
        if 'matrix' in n:
            return np.array(n['matrix'], dtype=np.float64).reshape(4, 4).T
        m = np.eye(4)
        x, y, z, w = n.get('rotation', [0, 0, 0, 1])
        r = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                      [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                      [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
        m[:3, :3] = r * np.array(n.get('scale', [1, 1, 1]))
        m[:3, 3] = n.get('translation', [0, 0, 0])
        return m

    idx = next(i for i, n in enumerate(nodes) if 'camera' in n)
    m = local(nodes[idx])
    p = parent.get(idx)
    while p is not None:
        m = local(nodes[p]) @ m
        p = parent.get(p)
    yfov = g['cameras'][nodes[idx]['camera']]['perspective']['yfov']
    return m[:3, :3], m[:3, 3], math.degrees(yfov)


def axis_error_deg(a, b):
    worst = 0.0
    for k in range(3):
        u, w = a[:, k] / np.linalg.norm(a[:, k]), b[:, k] / np.linalg.norm(b[:, k])
        worst = max(worst, math.degrees(math.acos(max(-1.0, min(1.0, float(u @ w))))))
    return worst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=7342)
    ap.add_argument('--seconds', type=float, default=5.0)
    ap.add_argument('--compare', help='glTF whose camera node the player view should match')
    ap.add_argument('--save-cars', help='write every car\'s last body matrix (game space, row vectors) to this JSON: '
                    'on the frozen grid, the placement fm3_track_export.py --car-matrices uses')
    a = ap.parse_args()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(('127.0.0.1', a.port))
    s.settimeout(0.25)
    seen = {}
    cars = {}
    end = time.time() + a.seconds
    while time.time() < end:
        try:
            data, _ = s.recvfrom(256)
        except socket.timeout:
            continue
        if len(data) != 96:
            continue
        if data[:4] == b'FM3K':
            _, _, _, car, *body = struct.unpack('<4sIII16f2Id', data)
            cars[car] = body[:16]
            continue
        magic, ver, seq, director, *rest = struct.unpack(FMT, data)
        if magic != b'FM3C' or ver != 1:
            continue
        view, fov, vtable, t = rest[:16], rest[16], rest[17], rest[18]
        d = seen.setdefault(director, {'n': 0, 't0': t})
        d.update(n=d['n'] + 1, t1=t, view=view, fov=fov, vtable=vtable, seq=seq)
    if a.save_cars:
        out = [{'car': f'{c:08X}', 'matrix': [float(x) for x in m]} for c, m in cars.items()]
        with open(a.save_cars, 'w', newline='\n') as f:
            json.dump({'note': 'FM3 car body matrices (car object +0x10, game space, row vectors: rows 0-2 the car axes, '
                       'row 3 its position), from FM3_LIVE on the frozen test grid', 'cars': out}, f, indent=1)
        print(f'{len(out)} car matrices -> {a.save_cars}')
    if not seen:
        print(f'no packets on udp 127.0.0.1:{a.port} in {a.seconds:.0f} s (is FM3 running with FM3_LIVE set?)')
        return 1
    ref = gltf_camera(a.compare) if a.compare else None
    if ref:
        print(f'{a.compare} camera: origin {np.round(ref[1], 3).tolist()}, yfov {ref[2]:.2f} deg')
    for director, d in seen.items():
        span = d.get('t1', d['t0']) - d['t0']
        rate = (d['n'] - 1) / span if span > 0 else 0
        c, right, up, fwd = camera_axes(d['view'])
        print(f'director {director:08X}: {d["n"]} packets, {rate:.1f}/s, camera vtable {d["vtable"]:08X}, '
              f'fov {math.degrees(d["fov"]):.2f} deg, position {np.round(c, 3).tolist()}, forward {np.round(fwd, 3).tolist()}')
        if ref:
            fits = []
            for axes in itertools.product((1, -1), repeat=5):
                basis, origin = to_gltf(d['view'], axes)
                if np.linalg.det(basis) <= 0:
                    continue  # (a camera basis must be right-handed)
                fits.append((float(np.linalg.norm(origin - ref[1])), axis_error_deg(basis, ref[0]), axes))
            fits.sort(key=lambda f: (round(f[0], 2), f[1]))
            for dist, ang, axes in fits[:3]:
                print(f'    --live-axes {",".join(str(x) for x in axes)}: origin off by {dist:.3f} m, axes by {ang:.2f} deg')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
