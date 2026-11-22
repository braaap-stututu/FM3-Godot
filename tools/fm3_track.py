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
'prim', 'indices'}]} — tolerant: it scans for the vertex block header after the model name.
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
LAYOUTS = {12: (None, None, None), 16: (12, None, None), 20: (12, 16, None), 24: (12, 16, 20), 28: (12, 16, None),
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
    if no is not None:
        w = raw[:, no:no + 4].copy().view('>u4').ravel().astype(np.int64)

        def s10(v):
            v = v & 0x3FF
            return np.where(v >= 512, v - 1024, v) / 511.0
        mesh['normals'] = np.stack([s10(w), s10(w >> 10), s10(w >> 20)], axis=1)
    off, tile = mesh.get('uv_offset', (0.0, 0.0)), mesh.get('uv_tile', (1.0, 1.0))
    for key, o in (('uv0', u0), ('uv1', u1)):
        if o is not None:
            uv = raw[:, o:o + 4].copy().view('>u2').reshape(n, 2).astype(np.float64) / 65535.0
            mesh[key] = uv * np.array(tile) + np.array(off)  # (no V flip: matches what FM3's shaders read)


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
