# A race HUD drawn by Godot over the live mirror (2026-11-26; the user: "add the HUD elements, maybe customizable").
# Elements, each with its own place, size and on / off switch in a JSON file:
#   - tach:     a round tachometer (rpm against the car's redline, red zone), the gear in the middle, speed below
#   - speed:    a digital speed readout (km/h or mph)
#   - pedals:   throttle and brake bars
#   - map:      a track map built from the cars' own paths as they drive (no track file needed), a dot per car
#   - info:     the stream's state (game frames, latency) for debugging; off by default
# The data comes from the game's stream (world_view.gd: "FM3E" telemetry, the cars' matrices; v9 (2026-11-27): the race
# clock, the race position and the track segment the viewer counts laps from). The race's lap total is not in the
# stream: "total_laps" in the config.
# Two styles: "game" (default: the game's own layout, place / laps / round tach / map, see _draw_game) and "simple"
# (the elements below, each placed by anchor / offset / scale).
# Config: res://viewer/hud_default.json, overridden key by key by user://fm3_hud.json (and FM3_HUD_CONFIG=<path>);
# FM3_HUD=0 turns the HUD off, H toggles it while running.
extends Control

var cfg := {}
var speed_ms := -1.0
var rpm := -1.0
var redline := 8000.0
var gear := -1
var throttle := 0.0
var brake := 0.0
var cars := {}  # car -> Vector2 (world x, z)
var player := -1
var info := ""
var place := 0  # (the stream's race position, 1-based; 0 = not known)
var lap := -1  # (laps completed, as the game's "LAPS" counter; -1 = not known)
var race_time := -1.0
var lap_time := -1.0
var last_lap := -1.0
var best_lap := -1.0
var _trail := []  # the player's path (Vector2), the map's outline
var _bounds := Rect2()
# The map's outline from a whole lap driven before (user://fm3_map_<track>.json, written when a lap completes), so
# the map is there from the grid on, as the game's; the game's own line data (.seg / .irt / .geo) is not decoded yet.
var _outline := []
var _outline_bounds := Rect2()
var _track := ""
var _lap_seen := -1
var _lap_from := 0  # (the trail's index where the current lap began)
var _font: Font


func _ready() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	_font = ThemeDB.fallback_font
	cfg = _load("res://viewer/hud_default.json")
	for p in ["user://fm3_hud.json", OS.get_environment("FM3_HUD_CONFIG")]:
		if p != "" and FileAccess.file_exists(p):
			var o := _load(p)
			for k in o:
				if cfg.get(k) is Dictionary and o[k] is Dictionary:
					for kk in o[k]:
						cfg[k][kk] = o[k][kk]
				else:
					cfg[k] = o[k]


static func _load(p: String) -> Dictionary:
	var t = JSON.parse_string(FileAccess.get_file_as_string(p)) if FileAccess.file_exists(p) else null
	return t if t is Dictionary else {}


func _unhandled_input(e: InputEvent) -> void:
	if e is InputEventKey and e.pressed and not e.echo and e.keycode == KEY_H:
		visible = not visible


