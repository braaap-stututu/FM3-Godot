#!/usr/bin/env python3
"""fir_read.py: read a .fir capture (Frame IR framing; ReGPU fir_tap stage 1 Xenos-native records).

    python -I fir_read.py capture.fir            summary, integrity check, frame-to-frame stability
    python -I fir_read.py capture.fir --draw N   one draw of the first frame in detail
    python -I fir_read.py capture.fir --dump-textures DIR   decoded RGBA8 textures as PNG

Integrity: every record's size matches its type, every blob reference lies inside its packet, every hash a draw
refers to has a data record in the same capture. Stability: draws matched by position in the frame (frozen scenes) or
by (vs, ps, buffer hashes) signature; reports how many keep identical shaders, buffers and textures between frames.
"""
import struct
import sys
import zlib
from collections import Counter, defaultdict

PACKET = struct.Struct('<IHHQIIQQ')        # magic, major, minor, sequence, direction, record_count, record_bytes, blob_bytes
RECHDR = struct.Struct('<HHI')
BLOB = struct.Struct('<QQ')
FIR_MAGIC = 0x31524946

REC = {0x0001: 'SESSION_BEGIN', 0x0010: 'FRAME_BEGIN', 0x0011: 'FRAME_END',
       0xF101: 'XENOS_REGS', 0xF102: 'XENOS_DRAW', 0xF103: 'XENOS_RESOLVE', 0xF104: 'XENOS_SHADER', 0xF105: 'XENOS_DATA'}
SIZES = {0x0001: 152, 0x0010: 48, 0x0011: 24, 0xF101: 32, 0xF102: 104, 0xF103: 32, 0xF104: 112, 0xF105: 56}
DATA_KIND = {0: 'index', 1: 'vertex', 2: 'texture raw', 3: 'texture rgba8'}
PRIM = {1: 'point list', 2: 'line list', 3: 'line strip', 4: 'triangle list', 5: 'triangle fan', 6: 'triangle strip',
        8: 'rect list', 13: 'quad list'}
BUFREF = struct.Struct('<IIIIII QQ')        # kind, slot, addr, bytes, endian, pad, hash lo, hi
TEXREF = struct.Struct('<II6I QQ')          # slot, flags, fetch[6], hash lo, hi
VPORT = {0x210F: 'xscale', 0x2110: 'xoffset', 0x2111: 'yscale', 0x2112: 'yoffset', 0x2113: 'zscale', 0x2114: 'zoffset'}


