"""fm3_track.py: FM3 track model files (.rmb.bin, from Media/Tracks/<track>/bin.zip, extracted with tools/fm3unzip).

Layout (big-endian), worked out from AmalfiGP against captured draws (index lists verbatim):
  u32 ?, f32[4] bbox min, f32[4] bbox max, f32[16] matrix,
  u32 a, u32 b, u32 0, u32 1, u32 1, u32 1, f32[4] centre?, f32[4] min, f32[4] max, u32 mesh count?,
  then per mesh section:
    u32 name length, name (e.g. BARR_JersyBarrier_LOD00_001), u32 ?, u32 vertex count, u32 stride (24),
    vertex count * stride bytes: f32[3] model-space position + 12 packed bytes (as the GPU buffer, which has the
    position in world space),
    u32 1, u32 1, u32 1, u32 2?, u32 material name length, material name, parameters, u32 prim (3 = strip),
    u32 index count, u32 index size (2), indices (u16, 0xFFFF = restart).

parse(data) -> {'name', 'meshes': [{'name', 'stride', 'positions' (n, 3), 'raw' vertex bytes, 'material',
'prim', 'indices', ...}]}: one entry per subsection (material), read sequentially (ForzaStudio-EVO layout); the old
tolerant scanner (first subsection only) remains as a fallback.
"""
import re
import struct

import numpy as np

_NAME = re.compile(rb'\x00\x00\x00([\x04-\x7f])([A-Za-z0-9_\-\.]{4,127})')


def _find_names(data, start=0):
    out = []
    for m in _NAME.finditer(data, start):
        if m.group(1)[0] == len(m.group(2)):
            out.append((m.start(), m.group(2).decode()))
    return out


def parse(data):
    """Sequential reader of the ForzaStudio-EVO layout (all subsections); falls back to the name scanner."""
    try:
        return _parse_sequential(data)
    except (struct.error, ValueError, UnicodeDecodeError):
        return _parse_scan(data)


