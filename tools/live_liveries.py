"""live_liveries.py: every car's livery texture from the running game, as PNGs the live viewer applies (LIVE.md).

    python tools/live_liveries.py <FM3 run dir (its fm3.log)> <gamedb.slt> <out dir> [car_name:colour ... | viewer.log]

The game paints each car with its livery layer t0 (fm3_carpaint: t0 laid over the database colour c118 by its alpha):
for the player that holds the custom paint (the CR-X's yellow; the car object keeps only the database colour, red,
PLAN-CARS). The tool asks ReGPU's debug server (TCP 7341, play.cmd turns it on) for a one-frame trace ("capture"),
reads every car-paint draw (ps e41e183a423e6f1b) from fm3.log: its t0 fetch constant and its c118, reads the texture
from guest memory ("peek", physical memory through the A0000000 mirror), decodes it (fm3_tex: Xenos tiling, DXT) and
names it by its car: c118 is that car's Combo_Colors RGB (the cars given as name:colour, e.g. from the viewer's FM3N
log; without them every car of the database is a candidate). Writes <out>/<car>.png (RGBA: alpha = the livery's
coverage over the paint colour) and <out>/index.json; the viewer polls the folder.
"""
import json
import os
import re
import socket
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fm3_tex  # noqa: E402
import fir_read as fr  # noqa: E402

PAINT_PS = 'e41e183a423e6f1b'


class Debug:
    def __init__(self, port=7341):
        self.s = socket.create_connection(('127.0.0.1', port), timeout=70)
        self.f = self.s.makefile('rwb')

    def cmd(self, line):
        self.f.write((line + '\n').encode())
        self.f.flush()
        return json.loads(self.f.readline().decode())

    def peek(self, addr, size):
        out = bytearray()
        while size > 0:
            n = min(4096, size)
            out += bytes.fromhex(self.cmd(f'peek {addr:08X} {n}')['hex'])
            addr += n
            size -= n
        return bytes(out)


def paint_draws(log_lines):
    """[(t0 fetch dwords, c118)] of the paint draws in the newest trace."""
    out, cur = [], None
    for line in log_lines:
        if ' draw #' in line:
            cur = None
            if f'ps {PAINT_PS}' in line:
                m = re.search(r't0=\S+ (\d+)x(\d+)@([0-9A-F]+) .*?\[([0-9A-F ]+)\]', line)
                if m:
                    cur = {'w': int(m.group(1)), 'h': int(m.group(2)), 'fetch': [int(x, 16) for x in m.group(4).split()]}
                    out.append(cur)
        elif cur is not None and 'pc118 = ' in line:
            cur['c118'] = tuple(round(float(x), 4) for x in line.split('pc118 = ')[1].split()[:3])
    return out


def main():
    a = sys.argv[1:]
    if len(a) < 3:
        print(__doc__)
        return 2
    run, db_path, outdir = a[:3]
    wanted = []
    for x in a[3:]:
        if x.endswith('.log') and os.path.exists(x):  # the viewer's log: 'live car .. is <NAME> colour <n>'
            wanted += [[m.group(1), m.group(2)] for m in re.finditer(r'is (\S+) colour (\d+)', open(x, errors='replace').read())]
        else:
            wanted.append(x.split(':'))
    os.makedirs(outdir, exist_ok=True)
    log = os.path.join(run, 'fm3.log')
    start = os.path.getsize(log)
    dbg = Debug()
    dbg.cmd('capture')
    time.sleep(6)  # (the trace lands at the next frame; a traced frame is slow)
    with open(log, errors='replace') as f:
        f.seek(start)
        draws = paint_draws(f.read().splitlines())
    db = sqlite3.connect(db_path)
    q = ('SELECT dc.MediaName, cc.Sequence, cc.RGB FROM Combo_Colors cc JOIN Data_Car dc ON cc.Ordinal = dc.Id')
    rows = [(n.lower(), s, rgb) for n, s, rgb in db.execute(q)]
    if wanted:
        rows = [r for r in rows if any(r[0] == w[0].lower() and str(r[1]) == w[1] for w in wanted)]
    index, done = {}, set()
    for d in draws:
        if 'c118' not in d:
            continue
        rgb = tuple(round(v * 255) for v in d['c118'])
        cands = [r for r in rows if (((r[2] >> 16) & 255, (r[2] >> 8) & 255, r[2] & 255) == rgb)]
        if len(cands) != 1:
            continue
        car = cands[0][0]
        d0, d1 = d['fetch'][0], d['fetch'][1]
        base = d1 & 0xFFFFF000
        if car in done:
            continue
        fmt, endian = d1 & 0x3F, (d1 >> 6) & 3
        bpb = {18: 8, 19: 16, 20: 16, 6: 64}.get(fmt)
        if bpb is None:
            continue
        size = d['w'] * d['h'] * bpb // (16 if fmt in (18, 19, 20) else 16)
        data = dbg.peek(0xA0000000 + base, size)
        img = fm3_tex.decode(data, d['w'], d['h'], fmt, endian, tiled=bool(d0 >> 31),
                             pitch=((d0 >> 22) & 0x1FF) * 32 or None)
        if img is None:
            continue
        fr.write_png(os.path.join(outdir, car + '.png'), d['w'], d['h'], img.tobytes())
        index[car] = {'colour': cands[0][1], 'base': f'{base:08X}', 'format': fmt, 'size': [d['w'], d['h']]}
        done.add(car)
        print(f'{car} colour {cands[0][1]}: t0 {d["w"]}x{d["h"]} format {fmt} at {base:08X}')
    with open(os.path.join(outdir, 'index.json'), 'w', newline='\n') as f:
        json.dump(index, f, indent=1)
    print(f'{len(index)} liveries ({len(draws)} paint draws) -> {outdir}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
