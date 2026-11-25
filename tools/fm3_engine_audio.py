"""A car's engine sound from FM3's own files, for Godot (2026-11-25).

    python tools/fm3_engine_audio.py <car MediaName> [--game <FM3-files\\game>] [--out out/audio]

Chain (FM3-files CATALOGUE.md "Audio"): Data_Car.MediaName -> its stock engine (List_UpgradeEngine IsStock = 1 ->
Data_Engine.MediaName) -> Media\\Audio\\cars\\Engines\\EngineTuning\\<engine>_ET.xml -> for each layer (Exhaust,
EngineIntake, EngineAmbient; upgrade level L0) a HarmonicTuning\\<x>_HT.xml -> its sound bank
Engines\\Soundbanks\\LOD1\\<bank>.fsb. Writes out/audio/<car>/: the bank's loops as WAV (fsb_extract.py's decode: XMA ->
PCM by FFmpeg) and engine.json, the recipe the viewer plays (fm3_engine_audio.gd): idle / redline rpm, volumes, and per
layer its loops (rpm_min, rpm_sample, rpm_max, volume, file) and its gain curve (PhysicsCoeff weights of rpm, throttle,
positive / negative torque -> a three-point curve).
"""
import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import wave
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BASE = os.path.dirname(os.path.dirname(ROOT))
sys.path.insert(0, os.path.join(BASE, 'FM3-files', 'tools'))
import fsb_extract  # noqa: E402


def find(folder, name):
    """A file in folder by name, ignoring case (the game's paths are case-insensitive)."""
    low = name.lower()
    for f in os.listdir(folder):
        if f.lower() == low:
            return os.path.join(folder, f)
    return None


def engine_of(game, car):
    dbs = [os.path.join(game, 'Media', 'DB', 'gamedb.slt')]
    dbs += sorted(os.path.join(game, 'Media', 'DB', 'patch', f) for f in os.listdir(os.path.join(game, 'Media', 'DB', 'patch'))
                  if f.endswith('_merge.slt'))
    for p in dbs:
        c = sqlite3.connect('file:%s?mode=ro' % p.replace('\\', '/'), uri=True)
        try:
            row = c.execute('select Id from Data_Car where lower(MediaName) = ?', (car.lower(),)).fetchone()
            if not row:
                continue
            e = c.execute('select EngineID from List_UpgradeEngine where Ordinal = ? and IsStock = 1', (row[0],)).fetchone()
            if not e:
                continue
            for q in dbs:
                m = sqlite3.connect('file:%s?mode=ro' % q.replace('\\', '/'), uri=True).execute(
                    'select MediaName from Data_Engine where EngineID = ?', (e[0],)).fetchone()
                if m:
                    return m[0]
        except sqlite3.Error:
            continue
    return None


def curve(el):
    """{'coeff': [rpm, throttle, pos torque, neg torque], 'curve': [x0, y0, x1, y1, x2, y2]} of a PhysicsCoeff +
    ThreePointCurve pair, or None."""
    if el is None:
        return None
    pc, tc = el.find('PhysicsCoeff'), el.find('ThreePointCurve')
    if pc is None or tc is None:
        return None
    return {'coeff': [float(pc.get(k, 0)) for k in ('RPM', 'Throttle', 'PosTorque', 'NegTorque')],
            'curve': [float(tc.get(k, 0)) for k in ('x0', 'y0', 'x1', 'y1', 'x2', 'y2')]}


def _curve(c, x):
    k = c['curve']
    if x <= k[2]:
        return k[1] + (k[3] - k[1]) * min(max((x - k[0]) / max(k[2] - k[0], 1e-5), 0.0), 1.0)
    return k[3] + (k[5] - k[3]) * min(max((x - k[2]) / max(k[4] - k[2], 1e-5), 0.0), 1.0)


