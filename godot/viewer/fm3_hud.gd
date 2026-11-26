# A race HUD drawn by Godot over the live mirror (2026-11-26; the user: "add the HUD elements, maybe customizable").
# Elements, each with its own place, size and on / off switch in a JSON file:
#   - tach:     a round tachometer (rpm against the car's redline, red zone), the gear in the middle, speed below
#   - speed:    a digital speed readout (km/h or mph)
#   - pedals:   throttle and brake bars
#   - map:      a track map built from the cars' own paths as they drive (no track file needed), a dot per car
#   - info:     the stream's state (game frames, latency) for debugging; off by default
# The data comes from the game's stream (world_view.gd: "FM3E" telemetry, the cars' matrices). The race position and
# lap counter are not in the stream yet (LIVE.md continuation plan).
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
var _trail := []  # the player's path (Vector2), the map's outline
var _bounds := Rect2()
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
	if cars.has(player):
		var p: Vector2 = cars[player]
		if _trail.is_empty() or (_trail[-1] as Vector2).distance_to(p) > 4.0:
			_trail.append(p)
			if _trail.size() > 4000:
				_trail.remove_at(0)
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


func _speed_text(e: Dictionary) -> String:
	if speed_ms < 0.0:
		return "--"
	var mph := String(e.get("units", cfg.get("units", "kmh"))) == "mph"
	return "%d" % roundi(speed_ms * (2.23694 if mph else 3.6))


func _draw() -> void:
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
