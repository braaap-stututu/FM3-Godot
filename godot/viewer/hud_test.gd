# The HUD alone with made-up data (a check of fm3_hud.gd's drawing; 2026-11-26):
#   Godot_v4.7.2-stable_win64.exe --path frame-ir/godot -s res://viewer/hud_test.gd -- <out.png>
extends SceneTree

var _hud: Control
var _n := 0


func _initialize() -> void:
	root.size = Vector2i(1280, 720)
	var bg := ColorRect.new()
	bg.color = Color(0.25, 0.3, 0.35)
	bg.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.add_child(bg)
	var layer := CanvasLayer.new()
	layer.layer = 100
	_hud = load("res://viewer/fm3_hud.gd").new()
	layer.add_child(_hud)
	root.add_child(layer)


func _process(_d: float) -> bool:
	_n += 1
	var cars := {}
	for i in 6:
		var a := float(_n) * 0.05 + i * 0.4
		cars[i] = Vector2(cos(a) * 300.0, sin(a * 2.0) * 120.0)
	_hud.call("feed", {"speed": 41.7, "rpm": 6100.0, "redline": 7600.0, "gear": 3, "throttle": 0.8, "brake": 0.1,
		"cars": cars, "player": 0})
	if _n == 120:
		var a := OS.get_cmdline_user_args()
		root.get_texture().get_image().save_png(a[0] if a.size() > 0 else "user://hud_test.png")
		return true
	return false
