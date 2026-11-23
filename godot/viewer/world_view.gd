extends SceneTree
# Loads a fir_world.py glTF at run time, looks through its capture_camera and saves one picture.
#   Godot_v4.7.2-stable_win64.exe --path frame-ir/godot -s res://viewer/world_view.gd -- --gltf <file> --out <png> [--size 1280x720] [--textured | --lit] [--triple layout.json] [--fly]

var _out := ""
var _frames := 0
var _scene: Node
var _cam: Camera3D
var _triple_layout := ""  # --triple <layout.json>: three screens (core/triple_view layout), stitched side by side
var _screens := []
var _msaa := 0  # --msaa 2|4|8 on the screens
var _fly := false  # --fly: interactive free camera (WASD, Q/E down/up, hold right mouse to look, Shift fast, Ctrl slow, Esc quits)
var _fly_xf: Transform3D
var _yaw := 0.0
var _pitch := 0.0
var _bench := 0  # --bench N: after the picture, render N more frames and report the frame rate
var _bench_t0 := 0
var _screen_size := Vector2i(1280, 720)
# --live <port>: follow the running game's camera (FM3_LIVE, FM3-ReGPU recomp src/hooks/live_camera.cpp; LIVE.md).
# The window stays open; Tab switches to the next camera director seen (player view, rear-view mirror, ...); Esc quits;
# creating the file <--out>.shot saves the next frame to --out.
var _live_port := 0
var _udp: PacketPeerUDP
var _live_director := 0
var _live_dirs: Array[int] = []
var _live_tab := false
var _live_packets := 0
var _live_last_ms := 0
# Game world -> glTF world for the camera: mirror signs per axis, then the signs for the game camera's right and up.
# Fitted on the frozen grid (tools/live_listen.py --compare grid.gltf, 2026-11-23): FM3's world with z mirrored, the
# F = diag(1, 1, -1) of fm3_track_export.py, and the director's axes as they are (the 180 deg screen turn that
# fir_world.py undoes is in the projection, not the view matrix): 0.000 m, 0.00 deg. --live-axes sx,sy,sz,sr,su overrides.
var _live_axes := PackedFloat32Array([1, 1, -1, 1, 1])
# Cars ("FM3K" datagrams: each car body's world matrix per drawn frame). Half a second after the first, every small
# mesh lying wholly inside a car's box is attached to that car, keeping its offset; from then on it moves with the car.
# So the game must be where the glTF was made (the capture's grid) when the viewer starts following.
var _cars := {}  # car object address -> latest datagram
var _car_first_ms := 0
var _car_attached := false
var _car_parts := []  # [node, car, offset]
var _live_has_drawn := false  # "FM3V" (the drawn camera) seen: the main view follows only those
var _live_frames := []  # the game's last drawn frames: {t (game clock, s), cam, fov, cars: {car: matrix}}
var _car_inv := {}  # car -> its matrix at attach time, inverted
var _wheels := {}  # car -> its latest four wheel matrices (glTF space)
var _car_prev := {}  # car -> [position (game space), game time]: for its speed
var _car_speed := {}  # car -> speed, m/s (smoothed)
var _wheel_inv := {}  # car -> its four wheel matrices at attach time, inverted
var _clock_off := INF  # Godot clock minus game clock (smallest seen)
var _frame_dt := 1.0 / 120.0  # the game's frame interval (smoothed)
var _live_raw := false  # --live-raw: the newest frame, no interpolation
var _live_last_now := 0.0
var _live_vtable := 0  # the game's active camera (its vtable, from the drawn-camera datagrams)
var _live_smooth := 1.0  # --live-smooth W: the shown motion averaged over W game frames (0 = off: 8 ms less delay at 60)
var _view_t := 0.0  # the viewer's steadied clock
var _view_dt := 1.0 / 60.0  # the viewer's frame interval (smoothed)
var _game_seq := 0  # the last drawn game frame's number and raw time
var _game_raw := 0.0
var _live_log: FileAccess  # --live-log <csv>: per viewer frame, time and the shown camera and followed car positions
const TripleCameras = preload("res://triple_cameras.gd")
const BAKED_SHADER = preload("res://viewer/fm3_baked.gdshader")
const BAKED_BLEND_SHADER = preload("res://viewer/fm3_baked_blend.gdshader")
const GLASS_SHADER = preload("res://viewer/fm3_glass.gdshader")
const CARPAINT_SHADER = preload("res://viewer/fm3_carpaint.gdshader")
const CARGLASS_SHADER = preload("res://viewer/fm3_carglass.gdshader")
const BLEND_SHADER = preload("res://viewer/fm3_blend.gdshader")


