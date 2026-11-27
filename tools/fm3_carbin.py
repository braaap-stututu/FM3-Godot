"""fm3_carbin.py: FM3 .carbin files read structurally, front to back (PLAN-CARS.md phase 1).

Layout from FM3-FORMATS.md ("Cars", ForzaStudio-EVO's description of the FM3 format, read as documentation; no code
copied). Big-endian. A carbin is a serialized object tree:

  header   u32 type (1 car / brake, 2 wheel); u32 at 4 = 0xD on brakes. Then (unless that word is 0xD) 0x100 bytes
           (type 1) or 20 (type 2), 8 bytes, u32 N + N x 140-byte exhaust emitters, 0x1AC bytes of driver / gauge anchors
  draws    u32 n, then 2n lists (u32 count + u32 entries (part << 16) | mesh): per LOD the see-through pass, then per
           LOD the opaque pass
  parts    u32 1, u32 part count, parts, then a 24-byte trailer
  part     u32 2; f32 origin[3], min[3], max[3]; 0x1C bytes (mass, centre of mass, detach damage, 2 versions); u32 count +
           count x vec4 glass-shard vertices; u32 1; u32 count + count x u16 shard indices; u32 + 1 byte (EVO: "2
           words", HasTransparentMeshes; FM3 has 5 bytes, the rest of the part is unaligned); name (u32 length + ASCII); u32 2 + vertex buffer (u32 count, u32 stride, data: LODs
           1-5); u32 1 + u32 mesh count + meshes; u32 2 + vertex buffer (LOD 0)
  mesh     9 bytes (u32 version, u8 RemoveFromShadow, u32 version); material name (u32 length); u32 LOD; u32
           primitive (6 strip with 0xFFFF restart / 4 list); u32 material index + UnpackingData (u32 version, f32
           PositionOffset[4], PositionScale[4], UVOffsetScale[4]); u32 3; u32 index count; u32 index size (2 / 4);
           indices; u32 mesh flags

Vertices (stride 40, car parts): half4 position at 0 (car space = xyz * w + offset), half2 UV0 at 8, half2 UV1 at 12,
normal at 16 (11:11:10: x bits 0-10 / 1023, y bits 11-21 / 1023, z bits 22-31 / 511, signed), baked lighting at 20
(8 bytes), damage word at 28 (11:11:10), ? at 32, bitangent at 36 (11:11:10). Stride 16 (brakes): position, UV0,
normal at 12. Stride 44 (wheels): position, UV0, normal at 12, lighting at 16, then constants.

    python tools/fm3_carbin.py <file.carbin | folder> [--verbose]     (parse check: every file read to its last byte)
"""
import os
import struct
import sys

import numpy as np


class CarbinError(Exception):
    pass


class _R:
    def __init__(self, data):
        self.d = data
        self.o = 0

    def u32(self):
        if self.o + 4 > len(self.d):
            raise CarbinError(f'read past the end at {self.o:#x}')
        v = struct.unpack_from('>I', self.d, self.o)[0]
        self.o += 4
        return v

    def u8(self):
        v = self.d[self.o]
        self.o += 1
        return v

    def f32(self, n):
        v = struct.unpack_from(f'>{n}f', self.d, self.o)
        self.o += 4 * n
        return v

    def skip(self, n):
        if self.o + n > len(self.d):
            raise CarbinError(f'skip of {n} past the end at {self.o:#x}')
        self.o += n

    def take(self, n):
        if self.o + n > len(self.d):
            raise CarbinError(f'take of {n} past the end at {self.o:#x}')
        b = self.d[self.o:self.o + n]
        self.o += n
        return b

    def string(self):
        n = self.u32()
        if n > 256:
            raise CarbinError(f'string length {n} at {self.o - 4:#x}')
        return self.take(n).decode('ascii', 'replace')

    def expect(self, value, what):
        v = self.u32()
        if v != value:
            raise CarbinError(f'{what}: expected {value}, got {v} at {self.o - 4:#x}')


