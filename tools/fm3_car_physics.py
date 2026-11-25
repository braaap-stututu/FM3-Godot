"""fm3_car_physics.py: a car's physics data from FM3's database, for a Godot car model (2026-11-25).

    python tools/fm3_car_physics.py <MediaName or Data_Car Id> [--db <gamedb.slt>] [--out <car>.json] [--check <camrec.npz>]

Writes the stock car's drivetrain and body numbers as JSON (SI units). What is checked against the running game, and
how (frame-ir LIVE.md "Physics in Godot"):
- engine torque: List_UpgradeEngineCamshaft (stock row: RedlineRPM, StallRPM, TorqueCurveMaxRPM, NumRPMEntriesArray,
  TorqueCurveFullThrottleID / ZeroThrottleID) -> List_TorqueCurve: NumRPMEntriesArray values over 0..TorqueCurveMaxRPM
  (100 rpm apart for 96 / 9500), times TorqueScale (N m). The full-throttle curve x scale is the game's own telemetry
  page's torque (CR-X: 145.2 / 151.45 / 150.8 N m at 6135 / 6826 / 7346 rpm, page 145.4 / 151.4 / 150.8), and power =
  torque x rad/s (116.0 kW, page 116). The zero-throttle curve is the engine braking (negative). How the game blends
  them by throttle: not checked.
- gearing: List_UpgradeDrivetrain (Ordinal = the car's Id) -> List_UpgradeDrivetrainTransmission (stock): ratios and
  the final drive. A profile's tuned car can differ (the test grid's CR-X: second gear within 3.4%, third 11% off).
- tyre radius from Data_Car's tyre size (CR-X 195/60 R14 = 0.2948 m = the wheel block's 0.295 in the running game).
Not checked yet: mass (Data_Car CurbWeight is in kN: 9.8 -> 999 kg), GameTorqueScale, the aero numbers' units.
--check <camrec.npz>: speed from rpm through each gear against the stream's speed (FM3E telemetry rows).
"""
import json
import math
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB = os.path.normpath(os.path.join(HERE, '..', '..', '..', 'FM3-files', 'game', 'Media', 'DB', 'gamedb.slt'))


def rows(c, sql, *args):
    cur = c.execute(sql, args)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def curve(c, cid):
    r = rows(c, 'SELECT * FROM List_TorqueCurve WHERE TorqueCurveID=?', cid)[0]
    n = int(r['NumTorqueValues'])
    vals = [r['v%d' % i] for i in range(n)]
    # (the last entry is a sentinel, -2.63 on every curve seen)
    return {'scale': r['TorqueScale'], 'values': vals[:-1] if vals and vals[-1] is not None and vals[-1] < -2 else vals}


def tyre_radius(width_mm, aspect, rim_in):
    return width_mm / 1000.0 * aspect / 100.0 + rim_in * 0.0254 / 2.0