func _init() -> void:
	var args := OS.get_cmdline_user_args()
	var gltf_path := ""
	var size := Vector2i(1280, 720)
	var no_shadows := false
	var grey_shadow := false
	var id_mode := false  # debug: every mesh instance a unique flat colour; writes <out>.ids.txt (index -> node name)  # debug: one grey lit material everywhere, sun shadows on
	var lit := false  # --lit: materials shaded, a sun with shadows and sky ambient (--sun elevation,azimuth in degrees)
	var look_from := ""  # --look-from x,y,z --look-at x,y,z: render from this camera instead of the glTF's
	var look_at := ""
	var filmic := false  # --filmic: Godot's filmic tone mapper and grade (the look before matching FM3's own)
	var sun_elev := 50.0
	var sun_azim := 30.0
	var textured := false  # --textured: the glTF's own materials, unshaded (no normals yet); else one grey lit material
	var fullscreen := false  # --fullscreen: the window covers the display (borderless)
	var i := 0
	while i < args.size():
		match args[i]:
			"--gltf":
				gltf_path = args[i + 1]; i += 1
			"--out":
				_out = args[i + 1]; i += 1
			"--size":
				var p := args[i + 1].split("x"); size = Vector2i(int(p[0]), int(p[1])); i += 1
			"--textured":
				textured = true
			"--lit":
				textured = true; lit = true
			"--filmic":
				filmic = true
			"--look-from":
				look_from = args[i + 1]; i += 1
			"--look-at":
				look_at = args[i + 1]; i += 1
			"--fly":
				_fly = true
			"--live":
				_live_port = int(args[i + 1]); i += 1
			"--live-raw":
				_live_raw = true
			"--live-cube":  # the live reflection cube's face size in pixels (0 = the layout's static cube)
				_live_cube_size = int(args[i + 1]); i += 1
			"--live-smooth":  # average the shown motion over this many game frames (0 = off)
				_live_smooth = float(args[i + 1]); i += 1
			"--fps":  # cap the viewer's frame rate (vsync stays on)
				Engine.max_fps = int(args[i + 1]); i += 1
			"--fullscreen":
				fullscreen = true
			"--live-log":
				_live_log = FileAccess.open(args[i + 1], FileAccess.WRITE); i += 1
			"--live-director":
				_live_director = args[i + 1].hex_to_int(); i += 1
			"--live-axes":
				_live_axes = PackedFloat32Array(Array(args[i + 1].split_floats(","))); i += 1
			"--id":
				id_mode = true
			"--grey-shadow":
				grey_shadow = true
			"--no-shadows":
				no_shadows = true
			"--msaa":
				_msaa = int(args[i + 1]); i += 1
			"--bench":
				_bench = int(args[i + 1]); i += 1
			"--triple":
				_triple_layout = args[i + 1]; i += 1
			"--sun":
				var q := args[i + 1].split(","); sun_elev = float(q[0]); sun_azim = float(q[1]); i += 1
		i += 1
	DisplayServer.window_set_size(size)
	root.size = size
	if fullscreen:
		DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_FULLSCREEN)
	root.mesh_lod_threshold = 0.0  # full detail: merged meshes span the whole track, their LOD pick would drop parts
	var doc := GLTFDocument.new()
	var state := GLTFState.new()
	if doc.append_from_file(gltf_path, state) != OK:
		push_error("cannot read " + gltf_path)
		quit(1)
		return
	var scene := doc.generate_scene(state)
	root.add_child(scene)
	_scene = scene
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.75, 0.75, 0.72)
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	var meshes := 0
	var baked := 0
	var baked_no_tex := 0
	var baked_gain := 1.0  # (the baked shader evaluates FM3's own lightmap formula; 1 = as the game)
	var grey_unshaded := StandardMaterial3D.new()
	grey_unshaded.albedo_color = Color(0.5, 0.5, 0.5)
	grey_unshaded.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	grey_unshaded.cull_mode = BaseMaterial3D.CULL_DISABLED
	var id_lines := PackedStringArray()
	var car_centres := []
	for n in scene.find_children("*", "MeshInstance3D", true, false):
		var mi := n as MeshInstance3D
		meshes += 1
		if id_mode and OS.get_environment("FM3_ID_HIDE") != "" and String(mi.name).contains(OS.get_environment("FM3_ID_HIDE")):
			mi.visible = false  # (debug: FM3_ID_HIDE=<text> hides meshes whose name contains it, to see what is behind)
			continue
		if id_mode:
			var k := meshes
			var im := StandardMaterial3D.new()
			im.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
			im.cull_mode = BaseMaterial3D.CULL_DISABLED
			im.albedo_color = Color8(k & 255, (k >> 8) & 255, 77)
			mi.material_override = im
			id_lines.append("%d %s" % [k, mi.get_parent().name if mi.name.begins_with("Mesh") or mi.name == "" else mi.name])
			continue
		# A wheel's motion-blur meshes (the game's blur_rim / blur_lip ...): faded in with the car's speed when live, so
		# hidden at rest (the grid).
		if _is_blur_wheel(mi):
			mi.transparency = 1.0
		if String(mi.name).begins_with("cockpit_"):
			mi.visible = false  # (the in-car model: shown only in the game's first-person views, live)
		if _is_car_mesh(mi):
			mi.layers = 2  # (left out of the live reflection cube)
			car_centres.append(mi.global_transform * mi.get_aabb().get_center() if mi.is_inside_tree() else mi.transform * mi.get_aabb().get_center())
		# The sky dome (unlit) surrounds everything: as a shadow caster it would shade the whole scene.
		for s0 in mi.mesh.get_surface_count():
			var m0 := mi.mesh.surface_get_material(s0) as BaseMaterial3D
			if m0 != null and m0.shading_mode == BaseMaterial3D.SHADING_MODE_UNSHADED:
				mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		if not textured:
			mi.material_override = mat
			continue
		for s in mi.mesh.get_surface_count():
			var m := mi.mesh.surface_get_material(s) as StandardMaterial3D
			if m == null:
				mi.set_surface_override_material(s, mat if lit else grey_unshaded)
				continue
			var fm3_extras = m.get_meta("extras").get("fm3") if m.has_meta("extras") and m.get_meta("extras") is Dictionary else null
			if lit and fm3_extras != null:
				# FM3 multi-texture shader family (tools/fm3_families.py, fm3_blend.gdshader)
				mi.set_surface_override_material(s, _blend_material(m, fm3_extras, gltf_path))
				mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
				baked += 1
				continue
			m = m.duplicate()
			if m.resource_name == "fm3_shadow_blob":
				# a car's soft contact shadow (fir_world.py): lie just above the road it would otherwise z-fight
				mi.position += Vector3(0, 0.03, 0)  # (before entering the tree: local = world, glTF nodes sit at the root)
				mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			if m.shading_mode != BaseMaterial3D.SHADING_MODE_UNSHADED:  # (the glTF's unlit materials stay unlit)
				m.shading_mode = BaseMaterial3D.SHADING_MODE_PER_PIXEL if lit else BaseMaterial3D.SHADING_MODE_UNSHADED
			m.cull_mode = BaseMaterial3D.CULL_DISABLED
			if lit and m.ao_enabled and m.ao_texture != null and m.ao_on_uv2 and (not _blended(m) or m.albedo_texture != null):
				# FM3's static world: its baked colour lightmap (slot 7, UV2) carries the light; the sun only adds
				# the shadows of dynamic objects (fm3_baked.gdshader). Its own shadows are in the lightmap: it casts none.
				var sm := ShaderMaterial.new()
				sm.shader = BAKED_BLEND_SHADER if _blended(m) else BAKED_SHADER
				sm.set_shader_parameter("albedo_tex", m.albedo_texture)
				sm.set_shader_parameter("light_tex", m.ao_texture)
				sm.set_shader_parameter("albedo_color", m.albedo_color)
				sm.set_shader_parameter("gain", baked_gain)
				if m.transparency == BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR:
					sm.set_shader_parameter("alpha_cut", m.alpha_scissor_threshold)
				if _blended(m):
					mi.sorting_offset = -1.0  # (decals over the ground they lie on)
				mi.set_surface_override_material(s, sm)
				mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
				baked += 1
				if m.albedo_texture == null:
					baked_no_tex += 1
				continue
			if lit and _blended(m) and m.roughness < 0.1 and m.albedo_texture == null:
				# car glass: FM3's dark, reflective windows (fm3_carglass.gdshader), not a clear pane
				mi.set_surface_override_material(s, _car_material(CARGLASS_SHADER, m, gltf_path, "FM3_CARGLASS",
					["env_scale", "fresnel_min", "fresnel_power", "max_opacity"]))
				continue
			if lit and m.roughness >= 0.9:
				m.metallic_specular = 0.04  # matte surfaces: almost no sky reflection (FM3's dark trim stays dark)
			if lit and m.roughness_texture != null and m.albedo_texture != null:
				# car paint (fir_world.py writes a roughness texture only for paint): FM3's paint shader
				# (fm3_carpaint.gdshader: lit colour + Fresnel environment reflection + sun highlight)
				mi.set_surface_override_material(s, _car_material(CARPAINT_SHADER, m, gltf_path, "FM3_CARPAINT",
					["refl_gain", "refl_f0", "spec_gain", "spec_power", "shadow_strength", "refl_metal"]))
				continue
			m.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
			if mi.mesh.surface_get_format(s) & Mesh.ARRAY_FORMAT_COLOR:
				m.vertex_color_use_as_albedo = true  # (the cockpit's baked brightness, fm3_track_export.py)
			if m.resource_name.contains("gauge") and m.albedo_texture != null:
				# cockpit gauges: lit markings (the texture's alpha) on a dark face (fm3_gauge.gdshader)
				var gm := ShaderMaterial.new()
				gm.shader = load("res://viewer/fm3_gauge.gdshader")
				gm.set_shader_parameter("tex", m.albedo_texture)
				mi.set_surface_override_material(s, gm)
				continue
			mi.set_surface_override_material(s, m)
	if id_mode:
		var fa := FileAccess.open(_out + ".ids.txt", FileAccess.WRITE)
		fa.store_string("
".join(id_lines))
		fa.close()
	var cams := scene.find_children("*", "Camera3D", true, false)
	if cams.is_empty():
		push_error("no camera in the glTF")
		quit(1)
		return
	var cam := cams[0] as Camera3D
	cam.keep_aspect = Camera3D.KEEP_HEIGHT
	cam.far = maxf(cam.far, 100000.0)  # the sky dome is ~5 km out (FM3: infinite far plane)
	if look_from != "" and look_at != "":
		var f := look_from.split_floats(",")
		var t := look_at.split_floats(",")
		var xf := Transform3D(Basis(), Vector3(f[0], f[1], f[2])).looking_at(Vector3(t[0], t[1], t[2]), Vector3.UP)
		if cam.is_inside_tree():
			cam.global_transform = xf
		else:
			cam.transform = xf
	cam.current = true
	_cam = cam
	var env := WorldEnvironment.new()
	env.environment = Environment.new()
	env.environment.background_mode = Environment.BG_COLOR
	env.environment.background_color = Color(0.45, 0.6, 0.8)
	env.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.environment.ambient_light_color = Color(0.5, 0.5, 0.5)
	if lit:
		# A procedural sky for ambient light and reflections (the visible sky is FM3's own dome mesh).
		var sky := Sky.new()
		var psky := ProceduralSkyMaterial.new()
		psky.sky_top_color = Color(0.42, 0.58, 0.8)  # (FM3's sky/fog constant c242: 0.51, 0.69, 0.84)
		psky.sky_horizon_color = Color(0.8, 0.85, 0.9)
		psky.ground_bottom_color = Color(0.25, 0.24, 0.22)
		psky.ground_horizon_color = Color(0.6, 0.62, 0.64)
		sky.sky_material = psky
		env.environment.sky = sky
		env.environment.background_mode = Environment.BG_SKY
		env.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
		env.environment.ambient_light_color = Color(0.72, 0.73, 0.75)
		env.environment.ambient_light_energy = 0.85 if filmic else 0.12
		env.environment.reflected_light_source = Environment.REFLECTION_SOURCE_SKY
		if filmic:
			env.environment.tonemap_mode = Environment.TONE_MAPPER_FILMIC
			env.environment.tonemap_exposure = 1.2
			env.environment.adjustment_enabled = true
			env.environment.adjustment_contrast = 1.12
			env.environment.adjustment_saturation = 0.95
		else:
			# FM3's look: the baked world shader already produces the game's (LDR, gamma-space) colour; a linear tone
			# mapper passes it to the screen unchanged.
			env.environment.tonemap_mode = Environment.TONE_MAPPER_LINEAR
			env.environment.tonemap_exposure = 1.0
	root.add_child(env)
	if lit:
		# Reflections of the real scene (FM3 renders a dynamic environment map for its car paint and glass): one probe
		# around the grid, rendered once from just above the cars.
		var probe := ReflectionProbe.new()
		probe.size = Vector3(260, 80, 260)
		probe.update_mode = ReflectionProbe.UPDATE_ONCE
		probe.max_distance = 1500.0
		probe.ambient_mode = ReflectionProbe.AMBIENT_DISABLED
		# (above the cars: placed among them, the probe saw the nearest car's interior and every car reflected it)
		var cam_o := cam.global_transform.origin if cam.is_inside_tree() else cam.transform.origin
		var cam_f := -(cam.global_transform.basis.z if cam.is_inside_tree() else cam.transform.basis.z)
		probe.position = cam_o + Vector3(cam_f.x, 0, cam_f.z).normalized() * 15.0 + Vector3(0, 6.0, 0)
		root.add_child(probe)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-sun_elev, sun_azim, 0)
	var glights := scene.find_children("*", "DirectionalLight3D", true, false)
	if not glights.is_empty():  # the capture's sun (fir_world.py writes FM3's sun direction)
		sun.global_transform = (glights[0] as Node3D).global_transform if (glights[0] as Node3D).is_inside_tree() else (glights[0] as Node3D).transform
		(glights[0] as Node3D).visible = false
		print("world_view: sun from the glTF")
	sun.light_energy = (1.45 if filmic else 1.3) if lit else 1.0  # (linear tone mapping: calibrated on the grid's cars)
	sun.light_color = Color(1.0, 0.97, 0.92)
	sun.shadow_enabled = (lit or grey_shadow) and not no_shadows
	print("world_view: sun forward ", -sun.global_transform.basis.z if sun.is_inside_tree() else -sun.transform.basis.z, " shadows ", sun.shadow_enabled)
	sun.directional_shadow_max_distance = 250.0
	root.add_child(sun)
	print("world_view: camera ", cam.global_transform if cam.is_inside_tree() else cam.transform, " parent ", cam.get_parent().name)
	print("world_view: %d surfaces lit by FM3's baked lightmaps (%d without an albedo texture)" % [baked, baked_no_tex])
	print("world_view: %d mesh instances, camera fov %.2f near %.3f" % [meshes, cam.fov, cam.near])
	if lit and _live_cube_size > 0 and not _car_mats.is_empty():
		# at the player car: the car meshes' centre nearest the camera, 0.8 m up (live: it follows that car)
		var co: Vector3 = cam.global_transform.origin if cam.is_inside_tree() else cam.transform.origin
		var best := co
		var best_d := INF
		for c in car_centres:
			var d := (c as Vector3).distance_to(co)
			if d < best_d:
				best_d = d
				best = c
		_make_live_cube(best + Vector3(0, 0.8, 0))
	if _live_port > 0:
		_udp = PacketPeerUDP.new()
		var err := _udp.bind(_live_port, "127.0.0.1")
		print("world_view: live camera on udp 127.0.0.1:%d (%s; start FM3 with FM3_LIVE=%d)" % [_live_port, "listening" if err == OK else "bind failed: %d" % err, _live_port])


