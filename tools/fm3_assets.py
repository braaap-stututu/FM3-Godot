"""fm3_assets.py: FM3's own asset files as the authority for what a captured draw is.

Car models (.carbin, from Media/Cars/*.zip, extracted with tools/fm3unzip) keep each mesh section as a material name
record (u32 2, u32 length, name, u32 1, parameters) followed by its index list (big-endian u16, 0xFFFF restarts). The
game uploads those index lists unchanged, so a captured draw's index buffer is found verbatim in a .carbin, and the
material record before it names the draw's material (body, rubber_trim, chrome, window, black_glass, ...).

    lib = CarLibrary(carbin_dir)          # indexes every *.carbin (memory-mapped search)
    car, material = lib.identify(index_bytes)
"""
import bisect
import glob
import os
import re

_REC = re.compile(rb'\x00\x00\x00\x02\x00\x00\x00([\x04-\x40])([a-z][a-z0-9_]{3,63})\x00\x00\x00\x01')


class CarLibrary:
    def __init__(self, carbin_dir, *more_dirs):
        self.cars = {}
        paths = []
        for dr in (carbin_dir,) + more_dirs:
            paths += sorted(glob.glob(os.path.join(dr, '*.carbin')))
        for path in paths:
            data = open(path, 'rb').read()
            recs = [(m.start(), m.group(2).decode()) for m in _REC.finditer(data) if m.group(1)[0] == len(m.group(2))]
            if recs:
                key = os.path.splitext(os.path.basename(path))[0]
                if 'wheels' in os.path.basename(os.path.dirname(path)).lower():
                    key = 'wheel:' + key
                self.cars[key] = (data, [o for o, _ in recs], [n for _, n in recs])
        self.cache = {}

    def identify(self, index_bytes, vertex_bytes=b'', prefer=None):
        """(car, material) for a draw's index buffer bytes, or (None, None). The index probe is up to 256 bytes; when a
        vertex buffer is given, a 64-byte piece of it must be in the same file too (short index lists like 0, 1, 2, ...
        occur in many cars). `prefer` (a car name) is tried first."""
        probe = bytes(index_bytes[:256])
        vprobe = bytes(vertex_bytes[64:128]) if len(vertex_bytes) >= 128 else b''
        if len(probe) < 32:
            return None, None
        key = (probe, vprobe)
        if key in self.cache:
            return self.cache[key]
        order = ([prefer] if prefer in self.cars else []) + [c for c in self.cars if c != prefer]
        res = (None, None)
        for car in order:
            data, offs, names = self.cars[car]
            i = data.find(probe)
            if i >= 0 and (not vprobe or data.find(vprobe) >= 0):
                k = bisect.bisect_right(offs, i) - 1
                res = (car, names[k] if k >= 0 else None)
                break
        self.cache[key] = res
        return res
