"""fm3_track_texmap.py: which captured texture (and UV channel and transform) each track material uses.

Matches captured draws (fir_world.py --material-map) to track meshes by their index lists (verbatim in .rmb.bin), then
fits the captured per-vertex UVs as  uv_captured = a * uv_mesh + b  per axis, for UV0 and UV1, and keeps the channel with
the smallest error. Returns {material name: {'base': png, 'chan': 'uv0'|'uv1', 'a': [ax, ay], 'b': [bx, by], 'err',
'lightmap': png, 'lm_chan', 'lm_a', 'lm_b', 'blend', 'factor', 'n'}}.
"""
import glob
import json
import os
from collections import defaultdict

import numpy as np

import fm3_track


def fit(cap_uv, mesh_uv):
    """Per-axis least squares cap = a * mesh + b; returns (a, b, max error) or None."""
    ok = np.all(np.isfinite(cap_uv), axis=1) & np.all(np.isfinite(mesh_uv), axis=1)
    if ok.sum() < 3:
        return None
    a, b, err = [], [], 0.0
    for k in range(2):
        x, y = mesh_uv[ok, k], cap_uv[ok, k]
        A = np.c_[x, np.ones_like(x)]
        sol, *_ = np.linalg.lstsq(A, y, rcond=None)
        a.append(float(sol[0])); b.append(float(sol[1]))
        err = max(err, float(np.abs(A @ sol - y).max()))
    return a, b, err


def fit_world(cap_uv, pos):
    """cap = M @ [x, y, z, 1] per axis (world-projected UVs, e.g. terrain); returns (M rows, max error) or None."""
    ok = np.all(np.isfinite(cap_uv), axis=1)
    if ok.sum() < 5:
        return None
    A = np.c_[pos[ok], np.ones(ok.sum())]
    rows, err = [], 0.0
    for k in range(2):
        sol, *_ = np.linalg.lstsq(A, cap_uv[ok, k], rcond=None)
        rows.append(sol.tolist())
        err = max(err, float(np.abs(A @ sol - cap_uv[ok, k]).max()))
    return rows, err


def build(track_dir, capmap_dir):
    recs = json.load(open(os.path.join(capmap_dir, 'materials.json')))
    by_ib = defaultdict(list)
    for r in recs:
        by_ib[r['ib']].append(r)
    fits = defaultdict(list)
    lm_by_mesh, tex_by_mesh = {}, {}
    for path in glob.glob(os.path.join(track_dir, '*.rmb.bin')):
        data = open(path, 'rb').read()
        for me in fm3_track.parse(data)['meshes']:
            if me['indices'] is None or me.get('uv0') is None:
                continue
            ib = data[me['index_offset']: me['index_offset'] + len(me['indices']) * me['index_size']].hex()
            for r in by_ib.get(ib, []):
                vi = np.array(r['vindex'])
                if len(vi) == 0 or vi.max() >= len(me['positions']):
                    continue
                cap = np.array(r['uv'], float)
                best = None
                for ch in ('uv0', 'uv1'):
                    if me.get(ch) is None:
                        continue
                    f = fit(cap, me[ch][vi])
                    if f and (best is None or f[2] < best[3]):
                        best = (ch, f[0], f[1], f[2])
                fw = fit_world(cap, me['positions'][vi])
                if fw and (best is None or fw[1] < best[3] - 1e-4):
                    best = ('world', fw[0], None, fw[1])
                if best is None:
                    continue
                rec = {'base': r['base'], 'chan': best[0], 'a': best[1], 'b': best[2], 'err': best[3], 'blend': r['blend'],
                       'factor': r['factor'], 'seq': r['seq']}
                if 'lightmap' in r:
                    lcap = np.array(r['lm_uv'], float)
                    lb = None
                    for ch in ('uv0', 'uv1'):
                        if me.get(ch) is None:
                            continue
                        f = fit(lcap, me[ch][vi])
                        if f and (lb is None or f[2] < lb[3]):
                            lb = (ch, f[0], f[1], f[2])
                    if lb:
                        rec.update(lightmap=r['lightmap'], lm_chan=lb[0], lm_a=lb[1], lm_b=lb[2], lm_err=lb[3])
                rec['mesh'] = (os.path.basename(path), me['index_offset'])
                lm_by_mesh[rec['mesh']] = {k: rec[k] for k in ('lightmap', 'lm_chan', 'lm_a', 'lm_b', 'lm_err') if k in rec}
                if rec['mesh'] not in tex_by_mesh or rec['err'] < tex_by_mesh[rec['mesh']]['err']:
                    tex_by_mesh[rec['mesh']] = rec
                fits[me['material']].append(rec)
    out = {}
    for mat, lst in fits.items():
        lst.sort(key=lambda r: r['err'])
        out[mat] = dict(lst[0], n=len(lst))
    build.tex_by_mesh = tex_by_mesh
    return out, lm_by_mesh


if __name__ == '__main__':
    import sys
    res, lms = build(sys.argv[1], sys.argv[2])
    print(len(lms), 'meshes with a captured lightmap placement')
    errs = np.array([r['err'] for r in res.values()])
    from collections import Counter
    print(len(res), 'materials mapped; fit error median', np.median(errs) if len(errs) else None, '; under 0.01:', int((errs < 0.01).sum()))
    print('channels', Counter(r['chan'] for r in res.values()), 'lightmap channels', Counter(r.get('lm_chan') for r in res.values()))
    for m, r in list(res.items())[:12]:
        print(' ', m, r['chan'], np.round(r['a'], 3).tolist(), None if r['b'] is None else np.round(r['b'], 3).tolist(), 'err %.4f' % r['err'], '| lm', r.get('lm_chan'), None if 'lm_a' not in r else np.round(r['lm_a'], 3).tolist(), None if 'lm_err' not in r else round(r['lm_err'], 4))
    if len(sys.argv) > 3:
        json.dump({'materials': res, 'lightmaps': {f'{k[0]}@{k[1]}': v for k, v in lms.items()},
                   'meshes': {f'{k[0]}@{k[1]}': v for k, v in build.tex_by_mesh.items()}}, open(sys.argv[3], 'w'), indent=1)