func _blended(m: BaseMaterial3D) -> bool:
	# (Godot's glTF import gives alphaMode BLEND as alpha with a depth pre-pass)
	return m.transparency == BaseMaterial3D.TRANSPARENCY_ALPHA or m.transparency == BaseMaterial3D.TRANSPARENCY_ALPHA_DEPTH_PRE_PASS


var _env := {}


func _env_cube(gltf_path: String, tex_dir: String) -> Cubemap:
	# envcube_0..5.png (fm3_track_export.py: the layout's staticcarcubemap.xpr, D3D face order = Godot's)
	var key := gltf_path.get_base_dir().path_join(tex_dir)
	if not _env.has(key):
		var imgs: Array[Image] = []
		for k in 6:
			var img := Image.load_from_file(key.path_join("envcube_%d.png" % k))
			if img == null:
				_env[key] = null
				return null
			img.convert(Image.FORMAT_RGBA8)
			img.generate_mipmaps()
			imgs.append(img)
		var c := Cubemap.new()
		c.create_from_images(imgs)
		_env[key] = c
	return _env[key]


# A car paint / glass ShaderMaterial from the glTF's material: its colour (and texture), the layout's static car cube.
# Fitting: <env> = comma-separated values for <names> (e.g. FM3_CARPAINT=0.9,0.06,0.8,60,0.85); FM3_CARPAINT_AMB /
# FM3_CARPAINT_SUN = r,g,b override the paint's ambient and sun light.
func _car_material(shader: Shader, m: BaseMaterial3D, gltf_path: String, env: String, names: Array) -> ShaderMaterial:
	var sm := ShaderMaterial.new()
	sm.shader = shader
	_car_mats.append(sm)
	sm.set_shader_parameter("albedo_color", m.albedo_color)
	sm.set_shader_parameter("metallic", m.metallic)
	if m.albedo_texture != null:
		sm.set_shader_parameter("albedo_tex", m.albedo_texture)
	var cube := _env_cube(gltf_path, gltf_path.get_file().get_basename() + "_tex")
	sm.set_shader_parameter("has_env", cube != null)
	if cube != null:
		sm.set_shader_parameter("env_cube", cube)
	var v := OS.get_environment(env)
	if v != "":
		var f := v.split_floats(",")
		for k in mini(f.size(), names.size()):
			sm.set_shader_parameter(names[k], f[k])
	for extra in [["_AMB", "ambient"], ["_GROUND", "ambient_ground"], ["_SUN", "sun"]]:
		var e := OS.get_environment(env + extra[0])
		if e != "":
			var c := e.split_floats(",")
			sm.set_shader_parameter(extra[1], Vector3(c[0], c[1], c[2]))
	return sm


