#!/usr/bin/env python3
"""fm3_track_export.py: a whole FM3 track from its own files as glTF, for the viewer.

    python fm3_track_export.py <extracted bin.zip dir> <out.gltf> [--camera-from world.gltf] [--texmap capmap_dir]
                               [--pvs <track>_NN.pvs]

--pvs: textures from the game's own files for every mesh. The .pvs model table lists each model's texture-table
entries (texture file id + atlas rectangle); the model file's shaders (names end in their texture count) take blocks
of the non-atlas entries in order, and the first of a block is the base texture (85 % right against a captured frame);
the atlas entry is the lightmap: a whole texture when _0x<id>.bix exists, otherwise the rectangle (applied to UV1, or UV0
without one) in the <track>.stx.bin atlas whose id is the largest atlas id <= the entry's id. .bix base levels decode with
tools/fm3_tex.py. Props (model space) are placed by the .pvs instances of that ribbon (layout): world = F (R^T p + pos)
with F = diag(1, 1, -1) and R the instance's 3x3 (origin instances carry R = F, i.e. identity); each instance's own
lightmap entry overrides the model's. Model files without instances are world-space track pieces and are drawn as is.

Track model files (.rmb.bin, tools/fm3_track.py) hold world-space vertices for the track itself (Ladera: all 1,914
files have an identity header matrix and their vertices are what the GPU draws). Meshes are merged per material (and
lightmap). --texmap: textures per material and lightmap placements per mesh, learned from a captured frame
(fir_world.py --material-map, then tools/fm3_track_texmap.py writing <capmap_dir>/track_materials.json); other materials
get stand-in colours by name. --camera-from copies the camera and sun nodes from a fir_world.py export.
"""
import glob
import json
import os
import shutil
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fm3_track  # noqa: E402
import fm3_tex  # noqa: E402
import fm3_pvs  # noqa: E402
import fm3_families  # noqa: E402
import fir_read as fr  # noqa: E402
import re  # noqa: E402
from fir_world import smooth_normals  # noqa: E402

COLOURS = [  # (substring of the lower-case material name, base colour)
    ('rdline', (0.85, 0.85, 0.82)), ('line', (0.85, 0.85, 0.82)), ('kerb', (0.75, 0.2, 0.15)), ('curb', (0.75, 0.2, 0.15)),
    ('road', (0.22, 0.22, 0.22)), ('asphalt', (0.22, 0.22, 0.22)), ('pit', (0.3, 0.3, 0.3)),
    ('grass', (0.28, 0.38, 0.16)), ('veg', (0.2, 0.32, 0.12)), ('tree', (0.18, 0.28, 0.1)), ('bush', (0.2, 0.3, 0.12)),
    ('rock', (0.48, 0.46, 0.43)), ('terr', (0.45, 0.4, 0.32)), ('dirt', (0.45, 0.37, 0.27)), ('sand', (0.65, 0.58, 0.45)),
    ('gravel', (0.55, 0.52, 0.47)), ('barr', (0.7, 0.7, 0.7)), ('wall', (0.65, 0.63, 0.6)), ('facility', (0.7, 0.68, 0.64)),
    ('build', (0.7, 0.68, 0.64)), ('roof', (0.5, 0.5, 0.52)), ('glass', (0.2, 0.25, 0.3)), ('water', (0.15, 0.3, 0.4)),
]


def colour_for(name):
    n = (name or '').lower()
    for key, c in COLOURS:
        if key in n:
            return c
    return (0.6, 0.6, 0.6)


def apply_uv(chan, a, b, me):
    if chan == 'world':
        return (np.c_[me['positions'], np.ones(len(me['positions']))] @ np.array(a).T).astype(np.float32)
    uv = me.get(chan)
    if uv is None:
        return None
    return (uv * np.array(a) + np.array(b)).astype(np.float32)


