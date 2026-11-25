import collections, glob, re, sys
sys.path.insert(0, 'tools')
import fm3_track
want = sys.argv[2].split(',')
stats = collections.Counter()
for p in glob.glob(sys.argv[1] + '/*.rmb.bin'):
    d = open(p, 'rb').read()
    try:
        m = fm3_track.parse(d)
    except Exception:
        continue
    shaders = [x.decode() for x in re.findall(rb'shaders\\track\\([a-z0-9_]+)', d)]
    mats = m.get('materials') or []
    for me in m['meshes']:
        nm = me['material'] or ''
        if not any(w.lower() in nm.lower() for w in want): continue
        i = me.get('material_index', 99999)
        sh = '?'; par = None; sl = None
        if i < len(mats):
            mt = mats[i]; sh = shaders[mt['shader']] if mt['shader'] < len(shaders) else '?'
            par = tuple(tuple(round(v, 2) for v in q) for q in mt['params'][:3]); sl = tuple(mt['slots'])
        stats[(nm, sh, me['stride'], par, sl)] += 1
for k, v in stats.most_common(40): print(v, k)