# The live reflection cube (--live-cube N, default 128 px a face; 0 = the layout's static cube): six cameras at the
# player car render the scene into viewports each frame, as the game renders its car reflection cube each frame; the
# car paint and glass shaders look it up (fm3_livecube.gdshaderinc). Car meshes are on render layer 2, which the cube's
# cameras leave out (a car would otherwise reflect its own cabin).
const LIVE_DIRS = [Vector3.RIGHT, Vector3.LEFT, Vector3.UP, Vector3.DOWN, Vector3.BACK, Vector3.FORWARD]  # +x -x +y -y +z -z
const LIVE_UPS = [Vector3.UP, Vector3.UP, Vector3.FORWARD, Vector3.BACK, Vector3.UP, Vector3.UP]  # (+y: up -z; -y: up +z)
var _live_cube_size := 128
var _live_cube_cams := []
var _car_mats := []


func _make_live_cube(at: Vector3) -> void:
	var texs := []
	for k in 6:
		var vp := SubViewport.new()
		vp.size = Vector2i(_live_cube_size, _live_cube_size)
		vp.render_target_update_mode = SubViewport.UPDATE_ALWAYS
		vp.positional_shadow_atlas_size = 0
		vp.mesh_lod_threshold = 4.0  # (small faces: coarser LODs are fine)
		var c := Camera3D.new()
		c.fov = 90.0
		c.keep_aspect = Camera3D.KEEP_HEIGHT
		c.near = 0.05
		c.far = 3000.0
		c.cull_mask = 0xFFFFF & ~2  # (not layer 2: the cars)
		vp.add_child(c)
		root.add_child(vp)
		_live_cube_cams.append(c)
		texs.append(vp.get_texture())
	_place_live_cube(at)
	for sm in _car_mats:
		(sm as ShaderMaterial).set_shader_parameter("has_live", true)
		for k in 6:
			(sm as ShaderMaterial).set_shader_parameter("live%d" % k, texs[k])
	print("world_view: live reflection cube, %d px a face, at %s" % [_live_cube_size, at])


func _place_live_cube(at: Vector3) -> void:
	for k in _live_cube_cams.size():
		var c: Camera3D = _live_cube_cams[k]
		c.global_transform = Transform3D(Basis(), at).looking_at(at + LIVE_DIRS[k], LIVE_UPS[k])


static func _is_car_mesh(mi: Node) -> bool:
	var n := String(mi.name) + " " + String(mi.get_parent().name if mi.get_parent() else "")
	return n.begins_with("carbin_") or n.begins_with("cockpit_") or n.to_lower().contains("wheel") or RegEx.create_from_string("draw\\d+_[a-z]+_[a-z0-9]+_\\d\\d").search(n) != null


var _tex_cache := {}


func _load_tex(gltf_path: String, rel: String) -> Texture2D:
	var p := gltf_path.get_base_dir().path_join(rel)
	if not _tex_cache.has(p):
		var img := Image.load_from_file(p)
		if img == null:
			_tex_cache[p] = null
		else:
			img.generate_mipmaps()
			_tex_cache[p] = ImageTexture.create_from_image(img)
	return _tex_cache[p]


