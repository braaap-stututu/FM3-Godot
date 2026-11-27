"""The game's exposure state from a W probe shot (wtrack.ps1 mode 1, lensiter.ps1 -Probe 'p1'), 2026-11-27.

The probe edits the final pass to output input.o[1].y x 4 with the display gamma off. Its vertex shader
(2a342f670b5bb28a) makes o[1].y = (0.1 - B) / (W - B) from the adapted luminance L:
  k = saturate((L - LumMin / 255) * 255 / (LumMax - LumMin))
  W = lerp(dark white, light white, k) / 255 - 0.0006,  B = lerp(dark black, light black, k) / 255
(0.1 / W only where B = 0: RoadAtlanta's light curve has B 10, which made its L read ~0.03-0.06 too high until this.)

usage: python tools/research/wsolve.py <probe.png> <out/world/<scene>_track.json> [x0,y0,x1,y1]
"""
import json, struct, sys, zlib


def png_rows(path, rows):
    d = open(path, 'rb').read(); i = 8; idat = b''
    while i < len(d):
        n = struct.unpack('>I', d[i:i + 4])[0]; t = d[i + 4:i + 8]; c = d[i + 8:i + 8 + n]
        if t == b'IHDR':
            w, h, bd, ct = struct.unpack('>IIBB', c[:10])
        if t == b'IDAT':
            idat += c
        i += 12 + n
    ch = {2: 3, 6: 4}[ct]; raw = zlib.decompress(idat); s = w * ch
    prev = [0] * s; out = []
    for y in range(min(h, rows)):
        f = raw[y * (s + 1)]; row = list(raw[y * (s + 1) + 1:(y + 1) * (s + 1)])
        for x in range(s):
            a = row[x - ch] if x >= ch else 0; b = prev[x]; c = prev[x - ch] if x >= ch else 0
            if f == 1: row[x] = (row[x] + a) & 255
            elif f == 2: row[x] = (row[x] + b) & 255
            elif f == 3: row[x] = (row[x] + (a + b) // 2) & 255
            elif f == 4:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                row[x] = (row[x] + (a if pa <= pb and pa <= pc else (b if pb <= pc else c))) & 255
        out.append(row); prev = row
    return out, ch


def main():
    box = [int(v) for v in (sys.argv[3] if len(sys.argv) > 3 else '500,300,780,420').split(',')]
    rows, ch = png_rows(sys.argv[1], box[3])
    vals = [r[x * ch + 1] for r in rows[box[1]:box[3]] for x in range(box[0], box[2])]
    v = sum(vals) / len(vals) / 255.0 / 4.0  # o[1].y
    j = json.load(open(sys.argv[2])); tone = j.get('tone') or j['Tone']
    d, l, lum = tone['dark'], tone['light'], tone['lum']

    def probe(k):
        W = (d[2] + (l[2] - d[2]) * k) / 255 - 0.0006; B = (d[0] + (l[0] - d[0]) * k) / 255
        return (0.1 - B) / (W - B), W

    lo, hi = 0.0, 1.0
    for _ in range(60):
        m = (lo + hi) / 2
        if probe(m)[0] > v: lo = m
        else: hi = m
    k = lo; W = probe(k)[1]
    L = (lum[0] + (lum[1] - lum[0]) * k) / 255
    edge = ' (at the curve\'s end: L only bounded)' if k < 1e-3 or k > 1 - 1e-3 else ''
    print('o1y %.4f -> k %.3f  W %.4f  L %.4f%s' % (v, k, W, L, edge))


if __name__ == '__main__':
    main()