def unpack111110(w, signed=True):
    """(x, y, z) from an 11:11:10 word: x bits 0-10, y 11-21, z 22-31, each two's complement, / 1023, 1023, 511."""
    w = np.asarray(w, dtype=np.uint32)
    x = (w & 0x7FF).astype(np.int32)
    y = ((w >> 11) & 0x7FF).astype(np.int32)
    z = ((w >> 22) & 0x3FF).astype(np.int32)
    if signed:
        x = np.where(x >= 1024, x - 2048, x)
        y = np.where(y >= 1024, y - 2048, y)
        z = np.where(z >= 512, z - 1024, z)
    return np.stack([x / 1023.0, y / 1023.0, z / 511.0], axis=-1)


def _vertex_buffer(r):
    r.expect(2, 'vertex buffer version')
    count = r.u32()
    stride = r.u32()
    if count and stride not in (16, 40, 44):
        raise CarbinError(f'vertex stride {stride} at {r.o - 4:#x}')
    return {'count': count, 'stride': stride, 'data': r.take(count * stride)}


def _mesh(r):
    r.skip(9)
    m = {'material': r.string(), 'lod': r.u32(), 'prim': r.u32()}
    if m['prim'] not in (4, 6):
        raise CarbinError(f'mesh {m["material"]}: primitive {m["prim"]} at {r.o - 4:#x}')
    m['material_index'] = r.u32()
    r.expect(1, 'unpacking data version')
    m['pos_offset'], m['pos_scale'], m['uv_offset_scale'] = r.f32(4), r.f32(4), r.f32(4)
    r.expect(3, 'index buffer version')
    n = r.u32()
    size = r.u32()
    if size not in (2, 4):
        raise CarbinError(f'index size {size} at {r.o - 4:#x}')
    m['indices'] = np.frombuffer(r.take(n * size), dtype='>u2' if size == 2 else '>u4').astype(np.uint32)
    # strip restart: 0xFFFF in 16-bit lists, 0xFFFFFF in 32-bit ones (the Xenos's 24-bit index limit; LOD 0 files)
    m['restart'] = 0xFFFF if size == 2 else 0xFFFFFF
    m['flags'] = r.u32()
    return m


def _part(r):
    r.expect(2, 'part version')
    b = r.f32(9)
    p = {'origin': np.array(b[0:3]), 'min': np.array(b[3:6]), 'max': np.array(b[6:9])}
    r.skip(0x1C)
    p['shard_vertices'] = r.u32()
    r.skip(16 * p['shard_vertices'])
    r.expect(1, 'shard index version')
    p['shard_indices'] = r.u32()
    r.skip(2 * p['shard_indices'])
    # (FM3: a u32 and one byte here, not two words: the name's length then starts unaligned; checked on the CR-X's
    # caliper: u32 0, byte 1, then u32 9 "caliperLF")
    p['word'] = r.u32()
    p['flag'] = r.u8()
    p['name'] = r.string()
    p['vb'] = _vertex_buffer(r)
    r.expect(1, f'{p["name"]}: mesh list version')
    p['meshes'] = [_mesh(r) for _ in range(r.u32())]
    p['vb0'] = _vertex_buffer(r)
    return p


def parse(data):
    """The whole file: {'type', 'draw_lists', 'parts': [...]}; raises CarbinError where the layout does not hold."""
    r = _R(data)
    kind = r.u32()
    w4 = r.u32()
    if w4 != 0xD:
        r.skip(0x100 if kind == 1 else 20)
    r.skip(8)
    emitters = r.u32()
    if emitters > 64:
        raise CarbinError(f'{emitters} emitters at {r.o - 4:#x}')
    r.skip(140 * emitters)
    # the vertices' baked SH transfer (4 x s16 at byte 20) is stored compressed: value = lo + (s + 1) / 2 x range, with
    # (lo, range) at 0x19C of this block (the paint vertex shader's shCompressionFactors c126; 2026-11-25: on every car
    # checked, e.g. the CR-X -0.3378 / 0.6887)
    sh_factors = struct.unpack_from('>2f', data, r.o + 0x19C)
    r.skip(0x1AC)
    n = r.u32()
    if n > 16:
        raise CarbinError(f'{n} draw-list LODs at {r.o - 4:#x}')
    lists = []
    for _ in range(2 * n):
        c = r.u32()
        lists.append([r.u32() for _ in range(c)])
    r.expect(1, 'part container version')
    parts = [_part(r) for _ in range(r.u32())]
    trailer = r.take(24)
    if r.o != len(data):
        raise CarbinError(f'{len(data) - r.o} bytes left after the trailer')
    return {'type': kind, 'brake': w4 == 0xD, 'emitters': emitters, 'see_through': lists[:n], 'opaque': lists[n:],
            'parts': parts, 'trailer': trailer, 'sh_factors': sh_factors}


