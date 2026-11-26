"""fm3_car_lamps.py: <car>_lamps.json beside each built library car (2026-11-26), without rebuilding the library.

    python tools/fm3_car_lamps.py <car files dir (work/assets/cars)> <library dir (out/cars)> [car ...]

The car's own lamp parameters against Normal.xml's (fm3_track_export.lamp_params): reflection scale and Fresnel of its
reflectors / bulbs, brake and reverse lamp colours. fm3_car_library.py writes the same file when it builds a car.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fm3_track_export as tx  # noqa: E402


def main():
    a = sys.argv[1:]
    if len(a) < 2:
        print(__doc__)
        return 2
    cdir, lib = a[:2]
    tx.CAR_FILE_DIRS[:] = [cdir]
    cars = a[2:] or sorted(f[:-len('.gltf')] for f in os.listdir(lib) if f.endswith('.gltf'))
    n = 0
    for car in cars:
        zdir = os.path.join(cdir, car)
        if not os.path.isdir(zdir):
            continue
        with open(os.path.join(lib, car + '_lamps.json'), 'w', newline='\n') as f:
            json.dump(tx.lamp_params(zdir), f, indent=1)
        n += 1
    print(f'{n} cars')


if __name__ == '__main__':
    sys.exit(main())