func feed(d: Dictionary) -> void:
	speed_ms = d.get("speed", speed_ms)
	rpm = d.get("rpm", rpm)
	if float(d.get("redline", 0.0)) > 1000.0:
		redline = d["redline"]
	gear = d.get("gear", gear)
	throttle = d.get("throttle", throttle)
	brake = d.get("brake", brake)
	cars = d.get("cars", cars)
	player = d.get("player", player)
	info = d.get("info", info)
	place = d.get("place", place)
	lap = d.get("lap", lap)
	race_time = d.get("race_time", race_time)
	lap_time = d.get("lap_time", lap_time)
	last_lap = d.get("last_lap", last_lap)
	best_lap = d.get("best_lap", best_lap)
	if String(d.get("track", "")) != "" and _track == "":
		_track = d["track"]
		var o := _load("user://fm3_map_%s.json" % _track)
		for q in o.get("points", []):
			var v := Vector2(float(q[0]), float(q[1]))
			_outline_bounds = Rect2(v, Vector2.ZERO) if _outline.is_empty() else _outline_bounds.expand(v)
			_outline.append(v)
	if lap != _lap_seen:
		if _lap_seen >= 1 and lap == _lap_seen + 1 and _track != "" and _trail.size() - _lap_from > 20:
			# (a whole lap: its path becomes the track's outline for later starts)
			var pts := []
			for i in range(_lap_from, _trail.size()):
				pts.append([snappedf((_trail[i] as Vector2).x, 0.1), snappedf((_trail[i] as Vector2).y, 0.1)])
			var f := FileAccess.open("user://fm3_map_%s.json" % _track, FileAccess.WRITE)
			if f != null:
				f.store_string(JSON.stringify({"points": pts}))
		_lap_seen = lap
		_lap_from = _trail.size()
	if cars.has(player):
		var p: Vector2 = cars[player]
		if _trail.is_empty() or (_trail[-1] as Vector2).distance_to(p) > 4.0:
			_trail.append(p)
			if _trail.size() > 4000:
				_trail.remove_at(0)
				_lap_from = maxi(_lap_from - 1, 0)
			_bounds = Rect2(p, Vector2.ZERO) if _trail.size() == 1 else _bounds.expand(p)
	queue_redraw()


func _el(name: String) -> Dictionary:
	var e = cfg.get(name, {})
	return e if e is Dictionary and bool(e.get("enabled", true)) else {}


# An element's top-left corner from its anchor ("tl", "tr", "bl", "br") and offset, in pixels at its scale.
func _origin(e: Dictionary, sz: Vector2) -> Vector2:
	var a := String(e.get("anchor", "tl"))
	var off: Array = e.get("offset", [20, 20])
	var s := get_viewport_rect().size  # (under a CanvasLayer the Control's anchors do not resolve: its size stays 0)
	var x := float(off[0]) if a.ends_with("l") else s.x - sz.x - float(off[0])
	var y := float(off[1]) if a.begins_with("t") else s.y - sz.y - float(off[1])
	return Vector2(x, y)


func _col(e: Dictionary, k: String, d: Color) -> Color:
	var c = e.get(k)
	return Color(c[0], c[1], c[2], c[3] if c.size() > 3 else 1.0) if c is Array else d


# mm:ss.mmm, as the game's HUD
static func _clock_text(t: float) -> String:
	if t < 0.0:
		return "--:--.---"
	var ms := int(round(t * 1000.0))
	return "%02d:%02d.%03d" % [ms / 60000, (ms / 1000) % 60, ms % 1000]


func _speed_text(e: Dictionary) -> String:
	if speed_ms < 0.0:
		return "--"
	var mph := String(e.get("units", cfg.get("units", "kmh"))) == "mph"
	return "%d" % roundi(speed_ms * (2.23694 if mph else 3.6))