# The game's reflection dimming per vertex (2026-11-25, paint vertex shader a102319a5aef757b, ps e41e183a423e6f1b):
# d = dp4(transfer SH, shCubeMapDampnerLight), the latter the SH projection of a two-value hemisphere, TrackSettings
# SHEnvMapTop / SHEnvMapBottom: dc = 5.3174 x (top + bottom) / 2, linear = -1.535 x (top - bottom) (fitted exactly on
# MapleValley's capture, where the same constants give vc38-40 from SHTop 0.35). So d = top x a + bottom x b.
SH_DC, SH_LIN = 5.3174, -1.535


def env_sh(raw40, factors):
    """(n, 2) per-vertex (a, b) of the stride-40 vertices: the reflection's sky weight d = top x a + bottom x b."""
    n = len(raw40)
    lo, rng = factors
    t = lo + (raw40[:, 20:28].copy().view('>i2').astype(np.float64).reshape(n, 4) / 32767.0 + 1.0) * 0.5 * rng
    return np.stack([t[:, 0] * SH_DC / 2 + t[:, 1] * SH_LIN, t[:, 0] * SH_DC / 2 - t[:, 1] * SH_LIN], axis=1)


def sh_transfer(raw40, factors):
    """(n, 4) per-vertex SH transfer T0..T3 of the stride-40 vertices, decompressed (2026-11-27, the cockpit vertex
    shader 6190a07aa58ac0a9): T0 the constant term, T1 / T2 / T3 the car-space +y / -z / +x linear terms (the game's
    cockpit light = dp4(T, hemisphere SH) + dp4(T, sun SH); LIVE.md "The cockpit's light")."""
    n = len(raw40)
    lo, rng = factors
    return lo + (raw40[:, 20:28].copy().view('>i2').astype(np.float64).reshape(n, 4) / 32767.0 + 1.0) * 0.5 * rng


def vertices(part, lod0=False):
    """Decoded vertices of a part's LOD 1-5 buffer (or its LOD 0 buffer): position (car space, before the part's
    offset), uv0, and for stride 40 also uv1, normal, damage, bitangent; normal for 16 / 44."""
    vb = part['vb0'] if lod0 else part['vb']
    n, s = vb['count'], vb['stride']
    if not n:
        return None
    raw = np.frombuffer(vb['data'], np.uint8).reshape(n, s)
    h = raw[:, 0:8].copy().view('>f2').astype(np.float64).reshape(n, 4)
    out = {'xyzw': h, 'uv0': raw[:, 8:12].copy().view('>f2').astype(np.float64).reshape(n, 2)}
    words = lambda o: raw[:, o:o + 4].copy().view('>u4').reshape(n)  # noqa: E731
    if s == 40:
        out['uv1'] = raw[:, 12:16].copy().view('>f2').astype(np.float64).reshape(n, 2)
        # baked lighting, 8 bytes at 20 (EVO: FM4's SH0). Byte 20 behaves as a brightness (2026-11-23: CR-X cockpit
        # cabin median 43, hood / A-pillars 105-107, the most open); the other 7 bytes centre on 128 (signed terms).
        out['light'] = raw[:, 20].astype(np.float64)
        out['raw40'] = raw
        out['normal'] = unpack111110(words(16))
        out['damage'] = unpack111110(words(28))
        out['bitangent'] = unpack111110(words(36))
    elif s in (16, 44):
        out['normal'] = unpack111110(words(12))
        if s == 44:
            out['light'] = raw[:, 16].astype(np.float64)  # (wheels: baked brightness at 16, same scale as cars' byte 20)
    return out


