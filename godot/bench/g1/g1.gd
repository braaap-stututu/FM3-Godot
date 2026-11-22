# g1.gd — M0 benchmark G1: Godot's cost per mesh instance with three triple-screen views.
#
# Three 16:9 SubViewports side by side, each with a frustum camera from the triple layout
# (godot/triple_cameras.gd, numbers from tools/triple_layout_json.c), all sharing one 3D world.
# The scene stands in for a race track: a ground plane, one directional sun with shadows, a sky,
# and N RenderingServer mesh instances (as the Scene API backend will create them) drawn from a
# few hundred unique meshes and materials, placed along both sides of a 300 m loop. The game
# camera drives around the loop. For each N the benchmark warms up, then measures.
#
# Run (after `--`, all optional):
#   Godot_v4.7.2-stable_win64.exe --path frame-ir/godot -- --screen=2560x1440 --msaa=4
#       --counts=1000,2000,4000,7000,10000 --unique=300 --warmup=3 --measure=8
#       --layout=res://bench/g1/layout_auto.json --out=<file.json> --fullscreen --no-shadows
#   --quick   tiny counts and short phases, for a smoke test (also headless)
extends Node

const TripleCameras = preload("res://triple_cameras.gd")

const TRACK_RADIUS := 300.0
const CAMERA_HEIGHT := 1.2
const CAMERA_SPEED := 40.0 # m/s along the loop

var opts := {
	"screen": Vector2i(2560, 1440),
	"msaa": 4,
	"counts": [1000, 2000, 4000, 7000, 10000],
	"unique": 300,
	"warmup": 3.0,
	"measure": 8.0,
	"layout": "res://bench/g1/layout_auto.json",
	"out": "user://g1_results.json",
	"fullscreen": false,
	"shadows": true,
	"shots": "",
	"precreate": false,
	"max_fps": 0,
}

var visible_count := 0

var screens: Array = []
var layout: Dictionary
var scenario: RID
var meshes: Array[Mesh] = []
var instances: Array[RID] = []
var rng := RandomNumberGenerator.new()

var step := 0
var phase := "warmup"
var phase_time := 0.0
var sim_time := 0.0
var frame_times: Array[float] = []
var cpu_ms: Array[float] = []
var gpu_ms: Array[float] = []
var draws: Array[int] = []
var objects: Array[int] = []
var results: Array = []


func _ready() -> void:
	_parse_args()
	layout = JSON.parse_string(FileAccess.get_file_as_string(opts.layout))
	if layout == null or not layout.has("screens"):
		push_error("G1: cannot read layout '%s'" % opts.layout)
		get_tree().quit(2)
		return

	Engine.max_fps = opts.max_fps
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	# The three views always render at full size. If the desktop is smaller than three screens
	# (no Eyefinity/Surround span), only the on-screen preview is scaled down to fit.
	var total := Vector2i(opts.screen.x * 3, opts.screen.y)
	var desktop := DisplayServer.screen_get_size()
	var preview_scale := 1.0
	if desktop.x > 0 and desktop.y > 0:
		preview_scale = minf(1.0, minf(float(desktop.x) / total.x, float(desktop.y) / total.y))
	if opts.fullscreen and preview_scale >= 1.0:
		DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_EXCLUSIVE_FULLSCREEN)
	else:
		DisplayServer.window_set_size(Vector2i(int(total.x * preview_scale), int(total.y * preview_scale)))
		DisplayServer.window_set_position(Vector2i.ZERO)
	get_window().content_scale_mode = Window.CONTENT_SCALE_MODE_DISABLED

	screens = TripleCameras.make_screens(self, opts.screen)
	if preview_scale < 1.0:
		var row: Control = get_node("TripleScreens")
		row.scale = Vector2(preview_scale, preview_scale)
		print("G1: desktop is %dx%d, so the preview is scaled to %.2f; the views still render at %dx%d each" % [
			desktop.x, desktop.y, preview_scale, opts.screen.x, opts.screen.y])
	for s in screens:
		var vp: SubViewport = s.viewport
		vp.msaa_3d = {0: Viewport.MSAA_DISABLED, 2: Viewport.MSAA_2X, 4: Viewport.MSAA_4X, 8: Viewport.MSAA_8X}.get(opts.msaa, Viewport.MSAA_4X)
		RenderingServer.viewport_set_measure_render_time(vp.get_viewport_rid(), true)

	_build_world()
	rng.seed = 12345
	_make_unique_meshes(opts.unique)
	if opts.precreate:
		# Create every instance before the first frame, hidden; _grow_to only shows them.
		_grow_to(opts.counts.max())
		for i in instances:
			RenderingServer.instance_set_visible(i, false)
	_grow_to(opts.counts[0])
	print("G1: %d screens of %dx%d, MSAA %dx, layout %s (game FOV %.1f deg), shadows %s" % [
		3, opts.screen.x, opts.screen.y, opts.msaa, layout.get("mode", "?"),
		float(layout.get("game_fov_y_deg", 0.0)), "on" if opts.shadows else "off"])
	print("G1: renderer %s, adapter %s" % [
		RenderingServer.get_current_rendering_driver_name(), RenderingServer.get_video_adapter_name()])