def _parse_sequential(data):
    # u32 section count at 0x74; per section: u32 1, 3 x (f32[3] + f32 0), u32 1, name, u32 2, u32 vertex count,
    # u32 stride, vertices, u32 1, u32 subsection count; per subsection: u32 1, u32 2, name, u32 LOD, u32 index type,
    # u32, u32 1, u32 0 x4, f32 1.0 x4, f32[2] UV offset, f32[2] UV tile, u32 3, i32 index count, i32 index size,
    # indices, u32 flag.
    def name_at(o):
        n = struct.unpack_from('>I', data, o)[0]
        if not 0 < n < 256:
            raise ValueError('bad name length')
        return data[o + 4:o + 4 + n].decode('ascii'), o + 4 + n
    nsec = struct.unpack_from('>I', data, 0x74)[0]
    if not 0 < nsec < 10000:
        raise ValueError('bad section count')
    o = 0x78
    model = {'meshes': []}
    for _ in range(nsec):
        if struct.unpack_from('>I', data, o)[0] != 1:
            raise ValueError('section marker')
        o += 4 + 48 + 4
        sname, o = name_at(o)
        _, cnt, stride = struct.unpack_from('>III', data, o)
        o += 12
        if not (0 < cnt < 500000 and 8 <= stride <= 64):
            raise ValueError('vertex block')
        raw = data[o:o + cnt * stride]
        o += cnt * stride
        pos = np.frombuffer(raw, dtype='>f4').reshape(cnt, stride // 4)[:, :3].astype(np.float64)
        one, nsub = struct.unpack_from('>II', data, o)
        o += 8
        if not 0 < nsub < 1000:
            raise ValueError('subsection count')
        for _ in range(nsub):
            o += 8
            mat, o = name_at(o)
            lod, itype, matidx = struct.unpack_from('>III', data, o)
            uvo = struct.unpack_from('>2f', data, o + 4 * 12)
            uvt = struct.unpack_from('>2f', data, o + 4 * 14)
            three, icount, isize = struct.unpack_from('>Iii', data, o + 4 * 16)
            if three != 3 or isize not in (2, 4) or not 0 <= icount < 8000000:
                raise ValueError('subsection header')
            io = o + 4 * 19
            idx = np.frombuffer(data, dtype='>u2' if isize == 2 else '>u4', count=icount, offset=io).astype(np.int64)
            o = io + icount * isize + 4
            mesh = {'name': sname, 'stride': stride, 'positions': pos, 'raw': raw, 'material': mat, 'lod': lod,
                    'material_index': matidx,
                    'prim': itype, 'indices': idx, 'index_offset': io, 'uv_offset': uvo, 'uv_tile': uvt,
                    'index_size': isize}
            decode_attributes(mesh)
            model['meshes'].append(mesh)
    model['name'] = model['meshes'][0]['name'] if model['meshes'] else None
    try:
        model['materials'] = _parse_materials(data, o)
    except (struct.error, ValueError):
        model['materials'] = None
    return model


def _parse_materials(data, o):
    """The material table after the last subsection: u32 x4, u32 count, then per material: u32 3, u32 shader index
    (into the file's shader name list), u32 0, u32 1, u32 0, u32 1, u32 n + n vec4 parameters (the first is the
    colour, e.g. the pit lane's orange), u32 1, u32 slot count + slots (index into the model's .pvs texture list;
    -1 none, -2 unused; slot 0 = base texture, slot 7 = lightmap). A subsection's header names its material by index."""
    count = struct.unpack_from('>I', data, o + 16)[0]
    if not 0 < count < 1000:
        raise ValueError('material count')
    o += 20
    mats = []
    for _ in range(count):
        three, shader, z0, one0, z1, one1, nvec = struct.unpack_from('>7I', data, o)
        if three != 3 or (z0, one0, z1, one1) != (0, 1, 0, 1) or nvec > 64:
            raise ValueError('material record')
        o += 28
        params = [struct.unpack_from('>4f', data, o + 16 * k) for k in range(nvec)]
        o += 16 * nvec
        one, nslots = struct.unpack_from('>II', data, o)
        if one != 1 or nslots > 16:
            raise ValueError('sampler map')
        slots = list(struct.unpack_from('>%di' % nslots, data, o + 8))
        o += 8 + 4 * nslots
        mats.append({'shader': shader, 'params': params, 'slots': slots})
    return mats


def _parse_scan(data):
    model = {'meshes': []}
    names = _find_names(data)
    i = 0
    while i < len(names):
        off, nm = names[i]
        p = off + 4 + len(nm)
        # vertex block: u32 ?, u32 count, u32 stride (12..64)
        if p + 12 <= len(data):
            _, cnt, stride = struct.unpack_from('>III', data, p)
            if 0 < cnt < 200000 and stride in (16, 20, 24, 28, 32, 36, 40, 44, 48) and p + 12 + cnt * stride <= len(data):
                vstart = p + 12
                raw = data[vstart:vstart + cnt * stride]
                pos = np.frombuffer(raw, dtype='>f4').reshape(cnt, stride // 4)[:, :3].astype(np.float64)
                mesh = {'name': nm, 'stride': stride, 'positions': pos, 'raw': raw, 'material': None, 'prim': None, 'indices': None}
                # Subsection (ForzaStudio-EVO ForzaTrackSubSection): u32 1, u32 2, material name, u32 LOD, u32 index
                # type (6 strip, 4 list), u32, u32 1, u32 0 x4, f32 1.0 x4, f32[2] UV offset, f32[2] UV tile, u32 3,
                # i32 index count, i32 index size, u32 flag.
                after = vstart + cnt * stride
                mat = next(((o, n) for o, n in names if o >= after), None)
                if mat is not None:
                    q = mat[0] + 4 + len(mat[1])
                    if q + 4 * 21 <= len(data):
                        lod, itype = struct.unpack_from('>II', data, q)
                        uvo = struct.unpack_from('>2f', data, q + 4 * 12)
                        uvt = struct.unpack_from('>2f', data, q + 4 * 14)
                        three, icount, isize = struct.unpack_from('>Iii', data, q + 4 * 16)
                        if three == 3 and isize in (2, 4) and 0 < icount < 4000000 and q + 4 * 19 + icount * isize <= len(data):
                            fmt = '>u2' if isize == 2 else '>u4'
                            idx = np.frombuffer(data, dtype=fmt, count=icount, offset=q + 4 * 19).astype(np.int64)
                            mesh.update(material=mat[1], lod=lod, prim=itype, indices=idx, index_offset=q + 4 * 19,
                                        uv_offset=uvo, uv_tile=uvt, index_size=isize)
                decode_attributes(mesh)
                model['meshes'].append(mesh)
                # continue after this mesh's index list
                end = mesh.get('index_offset', after) + (len(mesh['indices']) * mesh.get('index_size', 2) if mesh['indices'] is not None else 0)
                while i < len(names) and names[i][0] < end:
                    i += 1
                continue
        if 'name' not in model:
            model['name'] = nm
        i += 1
    return model


# Track vertex layouts by stride (ForzaStudio-EVO ForzaVertex.cs, Track): (normal offset, UV0 offset, UV1 offset).
# Stride 28's UV1 (the lightmap coordinate) was found by fitting captured lightmap UVs (EVO leaves those bytes undecoded).
LAYOUTS = {12: (None, None, None), 16: (12, None, None), 20: (12, 16, None), 24: (12, 16, 20), 28: (12, 16, 24),
           32: (12, 16, 20), 36: (12, 20, 24), 40: (12, 16, 20)}


def decode_attributes(mesh):
    """Normals (packed u32, 10:10:10 signed normalised) and UV0/UV1 (u16 pairs / 65535, then * tile + offset)."""
    stride, n = mesh['stride'], len(mesh['positions'])
    lay = LAYOUTS.get(stride)
    mesh['normals'] = mesh['uv0'] = mesh['uv1'] = None
    if lay is None:
        return
    raw = np.frombuffer(mesh['raw'], dtype=np.uint8).reshape(n, stride)
    no, u0, u1 = lay
    if stride == 16 and (mesh.get('name') or '').upper().startswith('SKY'):
        no, u0 = None, 12  # sky dome: position + u16 UV pair (no normal)
    if no is not None:
        w = raw[:, no:no + 4].copy().view('>u4').ravel().astype(np.int64)

        def s10(v):
            v = v & 0x3FF
            return np.where(v >= 512, v - 1024, v) / 511.0
        mesh['normals'] = np.stack([s10(w), s10(w >> 10), s10(w >> 20)], axis=1)
    off, tile = mesh.get('uv_offset', (0.0, 0.0)), mesh.get('uv_tile', (1.0, 1.0))
    def uv_at(o):
        uv = raw[:, o:o + 4].copy().view('>u2').reshape(n, 2).astype(np.float64) / 65535.0
        return uv * np.array(tile) + np.array(off)  # (no V flip: matches what FM3's shaders read)

    def in_unit(uv):
        return uv.min() > -0.01 and uv.max() < 1.01
    for key, o in (('uv0', u0), ('uv1', u1)):
        if o is not None:
            mesh[key] = uv_at(o)
    if stride == 28 and not in_unit(mesh['uv1']) and in_unit(uv_at(20)):
        # stride 28: the lightmap UV (UV1, decoded like UV0, within 0..1) is at byte 24, in some sections at byte 20
        # (matched against captured lightmap coordinates)
        mesh['uv1'] = uv_at(20)


def triangles(mesh):
    """Triangles for a mesh by its index type (6 strip with 0xFFFF restarts, 4 list)."""
    idx = mesh['indices']
    if mesh.get('prim') == 4:
        n = len(idx) // 3 * 3
        return [tuple(t) for t in idx[:n].reshape(-1, 3).tolist()]
    return strip_to_triangles(idx)


def strip_to_triangles(idx, restart=0xFFFF):
    tris, run = [], []
    for v in list(idx) + [restart]:
        if v == restart:
            for k in range(len(run) - 2):
                a, b, c = run[k], run[k + 1], run[k + 2]
                if a != b and b != c and a != c:
                    tris.append((a, b, c) if k % 2 == 0 else (b, a, c))
            run = []
        else:
            run.append(int(v))
    return tris
