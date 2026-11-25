"""Run road_3clr_blnd_2's full pixel shader (with road specular) in fir_vs's interpreter, probing its inputs."""
import glob, os, sys
import numpy as np
sys.path.insert(0, 'tools')
import fir_vs, fm3_trackshader as T

f = [x for x in glob.glob('../work/assets/tracks/maplevalley/shaders/track/*.fxobj') if os.path.basename(x).lower() == 'road_3clr_blnd_2.fxobj'][0]
cs = [c for c in T.containers(open(f, 'rb').read()) if c['kind'] == 'ps']
full = max(cs, key=lambda c: len(c['words']))
defaults = {k['register']: (k.get('default') or [0, 0, 0, 0])[:4] for k in full['constants'] if k['set'] == 'float'}


def run(n, r0, r1, grain, value, lm, consts_over=None, shadow=1.0):
    consts = {}
    def put(reg, v):
        for i in range(4):
            consts[reg * 4 + i] = float(v[i])
    for reg, v in defaults.items():
        put(reg, list(v) + [0] * (4 - len(v)))
    for reg, v in full['literals'].items():
        put(reg, v)
    put(0, [0.15, 0.15, 0.14, 1]); put(1, [0.5, 1, 1, 0]); put(2, [0.08, 0.08, 0.07, 1])
    put(116, [0, 0, 1, 1]); put(120, [0, 0, 1, 1]); put(121, [0, 0, 1, 1])
    put(247, [0.11, 0.11, 0.13, 0]); put(248, [1.56, 1.59, 1.6, 1]); put(242, [0, 0, 0, 1]); put(249, [0, 0, 0, 1])
    put(240, [0.4, 0.46, 0.5, 1]); put(251, [1, 1, 1, 1]); put(250, [0, 1, 0, 0])
    for reg, v in (consts_over or {}).items():
        put(reg, v)
    pin = {0: r0, 1: r1, 2: np.tile([0.0, 0.5, 0.5, 0], (n, 1)), 3: np.tile([0.5, 0.5, 0.5, 0.5], (n, 1)),
           4: np.tile([0.3, 0.0, 0.3, 0.0], (n, 1)), 5: np.tile([0.5, 0.5, 0, 0], (n, 1)), 6: np.zeros((n, 4))}

    def sample(slot, dim, coords):
        if slot == 0:
            return grain
        if slot == 1:
            return value
        if slot == 7:
            return lm
        return np.full((n, 4), shadow)
    m = fir_vs.run(full['words'], consts, {}, None, n, pixel_inputs=pin, sample=sample)
    return m.color


if __name__ == '__main__':
    n = 7
    # the normal up, the view direction tilted from straight up to grazing toward the sun (sun from +y? set below)
    sun = np.array([0.0, 0.5, -0.866])  # toward the sun, low ahead
    ang = np.linspace(0, 80, n)
    views = np.stack([np.zeros(n), np.cos(np.radians(ang)), np.sin(np.radians(ang))], 1)  # surface -> eye
    r0 = np.tile([0, 1, 0, 0], (n, 1)).astype(float)
    r1 = np.concatenate([views, np.zeros((n, 1))], 1)
    grain = np.tile([0.5, 0.5, 0.5, 1.0], (n, 1))
    value = np.tile([0.0, 0.0, 0.0, 0.0], (n, 1))
    lm = np.tile([0.9, 0.9, 0.9, 1.0], (n, 1))
    for flip in (1, -1):
        c = run(n, r0 * flip, r1, grain, value, lm, {250: list(sun) + [0]})
        print('normal sign', flip)
        for a, row in zip(ang, c):
            print('  view %4.0f deg' % a, np.round(row, 4))


def spec_probe():
    n = 41
    sun = np.array([0.0, 0.5, -0.866])
    ang = np.linspace(20, 100, n)  # view tilt; the mirror direction is at 60
    views = np.stack([np.zeros(n), np.cos(np.radians(ang)), np.sin(np.radians(ang))], 1)
    r0 = np.tile([0, 1, 0, 0], (n, 1)).astype(float)
    r1 = np.concatenate([views, np.zeros((n, 1))], 1)
    def S(grain_a=1.0, val=(0, 0, 0, 0), lmv=0.9, over=None):
        base = {250: list(sun) + [0]}; base.update(over or {})
        g = np.tile([0.5, 0.5, 0.5, grain_a], (n, 1)); v = np.tile(list(val), (n, 1)); l = np.tile([lmv] * 3 + [1], (n, 1))
        return run(n, r0, r1, g, v, l, base)[:, 0]
    nh = np.cos(np.radians((ang - 60) / 2))  # N.H for these views
    ref = S()
    floor = ref.min()
    print('default consts: min %.4f max %.4f' % (ref.min(), ref.max()))
    sp = ref - S(grain_a=0.0)
    print('grain.a 0 vs 1, spec part max', sp.max().round(4))
    # power: log(spec) vs log(N.H)
    ok = sp > 1e-4
    if ok.sum() > 3:
        k = np.polyfit(np.log(nh[ok]), np.log(sp[ok]), 1)
        print('fit spec = %.4f * NH^%.2f' % (np.exp(k[1]), k[0]))
    for lmv in ():
        print(' lm %.1f spec max %.4f' % (lmv, (S(lmv=lmv) - S(grain_a=0.0, lmv=lmv)).max()))
    for val in ((0.5, 0, 0, 1), (1, 0, 0, 1), (0, 1, 0, 0), (0, 0, 0, 0.5)):
        s = S(val=val) - S(grain_a=0.0, val=val)
        print(' value', val, 'spec max %.4f' % s.max(), 'width(>half) %d' % (s > s.max() / 2).sum())
    for c223 in ([0.4, 0.7, -2, -0.5], [0.8, 0.7, -2, -0.5], [0.4, 1.4, -2, -0.5], [0.4, 0.7, -4, -0.5], [0.4, 0.7, -2, -1.0]):
        s = S(over={223: c223}) - S(grain_a=0.0, over={223: c223})
        print(' c223', c223, 'spec max %.4f' % s.max(), 'width %d' % (s > s.max() / 2).sum())
    for c224 in ([10, 20, 0.5, 0.75], [40, 20, 0.5, 0.75], [10, 80, 0.5, 0.75], [10, 20, 1.0, 0.75], [10, 20, 0.5, 1.5]):
        s = S(over={224: c224}) - S(grain_a=0.0, over={224: c224})
        print(' c224', c224, 'spec max %.4f' % s.max(), 'width %d' % (s > s.max() / 2).sum())


if __name__ == "__main__":
    spec_probe()