func _process(delta: float) -> void:
	if screens.is_empty():
		return
	sim_time += delta
	_move_cameras()
	phase_time += delta
	if phase == "warmup":
		if phase_time >= opts.warmup:
			phase = "measure"
			phase_time = 0.0
			frame_times.clear(); cpu_ms.clear(); gpu_ms.clear(); draws.clear(); objects.clear()
		return
	# measure
	frame_times.append(delta * 1000.0)
	var c := 0.0
	var g := 0.0
	for s in screens:
		var rid: RID = s.viewport.get_viewport_rid()
		c += RenderingServer.viewport_get_measured_render_time_cpu(rid)
		g += RenderingServer.viewport_get_measured_render_time_gpu(rid)
	cpu_ms.append(c)
	gpu_ms.append(g)
	draws.append(RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TOTAL_DRAW_CALLS_IN_FRAME))
	objects.append(RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TOTAL_OBJECTS_IN_FRAME))
	if phase_time >= opts.measure:
		_record(opts.counts[step])
		step += 1
		if step >= opts.counts.size():
			_finish()
			return
		_grow_to(opts.counts[step])
		phase = "warmup"
		phase_time = 0.0


func _record(count: int) -> void:
	var sorted := frame_times.duplicate()
	sorted.sort()
	var n := sorted.size()
	var mean := _mean(frame_times)
	var r := {
		"instances": count,
		"frames": n,
		"fps": 1000.0 / mean if mean > 0.0 else 0.0,
		"frame_ms_mean": mean,
		"frame_ms_p99": sorted[mini(n - 1, int(n * 0.99))] if n > 0 else 0.0,
		"render_cpu_ms_mean": _mean(cpu_ms),
		"render_gpu_ms_mean": _mean(gpu_ms),
		"draw_calls_mean": _mean(draws),
		"objects_drawn_mean": _mean(objects),
	}
	results.append(r)
	print("G1: %6d instances  %7.1f fps  p99 %6.2f ms  render CPU %6.2f ms  GPU %6.2f ms  draws %7.0f  objects %7.0f" % [
		count, r.fps, r.frame_ms_p99, r.render_cpu_ms_mean, r.render_gpu_ms_mean, r.draw_calls_mean, r.objects_drawn_mean])


func _finish() -> void:
	if opts.shots != "":
		DirAccess.make_dir_recursive_absolute(opts.shots)
		for i in 3:
			var img: Image = screens[i].viewport.get_texture().get_image()
			var path: String = opts.shots.path_join("g1_screen_%s.png" % ["left", "centre", "right"][i])
			img.save_png(path)
		print("G1: screenshots written to %s" % ProjectSettings.globalize_path(opts.shots))
	var report := {
		"benchmark": "G1",
		"godot": Engine.get_version_info().string,
		"renderer": RenderingServer.get_current_rendering_driver_name(),
		"adapter": RenderingServer.get_video_adapter_name(),
		"cpu": OS.get_processor_name(),
		"screen": [opts.screen.x, opts.screen.y],
		"msaa": opts.msaa,
		"shadows": opts.shadows,
		"unique_meshes": opts.unique,
		"layout": layout,
		"results": results,
	}
	var f := FileAccess.open(opts.out, FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify(report, "  "))
		f.close()
		print("G1: results written to %s" % ProjectSettings.globalize_path(opts.out))
	else:
		push_error("G1: cannot write %s" % opts.out)
	for i in instances:
		RenderingServer.free_rid(i)
	instances.clear()
	get_tree().quit(0)


# --- scene -------------------------------------------------------------------------------

func _build_world() -> void:
	var world := get_viewport().find_world_3d()
	scenario = world.scenario

	var env := Environment.new()
	env.background_mode = Environment.BG_SKY
	var sky := Sky.new()
	sky.sky_material = ProceduralSkyMaterial.new()
	env.sky = sky
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	var we := WorldEnvironment.new()
	we.environment = env
	add_child(we)

	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-50.0, 30.0, 0.0)
	sun.shadow_enabled = opts.shadows
	sun.directional_shadow_max_distance = 200.0
	add_child(sun)

	var ground := MeshInstance3D.new()
	var plane := PlaneMesh.new()
	plane.size = Vector2(TRACK_RADIUS * 3.0, TRACK_RADIUS * 3.0)
	var gm := StandardMaterial3D.new()
	gm.albedo_color = Color(0.32, 0.34, 0.3)
	gm.roughness = 0.95
	plane.material = gm
	ground.mesh = plane
	add_child(ground)


