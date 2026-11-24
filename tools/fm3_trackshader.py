"""fm3_trackshader.py: disassemble FM3's own track shaders from the game files (2026-11-24), no frame capture needed.

Every track zip carries its shaders as effect files, shaders\\track\\<NAME>.fxobj (unpacked by build_track.ps1 to
work\\assets\\tracks\\<track>\\shaders\\track). Each holds Xbox 360 shader containers (big-endian):

    u32 magic (0x102A1100 pixel, 0x102A1101 vertex), u32 data offset, u32 data size, u32 0, u32 0x24,
    u32 info offset, u32 code-info offset, u32 0; the D3DX constant table at +0x28 (fm3_fxobj.tables)
    at code-info: u32 code offset within the data, u32 code size
    data: the literal constants (16-byte float vectors, numbered down to c255), then the microcode

The microcode is the same Xenos code a capture holds (fir_disasm.disasm). A material's parameter vectors are the
pixel shader's constants c0..cN by register (the table names them: e.g. TextureMap_4903_uvOS = c120); slot k reads
material slot k, slot 7 is the lightmap, c247 / c248 the static light (TrackSettings DarkColor / LightColor).

    python tools/fm3_trackshader.py <shader.fxobj> [--vs] [--all]   (pixel shaders; --vs also vertex; --all every
                                                                    variant, else the plain one: the fewest constants)
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fm3_fxobj  # noqa: E402
import fir_disasm  # noqa: E402


def containers(d):
    """[{'at', 'kind', 'constants', 'literals' {reg: (x,y,z,w)}, 'words'}] for every shader container in the file."""
    tabs = {t['at']: t for t in fm3_fxobj.tables(d)}
    out, o = [], 0
    while True:
        o = d.find(b'\x10\x2a\x11', o)
        if o < 0 or o + 32 > len(d):
            break
        magic, doff, dsize, _, _, _, cinfo, _ = struct.unpack_from('>8I', d, o)
        if magic not in (0x102A1100, 0x102A1101) or not (0 < doff < 0x10000) or not (0 < dsize < 0x40000) \
                or o + cinfo + 8 > len(d):
            o += 1
            continue
        coff, csize = struct.unpack_from('>2I', d, o + cinfo)
        if coff > dsize or coff + csize > dsize or csize % 4:
            o += 1
            continue
        base = o + doff
        n_lit = coff // 16
        lits = {256 - n_lit + i: struct.unpack_from('>4f', d, base + 16 * i) for i in range(n_lit)}
        words = list(struct.unpack_from('<%dI' % (csize // 4), d, base + coff))
        t = tabs.get(o + 0x28) or next((tabs[a] for a in sorted(tabs) if o < a < o + doff), None)
        out.append({'at': o, 'kind': 'ps' if magic == 0x102A1100 else 'vs', 'constants': t['constants'] if t else [],
                    'literals': lits, 'words': words})
        o += 4
    return out


def describe(c):
    lines = []
    for k in sorted(c['constants'], key=lambda k: (k['set'], k['register'])):
        lines.append('  %-8s %s%d  %s%s' % (k['set'], 's' if k['set'] == 'sampler' else 'c', k['register'], k['name'],
                                           '  default %s' % [round(v, 4) for v in k['default'][:4]] if k.get('default') else ''))
    for r, v in sorted(c['literals'].items()):
        if any(v):
            lines.append('  literal  c%d  %s' % (r, [round(x, 4) for x in v]))
    try:
        lines += fir_disasm.disasm(c['words'])
    except Exception as e:  # (a vertex shader's fetches may not decode)
        lines.append('  (disassembly failed: %s)' % e)
    return lines


def plain_ps(cs):
    """The plain pixel shader of a file's containers: no shadow-map variant, not a depth / lightmap-only pass."""
    ps = [c for c in cs if c['kind'] == 'ps']
    full = [c for c in ps if 'TimeGain' not in [k['name'] for k in c['constants']] and len(c['words']) >= 30]
    return min(full, key=lambda c: len(c['constants'])) if full else None


_SIMPLE = {}


def simple_terms(path):
    """The base texture's terms in a single-texture shader, read from its plain pixel shader's code: {'uv0': param
    index (UV0 * P[k].xy: c120.zw * ck.xy, the TextureMap uvOS scale), 'gain': (param index, component) (the base
    texture times P[k].c)}; {} when the code has neither. c0..cN are the material's parameter vectors."""
    if path in _SIMPLE:
        return _SIMPLE[path]
    out = {}
    try:
        c = plain_ps(containers(open(path, 'rb').read()))
        lines = fir_disasm.disasm(c['words']) if c else []
    except Exception:
        lines = []
    import re
    for ln in lines:
        m = re.search(r'mul r\d+\.\w+ = c120\.\w+, c(\d+)\.\w+', ln)
        if m and int(m.group(1)) < 100 and 'uv0' not in out:
            out['uv0'] = int(m.group(1))
    t0 = None
    for ln in lines:
        m = re.search(r'tfetch r(\d+)\.\w+ <- t0 ', ln)
        if m:
            t0 = m.group(1)
        m = re.search(r'mul r\d+\.\w+ = r(\d+)\.xyzz, c(\d+)\.([xyzw])\3\3\3,', ln)
        if t0 is not None and m and m.group(1) == t0 and int(m.group(2)) < 100 and 'gain' not in out:
            out['gain'] = (int(m.group(2)), 'xyzw'.index(m.group(3)))
    _SIMPLE[path] = out
    return out


def main():
    a = [x for x in sys.argv[1:] if not x.startswith('--')]
    if not a:
        print(__doc__)
        return 2
    d = open(a[0], 'rb').read()
    cs = [c for c in containers(d) if c['kind'] == 'ps' or '--vs' in sys.argv]
    if '--all' not in sys.argv:
        ps = [c for c in cs if c['kind'] == 'ps']
        keep = min(ps, key=lambda c: (len(c['words']) < 30, len(c['constants'])), default=None) if ps else None
        # (the plain variant: no shadow map, still a full shader; the shortest ones are depth / lightmap-only passes)
        ps_full = [c for c in ps if 'TimeGain' not in [k['name'] for k in c['constants']] and len(c['words']) >= 30]
        keep = min(ps_full, key=lambda c: len(c['constants'])) if ps_full else keep
        cs = [c for c in cs if c['kind'] == 'vs' or c is keep]
    for c in cs:
        print('== %s at %d (%d words)' % (c['kind'], c['at'], len(c['words'])))
        print('\n'.join(describe(c)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