func _blend_material(m: BaseMaterial3D, f: Dictionary, gltf_path: String) -> ShaderMaterial:
	var sm := ShaderMaterial.new()
	sm.shader = GLASS_SHADER if String(f["mode"]) == "refl" else BLEND_SHADER
	var tex: Array = f["tex"]
	if String(f["mode"]) == "refl":
		var cube := _env_cube(gltf_path, String(tex[0]).get_base_dir())
		sm.set_shader_parameter("has_env", cube != null)
		if cube != null:
			sm.set_shader_parameter("env_cube", cube)
		if OS.get_environment("FM3_ENV_FLIP") != "":
			var fl := OS.get_environment("FM3_ENV_FLIP").split_floats(",")
			sm.set_shader_parameter("env_flip", Vector3(fl[0], fl[1], fl[2]))
		sm.set_shader_parameter("debug_env_only", OS.get_environment("FM3_ENV_ONLY") != "")
		if OS.get_environment("FM3_GLASS_PART") != "":
			sm.set_shader_parameter("debug_part", int(OS.get_environment("FM3_GLASS_PART")))
	sm.set_shader_parameter("albedo_tex", _load_tex(gltf_path, tex[0]))
	sm.set_shader_parameter("tex1", _load_tex(gltf_path, tex[1]))
	if tex.size() > 2:
		sm.set_shader_parameter("tex2", _load_tex(gltf_path, tex[2]))
	if tex.size() > 3:
		sm.set_shader_parameter("tex3", _load_tex(gltf_path, tex[3]))
	var mode_name := String(f["mode"])
	sm.set_shader_parameter("mode", {"blend": 1, "road": 2, "paint": 3, "edge": 4, "mix": 5, "curb": 6, "refl": 7}.get(mode_name, 1))
	if f.has("scale2"):
		sm.set_shader_parameter("scale2", Vector2(f["scale2"][0], f["scale2"][1]))
	sm.set_shader_parameter("vclr", bool(f.get("vclr", false)))
	sm.set_shader_parameter("scale0", Vector2(f["scale0"][0], f["scale0"][1]))
	sm.set_shader_parameter("scale1", Vector2(f["scale1"][0], f["scale1"][1]))
	sm.set_shader_parameter("tint0", Vector3(f["tint0"][0], f["tint0"][1], f["tint0"][2]))
	sm.set_shader_parameter("tint1", Vector3(f["tint1"][0], f["tint1"][1], f["tint1"][2]))
	if mode_name in ["road", "paint", "edge"]:
		var g := _load_tex(gltf_path, tex[0])
		if g != null:
			var gi := g.get_image()
			gi.resize(8, 8)
			var sum := 0.0
			for y in 8:
				for x in 8:
					var c := gi.get_pixel(x, y)
					sum += (c.r + c.g + c.b) / 3.0
			sm.set_shader_parameter("grain_mean", sum / 64.0)
	sm.set_shader_parameter("has_lightmap", m.ao_enabled and m.ao_texture != null)
	if m.ao_texture != null:
		sm.set_shader_parameter("light_tex", m.ao_texture)
	return sm


func _fly_step(delta: float) -> void:
	if Input.is_key_pressed(KEY_ESCAPE):
		quit(0)
		return
	var looking := Input.is_mouse_button_pressed(MOUSE_BUTTON_RIGHT)
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED if looking else Input.MOUSE_MODE_VISIBLE
	if looking:
		var mv := Input.get_last_mouse_velocity() * delta
		_yaw -= mv.x * 0.003
		_pitch = clamp(_pitch - mv.y * 0.003, -1.5, 1.5)
	var basis := Basis(Vector3.UP, _yaw) * Basis(Vector3.RIGHT, _pitch)
	var dir := Vector3.ZERO
	if Input.is_key_pressed(KEY_W): dir += -basis.z
	if Input.is_key_pressed(KEY_S): dir += basis.z
	if Input.is_key_pressed(KEY_A): dir += -basis.x
	if Input.is_key_pressed(KEY_D): dir += basis.x
	if Input.is_key_pressed(KEY_E): dir += Vector3.UP
	if Input.is_key_pressed(KEY_Q): dir += Vector3.DOWN
	var speed := 12.0
	if Input.is_key_pressed(KEY_SHIFT): speed = 60.0
	if Input.is_key_pressed(KEY_CTRL): speed = 2.0
	_fly_xf = Transform3D(basis, _fly_xf.origin + dir.normalized() * speed * delta if dir != Vector3.ZERO else _fly_xf.origin)
	if _screens.is_empty():
		_cam.global_transform = _fly_xf
	else:
		for scr in _screens:
			var c: Camera3D = scr["camera"]
			c.global_transform = TripleCameras.screen_transform(_fly_xf, float(scr.get("rot_y", 0.0)))


# The game camera (one FM3_LIVE datagram) as a Godot camera transform in the glTF's world.
static func live_transform(b: PackedByteArray, axes: PackedFloat32Array) -> Transform3D:
	var v := PackedFloat32Array()
	v.resize(16)
	for k in 16:
		v[k] = b.decode_float(16 + 4 * k)
	# p_cam = p_world * V (row vectors): the 3x3's columns are the camera's axes in the world, row 3 = -(c . axis).
	var right := Vector3(v[0], v[4], v[8])
	var up := Vector3(v[1], v[5], v[9])
	var fwd := Vector3(v[2], v[6], v[10])
	var c := -(right * v[12] + up * v[13] + fwd * v[14])
	var s := Vector3(axes[0], axes[1], axes[2])
	var x := s * right * axes[3]
	var y := s * up * axes[4]
	var z := -(s * fwd)
	return Transform3D(Basis(x, y, z).orthonormalized(), s * c)


# A car body's world matrix (one FM3K datagram) in the glTF's world: rows = the car's axes, row 3 = its position, each
# mirrored like the camera (a mirrored basis: only products A(t) * A(0)^-1 are used, where the mirror cancels).
static func car_transform(b: PackedByteArray, axes: PackedFloat32Array) -> Transform3D:
	var s := Vector3(axes[0], axes[1], axes[2])
	var r := []
	for row in 4:
		r.append(Vector3(b.decode_float(16 + 16 * row), b.decode_float(20 + 16 * row), b.decode_float(24 + 16 * row)) * s)
	return Transform3D(Basis(r[0], r[1], r[2]), r[3])


static func _is_blur_wheel(mi: Node) -> bool:
	var n := (String(mi.name) + " " + String(mi.get_parent().name if mi.get_parent() else "")).to_lower()
	return n.contains("wheel") and n.contains("blur")


# Wheel k of an FM3W datagram (its world matrix as drawn) in the glTF's world, mirrored like car_transform.
static func wheel_transform(b: PackedByteArray, k: int, axes: PackedFloat32Array) -> Transform3D:
	var s := Vector3(axes[0], axes[1], axes[2])
	var o := 16 + 64 * k
	var r := []
	for row in 4:
		r.append(Vector3(b.decode_float(o + 16 * row), b.decode_float(o + 16 * row + 4), b.decode_float(o + 16 * row + 8)) * s)
	return Transform3D(Basis(r[0], r[1], r[2]), r[3])


func _attach_cars() -> void:
	_car_attached = true
	var inv := _car_inv
	for car in _cars:
		inv[car] = car_transform(_cars[car], _live_axes).affine_inverse()
		if _wheels.has(car):
			var wi := []
			for w in _wheels[car]:
				wi.append((w as Transform3D).affine_inverse())
			_wheel_inv[car] = wi
	var per_car := {}
	var per_wheel := {}
	for mi in _scene.find_children("*", "MeshInstance3D", true, false):
		var m := mi as MeshInstance3D
		if m.mesh == null:
			continue
		var box: AABB = m.global_transform * m.get_aabb()
		if box.size.x > 6.0 or box.size.y > 6.0 or box.size.z > 6.0:
			continue
		for car in _cars:
			var inside := true
			for k in 8:
				var p: Vector3 = inv[car] * box.get_endpoint(k)
				if absf(p.x) > 1.5 or absf(p.y) > 2.0 or absf(p.z) > 3.2:
					inside = false
					break
			if inside:
				# A wheel's mesh (centre within 0.45 m of a wheel's centre, under 1 m across) follows that wheel's spin and
				# steering; everything else the body. (placed at D * this, D = A(t) * A(0)^-1)
				var wk := -1
				if _wheels.has(car) and maxf(box.size.x, maxf(box.size.y, box.size.z)) < 1.0:
					var c := box.get_center()
					var best_d := 0.45
					for k in 4:
						var d := c.distance_to((_wheels[car][k] as Transform3D).origin)
						if d < best_d:
							best_d = d
							wk = k
				_car_parts.append([m, car, m.global_transform, wk, (1 if _is_blur_wheel(m) else 0) if wk >= 0 else -1,
					String(m.name).begins_with("cockpit_"), m.cast_shadow])
				per_car[car] = per_car.get(car, 0) + 1
				if wk >= 0:
					per_wheel[car] = per_wheel.get(car, 0) + 1
				break
	for car in _cars:
		var o := car_transform(_cars[car], _live_axes).origin
		print("world_view: live car %08X at (%.2f, %.2f, %.2f): %d meshes attached (%d on its wheels)" % [car, o.x, o.y, o.z,
			per_car.get(car, 0), per_wheel.get(car, 0)])
	if per_car.size() < _cars.size():
		print("world_view: (a car with no meshes: the game was not at the glTF's grid when the viewer started, or its model is missing)")