func _make_unique_meshes(count: int) -> void:
	for i in count:
		var m: PrimitiveMesh
		match i % 5:
			0:
				var b := BoxMesh.new()
				b.size = Vector3(rng.randf_range(0.5, 8.0), rng.randf_range(0.5, 12.0), rng.randf_range(0.5, 8.0))
				m = b
			1:
				var c := CylinderMesh.new()
				c.height = rng.randf_range(1.0, 10.0)
				c.top_radius = rng.randf_range(0.1, 1.5)
				c.bottom_radius = c.top_radius * rng.randf_range(0.8, 1.5)
				m = c
			2:
				var s := SphereMesh.new()
				s.radius = rng.randf_range(0.3, 3.0)
				s.height = s.radius * 2.0
				m = s
			3:
				var p := PrismMesh.new()
				p.size = Vector3(rng.randf_range(1.0, 6.0), rng.randf_range(1.0, 6.0), rng.randf_range(1.0, 6.0))
				m = p
			_:
				var cap := CapsuleMesh.new()
				cap.radius = rng.randf_range(0.2, 1.0)
				cap.height = cap.radius * 2.0 + rng.randf_range(0.5, 4.0)
				m = cap
		var mat := StandardMaterial3D.new()
		mat.albedo_color = Color.from_hsv(rng.randf(), rng.randf_range(0.2, 0.8), rng.randf_range(0.3, 0.9))
		mat.roughness = rng.randf_range(0.2, 1.0)
		mat.metallic = 1.0 if rng.randf() < 0.15 else 0.0
		m.material = mat
		meshes.append(m)


# Adds instances until there are `count`, placed 4-80 m to either side of the loop.
# With --precreate they already exist (hidden) and are only made visible.
func _grow_to(count: int) -> void:
	if opts.precreate and instances.size() >= count:
		for i in range(visible_count, count):
			RenderingServer.instance_set_visible(instances[i], true)
		visible_count = maxi(visible_count, count)
		return
	while instances.size() < count:
		var mesh := meshes[rng.randi() % meshes.size()]
		var angle := rng.randf() * TAU
		var side := 1.0 if rng.randf() < 0.5 else -1.0
		var r := TRACK_RADIUS + side * rng.randf_range(4.0, 80.0)
		var pos := Vector3(cos(angle) * r, 0.0, sin(angle) * r)
		var basis := Basis(Vector3.UP, rng.randf() * TAU)
		var aabb := mesh.get_aabb()
		pos.y = -aabb.position.y # stand on the ground
		var inst := RenderingServer.instance_create2(mesh.get_rid(), scenario)
		RenderingServer.instance_set_transform(inst, Transform3D(basis, pos))
		instances.append(inst)


# The game camera drives counter-clockwise around the loop; each screen gets its triple camera.
func _move_cameras() -> void:
	var a := sim_time * CAMERA_SPEED / TRACK_RADIUS
	var pos := Vector3(cos(a) * TRACK_RADIUS, CAMERA_HEIGHT, sin(a) * TRACK_RADIUS)
	var forward := Vector3(-sin(a), 0.0, cos(a))
	var game := Transform3D(Basis.looking_at(forward, Vector3.UP), pos)
	for i in 3:
		var sc: Dictionary = layout.screens[i]
		TripleCameras.apply(screens[i].camera, game, float(sc.rot_y), float(sc.size),
				Vector2(float(sc.offset[0]), float(sc.offset[1])), float(sc.near), float(sc.far))


# --- helpers -----------------------------------------------------------------------------

func _parse_args() -> void:
	for a in OS.get_cmdline_user_args():
		var kv := a.trim_prefix("--").split("=", true, 1)
		var key := kv[0]
		var val := kv[1] if kv.size() > 1 else ""
		match key:
			"screen":
				var wh := val.split("x")
				opts.screen = Vector2i(int(wh[0]), int(wh[1]))
			"msaa": opts.msaa = int(val)
			"counts":
				opts.counts = Array(val.split(",")).map(func(x): return int(x))
			"unique": opts.unique = int(val)
			"warmup": opts.warmup = float(val)
			"measure": opts.measure = float(val)
			"layout": opts.layout = val
			"out": opts.out = val
			"fullscreen": opts.fullscreen = true
			"no-shadows": opts.shadows = false
			"shots": opts.shots = val
			"precreate": opts.precreate = true
			"max-fps": opts.max_fps = int(val)
			"quick":
				opts.counts = [100, 500]
				opts.unique = 20
				opts.warmup = 0.2
				opts.measure = 0.5
			_:
				push_warning("G1: unknown option '%s'" % a)


func _mean(values: Array) -> float:
	if values.is_empty():
		return 0.0
	var sum := 0.0
	for v in values:
		sum += float(v)
	return sum / values.size()