def car_physics(c, key):
    car = rows(c, 'SELECT * FROM Data_Car WHERE MediaName=? OR Id=?', key, key)
    if not car:
        raise SystemExit('no car %r' % key)
    car = car[0]
    cid = car['Id']
    eng = rows(c, 'SELECT * FROM List_UpgradeEngine WHERE Ordinal=? AND IsStock=1', cid)[0]
    cam = rows(c, 'SELECT * FROM List_UpgradeEngineCamshaft WHERE EngineID=? AND IsStock=1', eng['EngineID'])[0]
    de = rows(c, 'SELECT * FROM Data_Engine WHERE EngineID=?', eng['EngineID'])[0]
    dt = rows(c, 'SELECT * FROM List_UpgradeDrivetrain WHERE Ordinal=? AND IsStock=1', cid)[0]
    tr = rows(c, 'SELECT * FROM List_UpgradeDrivetrainTransmission WHERE DrivetrainID=? AND IsStock=1',
              dt['DrivetrainID'])[0]
    ngear = int(tr['NumGears'])
    gears = [tr['GearRatio%d' % i] for i in range(ngear)]
    full, zero = curve(c, cam['TorqueCurveFullThrottleID']), curve(c, cam['TorqueCurveZeroThrottleID'])
    return {
        'car': car['MediaName'], 'id': cid, 'drive_type': car.get('DriveTypeID'),
        'mass_kg': car['CurbWeight'] * 1000.0 / 9.81, 'weight_front': car['WeightDistribution'],
        'engine': {'name': de['EngineName'].strip(), 'redline_rpm': cam['RedlineRPM'], 'stall_rpm': cam['StallRPM'],
                   'curve_max_rpm': cam['TorqueCurveMaxRPM'], 'inertia': de['MomentInertia'],
                   'torque_full': full, 'torque_zero': zero,
                   'game_torque_scale': car.get('GameTorqueScale')},
        'gearbox': {'reverse': gears[0], 'gears': gears[1:], 'final_drive': tr['FinalDriveRatio'],
                    'shift_time': tr['GearShiftTime'], 'inertia': tr['MomentInertia']},
        'tyre_radius_front': tyre_radius(car['FrontTireWidthMM'], car['FrontTireAspect'], car['FrontWheelDiameterIN']),
        'tyre_radius_rear': tyre_radius(car['RearTireWidthMM'], car['RearTireAspect'], car['RearWheelDiameterIN']),
        'aero': {k: car.get(k) for k in ('BodyAeroLongitudinalDrag', 'BodyAeroForwardDownforceFront',
                                         'BodyAeroForwardDownforceRear', 'GameDragScale')},
        'steer': {'max_angle': car.get('SteerMaxAngle'), 'max_rate': car.get('SteerMaxAngVelTurning')},
        'sim': {k: car.get(k) for k in ('SimPeakTorque', 'SimPeakTorqueAngVel', 'SimRedlineAngVel', 'SimTopSpeed')},
    }


def torque_at(curve_, max_rpm, rpm):
    v = curve_['values']
    x = max(0.0, min(rpm / max_rpm * (len(v)), len(v) - 1.0))
    i = int(x)
    j = min(i + 1, len(v) - 1)
    return (v[i] + (v[j] - v[i]) * (x - i)) * curve_['scale']


def check(p, npz):
    import numpy as np
    e = np.load(npz)['eng']
    rpm, gear, clu, spd = e[:, 1], e[:, 5], e[:, 6], e[:, 7]
    fd = p['gearbox']['final_drive']
    r = p['tyre_radius_front']
    for g, ratio in enumerate(p['gearbox']['gears'], 1):
        m = (gear == g) & (clu < 0.05) & (spd > 3)
        if m.sum() < 5:
            continue
        pred = rpm[m] * 2 * math.pi / 60 / (ratio * fd) * r
        print('gear %d: %d samples, speed from rpm / stream speed %.3f' % (g, m.sum(), float(np.median(pred / spd[m]))))


def main():
    a = sys.argv[1:]
    db = a[a.index('--db') + 1] if '--db' in a else DEFAULT_DB
    c = sqlite3.connect(db)
    p = car_physics(c, a[0])
    out = a[a.index('--out') + 1] if '--out' in a else None
    if out:
        with open(out, 'w', newline='\n') as f:
            json.dump(p, f, indent=1)
    e = p['engine']
    print('%s: %.0f kg, %d gears %s final %.3f, tyre r %.4f m, redline %.0f rpm' % (
        p['car'], p['mass_kg'], len(p['gearbox']['gears']), p['gearbox']['gears'], p['gearbox']['final_drive'],
        p['tyre_radius_front'], e['redline_rpm']))
    for rpm in (3000, 5000, 6135, 6826, 7346, 8000):
        t = torque_at(e['torque_full'], e['curve_max_rpm'], rpm)
        print('  %5d rpm: %6.1f N m full throttle, %6.1f kW; %6.1f N m closed' % (
            rpm, t, t * rpm * 2 * math.pi / 60 / 1000, torque_at(e['torque_zero'], e['curve_max_rpm'], rpm)))
    if '--check' in a:
        check(p, a[a.index('--check') + 1])


if __name__ == '__main__':
    main()