func _set_view(xf: Transform3D) -> void:
	if _screens.is_empty():
		_cam.global_transform = xf
	else:
		for scr in _screens:
			var c: Camera3D = scr["camera"]
			c.global_transform = TripleCameras.screen_transform(xf, float(scr.get("rot_y", 0.0)))


func _live_step() -> void:
	if Input.is_key_pressed(KEY_ESCAPE):
		quit(0)
		return
	var tab := Input.is_key_pressed(KEY_TAB)
	if tab and not _live_tab and _live_dirs.size() > 1:
		_live_director = _live_dirs[(_live_dirs.find(_live_director) + 1) % _live_dirs.size()]
		print("world_view: live director %08X%s" % [_live_director, " (the drawn camera)" if _live_director == _live_dirs[0] else ""])
	_live_tab = tab
	# A picture on request: create <out>.shot and the next frame is saved to <out> (the file is removed).
	if _out != "" and FileAccess.file_exists(_out + ".shot"):
		DirAccess.remove_absolute(_out + ".shot")
		root.get_texture().get_image().save_png(_out)
		print("world_view: saved ", _out)
	var latest := PackedByteArray()
	var raw_now := Time.get_ticks_usec() / 1e6
	# The viewer's clock, steadied (2026-11-23): its frames reach the screen at a fixed refresh, but the time this code
	# runs wobbles by a millisecond or so; sampling the game at that raw time put the wobble into the motion. Each frame
	# advances by the smoothed frame interval, pulled 5% toward the raw time; a jump (a hitch) resets it.
	if _live_last_now > 0.0:
		var d := raw_now - _live_last_now
		if d > 0.0005 and d < 0.1:
			_view_dt = lerpf(_view_dt, d, 0.02)
	_live_last_now = raw_now
	var pred := _view_t + _view_dt
	_view_t = raw_now if _view_t == 0.0 or absf(raw_now - pred) > 0.03 else pred + 0.05 * (raw_now - pred)
	var now := _view_t
	while _udp.get_available_packet_count() > 0:
		var b := _udp.get_packet()
		if b.size() == 280 and b.slice(0, 4).get_string_from_ascii() == "FM3W" and b.decode_u32(4) == 1:
			# A car's four wheels as drawn (spin and steering), right after that car's datagram.
			var wcar := int(b.decode_u32(12))
			var ws := []
			for k in 4:
				ws.append(wheel_transform(b, k, _live_axes))
			_wheels[wcar] = ws
			if not _live_frames.is_empty():
				_live_frames[-1]["wheels"][wcar] = ws
			continue
		if b.size() != 96 or b.decode_u32(4) != 1:
			continue
		var magic := b.slice(0, 4).get_string_from_ascii()
		if magic == "FM3V":
			# A drawn game frame begins: its camera, then (the datagrams after it) its cars.
			# Its time on a steady timeline (2026-11-23): the game advances a fixed step per frame (the car moves the
			# same distance each frame to 0.2%), but the timestamps, taken on the render thread, wobble +-1.5 ms, and
			# placing frames by them made the shown motion uneven. So frame n sits one smoothed interval per frame
			# number after the last, pulled 2% toward its raw time; a gap of more than 50 ms resets the timeline.
			var raw_t := b.decode_double(88)
			var seq := int(b.decode_u32(8))
			var t := raw_t
			if not _live_frames.is_empty() and seq > _game_seq:
				var n := seq - _game_seq
				var dt := (raw_t - _game_raw) / n
				if dt > 0.0005 and dt < 0.1:
					_frame_dt = lerpf(_frame_dt, dt, 0.02)
				var pred_t := float(_live_frames[-1]["t"]) + _frame_dt * n
				t = raw_t if absf(raw_t - pred_t) > 0.05 else pred_t + 0.02 * (raw_t - pred_t)
			_game_seq = seq
			_game_raw = raw_t
			# Viewer clock minus game clock: a slow average (the old "smallest seen" crept up and snapped back).
			_clock_off = now - t if _clock_off == INF or absf((now - t) - _clock_off) > 0.1 else lerpf(_clock_off, now - t, 0.01)
			_live_frames.append({"t": t, "cam": live_transform(b, _live_axes), "fov": b.decode_float(80), "cars": {}, "wheels": {}})
			_live_vtable = int(b.decode_u32(84))  # (the game's active camera: first-person views show the cockpit)
			if _live_frames.size() > 32:
				_live_frames.pop_front()
			_live_has_drawn = true
			continue
		if magic == "FM3K":
			var car := int(b.decode_u32(12))
			# The car's speed (m/s, smoothed) from its positions and the game's timestamps: the wheels' motion blur.
			var pos := Vector3(b.decode_float(64), b.decode_float(68), b.decode_float(72))
			var tk := b.decode_double(88)
			if _car_prev.has(car):
				var dtk := tk - float(_car_prev[car][1])
				if dtk > 0.002 and dtk < 0.2:
					_car_speed[car] = lerpf(float(_car_speed.get(car, 0.0)), pos.distance_to(_car_prev[car][0]) / dtk, 0.2)
			if not _car_prev.has(car) or tk - float(_car_prev[car][1]) > 0.002:
				_car_prev[car] = [pos, tk]
			_cars[car] = b
			if _car_first_ms == 0:
				_car_first_ms = Time.get_ticks_msec()
			if not _live_frames.is_empty():
				_live_frames[-1]["cars"][car] = car_transform(b, _live_axes)
			continue
		if magic != "FM3C":
			continue
		var director := int(b.decode_u32(12))
		if not _live_dirs.has(director):
			_live_dirs.append(director)
			print("world_view: live director %08X seen (camera vtable %08X, fov %.2f deg)%s" % [director, b.decode_u32(84),
				rad_to_deg(b.decode_float(80)), "" if _live_dirs.size() > 1 else " (following it; Tab = next)"])
		if _live_director == 0:
			_live_director = director
		if director == _live_director:
			latest = b
	if not _car_attached and _car_first_ms > 0 and Time.get_ticks_msec() - _car_first_ms > 500:
		_attach_cars()
	var main_view := _live_dirs.is_empty() or _live_director == _live_dirs[0]
	if _live_has_drawn and main_view and not _live_frames.is_empty():
		_show_drawn(now)
	else:
		# No drawn frames (an older game build), or another director (Tab: the mirror): its hand-off, newest only.
		if _car_attached:
			for part in _car_parts:
				var b: PackedByteArray = _cars.get(part[1], PackedByteArray())
				if not b.is_empty() and _car_inv.has(part[1]):
					(part[0] as Node3D).global_transform = car_transform(b, _live_axes) * _car_inv[part[1]] * (part[2] as Transform3D)
		if latest.is_empty():
			return
		_set_view(live_transform(latest, _live_axes))
		if _screens.is_empty():
			_cam.fov = rad_to_deg(latest.decode_float(80))
	_live_packets += 1
	if Time.get_ticks_msec() - _live_last_ms > 5000:
		_live_last_ms = Time.get_ticks_msec()
		print("world_view: live camera ", _cam.global_transform if _screens.is_empty() else _screens[0]["camera"].global_transform,
			" (viewer %d fps, game frames every %.1f ms, shown %.1f ms behind)%s" % [Engine.get_frames_per_second(), _frame_dt * 1000,
			_live_delay() * 1000, " raw" if _live_raw else (" smooth %.1f" % _live_smooth if _live_smooth > 0.0 else "")])


