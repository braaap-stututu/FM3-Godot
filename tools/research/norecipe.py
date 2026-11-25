import collections, glob, os, re, sys
sys.path.insert(0, 'tools')
import fm3_track, fm3_families, fm3_trackshader  # noqa: E402

root = '../work/assets/tracks'
need = collections.Counter()
where = collections.defaultdict(set)
samplers = {}
for tdir in sorted(glob.glob(root + '/*')):
    t = os.path.basename(tdir)
    if t == 'autopark':
        continue
    shdir = os.path.join(tdir, 'shaders', 'track')
    for p in glob.glob(tdir + '/*.rmb.bin'):
        d = open(p, 'rb').read()
        try:
            m = fm3_track.parse(d)
        except Exception:
            continue
        sh = [x.decode() for x in re.findall(rb'shaders.track.([a-z0-9_]+)', d)]
        mats = m.get('materials') or []
        for me in m['meshes']:
            i = me.get('material_index', 99999)
            if i >= len(mats) or mats[i]['shader'] >= len(sh):
                continue
            s = sh[mats[i]['shader']]
            if s not in samplers:
                f = [x for x in glob.glob(shdir + '/*.fxobj') if os.path.basename(x)[:-6].lower() == s]
                n = 0
                if f:
                    cs = [c for c in fm3_trackshader.containers(open(f[0], 'rb').read()) if c['kind'] == 'ps']
                    for c in cs:
                        n = max(n, len([k for k in c['constants'] if k['set'] == 'sampler' and k['register'] not in (7, 11)]))
                samplers[s] = n
            if samplers[s] < 2:
                continue
            r = fm3_families.recipe(s, mats[i]['params'], me['stride'], mats[i]['slots'])
            if r is None:
                need[s] += 1
                where[s].add(t)
for s, n in need.most_common(60):
    print(n, s, samplers[s], sorted(where[s]))
