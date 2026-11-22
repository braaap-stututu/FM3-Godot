extends SceneTree
# Loads a fir_world.py glTF at run time, looks through its capture_camera and saves one picture.
#   Godot_v4.7.2-stable_win64.exe --path frame-ir/godot -s res://viewer/world_view.gd -- --gltf <file> --out <png> [--size 1280x720] [--textured]

var _out := ""
var _frames := 0
var _scene: Node
var _cam: Camera3D
var _triple_layout := ""  # --triple <layout.json>: three screens (core/triple_view layout), stitched side by side
var _screens := []
var _msaa := 0  # --msaa 2|4|8 on the screens
var _bench := 0  # --bench N: after the picture, render N more frames and report the frame rate
var _bench_t0 := 0
var _screen_size := Vector2i(1280, 720)
const TripleCameras = preload("res://triple_cameras.gd")
const BAKED_SHADER = preload("res://viewer/fm3_baked.gdshader")


func _init() -> void:
	var args := OS.get_cmdline_user_args()
	var gltf_path := ""
	var size := Vector2i(1280, 720)
	var no_shadows := false
	var grey_shadow := false  # debug: one grey lit material everywhere, sun shadows on
	var lit := false  # --lit: materials shaded, a sun with shadows and sky ambient (--sun elevation,azimuth in degrees)
	var sun_elev := 50.0
	var sun_azim := 30.0
	var textured := false  # --textured: the glTF's own materials, unshaded (no normals yet); else one grey lit material
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
	var baked_gain := 1.15  # (calibrated against the game: the sun now reaches the baked world)
	var grey_unshaded := StandardMaterial3D.new()
	grey_unshaded.albedo_color = Color(0.5, 0.5, 0.5)
	grey_unshaded.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	grey_unshaded.cull_mode = BaseMaterial3D.CULL_DISABLED
	for n in scene.find_children("*", "MeshInstance3D", true, false):
		var mi := n as MeshInstance3D
		meshes += 1
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
			m = m.duplicate()
			if m.shading_mode != BaseMaterial3D.SHADING_MODE_UNSHADED:  # (the glTF's unlit materials stay unlit)
				m.shading_mode = BaseMaterial3D.SHADING_MODE_PER_PIXEL if lit else BaseMaterial3D.SHADING_MODE_UNSHADED
			m.cull_mode = BaseMaterial3D.CULL_DISABLED
			if lit and m.ao_enabled and m.ao_texture != null and m.ao_on_uv2 and m.transparency != BaseMaterial3D.TRANSPARENCY_ALPHA:
				# FM3's static world: its baked colour lightmap (slot 7, UV2) carries the light; the sun only adds
				# the shadows of dynamic objects (fm3_baked.gdshader). Its own shadows are in the lightmap: it casts none.
				var sm := ShaderMaterial.new()
				sm.shader = BAKED_SHADER
				sm.set_shader_parameter("albedo_tex", m.albedo_texture)
				sm.set_shader_parameter("light_tex", m.ao_texture)
				sm.set_shader_parameter("albedo_color", m.albedo_color)
				sm.set_shader_parameter("gain", baked_gain)
				if m.transparency == BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR:
					sm.set_shader_parameter("alpha_cut", m.alpha_scissor_threshold)
				mi.set_surface_override_material(s, sm)
				mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
				baked += 1
				if m.albedo_texture == null:
					baked_no_tex += 1
				continue
			if lit and m.transparency == BaseMaterial3D.TRANSPARENCY_ALPHA and m.roughness < 0.1 and m.albedo_texture == null:
				m.metallic_specular = 0.6  # glass: strong Fresnel reflections of the probe and sky
				m.specular_mode = BaseMaterial3D.SPECULAR_SCHLICK_GGX
			if lit and m.roughness >= 0.9:
				m.metallic_specular = 0.15  # matte surfaces: little sky reflection at grazing angles (FM3's look)
			m.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
			mi.set_surface_override_material(s, m)
	var cams := scene.find_children("*", "Camera3D", true, false)
	if cams.is_empty():
		push_error("no camera in the glTF")
		quit(1)
		return
	var cam := cams[0] as Camera3D
	cam.keep_aspect = Camera3D.KEEP_HEIGHT
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
		env.environment.ambient_light_energy = 0.85
		env.environment.reflected_light_source = Environment.REFLECTION_SOURCE_SKY
		env.environment.tonemap_mode = Environment.TONE_MAPPER_FILMIC
		env.environment.tonemap_exposure = 1.2
		env.environment.adjustment_enabled = true
		env.environment.adjustment_contrast = 1.12
		env.environment.adjustment_saturation = 0.95
	root.add_child(env)
	if lit:
		# Reflections of the real scene (FM3 renders a dynamic environment map for its car paint and glass): one probe
		# around the grid, rendered once from just above the cars.
		var probe := ReflectionProbe.new()
		probe.size = Vector3(260, 80, 260)
		probe.update_mode = ReflectionProbe.UPDATE_ONCE
		probe.max_distance = 1500.0
		probe.ambient_mode = ReflectionProbe.AMBIENT_DISABLED
		probe.position = cam.global_transform.origin + (-cam.global_transform.basis.z * 8.0) + Vector3(0, 0.6, 0) if cam.is_inside_tree() else cam.transform.origin + (-cam.transform.basis.z * 8.0) + Vector3(0, 0.6, 0)
		root.add_child(probe)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-sun_elev, sun_azim, 0)
	var glights := scene.find_children("*", "DirectionalLight3D", true, false)
	if not glights.is_empty():  # the capture's sun (fir_world.py writes FM3's sun direction)
		sun.global_transform = (glights[0] as Node3D).global_transform if (glights[0] as Node3D).is_inside_tree() else (glights[0] as Node3D).transform
		(glights[0] as Node3D).visible = false
		print("world_view: sun from the glTF")
	sun.light_energy = 1.45 if lit else 1.0
	sun.light_color = Color(1.0, 0.97, 0.92)
	sun.shadow_enabled = (lit or grey_shadow) and not no_shadows
	print("world_view: sun forward ", -sun.global_transform.basis.z if sun.is_inside_tree() else -sun.transform.basis.z, " shadows ", sun.shadow_enabled)
	sun.directional_shadow_max_distance = 250.0
	root.add_child(sun)
	print("world_view: camera ", cam.global_transform if cam.is_inside_tree() else cam.transform, " parent ", cam.get_parent().name)
	print("world_view: %d surfaces lit by FM3's baked lightmaps (%d without an albedo texture)" % [baked, baked_no_tex])
	print("world_view: %d mesh instances, camera fov %.2f near %.3f" % [meshes, cam.fov, cam.near])


func _process(_delta: float) -> bool:
	_frames += 1
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