def preview(recipe, out_dir, seconds=12.0, rate=48000):
    """engine_preview.wav: a sweep idle -> redline -> idle at full then no throttle, mixed by the same rules as
    fm3_engine_audio.gd (crossfades, pitch = rpm / rpm_sample, the layers' gain curves): to hear the result."""
    import numpy as np
    n = int(seconds * rate)
    t = np.arange(n) / rate
    idle, red = recipe['idle'], recipe['redline']
    up = t < seconds / 2
    rpm = np.where(up, idle + (red - idle) * (t / (seconds / 2)) ** 0.8, red - (red - idle) * ((t - seconds / 2) / (seconds / 2)) ** 0.6)
    throttle = np.where(up, 1.0, 0.0)
    rn = np.clip((rpm - idle) / (red - idle), 0, 1)
    mix = np.zeros(n)

    def inp(c):
        w = c['coeff']
        return np.clip(w[0] * rn + w[1] * throttle + w[2] * np.maximum(throttle - 0.5, 0) * 2 + 0.0 * w[3], 0, 1)
    glob = np.vectorize(lambda x: _curve(recipe['global_volume'], x))(inp(recipe['global_volume'])) if recipe.get('global_volume') else 1.0
    for layer in recipe['layers']:
        g = np.vectorize(lambda x: _curve(layer['gain'], x))(inp(layer['gain'])) if layer.get('gain') else 1.0
        for lp in layer['loops']:
            lo, hi, smp = lp['rpm_min'], lp['rpm_max'], lp['rpm_sample']
            w = ((rpm >= lo) & (rpm <= hi)).astype(float)
            if lo > 500:
                w = np.where(rpm < smp, w * np.clip((rpm - lo) / max(smp - lo, 1), 0, 1), w)
            if hi < 20000:
                w = np.where(rpm > smp, w * np.clip((hi - rpm) / max(hi - smp, 1), 0, 1), w)
            if w.max() <= 0:
                continue
            with wave.open(os.path.join(out_dir, lp['file'])) as f:
                a = np.frombuffer(f.readframes(f.getnframes()), np.int16).astype(float) / 32768.0
                if f.getnchannels() == 2:
                    a = a.reshape(-1, 2).mean(1)
            phase = np.cumsum(rpm / smp * lp['rate'] / rate) % len(a)
            i0 = phase.astype(int)
            frac = phase - i0
            s = a[i0] * (1 - frac) + a[(i0 + 1) % len(a)] * frac
            mix += s * w * lp['volume'] * g * glob * recipe['engine_volume']
    mix /= max(np.abs(mix).max(), 1e-6) * 1.12
    p = os.path.join(out_dir, 'engine_preview.wav')
    with wave.open(p, 'wb') as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes((mix * 32767).astype(np.int16).tobytes())
    print('preview:', p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('car')
    ap.add_argument('--preview', action='store_true')
    ap.add_argument('--game', default=os.path.join(BASE, 'FM3-files', 'game'))
    ap.add_argument('--out', default=os.path.join(ROOT, 'out', 'audio'))
    a = ap.parse_args()
    eng_dir = os.path.join(a.game, 'Media', 'Audio', 'cars', 'Engines')
    engine = engine_of(a.game, a.car)
    if not engine:
        print('no stock engine for', a.car)
        return 1
    et_path = find(os.path.join(eng_dir, 'EngineTuning'), engine + '_ET.xml')
    if not et_path:
        print('no EngineTuning for', engine)
        return 1
    et = ET.parse(et_path).getroot()
    s = et.find('EngineSettings')
    vol = et.find('VolumeAdjustments')
    out_dir = os.path.join(a.out, a.car)
    os.makedirs(out_dir, exist_ok=True)
    recipe = {'car': a.car, 'engine': engine, 'idle': float(s.get('audio_rpm_idle', 800)),
              'redline': float(s.get('audio_rpm_redline', 7000)),
              'engine_volume': float(vol.get('EngineVolume', 1)) if vol is not None else 1.0,
              'global_volume': curve(et.find('GlobalCarVolume')), 'layers': []}
    for layer in ('Exhaust', 'EngineIntake', 'EngineAmbient'):
        up = et.find(layer + '/Upgrade')
        if up is None or not up.get('L0'):
            continue
        ht_path = find(os.path.join(eng_dir, 'HarmonicTuning'), up.get('L0'))
        if not ht_path:
            print('missing', up.get('L0'))
            continue
        ht = ET.parse(ht_path).getroot()
        bank = find(os.path.join(eng_dir, 'Soundbanks', 'LOD1'), ht.get('name'))
        if not bank:
            print('missing bank', ht.get('name'))
            continue
        snd = fsb_extract.sounds(bank)
        gain = curve(ht.find('DSP/Volume/Gain'))
        for group in ht:
            loops = group.findall('Loop')
            if not loops:
                continue
            L = {'name': '%s/%s' % (layer, group.tag), 'gain': gain, 'loops': []}
            for lp in loops:
                i = int(lp.get('wavebankindex'))
                name, samples, ssize, rate, ch, mode, ls, le, data = snd[i]
                stem = '%s_%02d' % (os.path.splitext(os.path.basename(bank))[0], i)
                w = os.path.join(out_dir, stem + '.wav')
                if not os.path.exists(w):
                    x = w[:-4] + '.xma'
                    open(x, 'wb').write(fsb_extract.riff_xma1(data, rate, ch))
                    subprocess.run([fsb_extract.FFMPEG, '-hide_banner', '-loglevel', 'error', '-y', '-i', x, w], check=True)
                    os.remove(x)
                L['loops'].append({'file': os.path.basename(w), 'rpm_min': float(lp.get('rpm_min')),
                                   'rpm_sample': float(lp.get('rpm_sample')), 'rpm_max': float(lp.get('rpm_max')),
                                   'volume': float(lp.get('volume', 1)), 'samples': samples, 'rate': rate})
            recipe['layers'].append(L)
    with open(os.path.join(out_dir, 'engine.json'), 'w', newline='\n') as f:
        json.dump(recipe, f, indent=1)
    if '--preview' in sys.argv:
        preview(recipe, out_dir)
    print('%s: engine %s, %d layers, %d loops -> %s' % (a.car, engine, len(recipe['layers']),
                                                       sum(len(l['loops']) for l in recipe['layers']), out_dir))


if __name__ == '__main__':
    raise SystemExit(main())