# The game's drawn frames, interpolated: show the moment 1.5 game frames ago (host clock mapped by the smallest
# latency seen), blending camera, field of view and every car between the two frames around it, so the viewer's own
# frame rate never has to match the game's. --live-raw shows the newest frame as it is.
func _show_drawn(now: float) -> void:
	var s: Dictionary
	if _live_raw or _live_frames.size() < 2:
		s = _sample(INF)
	else:
		# --live-smooth W (game frames; 0 = off): average two samples W game frames apart around the moment shown. The
		# game moves its cars by uneven steps on about 12% of its frames (+-4-9%, often alternating); W = 1 cancels
		# that frame-to-frame alternation, for W/2 game frames more delay.
		var t := now - _clock_off - _live_delay()
		if _live_smooth > 0.0:
			var h := 0.5 * _live_smooth * _frame_dt
			var a := _sample(t - h)
			var b := _sample(t + h)
			var mv := {}
			for car in a["moves"]:
				if b["moves"].has(car):
					mv[car] = (a["moves"][car] as Transform3D).interpolate_with(b["moves"][car] as Transform3D, 0.5)
			var wv := {}
			for car in a["wmoves"]:
				if b["wmoves"].has(car):
					var ws := []
					for k in 4:
						ws.append((a["wmoves"][car][k] as Transform3D).interpolate_with(b["wmoves"][car][k] as Transform3D, 0.5))
					wv[car] = ws
			s = {"cam": (a["cam"] as Transform3D).interpolate_with(b["cam"] as Transform3D, 0.5),
				"fov": 0.5 * (float(a["fov"]) + float(b["fov"])), "moves": mv, "wmoves": wv}
		else:
			s = _sample(t)
	var cam: Transform3D = s["cam"]
	var moves: Dictionary = s["moves"]
	_set_view(cam)
	if _screens.is_empty():
		_cam.fov = rad_to_deg(float(s["fov"]))
	if not _car_attached:
		return
	var wmoves: Dictionary = s.get("wmoves", {})
	# The cockpit (PLAN-CARS phase 4): in the game's in-car views (CCamDriver 0x8200206C, CCamCockpit 0x82034FC4) the
	# player car (the one nearest the camera) shows its cockpit model instead of its body and wheels.
	var player := -1
	var pdist := INF
	for car in moves:
		var o: Vector3 = (moves[car] as Transform3D) * ((_car_inv[car] as Transform3D).affine_inverse().origin)
		if o.distance_to(cam.origin) < pdist:
			pdist = o.distance_to(cam.origin)
			player = car
	var in_car := _live_vtable == 0x8200206C or _live_vtable == 0x82034FC4
	for part in _car_parts:
		var mine: bool = int(part[1]) == player and in_car
		var gi := part[0] as GeometryInstance3D
		if bool(part[5]):
			gi.visible = mine
		else:
			# (the body stays as a shadow caster only: its roof and doors still shade the cabin, as in the game)
			var own: int = part[6]
			# Meshes that cast no shadow (glass, the exterior model's own low-detail interior and dash) are hidden outright:
			# as SHADOWS_ONLY they would stay drawn, the outside view's dash over the cockpit's.
			if own != GeometryInstance3D.SHADOW_CASTING_SETTING_OFF:
				gi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_SHADOWS_ONLY if mine else own
			elif int(part[3]) < 0:
				gi.visible = not mine
	for part in _car_parts:
		var wk: int = part[3]
		if int(part[4]) >= 0:
			# Wheel motion blur: the game's blurred wheel meshes fade in between 4 and 14 m/s (fully blurred at the 67 km/h
			# of the captured race), the sharp rim and spokes out.
			var blur := smoothstep(4.0, 14.0, float(_car_speed.get(part[1], 0.0)))
			(part[0] as GeometryInstance3D).transparency = (1.0 - blur) if int(part[4]) == 1 else blur
		if wk >= 0 and wmoves.has(part[1]):
			(part[0] as Node3D).global_transform = (wmoves[part[1]][wk] as Transform3D) * (part[2] as Transform3D)
		elif moves.has(part[1]):
			(part[0] as Node3D).global_transform = (moves[part[1]] as Transform3D) * (part[2] as Transform3D)
	if not _live_cube_cams.is_empty():
		# the live reflection cube follows the player car (the car nearest the camera), 0.8 m above its origin
		var pc := Vector3.ZERO
		var pd := INF
		for car in moves:
			var o: Vector3 = (moves[car] as Transform3D) * ((_car_inv[car] as Transform3D).affine_inverse().origin)
			if o.distance_to(cam.origin) < pd:
				pd = o.distance_to(cam.origin)
				pc = o
		if pd < INF:
			_place_live_cube(pc + Vector3(0, 0.8, 0))
	if _live_log != null:
		# What this viewer frame shows: the camera and the car nearest to it (the one it follows).
		var best := -1
		var best_d := INF
		var best_o := Vector3.ZERO
		for car in moves:
			var o: Vector3 = (moves[car] as Transform3D) * ((_car_inv[car] as Transform3D).affine_inverse().origin)
			var d := o.distance_to(cam.origin)
			if d < best_d:
				best_d = d
				best = car
				best_o = o
		_live_log.store_line("%.6f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f" % [now, cam.origin.x, cam.origin.y, cam.origin.z, best_o.x, best_o.y, best_o.z])


