"""fm3_fxobj.py: the constant tables inside FM3's shader effect files (Media\\Shaders\\Cars\\shaders_v11.fxobj), with
their parameters' defaults (PLAN-CARS.md phase 0: the window glass and paint parameters no car overrides in its
shadersettings.xml come from here).

Each shader in the effect carries a D3DX constant table (big-endian; no 'CTAB' tag in FM3's file): a 28-byte header
(u32 Size = 0x1C, Creator offset, Version (0xFFFF03xx pixel / 0xFFFE03xx vertex), Constants, ConstantInfo offset,
Flags, Target offset), then per constant 20 bytes: Name offset, u16 RegisterSet, u16 RegisterIndex, u16 RegisterCount,
u16 reserved, TypeInfo offset, DefaultValue offset (all offsets from the header). TypeInfo: u16 Class, Type, Rows,
Columns, Elements, StructMembers, u32 members offset. Defaults: Rows x 4 floats (each row padded to a vec4).

    python tools/fm3_fxobj.py <shaders_v11.fxobj> [name ...]   (every table's parameters, or the named ones' defaults)
"""
import struct
import sys

SETS = {0: 'bool', 1: 'int', 2: 'float', 3: 'sampler'}


def _cstr(d, o):
    e = d.find(b'\0', o)
    return d[o:e].decode('ascii', 'replace') if 0 <= o < len(d) and e > o else None


def tables(d):
    """Every constant table: [{'at', 'kind' ('ps'/'vs'), 'constants': [{name, set, register, count, class, type,
    rows, columns, elements, default (floats or None)}]}]."""
    out = []
    o = 0
    while True:
        o = d.find(b'\x00\x00\x00\x1c', o)
        if o < 0 or o + 28 > len(d):
            break
        size, creator, version, n, info, flags, target = struct.unpack_from('>7I', d, o)
        base = o
        o += 4
        if version >> 16 not in (0xFFFF, 0xFFFE) or not (0 < n < 512) or info >= 0x10000:
            continue
        consts = []
        ok = True
        for k in range(n):
            p = base + info + 20 * k
            if p + 20 > len(d):
                ok = False
                break
            name_o, rset, reg, cnt, _res, ti, dv = struct.unpack_from('>I4H2I', d, p)
            name = _cstr(d, base + name_o)
            if not name or not name.replace('_', 'a').replace('[', 'a').replace(']', 'a').isalnum() or ti == 0:
                ok = False
                break
            cls, typ, rows, cols, elems, members = struct.unpack_from('>6H', d, base + ti)
            default = None
            if dv:
                nf = 4 * max(rows, 1) * max(elems, 1)
                default = list(struct.unpack_from(f'>{nf}f', d, base + dv))
            consts.append({'name': name, 'set': SETS.get(rset, rset), 'register': reg, 'count': cnt, 'class': cls,
                           'type': typ, 'rows': rows, 'columns': cols, 'elements': elems, 'default': default})
        if ok and consts:
            out.append({'at': base, 'kind': 'ps' if version >> 16 == 0xFFFF else 'vs', 'constants': consts})
    return out


def main():
    d = open(sys.argv[1], 'rb').read()
    want = sys.argv[2:]
    ts = tables(d)
    print(f'{len(ts)} constant tables ({sum(t["kind"] == "ps" for t in ts)} pixel, {sum(t["kind"] == "vs" for t in ts)} vertex)')
    seen = {}
    for t in ts:
        for c in t['constants']:
            if want and c['name'] not in want:
                continue
            val = None if c['default'] is None else tuple(round(x, 4) for x in c['default'][:max(c['columns'], 1)])
            seen.setdefault((c['name'], val), []).append((t['at'], c['set'], c['register']))
    for (name, val), where in sorted(seen.items(), key=lambda kv: kv[0][0]):
        print(f'{name:28s} default {val}  in {len(where)} tables (first at {where[0][0]:#x}, {where[0][1]} c{where[0][2]})')


if __name__ == '__main__':
    raise SystemExit(main())