func _draw() -> void:
	if String(cfg.get("style", "game")) == "game":
		_draw_game()
		return
	var units := String(cfg.get("units", "kmh"))
	var e := _el("tach")
	if not e.is_empty():
		var k := float(e.get("scale", 1.0))
		var r := 90.0 * k
		var o := _origin(e, Vector2(2 * r, 2 * r))
		var c := o + Vector2(r, r)
		draw_circle(c, r, _col(e, "back", Color(0, 0, 0, 0.55)))
		var a0 := deg_to_rad(135.0)
		var sweep := deg_to_rad(270.0)
		var top := ceilf(redline / 1000.0 + 0.5) * 1000.0
		var red_from := a0 + sweep * clampf(redline / top, 0.0, 1.0)
		draw_arc(c, r * 0.86, red_from, a0 + sweep, 24, Color(0.85, 0.1, 0.1), 6.0 * k)
		for i in int(top / 1000.0) + 1:
			var a := a0 + sweep * (float(i) * 1000.0 / top)
			var d := Vector2(cos(a), sin(a))
			draw_line(c + d * r * 0.78, c + d * r * 0.92, Color.WHITE, 2.0 * k)
			draw_string(_font, c + d * r * 0.64 - Vector2(6, -6) * k, str(i), HORIZONTAL_ALIGNMENT_LEFT, -1, int(14 * k))
		if rpm >= 0.0:
			var a := a0 + sweep * clampf(rpm / top, 0.0, 1.0)
			draw_line(c, c + Vector2(cos(a), sin(a)) * r * 0.85, Color(1.0, 0.35, 0.1), 3.0 * k)
		draw_circle(c, 6.0 * k, Color(0.2, 0.2, 0.2))
		var g := "N" if gear == 0 else ("R" if gear < 0 and gear != -1 else ("-" if gear == -1 else str(gear)))
		draw_string(_font, c + Vector2(-14, 18) * k, g, HORIZONTAL_ALIGNMENT_CENTER, 28 * k, int(34 * k))
		draw_string(_font, c + Vector2(-45, 52) * k, _speed_text(e) + (" mph" if units == "mph" else " km/h"), HORIZONTAL_ALIGNMENT_CENTER, 90 * k, int(14 * k))
	e = _el("speed")
	if not e.is_empty():
		var k := float(e.get("scale", 1.0))
		var sz := Vector2(150, 60) * k
		var o := _origin(e, sz)
		draw_rect(Rect2(o, sz), _col(e, "back", Color(0, 0, 0, 0.45)))
		draw_string(_font, o + Vector2(10, 44) * k, _speed_text(e), HORIZONTAL_ALIGNMENT_LEFT, -1, int(40 * k))
		draw_string(_font, o + Vector2(100, 44) * k, "mph" if units == "mph" else "km/h", HORIZONTAL_ALIGNMENT_LEFT, -1, int(14 * k))
	e = _el("pedals")
	if not e.is_empty():
		var k := float(e.get("scale", 1.0))
		var sz := Vector2(40, 120) * k
		var o := _origin(e, sz)
		for i in 2:
			var v := throttle if i == 0 else brake
			var rr := Rect2(o + Vector2(i * 22, 0) * k, Vector2(16, 120) * k)
			draw_rect(rr, Color(0, 0, 0, 0.45))
			var h := rr.size.y * clampf(v, 0.0, 1.0)
			draw_rect(Rect2(rr.position + Vector2(0, rr.size.y - h), Vector2(rr.size.x, h)), Color(0.2, 0.85, 0.3) if i == 0 else Color(0.9, 0.2, 0.2))
	e = _el("map")
	if not e.is_empty() and _trail.size() > 1:
		var k := float(e.get("scale", 1.0))
		var sz := Vector2(200, 200) * k
		var o := _origin(e, sz)
		draw_rect(Rect2(o, sz), _col(e, "back", Color(0, 0, 0, 0.35)))
		var b := _bounds.grow(10.0)
		var f := minf(sz.x / maxf(b.size.x, 1.0), sz.y / maxf(b.size.y, 1.0))
		var mid := o + sz * 0.5
		var to := func(p: Vector2) -> Vector2: return mid + (p - b.get_center()) * f
		var pts := PackedVector2Array()
		for p in _trail:
			pts.append(to.call(p))
		draw_polyline(pts, Color(1, 1, 1, 0.7), 2.0 * k)
		for car in cars:
			draw_circle(to.call(cars[car]), (5.0 if car == player else 3.5) * k, Color(1.0, 0.8, 0.1) if car == player else Color(0.3, 0.6, 1.0))
	e = _el("info")
	if not e.is_empty():
		draw_string(_font, _origin(e, Vector2(400, 20)) + Vector2(0, 16), info, HORIZONTAL_ALIGNMENT_LEFT, -1, 14)