# How far behind the game the viewer shows it: 1.5 game frames (so the frame after the moment has arrived), plus half
# the smoothing width, plus 2 ms.
func _live_delay() -> float:
	return _frame_dt * (1.5 + 0.5 * _live_smooth) + 0.002


# The game at time t (game clock; INF = the newest frame): camera, field of view and each car's move D = A(t) * A(0)^-1,
# blended between the two drawn frames around t.
func _sample(t: float) -> Dictionary:
	var k1 := _live_frames.size() - 1
	var k0 := k1
	var alpha := 1.0
	if t != INF and _live_frames.size() > 1:
		var i := _live_frames.size() - 1
		while i > 0 and float(_live_frames[i]["t"]) > t:
			i -= 1
		k0 = i
		k1 = mini(i + 1, _live_frames.size() - 1)
		var span := float(_live_frames[k1]["t"]) - float(_live_frames[k0]["t"])
		alpha = clampf((t - float(_live_frames[k0]["t"])) / span, 0.0, 1.0) if span > 0.0 else 1.0
	var f0: Dictionary = _live_frames[k0]
	var f1: Dictionary = _live_frames[k1]
	var moves := {}
	if _car_attached:
		for car in _car_inv:
			var a0 = _car_in_frame(car, k0)
			var a1 = _car_in_frame(car, k1)
			if a0 == null or a1 == null:
				continue
			var d0: Transform3D = (a0 as Transform3D) * (_car_inv[car] as Transform3D)
			var d1: Transform3D = (a1 as Transform3D) * (_car_inv[car] as Transform3D)
			d0.basis = d0.basis.orthonormalized()
			d1.basis = d1.basis.orthonormalized()
			moves[car] = d0.interpolate_with(d1, alpha)
	# Each wheel's move, the same way (spin between two frames stays under half a turn up to ~200 km/h at 60 fps).
	var wmoves := {}
	if _car_attached:
		for car in _wheel_inv:
			var w0 = _wheels_in_frame(car, k0)
			var w1 = _wheels_in_frame(car, k1)
			if w0 == null or w1 == null:
				continue
			var ws := []
			for k in 4:
				var e0: Transform3D = (w0[k] as Transform3D) * (_wheel_inv[car][k] as Transform3D)
				var e1: Transform3D = (w1[k] as Transform3D) * (_wheel_inv[car][k] as Transform3D)
				e0.basis = e0.basis.orthonormalized()
				e1.basis = e1.basis.orthonormalized()
				ws.append(e0.interpolate_with(e1, alpha))
			wmoves[car] = ws
	return {"cam": (f0["cam"] as Transform3D).interpolate_with(f1["cam"] as Transform3D, alpha),
		"fov": lerpf(float(f0["fov"]), float(f1["fov"]), alpha), "moves": moves, "wmoves": wmoves}


# A car's four wheel matrices as of frame k (that frame's, or the latest earlier ones).
func _wheels_in_frame(car: int, k: int):
	while k >= 0:
		var w: Dictionary = _live_frames[k]["wheels"]
		if w.has(car):
			return w[car]
		k -= 1
	return null


# A car's matrix as of frame k: that frame's, or the latest earlier one (a car can be missing from a frame).
func _car_in_frame(car: int, k: int):
	while k >= 0:
		var cars: Dictionary = _live_frames[k]["cars"]
		if cars.has(car):
			return cars[car]
		k -= 1
	return null


func _process(_delta: float) -> bool:
	_frames += 1
	if _live_port > 0 and _frames > 3:
		_live_step()
		return false
	if _fly and _frames > 3:
		if _frames == 4:
			_fly_xf = _cam.global_transform
			var fwd := -_fly_xf.basis.z
			_yaw = atan2(-fwd.x, -fwd.z)
			_pitch = asin(clamp(fwd.y, -1.0, 1.0))
			print("world_view: free-fly mode (WASD, Q/E, right mouse to look, Shift/Ctrl speed, Esc quits)")
		_fly_step(_delta)
		return false
	if _frames == 2 and _triple_layout != "":
		var layout = JSON.parse_string(FileAccess.get_file_as_string(_triple_layout))
		_screen_size = root.size
		root.size = Vector2i(_screen_size.x * 3, _screen_size.y)
		DisplayServer.window_set_size(root.size)
		_screens = TripleCameras.make_screens(root, _screen_size)
		for scr in _screens:
			scr["viewport"].mesh_lod_threshold = 0.0
			scr["viewport"].msaa_3d = {2: Viewport.MSAA_2X, 4: Viewport.MSAA_4X, 8: Viewport.MSAA_8X}.get(_msaa, Viewport.MSAA_DISABLED)
		var game := _cam.global_transform
		for k in 3:
			var sc: Dictionary = layout["screens"][k]
			_screens[k]["rot_y"] = float(sc["rot_y"])
			TripleCameras.apply(_screens[k]["camera"], game, float(sc["rot_y"]), float(sc["size"]),
				Vector2(float(sc["offset"][0]), float(sc["offset"][1])), float(sc["near"]), float(sc["far"]))
		print("world_view: triple screens from ", _triple_layout)
	if _frames == 2:
		var first := _scene.find_child("draw723", true, false) as Node3D
		if first:
			var mi := first as MeshInstance3D
			var v0: Vector3 = mi.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX][0] if mi and mi.mesh else Vector3.ZERO
			print("world_view: draw723 ", first.global_transform, " v0 ", v0, " world ", first.global_transform * v0, " screen ", _cam.unproject_position(first.global_transform * v0))
		print("world_view: camera ", _cam.global_transform)
	if _frames == 8 and not _screens.is_empty():
		var out := Image.create(_screen_size.x * 3, _screen_size.y, false, Image.FORMAT_RGBA8)
		for k in 3:
			var im: Image = _screens[k]["viewport"].get_texture().get_image()
			im.convert(Image.FORMAT_RGBA8)
			out.blit_rect(im, Rect2i(Vector2i.ZERO, _screen_size), Vector2i(_screen_size.x * k, 0))
		out.save_png(_out)
		print("world_view: saved ", _out)
		if _bench == 0:
			quit(0)
		_bench_t0 = Time.get_ticks_usec()
	if _bench > 0 and _frames == 8 + 60:
		_bench_t0 = Time.get_ticks_usec()  # (after 60 warm-up frames)
	if _bench > 0 and _frames == 8 + 60 + _bench:
		var secs := (Time.get_ticks_usec() - _bench_t0) / 1e6
		print("world_view: bench %d frames in %.3f s = %.1f fps (%s, %d draws visible to the renderer)" % [_bench, secs, _bench / secs,
			"triple" if not _screens.is_empty() else "single", RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TOTAL_DRAW_CALLS_IN_FRAME)])
		quit(0)
	if _frames == 5 and _screens.is_empty():
		var img := root.get_texture().get_image()
		img.save_png(_out)
		print("world_view: saved ", _out)
		if _bench == 0:
			quit(0)
	return false
