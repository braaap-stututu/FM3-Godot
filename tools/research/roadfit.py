import sys, numpy as np
sys.path.insert(0, sys.argv[1])
sys.path.insert(0, 'tools')
from roadprobe import run

C223 = [-0.404, 1.413, 0.024996, 2.01]
C224 = [3, 23, 0.428, 0.801]
sun = np.array([0.0, 0.529, -0.849]); sun /= np.linalg.norm(sun)
n = 61
ang = np.linspace(0, 120, n)
views = np.stack([np.zeros(n), np.cos(np.radians(ang - 0)), np.sin(np.radians(ang))], 1)
views[:, 1] = np.abs(views[:, 1]) + 1e-3
views /= np.linalg.norm(views, axis=1, keepdims=True)
r0 = np.tile([0, 1, 0, 0], (n, 1)).astype(float)
r1 = np.concatenate([views, np.zeros((n, 1))], 1)
H = views + sun; H /= np.linalg.norm(H, axis=1, keepdims=True)
nh = H[:, 1]


def spec(ga=1.0, val=(0, 0, 0, 0), lmv=0.9, grgb=0.5):
    g = np.tile([grgb] * 3 + [ga], (n, 1)); v = np.tile(list(val), (n, 1)); l = np.tile([lmv] * 3 + [1], (n, 1))
    on = run(n, r0, r1, g, v, l, {223: C223, 224: C224, 250: list(sun) + [0], 251: [1, 1, 1, 1]})[:, 0]
    off = run(n, r0, r1, g, v, l, {223: C223, 224: C224, 250: list(sun) + [0], 251: [0, 0, 0, 1]})[:, 0]
    return on - off, off


s, base = spec()
i = int(np.argmax(s))
print('peak spec %.4f at NH %.4f, base there %.4f' % (s[i], nh[i], base[i]))
ok = s > 1e-4
k = np.polyfit(np.log(nh[ok]), np.log(s[ok]), 1)
print('fit: %.4f * NH^%.2f' % (np.exp(k[1]), k[0]))
print('-- grain alpha')
for ga in (0, 0.2, 0.25, 0.4, 0.6, 0.8, 1.0):
    s, _ = spec(ga=ga); ok = s > 1e-5
    kk = np.polyfit(np.log(nh[ok]), np.log(s[ok]), 1) if ok.sum() > 3 else (0, -99)
    print('  a %.2f peak %.4f power %.2f' % (ga, s.max(), kk[0]))
print('-- lightmap')
for lv in (0.3, 0.428, 0.5, 0.6, 0.7, 0.801, 0.9, 1.0):
    s, _ = spec(lmv=lv); print('  lm %.3f peak %.4f' % (lv, s.max()))
print('-- value channels (r g b a)')
for val in ((0.5, 0, 0, 0), (1, 0, 0, 0), (0, 0.5, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1)):
    s, b = spec(val=val); ok = s > 1e-5
    kk = np.polyfit(np.log(nh[ok]), np.log(s[ok]), 1) if ok.sum() > 3 else (0, -99)
    print('  v', val, 'peak %.4f power %.2f base %.4f' % (s.max(), kk[0], b.min()))
print('-- grain rgb (does the colour scale the spec?)')
for gr in (0.2, 0.5, 0.9):
    s, _ = spec(grgb=gr); print('  grain rgb %.1f peak %.4f' % (gr, s.max()))
