"""fm3_tex.py: FM3 (Xbox 360) texture data -> RGBA8.

BIX0 track textures (`_0x<id>.bix` = header + mips, `_0x<id>_B.bix` = base level), worked out against captured fetch
constants: big-endian u32 magic 'BIX0', width, height, mip count, format word (low byte = Xenos format | endian << 6,
the same bits as the fetch constant's dword 1), mip-chain size, base-level size. Data is Xenos-tiled with the pitch =
width (aligned to 32 texels).

Untiling: Xenia's / ForzaStudio-EVO's XenosTiling (FM3-FORMATS.md). Endian 1 = swap bytes in 16-bit words, 2 = reverse
32-bit words, 3 = swap 16-bit halves of 32-bit words.
"""
import struct

import numpy as np

# Xenos format -> (block size in texels, bytes per block, decoder name)
FORMATS = {18: (4, 8, 'dxt1'), 19: (4, 16, 'dxt3'), 20: (4, 16, 'dxt5'), 49: (4, 16, 'dxn'), 59: (4, 8, 'dxt5a'),
           6: (1, 4, 'argb8'), 2: (1, 1, 'l8'), 4: (1, 2, 'r5g6b5')}


def bix_header(data):
    if data[:4] != b'BIX0':
        return None
    w, h, mips, word, chain, base = struct.unpack_from('>6I', data, 4)
    return {'w': w, 'h': h, 'mips': mips, 'format': word & 63, 'endian': (word >> 6) & 3, 'chain': chain, 'base': base,
            'header_size': 28}


def swap(buf, endian):
    a = np.frombuffer(buf, dtype=np.uint8).copy()
    if endian == 1:
        a = a.reshape(-1, 2)[:, ::-1].ravel()
    elif endian == 2:
        a = a.reshape(-1, 4)[:, ::-1].ravel()
    elif endian == 3:
        a = a.reshape(-1, 2, 2)[:, ::-1, :].ravel()
    return a.tobytes()


def tiled_offsets(bw, bh, pitch_blocks, log2_bpb):
    """Byte offsets of each (x, y) block in Xenos tiled order (Xenia texture_address::Tiled2D)."""
    y, x = np.mgrid[0:bh, 0:bw].astype(np.int64)
    outer = (((y >> 5) * (pitch_blocks >> 5)) + (x >> 5)) << 6
    inner = (((y >> 1) & 7) << 3) | (x & 7)
    b = (outer | inner) << log2_bpb
    bank = (y >> 4) & 1
    pipe = ((x >> 3) & 3) ^ (((y >> 3) & 1) << 1)
    return (((y & 1) << 4) | (pipe << 6) | (bank << 11) | (b & 0xF) | (((b >> 4) & 1) << 5) | (((b >> 5) & 7) << 8)
            | ((b >> 8) << 12))


def _565(c):
    r = ((c >> 11) & 31) * 255 // 31
    g = ((c >> 5) & 63) * 255 // 63
    b = (c & 31) * 255 // 31
    return np.stack([r, g, b], -1).astype(np.int32)