def import_dynamic(ref_path, capdir, src, add_view, accessors, materials, images, textures, meshes, nodes, tex_out):
    """Copy the capture export's dynamic objects into this glTF: cars (nodes named after their car, fir_world.py's asset
    match) and every captured draw whose vertex data is not in the track's files (people, drivers, the crowd, flags)."""
    ref = json.load(open(ref_path))
    rbin = open(os.path.join(os.path.dirname(ref_path), ref['buffers'][0]['uri']), 'rb').read()
    caps = {c['seq']: c for c in json.load(open(os.path.join(capdir, 'materials.json')))} if capdir else {}
    blob = b''.join(open(f, 'rb').read() for f in glob.glob(os.path.join(src, '*.rmb.bin')))
    ref_dir = os.path.dirname(ref_path)
    acc_map, mat_map, tex_map = {}, {}, {}

    def copy_acc(i):
        if i not in acc_map:
            a = dict(ref['accessors'][i])
            v = ref['bufferViews'][a['bufferView']]
            n = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}[a['type']]
            size = {5126: 4, 5125: 4, 5123: 2, 5121: 1}[a['componentType']]
            start = v.get('byteOffset', 0) + a.pop('byteOffset', 0)
            data = rbin[start:start + a['count'] * n * size]
            a['bufferView'] = add_view(data, v.get('target', 34962))
            accessors.append(a)
            acc_map[i] = len(accessors) - 1
        return acc_map[i]

    def copy_tex(t):
        if t not in tex_map:
            uri = ref['images'][ref['textures'][t]['source']]['uri']
            dst = os.path.join(tex_out, 'cap_' + os.path.basename(uri))
            os.makedirs(tex_out, exist_ok=True)
            if not os.path.exists(dst):
                shutil.copyfile(os.path.join(ref_dir, uri), dst)
            images.append({'uri': os.path.basename(tex_out) + '/' + os.path.basename(dst)})
            textures.append({'source': len(images) - 1, 'sampler': 0})
            tex_map[t] = len(textures) - 1
        return tex_map[t]

    def copy_mat(i):
        if i not in mat_map:
            m = json.loads(json.dumps(ref['materials'][i]))
            pbr = m.get('pbrMetallicRoughness', {})
            for k in ('baseColorTexture', 'metallicRoughnessTexture'):
                if k in pbr:
                    pbr[k]['index'] = copy_tex(pbr[k]['index'])
            for k in ('occlusionTexture', 'normalTexture', 'emissiveTexture'):
                if k in m:
                    m[k]['index'] = copy_tex(m[k]['index'])
            materials.append(m)
            mat_map[i] = len(materials) - 1
        return mat_map[i]

    count = 0
    for n in ref['nodes']:
        if 'mesh' not in n:
            continue
        mo = re.match(r'draw(\d+)(.*)', n.get('name', ''))
        if not mo:
            continue
        car = bool(mo.group(2).strip())
        rec = caps.get(int(mo.group(1)))
        if not car and (rec is None or blob.find(bytes.fromhex(rec['vb_head'])[:32]) >= 0):
            continue
        prims = []
        for p in ref['meshes'][n['mesh']]['primitives']:
            q = {'attributes': {k: copy_acc(v) for k, v in p['attributes'].items()}}
            if 'indices' in p:
                q['indices'] = copy_acc(p['indices'])
            if 'material' in p:
                q['material'] = copy_mat(p['material'])
            if 'mode' in p:
                q['mode'] = p['mode']
            prims.append(q)
        meshes.append({'name': n.get('name'), 'primitives': prims})
        nd = {'mesh': len(meshes) - 1, 'name': n.get('name', '').replace(' ', '_').replace(':', '_')}
        for k in ('matrix', 'translation', 'rotation', 'scale'):
            if k in n:
                nd[k] = n[k]
        nodes.append(nd)
        count += 1
    return count


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    src, out = sys.argv[1], sys.argv[2]
    texmap, lmmap, texmesh, capdir = {}, {}, {}, None
    if '--texmap' in sys.argv:
        capdir = sys.argv[sys.argv.index('--texmap') + 1]
        tm = json.load(open(os.path.join(capdir, 'track_materials.json')))
        texmap = {k: v for k, v in tm['materials'].items() if v['err'] < 0.02}
        lmmap = {k: v for k, v in tm['lightmaps'].items() if v.get('lm_err', 1) < 0.02}
        texmesh = {k: v for k, v in tm.get('meshes', {}).items() if v['err'] < 0.02}
    tex_out = os.path.splitext(out)[0] + '_tex'
    pv, by_model = None, {}
    F = np.diag([1.0, 1.0, -1.0])
    if '--pvs' in sys.argv:
        pv = fm3_pvs.parse(open(sys.argv[sys.argv.index('--pvs') + 1], 'rb').read())
        for i in pv['instances']:
            by_model.setdefault(i['model'], []).append(i)
    bix_cache = {}

    def bix_png(tid):
        # Decode _0x<tid>.bix (+ _B) to a PNG in tex_out; the file name, or None.
        if tid in bix_cache:
            return bix_cache[tid]
        name = None
        hp = os.path.join(src, '_0x%08X.bix' % tid)
        bp = os.path.join(src, '_0x%08X_B.bix' % tid)
        if os.path.exists(hp) and os.path.exists(bp):
            hdr = fm3_tex.bix_header(open(hp, 'rb').read(64))
            base = open(bp, 'rb').read()
            if hdr and len(base) >= hdr['base']:
                img = fm3_tex.decode(base[:hdr['base']], hdr['w'], hdr['h'], hdr['format'], hdr['endian'])
                if img is not None:
                    os.makedirs(tex_out, exist_ok=True)
                    name = 'bix_%05x.png' % tid
                    fr.write_png(os.path.join(tex_out, name), img.shape[1], img.shape[0], img.tobytes())
        if name is None and stx is not None and tid in stx['stream']:
            # textures without a .bix live only in the stx (77 on Ladera, some full size: the grass tufts' cards)
            img = fm3_tex.decode_stx(stx_data, stx, stx['stream'][tid])
            if img is not None:
                os.makedirs(tex_out, exist_ok=True)
                name = 'stx_%05x.png' % tid
                fr.write_png(os.path.join(tex_out, name), img.shape[1], img.shape[0], img.tobytes())
        bix_cache[tid] = name
        return name

    stx_path = glob.glob(os.path.join(src, '*.stx.bin'))
    stx = fm3_tex.load_stx(stx_path[0]) if (pv is not None and stx_path) else None
    stx_data = open(stx_path[0], 'rb').read() if stx else None

    def atlas_png(piece_id):
        # The stx lightmap atlas holding a .pvs atlas entry, as a PNG in tex_out; the file name, or None.
        a = fm3_tex.stx_atlas_of(stx, piece_id) if stx else None
        if a is None:
            return None
        key = ('atlas', a)
        if key not in bix_cache:
            img = fm3_tex.decode_stx(stx_data, stx, stx['atlases'][a])
            name = None
            if img is not None:
                os.makedirs(tex_out, exist_ok=True)
                name = 'lmatlas_%05x.png' % a
                fr.write_png(os.path.join(tex_out, name), img.shape[1], img.shape[0], img.tobytes())
            bix_cache[key] = name
        return bix_cache[key]

    # Sky dome origin: the camera position (from --camera-from) lowered by SkyboxHeightOffset.
    sky_origin = np.zeros(3)
    if '--camera-from' in sys.argv:
        ref_ = json.load(open(sys.argv[sys.argv.index('--camera-from') + 1]))
        for n_ in ref_['nodes']:
            if 'camera' in n_ and 'matrix' in n_:
                sky_origin = np.array(n_['matrix'][12:15], float)
    if pv is not None:
        ts = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(sys.argv[sys.argv.index('--pvs') + 1]))),
                          'TrackSettings.xml')
        if os.path.exists(ts):
            mo = re.search(r'SkyboxHeightOffset value="([-0-9.]+)"', open(ts, errors='replace').read())
            if mo:
                sky_origin = sky_origin + np.array([0.0, float(mo.group(1)), 0.0])
    families_used = {}
    groups = {}
    nfiles = textured = lit = from_files = placed = 0
    for path in sorted(glob.glob(os.path.join(src, '*.rmb.bin'))):
        data = open(path, 'rb').read()
        model = fm3_track.parse(data)
        nfiles += 1
        is_sky = os.path.basename(path).endswith('out.sky.rmb.bin')
        if is_sky:
            # The sky dome: 16-byte vertices are position + u16 UV pair; FM3 centres it on the camera, lowered by the
            # track's SkyboxHeightOffset (TrackSettings.xml), and draws it unlit behind everything.
            for me_ in model['meshes']:
                raw_ = np.frombuffer(me_['raw'], np.uint8).reshape(-1, me_['stride'])
                me_['uv0'] = raw_[:, 12:16].copy().view('>u2').reshape(-1, 2) / 65535.0
                me_['normals'] = None
        file_tex, file_lm, mesh_tex, mesh_lm, mesh_mat = {}, None, {}, {}, {}
        mm = re.search(r'out\.(\d+)\.rmb', path)
        if pv is not None and mm and int(mm.group(1)) < len(pv['models']):
            mid = int(mm.group(1))
            entries = [pv['textures'][t] for t in pv['models'][mid]['textures'] if t < len(pv['textures'])]
            plain = [e['id'] for e in entries if e['rect'] == (1.0, 1.0, 0.0, 0.0)]
            atlas = [e for e in entries if e['rect'] != (1.0, 1.0, 0.0, 0.0)]
            shaders = [x.decode() for x in re.findall(rb'shaders\\track\\([a-z0-9_]+)', data)]
            counts = []
            for sh in shaders:
                mt = re.search(r'_(\d)(?:_|$)', sh)
                counts.append(int(mt.group(1)) if mt else 1)
            starts = np.cumsum([0] + counts[:-1]).tolist()
            order = []
            for me_ in model['meshes']:
                if me_['material'] not in order:
                    order.append(me_['material'])
            for k, mat_name in enumerate(order):
                if k < len(starts) and starts[k] < len(plain):
                    file_tex[mat_name] = (plain[starts[k]], shaders[k] if k < len(shaders) else '')
            if atlas:
                file_lm = atlas[0]
            # The file's own material table (fm3_track._parse_materials): slot 0 = base texture, slot 7 = lightmap,
            # both indices into this model's .pvs texture list; overrides the shader-block guess above.
            texl = pv['models'][mid]['textures']
            for me_ in model['meshes']:
                mats_ = model.get('materials')
                if not mats_ or me_.get('material_index', 99999) >= len(mats_):
                    continue
                mt_ = mats_[me_['material_index']]
                sl = mt_['slots']
                shn = shaders[mt_['shader']] if mt_['shader'] < len(shaders) else ''
                mesh_mat[me_['index_offset']] = (shn, mt_, texl)
                if sl and 0 <= sl[0] < len(texl):
                    mesh_tex[me_['index_offset']] = (pv['textures'][texl[sl[0]]]['id'], shn)
                if len(sl) > 7 and 0 <= sl[7] < len(texl):
                    mesh_lm[me_['index_offset']] = pv['textures'][texl[sl[7]]]
        # Placements: (3x3, translation, lightmap entry or None); world-space files once, as they are.
        places = [(np.eye(3), np.zeros(3), None)]
        if is_sky:
            places = [(np.eye(3), sky_origin, None)]
        if pv is not None and mm and int(mm.group(1)) in by_model:
            places = []
            for ins in by_model[int(mm.group(1))]:
                e = pv['textures'][ins['lightmap']] if ins['lightmap'] < len(pv['textures']) else None
                places.append((F @ ins['rot'].T, F @ np.array(ins['pos']), e if (e and e['rect'][0] < 0.9) else None))
            placed += len(places)
        for me in model['meshes']:
            if me['indices'] is None:
                continue
            tris = np.array(fm3_track.triangles(me), dtype=np.int64)
            if not len(tris):
                continue
            P0 = me['positions']
            if not np.all(np.isfinite(P0)):
                continue
            name = me['material'] or 'unnamed'
            shader_ = (mesh_mat.get(me['index_offset']) or ('',))[0]
            if shader_.startswith('flare_') or (me['name'] or '').startswith('LGHT_'):
                continue  # sun flare (a camera-facing effect) and light volumes/cookies (no material): not drawn as is
            if shader_.startswith('tree_') and me['stride'] == 24:
                # tree card shaders read UV0 at byte 12 (where other layouts keep the normal): 12 of 13 captured draws
                me = dict(me, uv0=fm3_track.uv_pair(me, 12))
            # Captured texture for this very mesh, else the game files' own, else a capture of the same material name.
            rec = texmesh.get(f"{os.path.basename(path)}@{me['index_offset']}")
            uv = apply_uv(rec['chan'], rec['a'], rec['b'], me) if rec else None
            base_png = rec['base'] if uv is not None else None
            ft = mesh_tex.get(me['index_offset']) or file_tex.get(name)
            if uv is None and ft and me.get('uv0') is not None:
                png = bix_png(ft[0])
                if png:
                    sh = ft[1]
                    # grass_* cards are soft decals (flat tuft shadows, upright tufts): alpha-blended; other opac: cut out
                    rec = {'factor': [1, 1, 1, 1], 'blend': 'BLEND' if sh.startswith('grass') else
                           ('MASK' if ('opac' in sh or 'tree' in sh) else False)}
                    uv, base_png = me['uv0'].astype(np.float32), png
                    from_files += 1
            if uv is None and texmap.get(name):
                rec = texmap[name]
                uv = apply_uv(rec['chan'], rec['a'], rec['b'], me)
                base_png = rec['base'] if uv is not None else None
            # FM3 shader families (fm3_families.py): multi-texture terrain, road and paint, from the files. Terrain blends
            # replace a capture's single texture; road and paint only fill in where the capture did not see the mesh.
            fam, fam_ex = None, None
            if shader_.startswith('lake_'):
                # Animated reflective water (lake_anim_norm_opac_refl_5): a dark glossy surface reflecting the sky.
                rec = {'factor': [0.06, 0.09, 0.09, 0.92], 'blend': 'BLEND', 'roughness': 0.05, 'water': True}
                uv, base_png = None, None
            mm_ = None if shader_.startswith('lake_') else mesh_mat.get(me['index_offset'])
            if mm_ is not None:
                r_ = fm3_families.recipe(mm_[0], mm_[1]['params'], me['stride'], mm_[1]['slots'])
                captured = texmesh.get(f"{os.path.basename(path)}@{me['index_offset']}") is not None
                if r_ is not None and (r_['mode'] == 'blend' or not captured):
                    texl_ = mm_[2]
                    pngs = [bix_png(pv['textures'][texl_[sl]]['id']) if 0 <= sl < len(texl_) else None for sl in r_['slots']]
                    if all(pngs):
                        def uv_src(o, me=me):
                            return me['positions'][:, [0, 2]] if o == 'xz' else fm3_track.uv_pair(me, o)
                        base_png, uv = pngs[0], uv_src(r_['src0']).astype(np.float32)
                        fam = dict(r_, tex=pngs, slots=None)
                        fam_ex = {'uv2': uv_src(r_['src1']).astype(np.float32),
                                  'uv3': (uv_src(r_['mask']) if r_['mask'] is not None else uv_src(r_['src1'])).astype(np.float32),
                                  'col': fm3_track.vertex_colour(me) if r_['vclr'] else None,
                                  'lmsrc': uv_src(r_['lm']) if r_['lm'] is not None else None}
                        rec = {'factor': [1, 1, 1, 1], 'blend': False}
                        families_used[r_['mode']] = families_used.get(r_['mode'], 0) + 1
            for M3, t, inst_lm in places:
                P = (P0 @ M3.T + t).astype(np.float32)
                luv = lm_png = None
                if len(places) == 1 and inst_lm is None:  # captured lightmap fits are per file mesh (world-space)
                    lmr = lmmap.get(f"{os.path.basename(path)}@{me['index_offset']}")
                    luv = apply_uv(lmr['lm_chan'], lmr['lm_a'], lmr['lm_b'], me) if (lmr and uv is not None) else None
                    lm_png = lmr['lightmap'] if luv is not None else None
                lm_e = inst_lm or mesh_lm.get(me['index_offset']) or file_lm
                ft_sh = (mesh_tex.get(me['index_offset']) or file_tex.get(name) or ('', ''))[1]
                if fam is not None:
                    luv = lm_png = None  # (captured lightmap fits are for the single-texture path)
                if luv is None and uv is not None and lm_e is not None and 'nolm' not in ft_sh:
                    src_uv = me.get('uv1') if me.get('uv1') is not None else me.get('uv0')
                    if fam_ex is not None and fam_ex['lmsrc'] is not None:
                        src_uv = fam_ex['lmsrc']
                    # An entry with its own .bix is a whole lightmap (rectangle unused); else a slot in an stx atlas.
                    own = bix_png(lm_e['id']) if src_uv is not None else None
                    png = own or (atlas_png(lm_e['id']) if src_uv is not None else None)
                    if own:
                        luv, lm_png = src_uv.astype(np.float32), own
                    elif png:
                        sx, sy, ox, oy = lm_e['rect']
                        luv, lm_png = (src_uv * np.array([sx, sy]) + np.array([ox, oy])).astype(np.float32), png
                key = (name + ('#sky' if is_sky else ''), base_png, lm_png, json.dumps(fam, sort_keys=True) if fam else None)
                textured += uv is not None
                lit += luv is not None
                ex = None
                if fam_ex is not None:
                    ex = dict(fam_ex)
                    if fam['src0'] == 'xz':  # world-space grain: the placed position
                        uv = P[:, [0, 2]].astype(np.float32)
                groups.setdefault(key, []).append((P, tris, uv, luv, rec if (uv is not None or (rec or {}).get('water')) else None, ex))

    bin_parts, views, accessors, meshes, nodes, materials, images, textures = [], [], [], [], [], [], [], []
    img_ids = {}
    offset = 0

    def add_view(data, target):
        nonlocal offset
        pad = (-len(data)) % 4
        bin_parts.append(data + b'\0' * pad)
        views.append({'buffer': 0, 'byteOffset': offset, 'byteLength': len(data), 'target': target})
        offset += len(data) + pad
        return len(views) - 1

    def image(png):
        if png not in img_ids:
            os.makedirs(tex_out, exist_ok=True)
            if os.path.exists(os.path.join(capdir, png)):  # (capture textures may change under the same name)
                shutil.copyfile(os.path.join(capdir, png), os.path.join(tex_out, png))
            images.append({'uri': os.path.basename(tex_out) + '/' + png})
            textures.append({'source': len(images) - 1, 'sampler': 0})
            img_ids[png] = len(textures) - 1
        return img_ids[png]

    nv = nt = 0
    for (name, base, lm, famj), parts in sorted(groups.items(), key=lambda kv: str(kv[0])):
        P = np.concatenate([q[0] for q in parts])
        off, tl = 0, []
        for q in parts:
            tl.append(q[1] + off)
            off += len(q[0])
        T = np.concatenate(tl).astype(np.uint32)
        N = smooth_normals(P, T)
        rec = parts[0][4]
        pbr = {'baseColorFactor': (list(colour_for(name)) + [1.0]) if base is None else list(rec.get('factor', [1, 1, 1, 1])),
               'metallicFactor': 0.0, 'roughnessFactor': 1.0}
        sky = name.endswith('#sky')
        name = name.replace('#sky', '')
        mat = {'name': name, 'pbrMetallicRoughness': pbr, 'doubleSided': True}
        if rec and rec.get('water'):
            pbr.update(baseColorFactor=rec['factor'], roughnessFactor=rec['roughness'])
            mat['alphaMode'] = 'BLEND'
        if sky:
            mat['extensions'] = {'KHR_materials_unlit': {}}
            lm = None
        prim = {'attributes': {}}
        accessors.append({'bufferView': add_view(P.tobytes(), 34962), 'componentType': 5126, 'count': len(P), 'type': 'VEC3',
                          'min': P.min(0).tolist(), 'max': P.max(0).tolist()})
        prim['attributes']['POSITION'] = len(accessors) - 1
        accessors.append({'bufferView': add_view(N.tobytes(), 34962), 'componentType': 5126, 'count': len(N), 'type': 'VEC3'})
        prim['attributes']['NORMAL'] = len(accessors) - 1
        if base is not None:
            U = np.ascontiguousarray(np.concatenate([q[2] for q in parts]).astype(np.float32))
            accessors.append({'bufferView': add_view(U.tobytes(), 34962), 'componentType': 5126, 'count': len(U), 'type': 'VEC2'})
            prim['attributes']['TEXCOORD_0'] = len(accessors) - 1
            pbr['baseColorTexture'] = {'index': image(base)}
            blend = rec.get('blend')
            if blend in ('MASK', 'BLEND', True):
                mat['alphaMode'] = 'MASK' if blend == 'MASK' else 'BLEND'
                if mat['alphaMode'] == 'MASK':
                    mat['alphaCutoff'] = 0.5
        if lm is not None:
            L = np.ascontiguousarray(np.concatenate([q[3] for q in parts]).astype(np.float32))
            accessors.append({'bufferView': add_view(L.tobytes(), 34962), 'componentType': 5126, 'count': len(L), 'type': 'VEC2'})
            prim['attributes']['TEXCOORD_1'] = len(accessors) - 1
            mat['occlusionTexture'] = {'index': image(lm), 'texCoord': 1}
        if famj:
            fam = json.loads(famj)
            for attr, k in (('TEXCOORD_2', 'uv2'), ('TEXCOORD_3', 'uv3')):
                A = np.ascontiguousarray(np.concatenate([q[5][k] for q in parts]).astype(np.float32))
                accessors.append({'bufferView': add_view(A.tobytes(), 34962), 'componentType': 5126, 'count': len(A),
                                  'type': 'VEC2'})
                prim['attributes'][attr] = len(accessors) - 1
            if fam['vclr']:
                C = np.ascontiguousarray(np.concatenate([q[5]['col'] for q in parts]).astype(np.float32))
                accessors.append({'bufferView': add_view(C.tobytes(), 34962), 'componentType': 5126, 'count': len(C),
                                  'type': 'VEC4'})
                prim['attributes']['COLOR_0'] = len(accessors) - 1
            for png in fam['tex']:
                image(png)
            fam['tex'] = [os.path.basename(tex_out) + '/' + png for png in fam['tex']]
            mat['extras'] = {'fm3': fam}
        materials.append(mat)
        accessors.append({'bufferView': add_view(T.tobytes(), 34963), 'componentType': 5125, 'count': int(T.size), 'type': 'SCALAR'})
        prim['indices'] = len(accessors) - 1
        prim['material'] = len(materials) - 1
        meshes.append({'name': name, 'primitives': [prim]})
        nodes.append({'mesh': len(meshes) - 1, 'name': f'{name}__{len(meshes) - 1}'})  # unique (Godot renames duplicates)
        nv += len(P)
        nt += len(T)
    if '--dynamic-from' in sys.argv:
        ndyn = import_dynamic(sys.argv[sys.argv.index('--dynamic-from') + 1], capdir, src, add_view, accessors, materials,
                              images, textures, meshes, nodes, tex_out)
        print(f'dynamic objects from the capture (cars, people, crowd): {ndyn} nodes')
    print(f'meshes textured: {textured} ({from_files} from the game files), with lightmaps: {lit}; '
          f'props placed by .pvs instances: {placed}; shader families: {families_used}')

    gltf = {'asset': {'version': '2.0', 'generator': 'frame-ir fm3_track_export.py'}, 'scene': 0, 'nodes': nodes,
            'meshes': meshes, 'materials': materials, 'accessors': accessors, 'bufferViews': views}
    if any('extensions' in m for m in materials):
        gltf['extensionsUsed'] = ['KHR_materials_unlit']
    if images:
        gltf.update(images=images, textures=textures, samplers=[{'wrapS': 10497, 'wrapT': 10497}])
    if '--camera-from' in sys.argv:
        ref = json.load(open(sys.argv[sys.argv.index('--camera-from') + 1]))
        for n in ref['nodes']:
            if 'camera' in n or n.get('name') == 'sun':
                nodes.append(dict(n))
        gltf['cameras'] = ref.get('cameras', [])
        if 'KHR_lights_punctual' in ref.get('extensions', {}):
            gltf['extensions'] = {'KHR_lights_punctual': ref['extensions']['KHR_lights_punctual']}
            gltf['extensionsUsed'] = gltf.get('extensionsUsed', []) + ['KHR_lights_punctual']
    gltf['scenes'] = [{'nodes': list(range(len(nodes)))}]
    blob = b''.join(bin_parts)
    gltf['buffers'] = [{'byteLength': len(blob), 'uri': os.path.basename(os.path.splitext(out)[0]) + '.bin'}]
    with open(os.path.splitext(out)[0] + '.bin', 'wb') as f:
        f.write(blob)
    with open(out, 'w') as f:
        json.dump(gltf, f)
    print(f'{nfiles} model files -> {len(meshes)} meshes, {nv} vertices, {nt} triangles, {len(blob) / 1e6:.0f} MB: {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
