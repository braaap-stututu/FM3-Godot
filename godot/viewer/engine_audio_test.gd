extends SceneTree
# (headless check: the engine recipe loads and the player updates; not audible here)
func _init():
	var e = load("res://viewer/fm3_engine_audio.gd").new()
	root.add_child(e)
	var ok = e.load_recipe(ProjectSettings.globalize_path("res://").path_join("../out/audio/HON_CRXsi_91/engine.json"))
	print("loaded ", ok, " players ", e._players.size())
	e.rpm = 5000.0
	e.throttle = 1.0
	for i in 5:
		e._process(0.016)
	var loud = []
	for p in e._players:
		if p[0].volume_db > -60.0:
			loud.append("%s pitch %.2f vol %.1f dB" % [p[1]["file"], p[0].pitch_scale, p[0].volume_db])
	print("audible at 5000 rpm: ", loud)
	quit()