# The game's own HUD layout (style "game"; measured from the game's 1280 x 720 picture on the CrownJewel grid): the
# position panel top left, laps and lap time top right, the round tach bottom right (0-10 x 1000 rpm over 222 degrees
# clockwise from straight down, red from the redline, the gear in the middle, km/h at its lower left), the track map
# bottom left with a green arrow for the player. Drawn in 1280 x 720 units scaled to the window. Race position, laps
# and lap time are not in the stream yet: shown as "-".
func _draw_game() -> void:
	var vs := get_viewport_rect().size
	var u := minf(vs.x / 1280.0, vs.y / 720.0)
	var off := Vector2((vs.x - 1280.0 * u) * 0.5, (vs.y - 720.0 * u) * 0.5)
	var P := func(x: float, y: float) -> Vector2: return off + Vector2(x, y) * u
	var white := Color(1, 1, 1, 0.95)
	var panel := Color(0.08, 0.1, 0.14, 0.55)
	var e := _el("place")
	if not e.is_empty():
		draw_rect(Rect2(P.call(60, 33), Vector2(350, 44) * u), panel)
		draw_string(_font, P.call(78, 70), str(place) if place > 0 else "-", HORIZONTAL_ALIGNMENT_LEFT, -1, int(34 * u), white)
		draw_string(_font, P.call(104, 56), "/" + str(cfg.get("cars", cars.size() if cars.size() > 0 else "-")), HORIZONTAL_ALIGNMENT_LEFT, -1, int(17 * u), white)
		draw_string(_font, P.call(288, 61), "PLACE", HORIZONTAL_ALIGNMENT_LEFT, -1, int(15 * u), white)
	e = _el("laps")
	if not e.is_empty():
		draw_rect(Rect2(P.call(955, 33), Vector2(262, 44) * u), panel)
		draw_string(_font, P.call(962, 61), "LAPS", HORIZONTAL_ALIGNMENT_LEFT, -1, int(15 * u), white)
		draw_string(_font, P.call(1150, 70), str(lap) if lap >= 0 else "-", HORIZONTAL_ALIGNMENT_LEFT, -1, int(34 * u), white)
		draw_string(_font, P.call(1176, 56), "/" + str(cfg.get("total_laps", "-")), HORIZONTAL_ALIGNMENT_LEFT, -1, int(17 * u), white)
		draw_rect(Rect2(P.call(955, 79), Vector2(127, 22) * u), Color(0.05, 0.07, 0.1, 0.75))
		draw_rect(Rect2(P.call(1082, 79), Vector2(126, 22) * u), Color(0.1, 0.13, 0.17, 0.6))
		# (the game's rows: race time, then last, best and the current lap once there are any)
		var rows := [[race_time, "race"]]
		if last_lap >= 0.0:
			rows.append([last_lap, "last"])
		if best_lap >= 0.0:
			rows.append([best_lap, "best"])
		if lap_time >= 0.0 and rows.size() > 1:
			rows.append([lap_time, "lap"])
		for i in rows.size():
			var y := 79.0 + 22.0 * i
			if i > 0:
				draw_rect(Rect2(P.call(955, y), Vector2(253, 22) * u), Color(0.05, 0.07, 0.1, 0.5))
			draw_string(_font, P.call(962, y + 17), _clock_text(float(rows[i][0])), HORIZONTAL_ALIGNMENT_LEFT, -1, int(14 * u), white)
			draw_string(_font, P.call(1208 - 7 * String(rows[i][1]).length(), y + 17), String(rows[i][1]), HORIZONTAL_ALIGNMENT_LEFT, -1, int(13 * u), white)
	e = _el("tach")
	if not e.is_empty():
		# (the game's dial, measured on its grid shot 2026-11-27: a band of 25 segments at radius ~72-82, grey getting
		# lighter towards the redline and red past it, no disc behind it; the numbers inside the band; a thin fuel arc
		# on from 10 round to the pump icon at the lower right; a dark centre of radius ~39 with the gear; a short needle
		# from the centre's edge)
		var c: Vector2 = P.call(1121, 599)
		var a0 := deg_to_rad(95.0)
		var sweep := deg_to_rad(222.0)
		var top := 10000.0 if redline <= 10000.0 else ceilf(redline / 2000.0) * 2000.0  # (the game's dial: 0-10 for a 9,500 rpm CR-X)
		draw_arc(c, 77.0 * u, a0 - 0.02, a0 + sweep + 0.02, 64, Color(0.05, 0.06, 0.08, 0.35), 15.0 * u)
		var n_seg := 25  # (the game's: five between 8 and 10)
		var gap := deg_to_rad(1.6)
		for i in n_seg:
			var f0 := float(i) / n_seg
			var f1 := float(i + 1) / n_seg
			var col := Color(0.85, 0.12, 0.12, 0.95) if f1 * top > redline + 1.0 else Color.from_hsv(0.0, 0.0, lerpf(0.45, 0.92, f0), 0.95)
			draw_arc(c, 77.0 * u, a0 + sweep * f0 + gap * 0.5, a0 + sweep * f1 - gap * 0.5, 4, col, 9.0 * u)
		var fa0 := a0 + sweep + deg_to_rad(4.0)
		draw_arc(c, 79.0 * u, fa0, fa0 + deg_to_rad(58.0), 24, Color(0.85, 0.85, 0.88, 0.85), 3.0 * u)
		var pump: Vector2 = c + Vector2(cos(fa0 + deg_to_rad(66.0)), sin(fa0 + deg_to_rad(66.0))) * 80.0 * u
		draw_rect(Rect2(pump - Vector2(4, 5) * u, Vector2(8, 11) * u), Color(0.85, 0.85, 0.88, 0.85))
		draw_rect(Rect2(pump - Vector2(2.5, 3.5) * u, Vector2(5, 3) * u), Color(0.15, 0.15, 0.17, 0.9))
		for k in 6:
			var f := float(k) / 5.0
			var a := a0 + sweep * f
			var d := Vector2(cos(a), sin(a))
			draw_string(_font, c + d * 59.0 * u - Vector2(5, -5) * u, str(int(f * top / 1000.0)), HORIZONTAL_ALIGNMENT_LEFT, -1, int(13 * u), Color(0.85, 0.85, 0.88, 0.9))
		draw_circle(c, 40.0 * u, Color(0.16, 0.17, 0.19, 0.85))
		draw_circle(c, 37.0 * u, Color(0.08, 0.09, 0.11, 0.9))
		if rpm >= 0.0:
			var a := a0 + sweep * clampf(rpm / top, 0.0, 1.0)
			var d := Vector2(cos(a), sin(a))
			draw_line(c + d * 41.0 * u, c + d * 66.0 * u, Color(0.95, 0.12, 0.1), 5.0 * u)
		var g := "N" if gear == 0 else ("-" if gear < 0 else str(gear))
		draw_string(_font, c + Vector2(-16, 16) * u, g, HORIZONTAL_ALIGNMENT_CENTER, 32 * u, int(44 * u), white)
		var mph := String(cfg.get("units", "kmh")) == "mph"
		draw_string(_font, P.call(1006, 650), "MPH" if mph else "KM/H", HORIZONTAL_ALIGNMENT_LEFT, -1, int(13 * u), Color(1, 1, 1, 0.8))
		draw_string(_font, P.call(1012, 683), _speed_text(e), HORIZONTAL_ALIGNMENT_LEFT, -1, int(26 * u), white)
	e = _el("map")
	var from_outline := _outline.size() > 1
	var line: Array = _outline if from_outline else _trail
	if not e.is_empty() and line.size() > 1:
		var o: Vector2 = P.call(140, 560)
		var sz := Vector2(120, 100) * u
		var b := (_outline_bounds if from_outline else _bounds).grow(10.0)
		var f := minf(sz.x / maxf(b.size.x, 1.0), sz.y / maxf(b.size.y, 1.0))
		var mid := o + sz * 0.5
		var to := func(p: Vector2) -> Vector2: return mid + (p - b.get_center()) * f
		var pts := PackedVector2Array()
		for p in line:
			pts.append(to.call(p))
		if from_outline:
			pts.append(pts[0])
		draw_polyline(pts, Color(0.55, 0.57, 0.6, 0.9), 5.0 * u)
		draw_polyline(pts, Color(0.75, 0.77, 0.8, 0.9), 2.0 * u)
		for car in cars:
			if car != player:
				draw_circle(to.call(cars[car]), 3.0 * u, Color(0.9, 0.9, 0.9))
		if cars.has(player):
			var pp: Vector2 = to.call(cars[player])
			var dir := Vector2(0, -1)
			if _trail.size() > 2:
				dir = ((_trail[-1] as Vector2) - (_trail[-2] as Vector2)).normalized()
			var n := Vector2(-dir.y, dir.x)
			draw_colored_polygon(PackedVector2Array([pp + dir * 10.0 * u, pp - dir * 6.0 * u + n * 6.0 * u, pp - dir * 6.0 * u - n * 6.0 * u]), Color(0.2, 0.9, 0.2))
