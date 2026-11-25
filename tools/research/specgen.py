"""For a track shader's full (shadowed) pixel variant: which sampler's alpha drives the road specular, and does
peak = m * gate, power = lerp(G1, G2, m), m = lerp(S1, S2, alpha) + Skid2 hold?"""
import glob, os, sys
import numpy as np
sys.path.insert(0, 'tools')
import fir_vs, fm3_trackshader as T

C223 = [-0.404, 1.413, 0.024996, 2.01]
C224 = [3, 23, 0.428, 0.801]
sun = np.array([0.0, 0.529, -0.849]); sun /= np.linalg.norm(sun)
n = 61
ang = np.linspace(0, 120, n)
views = np.stack([np.zeros(n), np.abs(np.cos(np.radians(ang))) + 1e-3, np.sin(np.radians(ang))], 1)
views /= np.linalg.norm(views, axis=1, keepdims=True)
H = views + sun; H /= np.linalg.norm(H, axis=1, keepdims=True); nh = H[:, 1]


def analyse(name, track):
    f = [x for x in glob.glob('../work/assets/%s/shaders/track/*.fxobj' % track) if os.path.basename(x)[:-6].lower() == name][0]
    cs = [c for c in T.containers(open(f, 'rb').read()) if c['kind'] == 'ps']
    full = max(cs, key=lambda c: len(c['words']))
    samplers = sorted(k['register'] for k in full['constants'] if k['set'] == 'sampler' and k['register'] not in (7, 11))
    regs_in = set()
    defaults = {k['register']: (k.get('default') or [0, 0, 0, 0]) for k in full['constants'] if k['set'] == 'float'}

    def run(alpha_of, sunc):
        consts = {}
        def put(reg, v):
            for i in range(4):
                consts[reg * 4 + i] = float(v[i]) if i < len(v) else 0.0
        for reg, v in defaults.items():
            put(reg, v)
        for reg, v in full['literals'].items():
            put(reg, v)
        for reg in range(0, 8):
            put(reg, [1, 1, 1, 1])
        for reg in (116, 120, 121, 122, 123, 124):
            put(reg, [0, 0, 1, 1])
        put(247, [0.11, 0.11, 0.13, 0]); put(248, [1.56, 1.59, 1.6, 1]); put(242, [0, 0, 0, 1]); put(249, [0, 0, 0, 1])
        put(240, [0.4, 0.46, 0.5, 1]); put(251, sunc); put(250, list(sun) + [0]); put(223, C223); put(224, C224)
        pin = {0: np.tile([0, 1, 0, 0], (n, 1)).astype(float), 1: np.concatenate([views, np.zeros((n, 1))], 1),
               2: np.tile([0.0, 0.5, 0.5, 0], (n, 1))}
        for r in range(3, 8):
            pin[r] = np.tile([0.3, 0.2, 0.3, 0.4], (n, 1))

        def sample(slot, dim, coords):
            if slot == 7:
                return np.tile([0.9, 0.9, 0.9, 1], (n, 1))
            if slot == 11:
                return np.ones((n, 4))
            return np.tile([0.5, 0.5, 0.5, alpha_of.get(slot, 1.0)], (n, 1))
        return fir_vs.run(full['words'], consts, {}, None, n, pixel_inputs=pin, sample=sample).color[:, 0]

    def spec(alpha_of):
        return run(alpha_of, [1, 1, 1, 1]) - run(alpha_of, [0, 0, 0, 1])

    out = []
    for s in samplers:
        lo, hi = spec({s: 0.0}), spec({s: 1.0})
        out.append((s, round(lo.max(), 3), round(hi.max(), 3)))
    s1 = spec({})
    pk = s1.max()
    ok = s1 > max(pk, 1e-9) * 1e-3
    p = np.polyfit(np.log(nh[ok]), np.log(s1[ok] / pk), 1)[0] if ok.sum() > 3 and pk > 1e-6 else float('nan')
    print(name, track, 'samplers', samplers, 'alpha 0/1 per sampler (peak):', out, '| all alpha 1: peak %.3f power %.2f' % (pk, p),
          '(formula: peak 4.331, power 71.46)')


for name, track in (('road_3clr_blnd_2', 'tracks/maplevalley'), ('road_2blnd_3', 'tracks/sebring'), ('road_2blnd_uv3_3', 'tracks/roadamerica'),
                    ('road_blnd_2', 'crownjewel'), ('road_diff_spec_ovly_2', 'tracks/amalfigp'), ('road_4clr_blnd_2', 'crownjewel'),
                    ('rdline_blnd_spec_opac_3', 'crownjewel'), ('shldr_road_blnd_spec_3', 'crownjewel')):
    try:
        analyse(name, track)
    except Exception as e:
        print(name, track, 'failed:', type(e).__name__, e)