def damage_dir(t):
    """(n, 3) per-vertex crash-damage displacement (car space, metres at full damage) from the stride-40 damage word
    (11:11:10 at 28; LIVE.md "Crash damage", the paint vertex shader a102319a5aef757b): with t = (x, y, z) the word's
    signed components, the vertex moves by amount x 2 y (x, sqrt(1 - x^2 - z^2), z) (a direction, length 2 |y|; on the
    NSX it points inward, 0-30 cm). amount = the car's damage lattice at the vertex, 0..1."""
    tx, ty, tz = t[:, 0], t[:, 1], t[:, 2]
    s = np.sqrt(np.abs(1.0 - tx * tx - tz * tz))
    return np.stack([2 * tx * ty, 2 * ty * s, 2 * tz * ty], axis=1)


def sections(car, lod):
    """The parts' meshes of one LOD as fm3_car.parse-like sections, for building cars: name, offset (the part origin),
    local (xyz * w: car space = local + offset, settled on all 18,444 FM3 parts: their bounds are symmetric, so EVO's
    origin + (min + max) / 2 is the same), uv0, normal (the file's, car space), subs [{material, prim, indices}].
    LOD 0 meshes index the part's LOD 0 buffer, LOD 1-5 meshes its other buffer. Parts with no mesh of that LOD are
    left out."""
    out = []
    for p in car['parts']:
        subs = [{'material': m['material'], 'prim': m['prim'], 'indices': m['indices'], 'restart': m['restart']}
                for m in p['meshes'] if m['lod'] == lod]
        v = vertices(p, lod0=(lod == 0))
        if not subs or v is None:
            continue
        out.append({'name': p['name'], 'offset': p['origin'], 'local': v['xyzw'][:, :3] * v['xyzw'][:, 3:4],
                    'uv0': v['uv0'], 'normal': v.get('normal'), 'light': v.get('light'), 'subs': subs,
                    'env_sh': env_sh(v['raw40'], car['sh_factors']) if 'raw40' in v else None,
                    'sh4': sh_transfer(v['raw40'], car['sh_factors']) if 'raw40' in v else None,
                    'damage_dir': damage_dir(v['damage']) if 'damage' in v else None})
    return out


def main():
    paths = []
    for a in sys.argv[1:]:
        if a.startswith('--'):
            continue
        if os.path.isdir(a):
            paths += [os.path.join(a, f) for f in sorted(os.listdir(a)) if f.lower().endswith('.carbin')]
        else:
            paths.append(a)
    verbose = '--verbose' in sys.argv
    ok, bad = 0, []
    for p in paths:
        try:
            c = parse(open(p, 'rb').read())
            ok += 1
            if verbose:
                meshes = sum(len(q['meshes']) for q in c['parts'])
                lods = sorted({m['lod'] for q in c['parts'] for m in q['meshes']})
                v1 = sum(q['vb']['count'] for q in c['parts'])
                v0 = sum(q['vb0']['count'] for q in c['parts'])
                st = {e for L in c['see_through'] for e in L}
                see = sorted({m['material'] for pi, q in enumerate(c['parts']) for i, m in enumerate(q['meshes'])
                              if ((pi << 16) | i) in st})
                print(f'{os.path.basename(p)}: type {c["type"]}{" brake" if c["brake"] else ""}, {len(c["parts"])} parts, '
                      f'{meshes} meshes, LODs {lods}, vertices LOD1-5 {v1} / LOD0 {v0}, see-through: {", ".join(see)}')
        except (CarbinError, struct.error, ValueError) as e:
            bad.append((p, str(e)))
    print(f'{ok} of {len(paths)} files read to the last byte')
    for p, e in bad[:15]:
        print(f'  {os.path.basename(p)}: {e}')
    return 0 if not bad else 1


if __name__ == '__main__':
    raise SystemExit(main())