class Capture:
    def __init__(self, path):
        self.frames = []          # each: dict(index, events=[...]) ; event = ('draw', dict) | ('resolve', dict)
        self.data = {}            # (kind, lo, hi) -> dict
        self.shaders = {}         # (hash, pixel) -> dict
        self.errors = []
        self.packets = 0
        self.bytes = 0
        self._read(path)

    def _blob(self, blob, ref, where):
        off, size = ref
        if size == 0:
            return b''
        if off + size > len(blob):
            self.errors.append(f'{where}: blob ref {off}+{size} past the blob area ({len(blob)})')
            return b''
        return blob[off:off + size]

    def _read(self, path):
        with open(path, 'rb') as f:
            buf = f.read()
        self.bytes = len(buf)
        pos = 0
        frame = None
        regs = {}
        while pos < len(buf):
            if pos + PACKET.size > len(buf):
                self.errors.append(f'truncated packet header at {pos}')
                break
            magic, major, minor, seq, direction, nrec, rbytes, bbytes = PACKET.unpack_from(buf, pos)
            if magic != FIR_MAGIC:
                self.errors.append(f'bad magic at {pos}')
                break
            self.packets += 1
            recs = buf[pos + PACKET.size: pos + PACKET.size + rbytes]
            blob = buf[pos + PACKET.size + rbytes: pos + PACKET.size + rbytes + bbytes]
            pos += PACKET.size + rbytes + bbytes
            rp = 0
            for _ in range(nrec):
                rtype, rflags, rsize = RECHDR.unpack_from(recs, rp)
                body = recs[rp:rp + rsize]
                rp += rsize
                if rtype in SIZES and rsize != SIZES[rtype]:
                    self.errors.append(f'{REC.get(rtype, hex(rtype))} size {rsize}, expected {SIZES[rtype]}')
                    continue
                if rtype == 0x0010:
                    (fidx,) = struct.unpack_from('<Q', body, 8)
                    frame = {'index': fidx, 'events': [], 'regs_full': None}
                    self.frames.append(frame)
                elif rtype == 0x0011:
                    frame = None
                elif rtype == 0xF101:
                    count, full = struct.unpack_from('<II', body, 8)
                    pairs = self._blob(blob, BLOB.unpack_from(body, 16), 'regs')
                    vals = struct.unpack(f'<{count * 2}I', pairs) if pairs else ()
                    regs = {vals[i]: vals[i + 1] for i in range(0, len(vals), 2)}
                    if frame is not None:
                        frame['regs_full'] = dict(regs)
                        frame['regs'] = dict(regs)
                elif rtype == 0xF105:
                    kind, fmt, w, h = struct.unpack_from('<IIII', body, 8)
                    lo, hi = struct.unpack_from('<QQ', body, 24)
                    data = self._blob(blob, BLOB.unpack_from(body, 40), 'data')
                    self.data[(kind, lo, hi)] = {'kind': kind, 'format': fmt, 'w': w, 'h': h, 'bytes': data}
                elif rtype == 0xF104:
                    (h,) = struct.unpack_from('<Q', body, 8)
                    pixel, slots = struct.unpack_from('<II', body, 16)
                    masks = struct.unpack_from('<4Q', body, 24)
                    nfc, nlay = struct.unpack_from('<II', body, 56)
                    code = self._blob(blob, BLOB.unpack_from(body, 64), 'shader code')
                    self.shaders[(h, pixel)] = {'code_dwords': len(code) // 4, 'slots': slots, 'consts': sum(bin(m).count('1') for m in masks),
                                                'fetch_consts': nfc, 'layouts': nlay}
                elif rtype in (0xF102, 0xF103):
                    if frame is None:
                        self.errors.append('draw/resolve outside a frame')
                        continue
                    if rtype == 0xF102:
                        seq_, init, dmab, dmas = struct.unpack_from('<IIII', body, 8)
                        vs, ps = struct.unpack_from('<QQ', body, 24)
                        flags, nreg = struct.unpack_from('<II', body, 40)
                        regblob = self._blob(blob, BLOB.unpack_from(body, 48), 'draw regs')
                        bufblob = self._blob(blob, BLOB.unpack_from(body, 64), 'draw buffers')
                        texblob = self._blob(blob, BLOB.unpack_from(body, 80), 'draw textures')
                        nbuf, ntex = struct.unpack_from('<II', body, 96)
                    else:
                        seq_, nreg = struct.unpack_from('<II', body, 8)
                        regblob = self._blob(blob, BLOB.unpack_from(body, 16), 'resolve regs')
                    vals = struct.unpack(f'<{nreg * 2}I', regblob) if regblob else ()
                    for i in range(0, len(vals), 2):
                        frame['regs'][vals[i]] = vals[i + 1]
                    if rtype == 0xF103:
                        frame['events'].append(('resolve', {'seq': seq_, 'nreg': nreg}))
                        continue
                    bufs = [BUFREF.unpack_from(bufblob, i * BUFREF.size) for i in range(nbuf)]
                    texs = [TEXREF.unpack_from(texblob, i * TEXREF.size) for i in range(ntex)]
                    vport = {name: struct.unpack('<f', struct.pack('<I', frame['regs'].get(r, 0)))[0] for r, name in VPORT.items()}
                    frame['events'].append(('draw', {'seq': seq_, 'initiator': init, 'prim': init & 0x3F, 'count': init >> 16, 'vs': vs, 'ps': ps,
                                                     'flags': flags, 'nreg': nreg, 'bufs': bufs, 'texs': texs, 'vport': vport,
                                                     'surface': frame['regs'].get(0x2000, 0)}))
                else:
                    pass

    def draws(self, f):
        return [e[1] for e in f['events'] if e[0] == 'draw']

    def check_refs(self):
        missing = Counter()
        for f in self.frames:
            for d in self.draws(f):
                for b in d['bufs']:
                    if b[3] and (b[0], b[6], b[7]) not in self.data:
                        missing[DATA_KIND[b[0]]] += 1
                for t in d['texs']:
                    if t[8] or t[9]:
                        if (2, t[8], t[9]) not in self.data:
                            missing['texture raw'] += 1
        return missing


def signature(d):
    return (d['vs'], d['ps'], d['prim'], d['count'], tuple((b[0], b[1], b[6], b[7]) for b in d['bufs']), tuple((t[0], t[8], t[9]) for t in d['texs']))


