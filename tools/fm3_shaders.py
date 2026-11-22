#!/usr/bin/env python3
"""fm3_shaders.py: how FM3's track shaders use their textures, learned from a captured frame against the track files.

    python fm3_shaders.py <extracted bin.zip dir> <track>_NN.pvs <capmap dir with fetches.json> [out.json]

For every captured draw whose index list is a track mesh: the file's shader name (material table), the material's
slots and parameters, and per hardware texture slot the captured texture (identified as one of the model's .pvs
texture entries by comparing pixels) and its UV transform: uv_captured = a * src + b with src = UV0, UV1 or the world
position (x, z). Summarised per shader name: which material slot each hardware slot reads, and how its UV scale relates
to the material parameters (fm3_track._parse_materials). The result drives fm3_track_export.py's shader families.
"""
import collections
import glob
import json
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fm3_pvs  # noqa: E402
import fm3_tex  # noqa: E402
import fm3_track  # noqa: E402
import fir_read  # noqa: E402,F401


def read_png(path):
    import zlib
    import struct
    b = open(path, 'rb').read()
    o, idat, w = 8, b'', None
    while o < len(b):
        n, t = struct.unpack('>I4s', b[o:o + 8])
        c = b[o + 8:o + 8 + n]
        if t == b'IHDR':
            w, h = struct.unpack('>II', c[:8])
        elif t == b'IDAT':
            idat += c
        o += 12 + n
    raw = zlib.decompress(idat)
    return np.frombuffer(raw, np.uint8).reshape(h, 1 + w * 4)[:, 1:].reshape(h, w, 4)  # (frame-ir PNGs: filter 0)


def thumb(img, n=16):
    h, w = img.shape[:2]
    ys = (np.arange(n) + 0.5) * h / n
    xs = (np.arange(n) + 0.5) * w / n
    return img[ys.astype(int)][:, xs.astype(int), :3].astype(np.float32)


def fit(cap, src):
    ok = np.all(np.isfinite(cap), 1) & np.all(np.isfinite(src), 1)
    if ok.sum() < 3:
        return None
    a, b, e = [], [], 0.0
    for k in range(2):
        A = np.c_[src[ok, k], np.ones(ok.sum())]
        sol, *_ = np.linalg.lstsq(A, cap[ok, k], rcond=None)
        a.append(float(sol[0]))
        b.append(float(sol[1]))
        e = max(e, float(np.abs(A @ sol - cap[ok, k]).max()))
    return a, b, e


def main():
    src_dir, pvs_path, capdir = sys.argv[1:4]
    pv = fm3_pvs.parse(open(pvs_path, 'rb').read())
    T = pv['textures']
    fl = json.load(open(os.path.join(capdir, 'fetches.json')))
    by_ib = collections.defaultdict(list)
    for r in fl:
        by_ib[r['ib']].append(r)
    thumbs, cap_thumbs = {}, {}

    def file_thumb(tid):
        if tid not in thumbs:
            h = os.path.join(src_dir, '_0x%08X.bix' % tid)
            img = fm3_tex.load_bix(h, os.path.join(src_dir, '_0x%08X_B.bix' % tid)) if os.path.exists(h) else None
            thumbs[tid] = (thumb(img), img.shape[:2]) if img is not None else None
        return thumbs[tid]

    def cap_thumb(name):
        if name not in cap_thumbs:
            img = read_png(os.path.join(capdir, name))
            cap_thumbs[name] = (thumb(img), img.shape[:2])
        return cap_thumbs[name]

    per_shader = collections.defaultdict(list)
    for path in sorted(glob.glob(os.path.join(src_dir, '*.rmb.bin'))):
        mm = re.search(r'out\.(\d+)\.rmb', path)
        if not mm:
            continue
        mid = int(mm.group(1))
        data = open(path, 'rb').read()
        model = fm3_track.parse(data)
        mats = model.get('materials') or []
        shaders = [x.decode() for x in re.findall(rb'shaders\\track\\([a-z0-9_]+)', data)]
        texl = pv['models'][mid]['textures'] if mid < len(pv['models']) else []
        for me in model['meshes']:
            if me['indices'] is None or me['material_index'] >= len(mats):
                continue
            ib = data[me['index_offset']:me['index_offset'] + len(me['indices']) * me['index_size']].hex()
            for r in sorted(by_ib.get(ib, []), key=lambda r: -len(r['slots']))[:1]:  # (the main pass: most slots)
                mt = mats[me['material_index']]
                sh = shaders[mt['shader']] if mt['shader'] < len(shaders) else '?'
                vi = np.array(r['vindex'])
                if not len(vi) or vi.max() >= len(me['positions']):
                    continue
                rec = {'file': os.path.basename(path), 'mesh': me['name'], 'material': me['material'], 'ps': r['ps'],
                       'slots': mt['slots'], 'params': [list(p) for p in mt['params']], 'hw': {}}
                srcs = {'uv0': me.get('uv0'), 'uv1': me.get('uv1'), 'xz': me['positions'][:, [0, 2]]}
                for hw, s in r['slots'].items():
                    cap = np.array(s['uv'], float)
                    best = None
                    for nm, arr in srcs.items():
                        if arr is None:
                            continue
                        f = fit(cap, arr[vi])
                        if f and (best is None or f[2] < best[3]):
                            best = (nm, f[0], f[1], f[2])
                    which = None
                    if s['tex']:
                        ct, cs = cap_thumb(s['tex'])
                        scores = []
                        for k, t in enumerate(texl):
                            ft = file_thumb(T[t]['id'])
                            if ft is not None and ft[1] == cs:
                                scores.append((float(np.abs(ft[0] - ct).mean()), k))
                        if scores and min(scores)[0] < 4:
                            which = min(scores)[1]
                    mslot = mt['slots'].index(which) if which is not None and which in mt['slots'] else None
                    rec['hw'][hw] = {'pvs_index': which, 'material_slot': mslot, 'uv': best[0] if best else None,
                                     'a': best[1] if best else None, 'b': best[2] if best else None,
                                     'err': best[3] if best else None}
                per_shader[sh].append(rec)
    out = {}
    for sh, recs in sorted(per_shader.items()):
        print(f'{sh}: {len(recs)} draws, ps {sorted(set(r["ps"] for r in recs))}')
        for r in recs[:3]:
            print(f'   {r["file"]} {r["material"]} slots {r["slots"]} params {[[round(x, 3) for x in p] for p in r["params"]]}')
            for hw, h in sorted(r['hw'].items(), key=lambda x: int(x[0])):
                a = None if h['a'] is None else [round(x, 4) for x in h['a']]
                print(f'      hw s{hw}: material slot {h["material_slot"]} (pvs {h["pvs_index"]}) uv {h["uv"]} a {a} '
                      f'err {None if h["err"] is None else round(h["err"], 4)}')
        out[sh] = recs
    if len(sys.argv) > 4:
        json.dump(out, open(sys.argv[4], 'w'), indent=0)
    return 0


if __name__ == '__main__':
    sys.exit(main())
