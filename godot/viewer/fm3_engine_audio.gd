## FM3's engine sound in Godot (2026-11-25): the recipe tools/fm3_engine_audio.py makes from the game's own files
## (EngineTuning -> HarmonicTuning -> the FSB loops, decoded to WAV) played as FMOD's harmonic engine does: per layer
## (exhaust left / right, intake, engine bay) a set of loops each recorded at one rpm (rpm_sample) and used over
## rpm_min..rpm_max, neighbours crossfading where their ranges overlap, each pitched by rpm / rpm_sample; the layer's
## gain from its curve (PhysicsCoeff: weights of normalised rpm, throttle, positive / negative torque, summed into a
## three-point curve). Not yet: the DSP blocks (expander, load EQs), burbles / backfires, intake chuff.
##   var e := FM3EngineAudio.new(); add_child(e); e.load_recipe("res://../out/audio/<car>/engine.json")
##   each frame: e.rpm = ...; e.throttle = ...
class_name FM3EngineAudio
extends Node3D

var rpm := 800.0
var throttle := 0.0
var neg_torque := 0.0
var master_db := 0.0
var _recipe := {}
var _players := []  # [AudioStreamPlayer3D, loop dict, layer dict]
var _rpm_smooth := -1.0


func load_recipe(path: String) -> bool:
	if not FileAccess.file_exists(path):
		return false
	var r = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not (r is Dictionary):
		return false
	_recipe = r
	var dir := path.get_base_dir()
	for layer in r["layers"]:
		for lp in layer["loops"]:
			var s := AudioStreamWAV.load_from_file(dir.path_join(lp["file"]))
			if s == null:
				continue
			s.loop_mode = AudioStreamWAV.LOOP_FORWARD
			s.loop_begin = 0
			s.loop_end = int(lp["samples"])
			var p := AudioStreamPlayer3D.new()
			p.stream = s
			p.volume_db = -80.0
			p.unit_size = 8.0
			p.max_distance = 300.0
			p.autoplay = true  # (starts when in the tree: a recipe may load before the node is added)
			add_child(p)
			if p.is_inside_tree():
				p.play()
			_players.append([p, lp, layer])
	rpm = float(r["idle"])
	return not _players.is_empty()


static func _curve(c, x: float) -> float:
	# FMOD Designer's three-point curve: piecewise linear through (x0, y0), (x1, y1), (x2, y2)
	var k: Array = c["curve"]
	if x <= k[2]:
		return lerpf(k[1], k[3], clampf((x - k[0]) / maxf(k[2] - k[0], 1e-5), 0.0, 1.0))
	return lerpf(k[3], k[5], clampf((x - k[2]) / maxf(k[4] - k[2], 1e-5), 0.0, 1.0))


func _input_of(c) -> float:
	var idle := float(_recipe["idle"])
	var red := float(_recipe["redline"])
	var rn := clampf((_rpm_smooth - idle) / maxf(red - idle, 1.0), 0.0, 1.0)
	var w: Array = c["coeff"]
	return clampf(w[0] * rn + w[1] * throttle + w[2] * maxf(throttle - 0.5, 0.0) * 2.0 + w[3] * neg_torque, 0.0, 1.0)


func _process(delta: float) -> void:
	if _players.is_empty():
		return
	# (a steady, smoothed rpm: the stream's values arrive in steps)
	_rpm_smooth = rpm if _rpm_smooth < 0.0 else lerpf(_rpm_smooth, rpm, 1.0 - exp(-delta * 30.0))
	var r := _rpm_smooth
	var global := 1.0
	if _recipe.get("global_volume") is Dictionary:
		global = _curve(_recipe["global_volume"], _input_of(_recipe["global_volume"]))
	var ev := float(_recipe.get("engine_volume", 1.0))
	for e in _players:
		var p: AudioStreamPlayer3D = e[0]
		var lp: Dictionary = e[1]
		var layer: Dictionary = e[2]
		var lo := float(lp["rpm_min"])
		var hi := float(lp["rpm_max"])
		var w := 0.0
		if r >= lo and r <= hi:
			w = 1.0
			# crossfade over the overlap with the neighbours: fade in from rpm_min to the sample rpm's side, out to rpm_max
			var smp := float(lp["rpm_sample"])
			if r < smp and lo > 500.0:
				w = clampf((r - lo) / maxf(smp - lo, 1.0), 0.0, 1.0)
			elif r > smp and hi < 20000.0:
				w = clampf((hi - r) / maxf(hi - smp, 1.0), 0.0, 1.0)
		if w <= 0.001:
			p.volume_db = -80.0
			continue
		var g := 1.0
		if layer.get("gain") is Dictionary:
			g = _curve(layer["gain"], _input_of(layer["gain"]))
		var v := w * float(lp["volume"]) * g * global * ev
		p.volume_db = linear_to_db(maxf(v, 1e-4)) + master_db
		p.pitch_scale = clampf(r / float(lp["rpm_sample"]), 0.25, 4.0)