def stability(cap):
    if len(cap.frames) < 2:
        return None
    base = cap.draws(cap.frames[0])
    out = []
    for f in cap.frames[1:]:
        other = cap.draws(f)
        same_pos = sum(1 for a, b in zip(base, other) if signature(a) == signature(b))
        sigs = Counter(signature(d) for d in base)
        hit = 0
        for d in other:
            s = signature(d)
            if sigs[s] > 0:
                sigs[s] -= 1
                hit += 1
        shaders_same = sum(1 for a, b in zip(base, other) if (a['vs'], a['ps']) == (b['vs'], b['ps']))
        out.append({'frame': f['index'], 'draws': len(other), 'same_position': same_pos, 'same_signature_anywhere': hit, 'same_shaders_by_position': shaders_same})
    return out


def write_png(path, w, h, rgba):
    raw = b''.join(b'\x00' + rgba[y * w * 4:(y + 1) * w * 4] for y in range(h))
    def chunk(t, d):
        c = struct.pack('>I', len(d)) + t + d
        return c + struct.pack('>I', zlib.crc32(t + d) & 0xFFFFFFFF)
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw, 6)) + chunk(b'IEND', b''))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cap = Capture(sys.argv[1])
    print(f'{sys.argv[1]}: {cap.bytes / 1048576:.1f} MB, {cap.packets} packets, {len(cap.frames)} frames')
    kinds = Counter()
    kbytes = Counter()
    for (k, _, _), d in cap.data.items():
        kinds[DATA_KIND[k]] += 1
        kbytes[DATA_KIND[k]] += len(d['bytes'])
    print('data: ' + ', '.join(f'{n} {k} ({kbytes[k] / 1048576:.1f} MB)' for k, n in kinds.items()))
    print(f'shaders: {sum(1 for (_, p) in cap.shaders if not p)} vertex, {sum(1 for (_, p) in cap.shaders if p)} pixel')
    for f in cap.frames:
        ds = cap.draws(f)
        rs = sum(1 for e in f['events'] if e[0] == 'resolve')
        prims = Counter(PRIM.get(d['prim'], str(d['prim'])) for d in ds)
        wide = sum(1 for d in ds if d['flags'] & 4)
        print(f"frame {f['index']}: {len(ds)} draws ({wide} main-view), {rs} resolves, register changes {sum(d['nreg'] for d in ds)}; "
              + ', '.join(f'{n} {p}' for p, n in prims.most_common(5)))
    missing = cap.check_refs()
    print('integrity: ' + ('ok' if not cap.errors and not missing else f'{len(cap.errors)} errors {cap.errors[:5]}, missing data {dict(missing)}'))
    st = stability(cap)
    if st:
        for s in st:
            n = max(s['draws'], 1)
            print(f"stability vs first frame, frame {s['frame']}: {s['draws']} draws, same by position {s['same_position']} ({100 * s['same_position'] / n:.1f}%), "
                  f"same signature anywhere {s['same_signature_anywhere']} ({100 * s['same_signature_anywhere'] / n:.1f}%), "
                  f"same shaders by position {s['same_shaders_by_position']} ({100 * s['same_shaders_by_position'] / n:.1f}%)")
    if '--draw' in sys.argv:
        i = int(sys.argv[sys.argv.index('--draw') + 1])
        d = cap.draws(cap.frames[0])[i]
        print(f"draw {i}: seq {d['seq']} {PRIM.get(d['prim'], d['prim'])} x{d['count']} vs {d['vs']:016x} ps {d['ps']:016x} flags {d['flags']:x} surface {d['surface']:08x}")
        print('  viewport ' + ' '.join(f'{k} {v:g}' for k, v in d['vport'].items()))
        for b in d['bufs']:
            print(f"  {DATA_KIND[b[0]]} slot {b[1]} @{b[2]:08x} {b[3]} bytes endian {b[4]} hash {b[7]:x}:{b[6]:016x}")
        for t in d['texs']:
            print(f"  t{t[0]} flags {t[1]:x} fetch {' '.join(f'{x:08x}' for x in t[2:8])} hash {t[9]:x}:{t[8]:016x}")
    if '--dump-textures' in sys.argv:
        import os
        out = sys.argv[sys.argv.index('--dump-textures') + 1]
        os.makedirs(out, exist_ok=True)
        n = 0
        for (k, lo, hi), d in cap.data.items():
            if k == 3 and d['w'] and d['h'] and len(d['bytes']) >= d['w'] * d['h'] * 4:
                write_png(os.path.join(out, f"{lo:016x}_{d['w']}x{d['h']}_f{d['format']}.png"), d['w'], d['h'], d['bytes'])
                n += 1
        print(f'{n} textures written to {out}')
    return 0 if not cap.errors else 1


if __name__ == '__main__':
    sys.exit(main())