def _dxt_colour(blk, dxt1):
    c0 = blk[:, 0].astype(np.int32) | (blk[:, 1].astype(np.int32) << 8)
    c1 = blk[:, 2].astype(np.int32) | (blk[:, 3].astype(np.int32) << 8)
    p0, p1 = _565(c0), _565(c1)
    four = (c0 > c1) | (not dxt1)
    p2 = np.where(four[:, None], (2 * p0 + p1) // 3, (p0 + p1) // 2)
    p3 = np.where(four[:, None], (p0 + 2 * p1) // 3, 0)
    pal = np.stack([p0, p1, p2, p3], 1)
    a3 = np.where(four, 255, 0)
    bits = blk[:, 4].astype(np.int64) | (blk[:, 5].astype(np.int64) << 8) | (blk[:, 6].astype(np.int64) << 16) | (blk[:, 7].astype(np.int64) << 24)
    idx = (bits[:, None] >> (2 * np.arange(16))) & 3
    rgb = np.take_along_axis(pal, idx[:, :, None].repeat(3, 2), 1)
    alpha = np.where(idx == 3, a3[:, None], 255) if dxt1 else np.full(idx.shape, 255)
    return rgb, alpha


def _dxt5_alpha(blk):
    a0, a1 = blk[:, 0].astype(np.int32), blk[:, 1].astype(np.int32)
    bits = np.zeros(len(blk), np.int64)
    for k in range(6):
        bits |= blk[:, 2 + k].astype(np.int64) << (8 * k)
    idx = (bits[:, None] >> (3 * np.arange(16))) & 7
    eight = a0 > a1
    pal = np.zeros((len(blk), 8), np.int32)
    pal[:, 0], pal[:, 1] = a0, a1
    for i in range(1, 7):
        pal[:, i + 1] = np.where(eight, ((7 - i) * a0 + i * a1) // 7, 0)
    for i in range(1, 5):
        pal[:, i + 1] = np.where(eight, pal[:, i + 1], ((5 - i) * a0 + i * a1) // 5)
    pal[:, 6] = np.where(eight, pal[:, 6], 0)
    pal[:, 7] = np.where(eight, pal[:, 7], 255)
    return np.take_along_axis(pal, idx, 1)


def decode(data, w, h, fmt, endian, tiled=True, pitch=None):
    """RGBA8 (h, w, 4) uint8, or None for an unsupported format."""
    if fmt not in FORMATS:
        return None
    bs, bpb, kind = FORMATS[fmt]
    pitch = pitch or w
    bw, bh = (w + bs - 1) // bs, (h + bs - 1) // bs
    pb = max(32, ((pitch + bs - 1) // bs + 31) // 32 * 32)
    hb = (bh + 31) // 32 * 32
    raw = swap(bytes(data), endian)
    if tiled:
        offs = tiled_offsets(bw, bh, pb, int(np.log2(bpb)))
    else:
        y, x = np.mgrid[0:bh, 0:bw]
        offs = (y * pb + x) * bpb
    need = int(offs.max()) + bpb
    if len(raw) < need:
        raw = raw + bytes(need - len(raw))
    arr = np.frombuffer(raw, np.uint8)
    blocks = arr[(offs.ravel()[:, None] + np.arange(bpb)[None, :])]
    n = len(blocks)
    if kind in ('dxt1', 'dxt3', 'dxt5'):
        colour = blocks if kind == 'dxt1' else blocks[:, 8:]
        rgb, alpha = _dxt_colour(colour, kind == 'dxt1')
        if kind == 'dxt5':
            alpha = _dxt5_alpha(blocks[:, :8])
        elif kind == 'dxt3':
            nib = np.zeros((n, 16), np.int32)
            for i in range(8):
                nib[:, 2 * i] = (blocks[:, i] & 15) * 17
                nib[:, 2 * i + 1] = (blocks[:, i] >> 4) * 17
            alpha = nib
        px = np.concatenate([rgb, alpha[:, :, None]], 2)
    elif kind == 'dxt5a':
        a = _dxt5_alpha(blocks)
        px = np.stack([a, a, a, np.full_like(a, 255)], 2)
    elif kind == 'dxn':
        x_, y_ = _dxt5_alpha(blocks[:, :8]), _dxt5_alpha(blocks[:, 8:])
        px = np.stack([x_, y_, np.full_like(x_, 255), np.full_like(x_, 255)], 2)
    elif kind == 'argb8':
        b = blocks.astype(np.int32)  # A R G B after the swap
        px = np.stack([b[:, 1], b[:, 2], b[:, 3], b[:, 0]], 1)[:, None, :]
    elif kind == 'l8':
        b = blocks[:, 0].astype(np.int32)
        px = np.stack([b, b, b, np.full_like(b, 255)], 1)[:, None, :]
    else:  # r5g6b5
        c = blocks[:, 0].astype(np.int32) << 8 | blocks[:, 1].astype(np.int32)
        px = np.concatenate([_565(c), np.full((n, 1), 255)], 1)[:, None, :]
    px = px.reshape(bh, bw, bs, bs, 4) if bs > 1 else px.reshape(bh, bw, 1, 1, 4)
    img = px.transpose(0, 2, 1, 3, 4).reshape(bh * bs, bw * bs, 4)[:h, :w]
    return np.clip(img, 0, 255).astype(np.uint8)


def load_bix(path_header, path_base=None):
    """The base level of a BIX texture as RGBA8, or None."""
    hdr = bix_header(open(path_header, 'rb').read(64))
    if hdr is None:
        return None
    base = open(path_base, 'rb').read() if path_base else b''
    return decode(base[:hdr['base']], hdr['w'], hdr['h'], hdr['format'], hdr['endian'])


def load_stx(path):
    r"""A track's <track>.stx.bin (CAFF container): the lightmap atlases (`_0x<id>_a`) and the low-resolution stream
    copies of the .bix textures (`_0x<id>_s`).

    CAFF header 0x190 bytes ('CAFF21.11.05.0034', u32 at 0x14 count, .data size at 0x60, .gpu size at 0x88), then
    .data, then .gpu. In .data: one 128-byte record per texture ('texture\0' '04.05.05.0032', u32 format word as
    BIX0, ..., u16 width, u16 height at +0x24, ..., u8 mip count at +0x30), the source file names
    ('...\compiled\_0x<id>_s.bin' / '_a.bin'), then a 28-byte table per texture whose words 5 and 6 give the GPU
    offset: (w5 & 0xFFFF) << 16 | w6 >> 16.

    Returns {'atlases': {id: entry}, 'stream': {id: entry}} with entry = {'w', 'h', 'format', 'endian', 'offset'};
    use decode_stx(path_bytes, entry) for the pixels."""
    import re
    b = open(path, 'rb').read()
    if b[:4] != b'CAFF':
        raise ValueError('not a CAFF file')
    dsize = struct.unpack_from('>I', b, 0x60)[0]
    d = b[0x190:0x190 + dsize]
    recs = [m.start() for m in re.finditer(rb'texture\x0004\.05', d)]
    names = [m.group(1).decode() for m in re.finditer(rb'_0x([0-9A-Fa-f]{8}_[as])\.bin\x00', d)]
    if len(names) != len(recs):
        raise ValueError('stx: %d records, %d names' % (len(recs), len(names)))
    table = d.find(b'\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x74')
    out = {'atlases': {}, 'stream': {}, 'gpu': 0x190 + dsize}
    for i, (r, n) in enumerate(zip(recs, names)):
        word = struct.unpack_from('>I', d, r + 0x18)[0]
        w, h = struct.unpack_from('>HH', d, r + 0x24)
        w5, w6 = struct.unpack_from('>II', d, table + 28 * i + 20)
        ent = {'w': w, 'h': h, 'format': word & 63, 'endian': (word >> 6) & 3,
               'offset': ((w5 & 0xFFFF) << 16) | (w6 >> 16)}
        out['atlases' if n.endswith('_a') else 'stream'][int(n[:8], 16)] = ent
    return out


def decode_stx(data, stx, ent):
    """Pixels of one stx entry (data = the whole .stx.bin)."""
    o = stx['gpu'] + ent['offset']
    bs, bpb, _ = FORMATS.get(ent['format'], (4, 16, ''))
    size = max(32, (ent['w'] + bs - 1) // bs) * max(32, (ent['h'] + bs - 1) // bs) * bpb
    return decode(data[o:o + size], ent['w'], ent['h'], ent['format'], ent['endian'])


def stx_atlas_of(stx, piece_id):
    """The lightmap atlas holding a .pvs atlas entry: the largest atlas id <= the entry's id, among the DXT1 atlases
    (Ladera's one DXT5 atlas, 0x28f, never matched a captured lightmap; entries in its id range belong to the DXT1 atlas
    before it, as the capture shows for the distant matte terrain)."""
    ids = sorted(a for a, e in stx['atlases'].items() if e['format'] == 18)
    best = None
    for a in ids:
        if a <= piece_id:
            best = a
    return best
