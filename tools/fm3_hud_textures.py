r"""The in-race HUD's own textures as PNGs (2026-11-27).

The race HUD is the UI scene `Media\UI\scenes\ui4\947_hud.{bgf,bsg,fbf}` (its .fbf names every texture it uses as
`GAME:\MEDIA\UI\TEXTURES\I_MAP\I_HUD\*.TGA`, i.e. the `.xds` files of `Media\UI\Textures\I_Map\I_HUD`; that folder
is the live HUD set, not a leftover). The analog gauge: I_HUD_Tach_BKG (241 x 187: the dial's shaded body), I_HUD_Tach_RED
(180 x 180: the redline arc), I_HUD_Tach_Needle (11 x 42), I_HUD_ICON_Fuel, I_HUD_Fuel_Level (180 x 180: the fuel arc);
the panels: I_HUD_LapAndPlace_bkgd, I_HUD_RaceTime_{top,mid,btm}_bkgd. The scene's element names (GAUGE_ANALOG.RPM_ANALOG,
FUEL_ANALOG, TEXT_GEAR_ANALOG, Elements.RPM and MPH.Redline, I_HUD_MiniMap, CUSTREND_MINIMAP = the map is a custom
render, ...) are in the .bgf; the scene format (Anark: AnarkBGF) is not decoded, so where each piece sits and how the
redline arc is cut are still to be read from it.

usage: python tools/fm3_hud_textures.py <FM3-files>/game/Media/UI/Textures/I_Map/I_HUD out/hud_tex   (game data: out/ only)
"""
import os, struct, sys, zlib

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fm3_tex  # noqa: E402


def write_png(path, a):
    h, w, _ = a.shape
    raw = b''.join(b'\x00' + a[y].tobytes() for y in range(h))

    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    open(path, 'wb').write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
                           + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))


def main():
    src, dst = sys.argv[1], sys.argv[2]
    os.makedirs(dst, exist_ok=True)
    for f in sorted(os.listdir(src)):
        if not f.lower().endswith('.xds'):
            continue
        h = fm3_tex.xds_header(open(os.path.join(src, f), 'rb').read())
        try:
            a = fm3_tex.load_xds(os.path.join(src, f))
            write_png(os.path.join(dst, f[:-4] + '.png'), np.ascontiguousarray(a.astype(np.uint8)))
            print('%-34s %4d x %-4d format %d' % (f, h['w'], h['h'], h['format']))
        except Exception as e:  # (a format fm3_tex does not decode yet)
            print('%-34s %4d x %-4d format %d: not decoded (%s)' % (f, h['w'], h['h'], h['format'], e))


if __name__ == '__main__':
    main()
