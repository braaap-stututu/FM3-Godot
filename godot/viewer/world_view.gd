extends SceneTree
# Loads a fir_world.py glTF at run time, looks through its capture_camera and saves one picture.
#   Godot_v4.7.2-stable_win64.exe --path frame-ir/godot -s res://viewer/world_view.gd -- --gltf <file> --out <png> [--size 1280x720] [--textured | --lit] [--triple layout.json] [--fly]

var _out := ""
var _frames := 0
var _scene: Node
var _cam: Camera3D
var _sky_nodes := []  # the sky dome's meshes: kept on the camera (_process)
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
# Lights (2026-11-24). The game lights a car's tail_light meshes by brakeReverseAmount (shader c198) x BrakeColor (the
# material's ShaderSettings: tail_light_lod0 7,0,0); its source per car was not found yet, so: the player's from its own
# brake input ("FM3E" v3, exact), every other car's from its deceleration (over 2.5 m/s2 above walking pace: an
# approximation; engine braking alone stays under it). Reverse lights (reverse_light meshes) when a car moves backwards.
var _car_accel := {}  # car -> acceleration along its path, m/s2 (smoothed)
var _car_back := {}  # car -> true while it moves backwards
var _car_lit := {}  # car -> brake light amount shown (0..1)
var _player_brake := -1.0  # the player's brake input ("FM3E" v3; -1 = none)
var _light_mats := {}  # car -> [[material, "brake" | "reverse"], ...]
# The live reflection cube is the player's car's only (the game's paint shader picks t6 / t7: the player car's cube,
# rendered every frame around it, or the static one): the other cars reflect the layout's static cube. Before this they
# all reflected the cube rendered at the player's car, wrong place and 128 px: streaks on the Eclipse's doors.
var _car_shader_mats := {}  # car -> its paint / glass ShaderMaterials
var _live_player := -2
const BRAKE_DECEL := 2.5
const BRAKE_ENERGY := 2.0  # emission at full brake (gamma-space look fitted by eye; the game's BrakeColor is HDR 7)
var _gltf_path := ""
var _car_names := {}  # car -> {name, color, metallic} ("FM3N")
var _library_tried := {}  # cars a library model was tried for
var _library_queue := []  # cars waiting for their library model
# The in-car view (2026-11-24, capture-free CrownJewel, RB twice): the game shows the outside brighter from the cockpit
# than from the chase camera (sky 209 vs 178; Godot 166 = as in its chase view) and its cabin dark (dash 19; Godot 30):
# its cockpit has no directional light (TrackSettings SHCockpitDir 0) and the view a higher exposure. Cockpit meshes
# sit on their own render layer the sun leaves out, and the exposure rises in-car by IN_CAR_EXPOSURE.
const COCKPIT_LAYER := 8
const STATIC_LAYER := 16  # (the lightmapped track: casts shadows only for the DYNLIT sun)
const DYNLIT_LAYER := 32  # (the track's sun-lit surfaces, fm3_dynlit: lit by their own sun)
# fm3_dynlit for the track's unlightmapped surfaces with static shadows from a second sun: opt-in (FM3_DYNLIT=1). Measured
# 2026-11-24: offline grid 19.5/18.6/17.6 -> 18.7/18.4/18.2, live 19.9/18.4/18.1 -> 19.1/18.2/18.7 (sunlit walls right,
# blue up), but the viewer 29 -> 23 fps (the static track in the second shadow map); the shader alone without the second
# sun scored the same average as Godot's lighting.
var DYNLIT := OS.get_environment("FM3_DYNLIT") != ""
var DYNLIT_SHADOWS := OS.get_environment("FM3_DYNLIT") == "1"  # (2 = the shader on the main sun, no static shadows)
var CABIN_K := float(OS.get_environment("FM3_CABIN_K")) if OS.get_environment("FM3_CABIN_K") != "" else 1.0
const COCKPIT_GAIN := 1.0  # (fm3_cockpit.gdshader's light scale)
# Cockpit mirrors (fm3_mirror.gdshader): one small viewport each, rendered only while the player's car is seen in-car.
const MIRROR_SIZE := Vector2i(512, 256)
# (fitted on the CR-X's middle mirror, live: 30 deg level 37.4, 6 deg up 33.8, 40 deg + 6 up 31.5 mean |diff| in its crop)
const MIRROR_FOV := 40.0  # (vertical degrees of a mirror's picture)
const MIRROR_PITCH := 6.0  # (degrees up from level)
const MIRROR_FAR := 300.0  # (metres: a mirror's far scene is a few pixels; drawn to 2 km, in-car 29 fps, now 30)
var _mirrors_on := true
var _car_lead := 0.0
var _mirror_turn := 0
var _mirrors := []  # [{mesh, car, centre, normal, radius (mesh space), mat, vp, cam}]
const IN_CAR_EXPOSURE := 1.5
# The gauges (unshaded, seen in-car only): the game's daylight dials are grey markings (~150) on black; at gain 1 / 1.5
# (the exposure undone) Godot's were white (~250) on grey, cluster p95 165 vs the game's 58. 0.25 fitted on the markings.
const GAUGE_GAIN := 0.25
var _world_env: WorldEnvironment = null
var _base_exposure := 1.0
var _was_in_car := false
var _shot_held_since := -1  # (ms: a requested picture waiting for the library cars)
var _shot_settle := 3
var _cars_with_parts := {}  # cars with meshes attached
var _sun_to := Vector3(0, 1, 0)  # towards the sun (glass highlights)
var _carmats := {}  # car mesh node name -> its glass parameters from the game's shader settings (<gltf>_carmaterials.json)
var _needles := {}  # cockpit gauge needle node name -> {pivot, axis, mid, max, gauge, ticks} (<gltf>_needles.json)
var _wheel_inv := {}  # car -> its four wheel matrices at attach time, inverted
var _clock_off := INF  # Godot clock minus game clock (smallest seen)
var _frame_dt := 1.0 / 120.0  # the game's frame interval (smoothed)
var _live_raw := false  # --live-raw: the newest frame, no interpolation
var _live_last_now := 0.0
var _engine_rpm := -1.0  # the player's engine speed ("FM3E"; -1 = none yet): the cockpit tach
# The cockpit steering wheel (--steering-wheel game|input|off, F7 cycles them while running):
#   game  = as FM3 turns it: player 1's steering input x the car's wheel angle (carattribs, STEER_GAME_DEG)
#   input = 1:1 with a real racing wheel: the input x half its lock (wheel_lock, streamed; --wheel-lock DEG for a pad)
#   off   = no steering wheel drawn
const STEER_MODES := ["game", "input", "off"]
var _steer_mode := "game"
var _steer := 0.0  # player 1's steering input, -1..1 ("FM3E" v2)
var _steer_lock := 0.0  # the racing wheel's lock in degrees as the game has it set (0 = no wheel)
var _wheel_lock_arg := 900.0  # --wheel-lock: the lock "input" uses when the game reports no wheel
var _f7 := false
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
const CARLENS_SHADER = preload("res://viewer/fm3_carlens.gdshader")
const BLEND_SHADER = preload("res://viewer/fm3_blend.gdshader")
const BLEND_ALPHA_SHADER = preload("res://viewer/fm3_blend_alpha.gdshader")


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
				_gltf_path = gltf_path
				var cm_ := gltf_path.get_basename() + "_carmaterials.json"
				if FileAccess.file_exists(cm_):
					var cparsed = JSON.parse_string(FileAccess.get_file_as_string(cm_))
					if cparsed is Dictionary:
						_carmats = cparsed
				var np_ := gltf_path.get_basename() + "_needles.json"
				if FileAccess.file_exists(np_):
					var parsed = JSON.parse_string(FileAccess.get_file_as_string(np_))
					if parsed is Dictionary:
						_needles = parsed
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
			"--steering-wheel":  # game | input | off (F7 cycles)
				_steer_mode = args[i + 1]; i += 1
				if not STEER_MODES.has(_steer_mode):
					push_error("--steering-wheel: game, input or off"); _steer_mode = "game"
			"--wheel-lock":  # degrees of real-wheel travel for full steering, for "input" without a wheel in the game
				_wheel_lock_arg = float(args[i + 1]); i += 1
			"--live-cube":  # the live reflection cube's face size in pixels (0 = the layout's static cube)
				_live_cube_size = int(args[i + 1]); i += 1
			"--mirrors":  # 0 = the cockpit mirrors stay dark glass (no mirror viewports)
				_mirrors_on = args[i + 1] != "0"; i += 1
			"--live-car-lead":  # sample the cars this many ms later than the camera
				_car_lead = float(args[i + 1]) / 1000.0; i += 1
			"--live-cube-faces":  # live cube faces rendered per frame, round-robin (6 = all, every frame)
				_live_cube_faces = clampi(int(args[i + 1]), 1, 6); i += 1
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
	# Textures GPU-compressed (2026-11-24): uncompressed, Ladera's 2,072 textures took ~2.8 GB of video memory (RGBA8 +
	# mips); with FM3 beside it (3.7 GB at 720p) and the desktop (~1.7 GB) the 8 GB RX 6650 XT ran out and the viewer died
	# loading. The glTF is read with its textures left out, then each is decoded, given mipmaps, compressed to BC1 / BC3
	# (as the game keeps them, DXT) and bound to its materials (_bind_textures): nothing uncompressed reaches the GPU.
	# --no-texture-compression = Godot's own loading.
	var compress_tex := not OS.get_cmdline_user_args().has("--no-texture-compression")
	if compress_tex:
		state.handle_binary_image = 0  # (discard: _bind_textures loads them)
	var t_load := Time.get_ticks_msec()
	if doc.append_from_file(gltf_path, state) != OK:
		push_error("cannot read " + gltf_path)
		quit(1)
		return
	if compress_tex:
		_bind_textures(state, gltf_path)
		print("world_view: textures GPU-compressed, loaded in %.1f s" % ((Time.get_ticks_msec() - t_load) / 1000.0))
	var scene := doc.generate_scene(state)
	root.add_child(scene)
	_scene = scene
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.75, 0.75, 0.72)
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	var meshes := 0
	var baked := 0
	var baked_no_tex := 0
	var glass_set := 0
	var rim_set := 0
	var dynlit_set := 0
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
		if String(mi.name).begins_with("skydome_"):
			_sky_nodes.append(mi)
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
				mi.set_meta("fm3_static", true)
				baked += 1
				continue
			m = m.duplicate()
			if m.resource_name == "fm3_shadow_blob":
				# a car's soft contact shadow (fir_world.py): lie just above the road it would otherwise z-fight
				mi.position += Vector3(0, 0.03, 0)  # (before entering the tree: local = world, glTF nodes sit at the root)
				mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			if m.has_meta("extras") and m.get_meta("extras") is Dictionary and m.get_meta("extras").has("fm3_sky_gain"):
				# the sky dome's brightness against CrownJewel's (TrackSettings skyScale / tone white point; fm3_track_export)
				var sg := float(m.get_meta("extras")["fm3_sky_gain"])
				m.albedo_color = Color(m.albedo_color.r * sg, m.albedo_color.g * sg, m.albedo_color.b * sg, m.albedo_color.a)
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
				_apply_track_light(sm, gltf_path)
				if m.transparency == BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR:
					sm.set_shader_parameter("alpha_cut", m.alpha_scissor_threshold)
				if _blended(m):
					mi.sorting_offset = -1.0  # (decals over the ground they lie on)
				mi.set_surface_override_material(s, sm)
				mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
				mi.set_meta("fm3_static", true)
				baked += 1
				if m.albedo_texture == null:
					baked_no_tex += 1
				continue
			if lit and _blended(m) and m.roughness < 0.1 and m.albedo_texture == null:
				# car glass: FM3's dark, reflective windows (fm3_carglass.gdshader), not a clear pane
				var lens_ := String(mi.name).contains("detail_glass") or String(mi.name).contains("red_glass")
				var gm_ := _car_material(CARLENS_SHADER if lens_ else CARGLASS_SHADER, m, gltf_path, "FM3_CARGLASS",
					["env_scale", "fresnel_min", "fresnel_power", "max_opacity"])
				# this mesh's own glass (the game's Media\Cars\ShaderSettings + the car's overrides: lenses red / amber /
				# clear, windows, mirrors); without an entry the shader's defaults = the window
				var gp_: Dictionary = _carmats.get(String(mi.name), {})
				for k_ in gp_:
					var v_ = gp_[k_]
					if v_ is Array:
						gm_.set_shader_parameter(k_, Vector4(v_[0], v_[1], v_[2], v_[3]) if k_ == "glass_color" else Vector3(v_[0], v_[1], v_[2]))
					else:
						gm_.set_shader_parameter(k_, float(v_))
				if not gp_.is_empty():
					glass_set += 1
				_lens_sync(gm_)
				# (offline: FM3_PLAYER_CAR=<car> marks that car's glass as the player's, fm3_carglass player_glass)
				if OS.get_environment("FM3_PLAYER_CAR") != "" and String(mi.name).contains(OS.get_environment("FM3_PLAYER_CAR")):
					gm_.set_shader_parameter("player_glass", true)
				mi.set_surface_override_material(s, gm_)
				continue
			if lit and m.roughness >= 0.9:
				m.metallic_specular = 0.04  # matte surfaces: almost no sky reflection (FM3's dark trim stays dark)
			if lit and m.roughness_texture != null and m.albedo_texture != null:
				# car paint (fir_world.py writes a roughness texture only for paint): FM3's paint shader
				# (fm3_carpaint.gdshader: lit colour + Fresnel environment reflection + sun highlight)
				var pm_ := _car_material(CARPAINT_SHADER, m, gltf_path, "FM3_CARPAINT",
					["refl_gain", "refl_f0", "spec_gain", "spec_power", "shadow_strength", "refl_metal"])
				if String(mi.name).begins_with("wheel_"):
					# rims are painted (the game's rim material has a PaintScale, 0.75; the capture gave them the paint
					# shader): its colour at that scale and a far weaker reflection than body paint (light grey spokes
					# where the game's are dark; same cause as the chrome's)
					pm_.set_shader_parameter("albedo_color", Vector4(m.albedo_color.r * 0.75, m.albedo_color.g * 0.75, m.albedo_color.b * 0.75, m.albedo_color.a))
					pm_.set_shader_parameter("refl_gain", RIM_REFLECTION)
					pm_.set_shader_parameter("refl_metal", RIM_REFLECTION)
					pm_.set_shader_parameter("spec_gain", 0.3)
					rim_set += 1
				mi.set_surface_override_material(s, pm_)
				continue
			m.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
			if lit and m.metallic >= 0.9 and (String(mi.name).begins_with("carbin_") or String(mi.name).begins_with("wheel_")):
				# car chrome (mirror faces, exhaust tips, trim): it reflects the game's own car cube, far darker than this
				# viewer's surroundings (the windows' env_scale 0.2, fm3_carglass.gdshader): the same scale here
				m.albedo_color = Color(m.albedo_color.r * CHROME_SCALE, m.albedo_color.g * CHROME_SCALE, m.albedo_color.b * CHROME_SCALE, m.albedo_color.a)
			if lit and String(mi.name).begins_with("wheel_") and m.metallic < 0.9:
				# rims: the game lights them by its ambient (SH) light, not the sun, at PaintScale 0.75 (ShaderSettings
				# rim): here the sunlit albedo at RIM_SCALE
				m.albedo_color = Color(m.albedo_color.r * RIM_SCALE, m.albedo_color.g * RIM_SCALE, m.albedo_color.b * RIM_SCALE, m.albedo_color.a)
				# (and their reflection: what made them light grey was Godot's reflection of its bright surroundings, the
				# chrome's problem: a colour scale of 0 changed nothing)
				m.metallic_specular = RIM_SPECULAR
				rim_set += 1
			if mi.mesh.surface_get_format(s) & Mesh.ARRAY_FORMAT_COLOR:
				m.vertex_color_use_as_albedo = true  # (the cockpit's baked brightness, fm3_track_export.py)
			if m.resource_name.contains("gauge") and m.albedo_texture != null:
				# cockpit gauges: lit markings (the texture's alpha) on a dark face (fm3_gauge.gdshader)
				var gm := ShaderMaterial.new()
				gm.shader = load("res://viewer/fm3_gauge.gdshader")
				gm.set_shader_parameter("tex", m.albedo_texture)
				gm.set_shader_parameter("gain", GAUGE_GAIN)
				mi.set_surface_override_material(s, gm)
				continue
			if lit and DYNLIT and m.albedo_texture != null and m.shading_mode == BaseMaterial3D.SHADING_MODE_PER_PIXEL and not _blended(m) \
					and not _is_car_mesh(mi) and not String(mi.name).begins_with("draw") and not String(mi.name).begins_with("skydome_") \
					and m.resource_name != "fm3_shadow_blob":
				# the track's sun-lit surfaces without a lightmap: the game's formula (fm3_dynlit.gdshader)
				var dm := ShaderMaterial.new()
				dm.shader = load("res://viewer/fm3_dynlit.gdshader")
				dm.set_shader_parameter("albedo_tex", m.albedo_texture)
				dm.set_shader_parameter("albedo_color", _vec4(m.albedo_color))
				dm.set_shader_parameter("use_vcol", m.vertex_color_use_as_albedo)
				if m.transparency == BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR:
					dm.set_shader_parameter("alpha_cut", m.alpha_scissor_threshold)
				mi.set_surface_override_material(s, dm)
				mi.set_meta("fm3_dyn", true)
				dynlit_set += 1
				continue
			mi.set_surface_override_material(s, m)
	if lit and DYNLIT_SHADOWS:
		# Static shadows for the sun-lit surfaces (fm3_dynlit): the lightmapped track casts for a second sun that lights only
		# them (DYNLIT_LAYER, set below with the main sun); the main sun ignores static casters (their shadows are in the
		# lightmaps). Meshes mixing both kinds stay with the main sun.
		for mi2 in scene.find_children("*", "MeshInstance3D", true, false):
			if mi2.has_meta("fm3_static"):
				mi2.layers = STATIC_LAYER
				mi2.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
			elif mi2.has_meta("fm3_dyn"):
				mi2.layers = DYNLIT_LAYER
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
	_world_env = env
	_base_exposure = env.environment.tonemap_exposure
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
	sun.light_cull_mask = 0xFFFFF & ~COCKPIT_LAYER & ~DYNLIT_LAYER
	sun.shadow_caster_mask = 0xFFFFF & ~STATIC_LAYER
	if not DYNLIT_SHADOWS:
		sun.light_cull_mask = 0xFFFFF & ~COCKPIT_LAYER
	sun.rotation_degrees = Vector3(-sun_elev, sun_azim, 0)
	var glights := scene.find_children("*", "DirectionalLight3D", true, false)
	if not glights.is_empty():  # the capture's sun (fir_world.py writes FM3's sun direction)
		sun.global_transform = (glights[0] as Node3D).global_transform if (glights[0] as Node3D).is_inside_tree() else (glights[0] as Node3D).transform
		(glights[0] as Node3D).visible = false
		print("world_view: sun from the glTF")
	sun.light_energy = (1.45 if filmic else 1.3) if lit else 1.0  # (linear tone mapping: calibrated on the grid's cars)
	sun.light_color = Color(1.0, 0.97, 0.92)
	sun.shadow_enabled = (lit or grey_shadow) and not no_shadows
	# Edges: FM3 renders with MSAA (its 720p 2x, the recomp up to 4x); live, the main view does too (--msaa N, default 4,
	# --msaa 1 = off)
	if _live_port > 0 and _triple_layout == "":
		root.msaa_3d = {1: Viewport.MSAA_DISABLED, 2: Viewport.MSAA_2X, 4: Viewport.MSAA_4X, 8: Viewport.MSAA_8X}.get(_msaa if _msaa > 0 else 4, Viewport.MSAA_4X)
	print("world_view: sun forward ", -sun.global_transform.basis.z if sun.is_inside_tree() else -sun.transform.basis.z, " shadows ", sun.shadow_enabled)
	var sun_fwd := -sun.global_transform.basis.z if sun.is_inside_tree() else -sun.transform.basis.z
	for cm in _car_mats:
		(cm as ShaderMaterial).set_shader_parameter("sun_dir", -sun_fwd)  # (towards the sun: the glass highlight)
	_sun_to = -sun_fwd
	for bm in _blend_mats:
		(bm as ShaderMaterial).set_shader_parameter("sun_dir", _sun_to)
	print("world_view: %d wheel rim surfaces dimmed, %d sky dome meshes (kept on the camera)" % [rim_set, _sky_nodes.size()])
	if glass_set:
		print("world_view: %d car glass surfaces with the game's own glass settings" % glass_set)
	sun.directional_shadow_max_distance = 250.0
	root.add_child(sun)
	if lit:
		_setup_exposure(gltf_path)
	if lit and DYNLIT_SHADOWS and dynlit_set > 0:
		# the sun of the track's sun-lit surfaces (fm3_dynlit), its shadows cast by everything incl. the static track
		var sun2 := sun.duplicate() as DirectionalLight3D
		sun2.light_cull_mask = DYNLIT_LAYER
		sun2.shadow_caster_mask = 0xFFFFF & ~COCKPIT_LAYER
		root.add_child(sun2)
		print("world_view: %d sun-lit track surfaces (fm3_dynlit) with static shadows" % dynlit_set)
	print("world_view: camera ", cam.global_transform if cam.is_inside_tree() else cam.transform, " parent ", cam.get_parent().name)
	print("world_view: %d surfaces lit by FM3's baked lightmaps (%d without an albedo texture)" % [baked, baked_no_tex])
	print("world_view: %d mesh instances, camera fov %.2f near %.3f" % [meshes, cam.fov, cam.near])
	if args.has("--library-swap"):
		_library_swap_test(args[args.find("--library-swap") + 1])
	if lit and _live_cube_size > 0 and (not _car_mats.is_empty() or _live_port > 0):
		# at the player car: the car meshes' centre nearest the camera, 0.8 m up (live: it follows that car)
		# (2026-11-25: also live without cars in the scene, the capture-free tracks whose cars all come from the
		# library: there the player had reflected the static cube, its roof Motegi 35 against the game's 100)
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
		var err := _udp.bind(_live_port, "127.0.0.1", 8 * 1024 * 1024)  # (8 MB: with the default 64 KB a busy viewer dropped packets, among them a car's once-a-second FM3N name: Silverstone drew one opponent less)
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


func _env_cube_gain(gltf_path: String) -> float:
	var f := gltf_path.get_basename() + "_tex/envcube.json"
	if FileAccess.file_exists(f):
		var t = JSON.parse_string(FileAccess.get_file_as_string(f))
		if t is Dictionary and t.has("gain"):
			return float(t["gain"])
	return 2.0


# A colour for a plain vec4 shader uniform. Godot 4.7 converts a Color given to a vec4 uniform from sRGB to linear even
# without source_color; the shaders here linearise themselves (to_linear), so a Color came out darkened twice: library
# cars' paint (white texture x the database colour) measured 22 where the captured copy (the colour in its texture) has
# 55, 56 once passed as a Vector4 (2026-11-24, --library-swap maz_axelasport_05).
static func _vec4(c: Color) -> Vector4:
	return Vector4(c.r, c.g, c.b, c.a)


# A car paint / glass ShaderMaterial from the glTF's material: its colour (and texture), the layout's static car cube.
# Fitting: <env> = comma-separated values for <names> (e.g. FM3_CARPAINT=0.9,0.06,0.8,60,0.85); FM3_CARPAINT_AMB /
# FM3_CARPAINT_SUN = r,g,b override the paint's ambient and sun light.
# A lens's cloudy pass takes the lens's own GlassColor (set after _car_material).
static func _lens_sync(m: ShaderMaterial) -> void:
	if m.shader == CARLENS_SHADER and m.next_pass is ShaderMaterial:
		(m.next_pass as ShaderMaterial).set_shader_parameter("glass_color", m.get_shader_parameter("glass_color"))


const CJ_SH_DIR := Vector3(0.78, 0.76, 0.73)  # CrownJewel's TrackSettings SHDir / SHTop: what the car paint was fitted under
const CJ_SH_TOP := Vector3(0.33, 0.34, 0.36)
var _car_light_cache := {}


# [sun ratio, sky ratio] of this track's car light against CrownJewel's, or [] (no 'SH' in its _track.json, or off)
func _car_light_ratio(gltf_path: String) -> Array:
	if OS.get_environment("FM3_NO_TRACK_CAR_LIGHT") != "":
		return []
	if not _car_light_cache.has(gltf_path):
		var f := gltf_path.get_basename() + "_track.json"
		var t = JSON.parse_string(FileAccess.get_file_as_string(f)) if FileAccess.file_exists(f) else null
		var r := []
		if t is Dictionary and t.has("SH") and t["SH"] is Dictionary:
			var d: Array = t["SH"]["dir"]
			var u: Array = t["SH"]["top"]
			r = [Vector3(d[0], d[1], d[2]) / CJ_SH_DIR, Vector3(u[0], u[1], u[2]) / CJ_SH_TOP]
			print("world_view: car light against CrownJewel's: sun x%s, sky x%s" % [r[0], r[1]])
		_car_light_cache[gltf_path] = r
	return _car_light_cache[gltf_path]


func _car_material(shader: Shader, m: BaseMaterial3D, gltf_path: String, env: String, names: Array) -> ShaderMaterial:
	var sm := ShaderMaterial.new()
	sm.shader = shader
	_car_mats.append(sm)
	sm.set_shader_parameter("albedo_color", _vec4(m.albedo_color))
	sm.set_shader_parameter("metallic", m.metallic)
	# (the live cube's faces: materials made after the cube, the library cars, had none bound, and the player's
	# paint read the samplers' default, a flat env of 1: a grey haze over the whole car; 2026-11-25)
	for k_ in _live_cube_texs.size():
		sm.set_shader_parameter("live%d" % k_, _live_cube_texs[k_])
	if m.albedo_texture != null:
		sm.set_shader_parameter("albedo_tex", m.albedo_texture)
	var cube := _env_cube(gltf_path, gltf_path.get_file().get_basename() + "_tex")
	sm.set_shader_parameter("has_env", cube != null)
	if (shader == CARPAINT_SHADER or shader == CARGLASS_SHADER) and cube != null:
		# the static cube's own scale (fm3_track_export.py envcube.json: its fetch constant's exponent adjust; x2 on
		# every race track but CrownJewel, x1 there; scenes exported before it get x2)
		sm.set_shader_parameter("static_cube_gain", _env_cube_gain(gltf_path))
	if cube != null:
		sm.set_shader_parameter("env_cube", cube)
	var v := OS.get_environment(env)
	if v != "":
		var f := v.split_floats(",")
		for k in mini(f.size(), names.size()):
			sm.set_shader_parameter(names[k], f[k])
	if shader == CARPAINT_SHADER:
		# the track's car light (2026-11-25): the paint was fitted on CrownJewel; the game lights cars with each track's
		# SHDir (sun, the paint shader's c179) and SHTop (the vertex SH sky), so both scale by the track's against
		# CrownJewel's (<track>_track.json 'SH', fm3_track_export.py). FM3_NO_TRACK_CAR_LIGHT=1: off.
		var cl := _car_light_ratio(gltf_path)
		if not cl.is_empty():
			var sun_d = RenderingServer.shader_get_parameter_default(shader.get_rid(), "sun")
			var amb_d = RenderingServer.shader_get_parameter_default(shader.get_rid(), "ambient")
			if sun_d is Vector3 and amb_d is Vector3:
				sm.set_shader_parameter("sun", (sun_d as Vector3) * (cl[0] as Vector3))
				sm.set_shader_parameter("ambient", (amb_d as Vector3) * (cl[1] as Vector3))
		# the game's paint reflection (fm3_carpaint.gdshader game_refl; LIVE.md "Car paint reflection"):
		# FM3_OLD_PAINT_REFL=1 = the older fitted term (A/B); FM3_PAINT_ENV=<static cube gain>,<live cube scale>
		if OS.get_environment("FM3_PAINT_DEBUG") != "":
			sm.set_shader_parameter("debug_out", int(OS.get_environment("FM3_PAINT_DEBUG")))
		if OS.get_environment("FM3_OLD_PAINT_REFL") != "":
			sm.set_shader_parameter("game_refl", false)
		var pe := OS.get_environment("FM3_PAINT_ENV").split_floats(",")
		if pe.size() >= 1 and OS.get_environment("FM3_PAINT_ENV") != "":
			sm.set_shader_parameter("game_env_gain", pe[0])
		if pe.size() >= 2:
			sm.set_shader_parameter("game_live_scale", pe[1])
	for extra in [["_AMB", "ambient"], ["_GROUND", "ambient_ground"], ["_SUN", "sun"]]:
		var e := OS.get_environment(env + extra[0])
		if e != "":
			var c := e.split_floats(",")
			sm.set_shader_parameter(extra[1], Vector3(c[0], c[1], c[2]))
	if shader == CARLENS_SHADER:
		# the lens's reflection over its filter (fm3_lensrefl.gdshader)
		var rp := ShaderMaterial.new()
		rp.shader = load("res://viewer/fm3_lensrefl.gdshader")
		rp.set_shader_parameter("has_env", cube != null)
		if cube != null:
			rp.set_shader_parameter("env_cube", cube)
		rp.render_priority = 2  # (after every lens filter: a later multiply took the reflection out again)
		# the diffusing plastic between them (fm3_lenscloud.gdshader; its colour copied in _lens_sync)
		var cl := ShaderMaterial.new()
		cl.shader = load("res://viewer/fm3_lenscloud.gdshader")
		cl.render_priority = 1
		cl.next_pass = rp
		sm.next_pass = cl
	return sm


# The live reflection cube (--live-cube N, default 128 px a face; 0 = the layout's static cube): six cameras at the
# player car render the scene into viewports each frame, as the game renders its car reflection cube each frame; the
# car paint and glass shaders look it up (fm3_livecube.gdshaderinc). Car meshes are on render layer 2, which the cube's
# cameras leave out (a car would otherwise reflect its own cabin).
const LIVE_DIRS = [Vector3.RIGHT, Vector3.LEFT, Vector3.UP, Vector3.DOWN, Vector3.BACK, Vector3.FORWARD]  # +x -x +y -y +z -z
const LIVE_UPS = [Vector3.UP, Vector3.UP, Vector3.FORWARD, Vector3.BACK, Vector3.UP, Vector3.UP]  # (+y: up -z; -y: up +z)
var _live_cube_size := 128
# Faces rendered per frame (round-robin; the others keep their last picture). The six faces cost ~40% of the live
# frame on the capture-free CrownJewel (RX 6650 XT, 720p: 32 fps with the cube, 52 without, 2026-11-24).
var _live_cube_faces := 6
var _live_cube_next := 0
var _live_cube_vps := []
var _live_cube_cams := []
var _live_cube_texs := []  # (the six faces, for car materials made after the cube: the library cars)
var _car_mats := []


func _make_live_cube(at: Vector3) -> void:
	var texs := []
	for k in 6:
		var vp := SubViewport.new()
		vp.size = Vector2i(_live_cube_size, _live_cube_size)
		vp.render_target_update_mode = SubViewport.UPDATE_ALWAYS if _live_cube_faces >= 6 else SubViewport.UPDATE_ONCE
		_live_cube_vps.append(vp)
		vp.positional_shadow_atlas_size = 0
		vp.mesh_lod_threshold = 4.0  # (small faces: coarser LODs are fine)
		var c := Camera3D.new()
		c.fov = 90.0
		c.keep_aspect = Camera3D.KEEP_HEIGHT
		c.near = 0.05
		c.far = 3000.0
		c.cull_mask = 0xFFFFF & ~2 & ~COCKPIT_LAYER  # (not layer 2: the cars; nor the cockpits)
		vp.add_child(c)
		root.add_child(vp)
		_live_cube_cams.append(c)
		texs.append(vp.get_texture())
	_live_cube_texs = texs
	_place_live_cube(at)
	_live_player = -2  # (has_live: the player's car only, set in _show_drawn)
	for sm in _car_mats:
		for k in 6:
			(sm as ShaderMaterial).set_shader_parameter("live%d" % k, texs[k])
	print("world_view: live reflection cube, %d px a face, at %s" % [_live_cube_size, at])


func _place_live_cube(at: Vector3) -> void:
	if _live_cube_faces < 6 and not _live_cube_vps.is_empty():
		for j in _live_cube_faces:
			(_live_cube_vps[_live_cube_next] as SubViewport).render_target_update_mode = SubViewport.UPDATE_ONCE
			_live_cube_next = (_live_cube_next + 1) % 6
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
	sm.shader = GLASS_SHADER if String(f["mode"]) == "refl" else (BLEND_ALPHA_SHADER if String(f["mode"]) in ["opac2", "rdline2", "rdline3"] else BLEND_SHADER)
	var tex: Array = f["tex"]
	if String(f["mode"]) == "refl":
		sm.set_shader_parameter("has_diffuse", bool(f.get("has_diffuse", false)))
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
	_apply_track_light(sm, gltf_path)
	_blend_mats.append(sm)
	sm.set_shader_parameter("sun_dir", _sun_to)
	sm.set_shader_parameter("albedo_tex", _load_tex(gltf_path, tex[0]))
	sm.set_shader_parameter("tex1", _load_tex(gltf_path, tex[1]))
	if tex.size() > 2:
		sm.set_shader_parameter("tex2", _load_tex(gltf_path, tex[2]))
	if tex.size() > 3:
		sm.set_shader_parameter("tex3", _load_tex(gltf_path, tex[3]))
	var mode_name := String(f["mode"])
	sm.set_shader_parameter("mode", {"blend": 1, "road": 2, "paint": 3, "edge": 4, "mix": 5, "curb": 6, "refl": 7, "ovly": 8, "blend3": 9, "road3": 10, "road2u": 11, "road2": 12, "opac2": 13, "rdline2": 14, "palette": 15, "dualmix": 16, "rdline3": 17, "road1": 18}.get(mode_name, 1))
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


# A wheel mesh's part in the speed blur: 1 the blurred rim / lip (fades in), 0 the sharp rim / lip it replaces (fades out),
# 2 the rest (tyre, inner barrel, hub: always drawn, as in the game).
static func _wheel_blur_kind(mi: Node) -> int:
	if _is_blur_wheel(mi):
		return 1
	var n := String(mi.name).to_lower()
	if n.contains("tire") or n.contains("tread") or n.contains("sidewall") or n.contains("inner_rim") or n.contains("wheel_black"):
		return 2
	return 0


# Wheel k of an FM3W datagram (its world matrix as drawn) in the glTF's world, mirrored like car_transform.
static func wheel_transform(b: PackedByteArray, k: int, axes: PackedFloat32Array) -> Transform3D:
	var s := Vector3(axes[0], axes[1], axes[2])
	var o := 16 + 64 * k
	var r := []
	for row in 4:
		r.append(Vector3(b.decode_float(o + 16 * row), b.decode_float(o + 16 * row + 4), b.decode_float(o + 16 * row + 8)) * s)
	return Transform3D(Basis(r[0], r[1], r[2]), r[3])


# A cockpit gauge needle's turn at grid placement (glTF space): the needle's parameter (0 = its _min part, 1 = _max)
# from the game's value through carattribs.xml's TickMarks (linear between them, extended past the ends), then the
# angle (min -> mid for 0..0.5, mid -> max for 0.5..1, fm3_track_export.py needle_turn). Speed: the car's own speed
# (m/s, from its streamed matrices); tach: the player's engine speed ("FM3E"; idle until one comes); fuel: full.
func needle_turn(n: Dictionary, car) -> Transform3D:
	var gauge := String(n.get("gauge", ""))
	if gauge == "steering":
		# turning right = clockwise seen from the driver = negative about the axis (which points at the driver)
		var deg := 0.0
		if _steer_mode == "input":
			deg = _steer * 0.5 * (_steer_lock if _steer_lock > 0.0 else _wheel_lock_arg)
		elif _steer_mode == "game":
			deg = _steer * float(n.get("game_deg", STEER_GAME_DEG))
		var ax: Array = n["axis"]
		var pv0: Array = n["pivot"]
		var sb := Basis(Vector3(ax[0], ax[1], ax[2]).normalized(), -deg_to_rad(deg))
		var sp := Vector3(pv0[0], pv0[1], pv0[2])
		return Transform3D(sb, sp - sb * sp)
	var param := 0.0
	if gauge == "fuel":
		param = 1.0
	else:
		var rpm := _engine_rpm if _engine_rpm >= 0.0 else NEEDLE_IDLE_RPM
		var value := float(_car_speed.get(car, 0.0)) if gauge == "speed" else rpm
		param = needle_param(n.get("ticks", []), value)
	param = clampf(param, 0.0, 1.0)
	var mid := float(n["mid"])
	var angle := param / 0.5 * mid if param <= 0.5 else mid + (param - 0.5) / 0.5 * (float(n["max"]) - mid)
	var a: Array = n["axis"]
	var pv: Array = n["pivot"]
	var b := Basis(Vector3(a[0], a[1], a[2]).normalized(), angle)
	var p := Vector3(pv[0], pv[1], pv[2])
	return Transform3D(b, p - b * p)


const NEEDLE_IDLE_RPM := 900.0
const RIM_SCALE := 0.5  # wheel rims' colour (the game lights them by its ambient at PaintScale 0.75; see the material loop)
const RIM_REFLECTION := 0.25  # painted rims' environment reflection (body paint 1.0 / 1.6)
const RIM_SPECULAR := 0.1  # ... and their reflection (Godot's default 0.5: light grey rims where the game's are dark)
const CHROME_SCALE := 0.25  # car chrome's reflection level (see the material loop)
# FM3's own cockpit wheel at full steering input: carattribs.xml SteeringWheelAngleOverride in turns (the export's
# game_deg; the CR-X's 0.206 = 74 deg matches its in-car pictures, ~73); cars without one (0) take the game's default,
# not measured yet: this guess.
const STEER_GAME_DEG := 90.0


func needle_param(ticks: Array, value: float) -> float:
	if ticks.is_empty():
		return 0.0
	if ticks.size() == 1:
		return float(ticks[0][0])
	var k := 0
	while k < ticks.size() - 2 and value > float(ticks[k + 1][1]):
		k += 1
	var p0 := float(ticks[k][0])
	var v0 := float(ticks[k][1])
	var p1 := float(ticks[k + 1][0])
	var v1 := float(ticks[k + 1][1])
	return p0 + (value - v0) * (p1 - p0) / maxf(v1 - v0, 1e-6)


# Brake and reverse lights per car (see _car_accel): the player's brake from its input, the others' from deceleration,
# held 0.25 s so they do not flicker; reverse while moving backwards.
# The player's engine sound (2026-11-25, fm3_engine_audio.gd): the game's own loops and tuning for the car FM3N names,
# from out/audio/<car>/engine.json (tools/fm3_engine_audio.py <car>), driven by the stream's rpm ("FM3E"). Throttle is
# not in the stream yet: estimated from how fast the rpm rises. FM3_NO_ENGINE_AUDIO=1: off.
var _engine_audio: Node3D = null
var _engine_audio_car := ""
var _engine_rpm_prev := -1.0
var _engine_throttle := 0.0


func _update_engine_audio(player, moves: Dictionary) -> void:
	if OS.get_environment("FM3_NO_ENGINE_AUDIO") != "" or player == null or int(player) < 0 or not _car_names.has(player):
		return
	var nm := String(_car_names[player]["name"])
	if nm != _engine_audio_car:
		_engine_audio_car = nm
		if _engine_audio != null:
			_engine_audio.queue_free()
			_engine_audio = null
		var dir := ProjectSettings.globalize_path("res://").path_join("../out/audio")
		var path := ""
		var d := DirAccess.open(dir)
		if d != null:
			for f in d.get_directories():
				if f.to_lower() == nm.to_lower():
					path = dir.path_join(f).path_join("engine.json")
		var e := load("res://viewer/fm3_engine_audio.gd").new() as Node3D
		root.add_child(e)
		if path != "" and e.call("load_recipe", path):
			_engine_audio = e
			print("world_view: engine sound for %s (%s)" % [nm, path])
		else:
			e.queue_free()
			print("world_view: no engine sound for %s (tools/fm3_engine_audio.py %s)" % [nm, nm])
	if _engine_audio == null or not moves.has(player):
		return
	_engine_audio.global_transform = moves[player] as Transform3D
	if _engine_rpm > 0.0:
		var dt := maxf(get_process_delta_time(), 1e-3)
		var rise := 0.0 if _engine_rpm_prev < 0.0 else (_engine_rpm - _engine_rpm_prev) / dt
		_engine_rpm_prev = _engine_rpm
		var want := clampf(rise / 2500.0 + 0.3, 0.0, 1.0) * (1.0 - maxf(_player_brake, 0.0))
		_engine_throttle = lerpf(_engine_throttle, want, 1.0 - exp(-dt * 6.0))
		_engine_audio.set("rpm", _engine_rpm)
		_engine_audio.set("throttle", _engine_throttle)


func _update_lights(player) -> void:
	var dt := 1.0 / 60.0
	for car in _light_mats:
		var on := 0.0
		if car == player and _player_brake >= 0.0:
			on = _player_brake
		elif float(_car_accel.get(car, 0.0)) < -BRAKE_DECEL and float(_car_speed.get(car, 0.0)) > 1.5:
			on = 1.0
		var shown := float(_car_lit.get(car, 0.0))
		shown = on if on >= shown else maxf(on, shown - dt * 4.0)
		_car_lit[car] = shown
		var back := bool(_car_back.get(car, false))
		for e in _light_mats[car]:
			if e[1] == "lens":
				(e[0] as ShaderMaterial).set_shader_parameter("glow", shown)
				if (e[0] as ShaderMaterial).next_pass is ShaderMaterial:
					((e[0] as ShaderMaterial).next_pass as ShaderMaterial).set_shader_parameter("glow", shown)
				continue
			var lm := e[0] as BaseMaterial3D
			if e[1] == "brake":
				lm.emission_energy_multiplier = shown * BRAKE_ENERGY
				# (the lamp's whitish texture tinted red while lit: the game's lit lamp is saturated red, not pink)
				lm.albedo_color = Color(1.0, 1.0 - 0.85 * shown, 1.0 - 0.85 * shown)
			else:
				lm.emission_energy_multiplier = 1.5 if back else 0.0


# The glTF's textures, compressed (see the loader): each material's base colour, metallic-roughness, occlusion (FM3's
# lightmaps, UV2), normal and emissive textures as Godot's glTF import binds them, from BC1 / BC3 ImageTextures.
func _bind_textures(state: GLTFState, gltf_path: String, compress := true) -> void:
	var j = JSON.parse_string(FileAccess.get_file_as_string(gltf_path))
	if not (j is Dictionary):
		return
	var base := gltf_path.get_base_dir()
	var cache := {}
	var images: Array = j.get("images", [])
	var textures: Array = j.get("textures", [])
	var load_tex := func(info) -> Texture2D:
		if not (info is Dictionary):
			return null
		var ti := int(info.get("index", -1))
		if ti < 0 or ti >= textures.size():
			return null
		var ii := int(textures[ti].get("source", -1))
		if ii < 0 or ii >= images.size():
			return null
		var uri := String(images[ii].get("uri", ""))
		if uri == "":
			return null
		if not cache.has(uri):
			var img := Image.load_from_file(base.path_join(uri.uri_decode()))
			if img == null:
				cache[uri] = null
			else:
				if compress and img.get_width() >= 4 and img.get_height() >= 4 and img.get_width() % 4 == 0 and img.get_height() % 4 == 0:
					img.generate_mipmaps()
					img.compress(Image.COMPRESS_S3TC, Image.COMPRESS_SOURCE_GENERIC)
				else:
					img.generate_mipmaps()
				cache[uri] = ImageTexture.create_from_image(img)
		return cache[uri]
	var mats := state.get_materials()
	var jm: Array = j.get("materials", [])
	for i in mini(mats.size(), jm.size()):
		var m := mats[i] as BaseMaterial3D
		if m == null:
			continue
		var d: Dictionary = jm[i]
		var pbr: Dictionary = d.get("pbrMetallicRoughness", {})
		var t: Texture2D = load_tex.call(pbr.get("baseColorTexture"))
		if t != null:
			m.albedo_texture = t
		t = load_tex.call(pbr.get("metallicRoughnessTexture"))
		if t != null:
			m.roughness_texture = t
			m.roughness_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_GREEN
			m.metallic_texture = t
			m.metallic_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_BLUE
		if d.has("occlusionTexture"):
			t = load_tex.call(d["occlusionTexture"])
			if t != null:
				m.ao_enabled = true
				m.ao_texture = t
				m.ao_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_RED
				m.ao_on_uv2 = int(d["occlusionTexture"].get("texCoord", 0)) == 1
		if d.has("normalTexture"):
			t = load_tex.call(d["normalTexture"])
			if t != null:
				m.normal_enabled = true
				m.normal_texture = t
		if d.has("emissiveTexture"):
			t = load_tex.call(d["emissiveTexture"])
			if t != null:
				m.emission_enabled = true
				m.emission_texture = t


# One car mesh joins the live cars: it follows its car (wk -1) or wheel wk at <offset> (global = move * offset), with
# its speed blur, cockpit flag, needle, paint / glass materials (the player's live cube) and brake / reverse lights.
func _register_part(m: MeshInstance3D, car, offset: Transform3D, wk: int, needle = null) -> void:
	if String(m.name).contains("_cockpit_mirror"):
		_add_mirror(m, car)
	if String(m.name).begins_with("cockpit_"):
		m.layers = COCKPIT_LAYER  # (not lit by the sun: FM3's cockpit has no directional light, SHCockpitDir 0)
		for s_ in m.get_surface_override_material_count():
			var bm_ := m.get_surface_override_material(s_) as BaseMaterial3D
			if bm_ != null and bm_.transparency != BaseMaterial3D.TRANSPARENCY_ALPHA:
				m.set_surface_override_material(s_, _cockpit_material(bm_))
	_car_parts.append([m, car, offset, wk, _wheel_blur_kind(m) if wk >= 0 else -1,
		String(m.name).begins_with("cockpit_"), m.cast_shadow, needle if needle != null else _needles.get(String(m.name))])
	_cars_with_parts[car] = true
	for si2_ in m.get_surface_override_material_count():
		var sm2_ = m.get_surface_override_material(si2_)
		if sm2_ is ShaderMaterial and _car_mats.has(sm2_):
			if not _car_shader_mats.has(car):
				_car_shader_mats[car] = []
			_car_shader_mats[car].append(sm2_)
			# (a car attached after the player was chosen, e.g. its library model arriving a moment later: the
			# player switch in _update_live_cars had already run, so its paint reflected the static cube; 2026-11-25)
			if not _live_cube_cams.is_empty():
				(sm2_ as ShaderMaterial).set_shader_parameter("has_live", car == _live_player)
	var nm_ := String(m.name)
	var kind_ := "brake" if nm_.contains("tail_light") or nm_.contains("brake_light") else ("reverse" if nm_.contains("reverse_light") else "")
	if nm_.contains("detail_glass_red") or nm_.contains("red_glass"):
		for si_ in m.get_surface_override_material_count():
			var gl_ = m.get_surface_override_material(si_)
			if gl_ is ShaderMaterial:
				if not _light_mats.has(car):
					_light_mats[car] = []
				_light_mats[car].append([gl_, "lens"])
	if kind_ != "":
		for si_ in m.get_surface_override_material_count():
			var lm_ = m.get_surface_override_material(si_)
			if lm_ is BaseMaterial3D and (lm_ as BaseMaterial3D).albedo_texture != null:
				var bm_ := lm_ as BaseMaterial3D
				bm_.emission_enabled = true
				bm_.emission_texture = bm_.albedo_texture
				bm_.emission = Color(1.0, 0.0, 0.0) if kind_ == "brake" else Color(1.0, 1.0, 0.95)
				bm_.emission_energy_multiplier = 0.0
				if not _light_mats.has(car):
					_light_mats[car] = []
				_light_mats[car].append([bm_, kind_])


# Cars the glTF does not hold (any track but the capture's grid, or a car not in it): built from the car library
# (tools/fm3_car_library.py: out/cars/<car>.gltf in its own car / wheel space), named by the game ("FM3N": media name,
# Combo_Colors colour, paint type), placed by its streamed matrices like the others.
# Streamed cars the scene lacks that have not had their library model yet (queued, or no FM3N name so far).
# A cockpit plain surface as fm3_cockpit.gdshader (FM3's cabin hemisphere light, no sun, no sky reflection).
func _cockpit_material(bm: BaseMaterial3D) -> ShaderMaterial:
	var sm := ShaderMaterial.new()
	sm.shader = load("res://viewer/fm3_cockpit.gdshader")
	if bm.albedo_texture != null:
		sm.set_shader_parameter("albedo_tex", bm.albedo_texture)
	sm.set_shader_parameter("albedo_color", _vec4(bm.albedo_color))
	sm.set_shader_parameter("use_vcol", bm.vertex_color_use_as_albedo)
	sm.set_shader_parameter("gain", COCKPIT_GAIN)
	if bm.transparency == BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR:
		sm.set_shader_parameter("alpha_cut", bm.alpha_scissor_threshold)
	return sm


func _add_mirror(m: MeshInstance3D, car) -> void:
	var arr = m.mesh.surface_get_arrays(0)
	var pall: PackedVector3Array = arr[Mesh.ARRAY_VERTEX]
	# (only the vertices its triangles use: a library mesh carries its whole part's vertex buffer, the CR-X's middle
	# mirror 23,687 vertices over the cabin)
	var p := PackedVector3Array()
	var idx = arr[Mesh.ARRAY_INDEX]
	if idx != null and (idx as PackedInt32Array).size() > 0:
		var seen := {}
		for i_ in (idx as PackedInt32Array):
			if not seen.has(i_):
				seen[i_] = true
				p.append(pall[i_])
	else:
		p = pall
	if p.size() < 3:
		return
	var c := Vector3.ZERO
	for v in p:
		c += v
	c /= p.size()
	# the plane's normal: the direction of least spread (the smallest eigenvector of the covariance, by power iteration
	# on its inverse's stand-in: the cross of the two widest directions)
	var far_ := p[0]
	for v in p:
		if v.distance_to(c) > far_.distance_to(c):
			far_ = v
	var a := (far_ - c).normalized()
	var best := Vector3.ZERO
	for v in p:
		var w := (v - c) - a * (v - c).dot(a)
		if w.length() > best.length():
			best = w
	var n := a.cross(best.normalized()).normalized()
	var r := 0.0
	var bn := best.normalized()
	var hw := 0.0
	var hh := 0.0
	for v in p:
		r = maxf(r, v.distance_to(c))
		hw = maxf(hw, absf((v - c).dot(a)))
		hh = maxf(hh, absf((v - c).dot(bn)))
	var mat := ShaderMaterial.new()
	mat.shader = load("res://viewer/fm3_mirror.gdshader")
	for s in m.mesh.get_surface_count():
		m.set_surface_override_material(s, mat)
	_mirrors.append({"mesh": m, "car": car, "centre": c, "normal": n, "radius": r, "hw": hw, "hh": maxf(hh, 0.01), "short": bn, "mat": mat, "vp": null, "cam": null})


# Each frame: the player's mirrors while in-car (the driver's eye = the drawn camera, reflected in each mirror's plane;
# near plane at the mirror so the dash in front of a reflected eye is cut away); other mirrors stop rendering.
func _update_mirrors(player, in_car: bool, eye: Transform3D) -> void:
	_mirror_turn += 1
	var nth := 0
	for mr in _mirrors:
		var on: bool = _mirrors_on and in_car and mr["car"] == player and (mr["mesh"] as Node3D).visible
		if not on:
			if mr["vp"] != null and (mr["vp"] as SubViewport).render_target_update_mode != SubViewport.UPDATE_DISABLED:
				(mr["vp"] as SubViewport).render_target_update_mode = SubViewport.UPDATE_DISABLED
				(mr["mat"] as ShaderMaterial).set_shader_parameter("active", false)
			continue
		if mr["vp"] == null:
			var vp := SubViewport.new()
			vp.size = Vector2i(MIRROR_SIZE.x, clampi(int(MIRROR_SIZE.x * float(mr["hh"]) / maxf(float(mr["hw"]), 0.01)), 32, MIRROR_SIZE.x))
			vp.positional_shadow_atlas_size = 0
			vp.mesh_lod_threshold = 4.0
			var c3 := Camera3D.new()
			c3.cull_mask = 0xFFFFF & ~COCKPIT_LAYER
			c3.far = MIRROR_FAR
			vp.add_child(c3)
			root.add_child(vp)
			mr["vp"] = vp
			mr["cam"] = c3
			(mr["mat"] as ShaderMaterial).set_shader_parameter("view_tex", vp.get_texture())
		var vp2: SubViewport = mr["vp"]
		# one mirror re-rendered a frame, in turn (the others keep their picture): three mirrors every frame cost the
		# in-car view 21% (33 -> 26 fps, capture-free CrownJewel); FM3 has a half-rate mirror option for the same reason
		vp2.render_target_update_mode = SubViewport.UPDATE_ONCE if (nth % 3) == (_mirror_turn % 3) or not mr.get("drawn", false) else SubViewport.UPDATE_DISABLED
		mr["drawn"] = true
		nth += 1
		var gt := (mr["mesh"] as Node3D).global_transform
		var c := gt * (mr["centre"] as Vector3)
		var n := (gt.basis * (mr["normal"] as Vector3)).normalized()
		var e := eye.origin
		var e2 := e - n * (2.0 * (e - c).dot(n))
		var d := e2.distance_to(c)
		var cam3: Camera3D = mr["cam"]
		var car_up := gt.basis.y.normalized()  # (cockpit meshes are placed with the car's transform)
		# The lookup camera: from the reflected eye at the glass, framing its rectangle (half height hh, the viewport's
		# aspect = its half width / half height), up along its short side: the whole picture lands on the glass.
		var up := (gt.basis * (mr["short"] as Vector3)).normalized()
		if up.dot(car_up) < 0.0:
			up = -up
		cam3.global_transform = Transform3D(Basis(), e2).looking_at(c, up)
		cam3.fov = clampf(rad_to_deg(2.0 * atan(float(mr["hh"]) * 1.05 / maxf(d, 0.05))), 2.0, 120.0)
		var vpm := cam3.get_camera_projection() * Projection(cam3.global_transform.affine_inverse())
		(mr["mat"] as ShaderMaterial).set_shader_parameter("mirror_vp", vpm)
		# The picture: FM3 draws its mirrors as a separate scene from a rear camera, level, a fixed field of view: the
		# middle mirror straight back, the side mirrors along their reflection without its pitch. (Optically reflected,
		# the CR-X's middle mirror, its glass tilted 11 deg down and the eye 4 cm below it, looked 14-22 deg down at the
		# asphalt, magnified, where the game's shows the stands and the track behind.)
		var ne := n if (e - c).dot(n) > 0.0 else -n
		var dir := ne if String((mr["mesh"] as Node).name).contains("mirrorMiddle") else ((c - e) - n * (2.0 * (c - e).dot(n)))
		var level := dir - car_up * dir.dot(car_up)
		if level.length() > 0.01:
			var ln := level.normalized()
			cam3.global_transform = Transform3D(Basis(), e2).looking_at(e2 + ln * cos(deg_to_rad(MIRROR_PITCH)) + car_up * sin(deg_to_rad(MIRROR_PITCH)), car_up)
		cam3.fov = MIRROR_FOV
		cam3.near = 0.3
		(mr["mat"] as ShaderMaterial).set_shader_parameter("active", true)


# Liveries from the running game (tools/live_liveries.py -> out/cars/live_liveries/<car>.png + index.json): checked
# about once a second; each car's body paint takes its livery (fm3_carpaint.gdshader livery) once it has a library
# model. The player's custom paint lives only there (the car object holds the database colour, PLAN-CARS).
var _livery_mtime := 0
var _livery_next_ms := 0
var _livery_applied := {}
var _livery_names := {}
var _library_cars := {}  # cars dressed from the car library (the captured ones carry their paint in their texture)


func _poll_liveries() -> void:
	if Time.get_ticks_msec() < _livery_next_ms or _gltf_path == "":
		return
	_livery_next_ms = Time.get_ticks_msec() + 1000
	var dir := _gltf_path.get_base_dir().path_join("../cars/live_liveries").simplify_path()
	var idx := dir.path_join("index.json")
	if not FileAccess.file_exists(idx):
		return
	var mt := FileAccess.get_modified_time(idx)
	if mt != _livery_mtime:
		_livery_mtime = mt
		_livery_applied.clear()
	var data = JSON.parse_string(FileAccess.get_file_as_string(idx))
	if not (data is Dictionary):
		return
	_livery_names = data
	for car in _car_names:
		var nm := String(_car_names[car]["name"]).to_lower()
		if _livery_applied.has(car) or not data.has(nm) or not _library_cars.has(car):
			continue
		var img := Image.load_from_file(dir.path_join(nm + ".png"))
		if img == null:
			continue
		img.generate_mipmaps()
		var tex := ImageTexture.create_from_image(img)
		var n := 0
		for p in _car_parts:
			if p[1] != car or not String((p[0] as Node).name).begins_with("carbin_"):
				continue
			var mi := p[0] as MeshInstance3D
			for s in mi.get_surface_override_material_count():
				var sm := mi.get_surface_override_material(s) as ShaderMaterial
				if sm != null and sm.shader == CARPAINT_SHADER:
					sm.set_shader_parameter("albedo_tex", tex)
					sm.set_shader_parameter("livery", true)
					n += 1
		_livery_applied[car] = true
		print("world_view: live car %08X (%s): livery from the game on %d paint surfaces" % [car, nm, n])


var _track_light_cache := {}
var _blend_mats := []  # the track's blend materials (their road specular needs the sun direction, set once it is known)
# The road's sun specular (the game's formula, fm3_blend.gdshaderinc), on since the game's exposure is in (2026-11-25):
# MapleValley facing the sun 36.1 -> 25.8 live (before the exposure it overshot: glare 253 vs 176); Motegi 23.4,
# Catalunya 20.3 (no harm). FM3_NO_ROAD_SPEC=1: off.
var _no_road_spec := OS.get_environment("FM3_NO_ROAD_SPEC") != ""


# The static world's ambient / sun (c247 / c248) from the track's TrackSettings DarkColor / LightColor, written by
# fm3_track_export.py beside the glTF (<name>_track.json); without it the shaders keep CrownJewel's.
func _apply_track_light(sm: ShaderMaterial, gltf_path: String) -> void:
	if not _track_light_cache.has(gltf_path):
		var f := gltf_path.get_basename() + "_track.json"
		_track_light_cache[gltf_path] = JSON.parse_string(FileAccess.get_file_as_string(f)) if FileAccess.file_exists(f) else {}
	var t = _track_light_cache[gltf_path]
	if not (t is Dictionary):
		return
	if t.has("DarkColor"):
		sm.set_shader_parameter("ambient", Vector3(t["DarkColor"][0], t["DarkColor"][1], t["DarkColor"][2]))
	if t.has("LightColor"):
		sm.set_shader_parameter("sun", Vector3(t["LightColor"][0], t["LightColor"][1], t["LightColor"][2]))
	if t.has("RoadSpec") and t.has("RoadGloss") and not _no_road_spec:
		var a: Array = t["RoadSpec"]
		var b: Array = t["RoadGloss"]
		sm.set_shader_parameter("road_spec", Vector4(a[0], a[1], a[2], a[3]))
		sm.set_shader_parameter("road_gloss", Vector4(b[0], b[1], b[2], b[3]))
		sm.set_shader_parameter("road_spec_on", true)


# The game's exposure (fm3_exposure.gdshader): a full-screen pass over the 3D picture with the track's tone curve,
# blended by an adapted scene luminance like FM3's final pass. FM3_NO_EXPOSURE=1: off (A/B).
const EXPOSURE_W_CJ := 0.942  # CrownJewel's own W on the test grid (read from the running game): our calibration's
var _expo_mat: ShaderMaterial = null
var _expo_tone := {}
var _expo_L := -1.0
var _expo_last := 0


func _setup_exposure(gltf_path: String) -> void:
	if OS.get_environment("FM3_NO_EXPOSURE") != "":
		return
	var f := gltf_path.get_basename() + "_track.json"
	var t = JSON.parse_string(FileAccess.get_file_as_string(f)) if FileAccess.file_exists(f) else null
	if not (t is Dictionary) or not t.has("Tone") or not (t["Tone"] is Dictionary):
		return
	_expo_tone = t["Tone"]
	var layer := CanvasLayer.new()
	layer.layer = 90
	var rect := ColorRect.new()
	rect.set_anchors_preset(Control.PRESET_FULL_RECT)
	rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_expo_mat = ShaderMaterial.new()
	_expo_mat.shader = load("res://viewer/fm3_exposure.gdshader")
	# Our picture is the game's scene (its shaders' output): the final pass runs on it as it is, then the display table.
	# (Until 2026-11-25 s_scale was W_cj / 0.9874, which made the pass a no-op on CrownJewel: the picture had been
	# calibrated against the game's displayed picture, display table included; now the table is applied here.)
	_expo_mat.set_shader_parameter("s_scale", 1.0)
	_expo_mat.set_shader_parameter("desat", float(_expo_tone.get("desat", 1.0)))
	_expo_mat.set_shader_parameter("display_toe", OS.get_environment("FM3_NO_TOE") == "")
	if OS.get_environment("FM3_EXPO_SSCALE") != "":
		_expo_mat.set_shader_parameter("s_scale", float(OS.get_environment("FM3_EXPO_SSCALE")))
	rect.material = _expo_mat
	layer.add_child(rect)
	root.add_child(layer)
	_expo_apply(0.73)  # (until the first measurement: CrownJewel's grid state)
	print("world_view: the game's exposure on (tone %s)" % [_expo_tone])


# The curve at blend k (0 = the dark curve, 1 = the light one): [white, black, 1/gamma, boost] as the final pass's vertex
# shader makes them (white - 0.0006, gamma x 0.9994).
func _expo_curve(k: float) -> Array:
	var d: Array = _expo_tone["dark"]
	var l: Array = _expo_tone["light"]
	var black := lerpf(d[0], l[0], k) / 255.0
	var gam := lerpf(d[1], l[1], k) * 0.9994
	var white := lerpf(d[2], l[2], k) / 255.0 - 0.0006
	var boost := lerpf(d[3], l[3], k) / 255.0
	return [white, black, 1.0 / max(gam, 0.01), boost]


func _expo_apply(k: float) -> void:
	var c := _expo_curve(k)
	_expo_mat.set_shader_parameter("white", c[0])
	_expo_mat.set_shader_parameter("black", c[1])
	_expo_mat.set_shader_parameter("gamma_inv", c[2])
	_expo_mat.set_shader_parameter("boost", c[3])
	_expo_mat.set_meta("k", k)


func _expo_k(lum: float) -> float:
	var lim: Array = _expo_tone["lum"]
	return clampf((lum - float(lim[0]) / 255.0) * 255.0 / max(float(lim[1]) - float(lim[0]), 1.0), 0.0, 1.0)


# Every 10 frames: the picture's mean luminance (it already has the exposure pass on it: undone through the current
# curve), as the game's scene luminance L, adapted 2% a frame like the game's luminance pass (the first one taken as is).
# The display table's points (fm3_exposure.gdshader TOE: input k * 16, the last 255) and its inverse.
const TOE_PTS := [0.0, 6.0, 16.0, 32.0, 48.0, 65.0, 81.0, 98.0, 115.0, 132.0, 150.0, 167.0, 185.0, 202.0, 220.0, 238.0, 255.0]


static func _untoe(v: float) -> float:
	var o := clampf(v, 0.0, 1.0) * 255.0
	for i in 16:
		var a: float = TOE_PTS[i]
		var b: float = TOE_PTS[i + 1]
		if o <= b or i == 15:
			var x0 := float(i) * 16.0
			var x1 := 255.0 if i == 15 else float(i + 1) * 16.0
			return (x0 + (x1 - x0) * clampf((o - a) / maxf(b - a, 1e-4), 0.0, 1.0)) / 255.0
	return v


func _exposure_update() -> void:
	if _expo_mat == null or _frames < 3 or _frames - _expo_last < 10:
		return
	var n := _frames - _expo_last
	_expo_last = _frames
	var img := root.get_texture().get_image()
	if img == null:
		return
	img.resize(64, 36, Image.INTERPOLATE_BILINEAR)
	var sum := 0.0
	var toe_on := bool(_expo_mat.get_shader_parameter("display_toe"))
	for y in 36:
		for x in 64:
			var c := img.get_pixel(x, y)
			if toe_on:
				# (the display table undone per pixel: the picture's values before it)
				c = Color(_untoe(c.r), _untoe(c.g), _untoe(c.b))
			sum += c.r * 0.2 + c.g * 0.7152 + c.b * 0.0722
	var y_out := sum / (64.0 * 36.0)
	var k := float(_expo_mat.get_meta("k", 0.73))
	var cur := _expo_curve(k)
	# out = Y * t(0.9874 Y) / max(0.9874 Y, 0.1) + boost: solve for Y (a few fixed-point steps)
	var y_s := y_out
	for i in 4:
		var yp := y_s * 0.9874
		var wb := maxf(cur[0] - cur[1], 1e-4)
		var x := maxf((yp - cur[1]) / wb, maxf((0.1 - cur[1]) / wb, 0.0))
		var f := pow(maxf(x, 1e-6), cur[2]) / maxf(yp, 0.1)
		y_s = maxf(y_out - cur[3], 0.0) / maxf(f, 1e-4)
	if _expo_L < 0.0:
		_expo_L = y_s
	else:
		_expo_L += (1.0 - pow(0.98, float(n))) * (y_s - _expo_L)
	_expo_apply(_expo_k(_expo_L))


func _cars_pending() -> bool:
	if not _library_queue.is_empty():
		return true
	if not _car_attached:
		# (the cars not attached yet: on a 400 MB scene (Catalunya) the viewer still ran at 1 fps when live_track asked for
		# its picture, and the cars attached right after it; with a live stream, wait for them too)
		return _live_port > 0
	for c in _cars:
		if not _cars_with_parts.has(c) and not _library_tried.has(c):
			return true
	# (and the game's liveries: a car with an entry in live_liveries/index.json not dressed yet)
	if _livery_mtime != 0:
		for c in _car_names:
			if _library_cars.has(c) and not _livery_applied.has(c) and _livery_names.has(String(_car_names[c]["name"]).to_lower()):
				return true
	return false


func _attach_library_car(car) -> void:
	_library_tried[car] = true
	var info: Dictionary = _car_names[car]
	var lname := String(info["name"]).to_lower()
	var path := _gltf_path.get_base_dir().path_join("../cars/%s.gltf" % lname).simplify_path()
	if not FileAccess.file_exists(path) or not _cars.has(car) or not _wheels.has(car):
		print("world_view: live car %08X is %s: no library model (%s) or no matrices yet" % [car, info["name"], path])
		return
	# (textures with mipmaps but not compressed: compressing a car's 2048 px textures stalled the live view for seconds
	# a car; Godot's own glTF texture loading gives none, and a far car's paint then sampled black)
	var t0 := Time.get_ticks_msec()
	var doc := GLTFDocument.new()
	var st := GLTFState.new()
	st.handle_binary_image = 0
	if doc.append_from_file(path, st) != OK:
		print("world_view: live car %08X is %s: its library model %s did not load" % [car, info["name"], path])
		return
	_bind_textures(st, path, false)
	var scene_ := doc.generate_scene(st)
	root.add_child(scene_)
	var base := path.get_basename()
	var cm = JSON.parse_string(FileAccess.get_file_as_string(base + "_carmaterials.json")) if FileAccess.file_exists(base + "_carmaterials.json") else {}
	var nd = JSON.parse_string(FileAccess.get_file_as_string(base + "_needles.json")) if FileAccess.file_exists(base + "_needles.json") else {}
	var cols = JSON.parse_string(FileAccess.get_file_as_string(base + "_colors.json")) if FileAccess.file_exists(base + "_colors.json") else {}
	var a_att := car_transform(_cars[car], _live_axes)
	_car_inv[car] = a_att.affine_inverse()
	var w_att: Array = _wheels[car]
	var wi := []
	for k in 4:
		wi.append((w_att[k] as Transform3D).affine_inverse())
	_wheel_inv[car] = wi
	var flip := a_att.basis.determinant() < 0.0
	var paint_col := Color(1, 1, 1)
	var metal := 0.0
	var key := str(int(info["color"]))
	if cols is Dictionary and cols.has(key):
		var c: Array = cols[key]
		var scale := 0.6 if bool(info["metallic"]) else 0.8  # (ShaderSettings PaintScale: Metallic.xml 0.6, Normal.xml 0.8)
		paint_col = Color(float(c[0]) * scale, float(c[1]) * scale, float(c[2]) * scale)
		metal = 1.0 if int(c[3]) == 1 else 0.0
	var n := 0
	for mi in scene_.find_children("*", "MeshInstance3D", true, false):
		var m := mi as MeshInstance3D
		var nm := String(m.name)
		_setup_library_mesh(m, cm if cm is Dictionary else {}, paint_col, metal)
		var wk := -1
		var mk := RegEx.create_from_string("^(wheel|brake)_[a-z0-9_]+?_([0-3])_").search(nm)
		if mk != null:
			wk = int(mk.get_string(2))
		var needle = null
		if nd is Dictionary and nd.has(nm):
			# the turn in the attach frame (car space -> a_att), its axis flipped if that frame is mirrored
			needle = (nd[nm] as Dictionary).duplicate()
			var pv: Array = needle["pivot"]
			var ax: Array = needle["axis"]
			var p2 := a_att * Vector3(pv[0], pv[1], pv[2])
			var a2 := (a_att.basis * Vector3(ax[0], ax[1], ax[2])).normalized() * (-1.0 if flip else 1.0)
			needle["pivot"] = [p2.x, p2.y, p2.z]
			needle["axis"] = [a2.x, a2.y, a2.z]
		if nm.begins_with("cockpit_"):
			m.visible = false
		# (the library's vertices are in raw car / wheel space: placed by the streamed matrix itself, mirrored or not)
		var off: Transform3D = (w_att[wk] as Transform3D) if wk >= 0 else a_att
		if wk >= 0 and nm.contains("_caliper_"):
			# a caliper does not spin: the wheel's place and axle with the car's up (as fm3_track_export.py's
			# build_wheels), moved with the body; the axle keeps the wheel matrix's handedness (mirrored or not)
			var w := w_att[wk] as Transform3D
			var ax := w.basis.x
			var up := a_att.basis.y.normalized()
			var yv := (up - ax.normalized() * up.dot(ax.normalized())).normalized() * w.basis.y.length()
			var zv := ax.cross(yv).normalized() * w.basis.z.length() * signf(w.basis.determinant())
			off = Transform3D(Basis(ax, yv, zv), w.origin)
			wk = -1
		if nm.begins_with("wheel_") or nm.begins_with("brake_"):
			# (wheels and brakes carry the glTF mirror in their vertices, fm3_car_library.py fz: the wheel matrices are
			# mirrored where the body's is not, so matrix x F is the proper rotation)
			off = off * Transform3D(Basis.from_scale(Vector3(1, 1, -1)), Vector3.ZERO)
		_register_part(m, car, off, wk, needle)
		m.global_transform = off  # (now: offline renders; live moves it)
		n += 1
	_live_player = -2  # (re-evaluate has_live: this car's new paint / glass materials may be the player's)
	_library_cars[car] = true
	print("world_view: live car %08X is %s colour %s: %d meshes from the car library (%d ms; paint %s)" % [car, info["name"], key, n, Time.get_ticks_msec() - t0, paint_col])


# Debug (offline, the grid scene): --library-swap <car>:<colour>:<metallic 0|1> hides the scene's (captured) copy of a
# car and puts its library model in the same place (its matrices from work/fir/grid-cars.json), so a render compares
# the library car with the captured one in the same light.
func _library_swap_test(spec: String) -> void:
	var parts := spec.split(":")
	var lname := parts[0].to_lower()
	var centre := Vector3.ZERO
	var cnt := 0
	for mi in _scene.find_children("*", "MeshInstance3D", true, false):
		var nm := String(mi.name)
		if nm.contains("_" + lname + "_") or nm.begins_with("carbin_" + lname) or nm.begins_with("wheel_" + lname) or nm.begins_with("brake_" + lname) or nm.begins_with("cockpit_" + lname):
			if nm.begins_with("carbin_"):
				centre += (mi as MeshInstance3D).transform * (mi as MeshInstance3D).get_aabb().get_center()  # (glTF nodes at the root)
				cnt += 1
			(mi as MeshInstance3D).visible = false
	if cnt == 0:
		print("world_view: --library-swap: no %s in the scene" % lname)
		return
	centre /= cnt
	var gc = JSON.parse_string(FileAccess.get_file_as_string(_gltf_path.get_base_dir().path_join("../../../work/fir/grid-cars.json").simplify_path()))
	var best = null
	var bd := INF
	for c in gc["cars"]:
		var mtx: Array = c["matrix"]
		var o := Vector3(mtx[12], mtx[13], -float(mtx[14]))
		if o.distance_to(centre) < bd:
			bd = o.distance_to(centre)
			best = c
	var pkt := PackedByteArray()
	pkt.resize(96)
	for i in 16:
		pkt.encode_float(16 + 4 * i, float(best["matrix"][i]))
	var wpk := PackedByteArray()
	wpk.resize(280)
	for k in 4:
		for i in 16:
			wpk.encode_float(16 + 64 * k + 4 * i, float(best["wheels"][k][i]))
	var ws := []
	for k in 4:
		ws.append(wheel_transform(wpk, k, _live_axes))
	_cars[-7] = pkt
	_wheels[-7] = ws
	_car_names[-7] = {"name": parts[0], "color": int(parts[1]), "metallic": parts[2] == "1"}
	_attach_library_car(-7)
	# (car:colour:metallic:hide1,hide2,..: library meshes whose names contain these stay hidden; 'noshadow' = the
	# library car casts no shadow)
	if parts.size() > 3:
		for p in _car_parts:
			if p[1] == -7:
				for h in parts[3].split(","):
					if h == "noshadow" and p[0] is GeometryInstance3D:
						(p[0] as GeometryInstance3D).cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
					elif h != "" and String((p[0] as Node).name).contains(h):
						(p[0] as Node3D).visible = false
	print("world_view: --library-swap %s (matrix %.2f m from the captured car)" % [lname, bd])


# A library car mesh's materials, as the scene's cars get them in the loader: paint (the game's colour), glass / lens
# (the game's settings), gauges, plain parts (vertex brightness, chrome and rim levels).
func _setup_library_mesh(mi: MeshInstance3D, cm: Dictionary, paint_col: Color, metal: float) -> void:
	mi.layers = 2
	var nm := String(mi.name)
	for s in mi.mesh.get_surface_count():
		var m0 := mi.mesh.surface_get_material(s) as BaseMaterial3D
		if m0 == null:
			continue
		var m := m0.duplicate() as BaseMaterial3D
		if m.roughness_texture != null and m.albedo_texture != null:
			m.albedo_color = paint_col
			m.metallic = metal
			var pm := _car_material(CARPAINT_SHADER, m, _gltf_path, "FM3_CARPAINT",
				["refl_gain", "refl_f0", "spec_gain", "spec_power", "shadow_strength", "refl_metal"])
			pm.set_shader_parameter("sun_dir", _sun_to)
			mi.set_surface_override_material(s, pm)
			continue
		if _blended(m) and m.roughness < 0.1 and m.albedo_texture == null:
			var lens := nm.contains("detail_glass") or nm.contains("red_glass")
			var gm := _car_material(CARLENS_SHADER if lens else CARGLASS_SHADER, m, _gltf_path, "FM3_CARGLASS",
				["env_scale", "fresnel_min", "fresnel_power", "max_opacity"])
			var gp: Dictionary = cm.get(nm, {})
			for k in gp:
				var v = gp[k]
				if v is Array:
					gm.set_shader_parameter(k, Vector4(v[0], v[1], v[2], v[3]) if k == "glass_color" else Vector3(v[0], v[1], v[2]))
				else:
					gm.set_shader_parameter(k, float(v))
			gm.set_shader_parameter("sun_dir", _sun_to)
			_lens_sync(gm)
			if OS.get_environment("FM3_PLAYER_CAR") != "" and nm.contains(OS.get_environment("FM3_PLAYER_CAR")):
				gm.set_shader_parameter("player_glass", true)
			mi.set_surface_override_material(s, gm)
			continue
		if nm.contains("gauge") and m.albedo_texture != null:
			var gg := ShaderMaterial.new()
			gg.shader = load("res://viewer/fm3_gauge.gdshader")
			gg.set_shader_parameter("tex", m.albedo_texture)
			gg.set_shader_parameter("gain", GAUGE_GAIN)
			mi.set_surface_override_material(s, gg)
			continue
		m.shading_mode = BaseMaterial3D.SHADING_MODE_PER_PIXEL
		if nm.contains("_interior_") or nm.contains("_seat"):
			# the exterior model's own cabin, seen through the windows: dark in the game (CABIN_K)
			m.albedo_color = Color(m.albedo_color.r * CABIN_K, m.albedo_color.g * CABIN_K, m.albedo_color.b * CABIN_K, m.albedo_color.a)
			m.metallic_specular = 0.0
		m.cull_mode = BaseMaterial3D.CULL_DISABLED
		m.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
		if m.roughness >= 0.9:
			m.metallic_specular = 0.04
		if m.metallic >= 0.9:
			m.albedo_color = Color(m.albedo_color.r * CHROME_SCALE, m.albedo_color.g * CHROME_SCALE, m.albedo_color.b * CHROME_SCALE, m.albedo_color.a)
		elif nm.begins_with("wheel_"):
			m.albedo_color = Color(m.albedo_color.r * RIM_SCALE, m.albedo_color.g * RIM_SCALE, m.albedo_color.b * RIM_SCALE, m.albedo_color.a)
			m.metallic_specular = RIM_SPECULAR
		if mi.mesh.surface_get_format(s) & Mesh.ARRAY_FORMAT_COLOR:
			m.vertex_color_use_as_albedo = true
		mi.set_surface_override_material(s, m)


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
				# (brake calipers do not spin: they stay with the body; fm3_track_export.py build_wheels)
				if _wheels.has(car) and maxf(box.size.x, maxf(box.size.y, box.size.z)) < 1.0 and not String(m.name).contains("caliper"):
					var c := box.get_center()
					var best_d := 0.45
					for k in 4:
						var d := c.distance_to((_wheels[car][k] as Transform3D).origin)
						if d < best_d:
							best_d = d
							wk = k
				_register_part(m, car, m.global_transform, wk)
				per_car[car] = per_car.get(car, 0) + 1
				if wk >= 0:
					per_wheel[car] = per_wheel.get(car, 0) + 1
				break
	# A captured car has dozens of meshes; a few matched ones are scene meshes near a grid slot (Motegi: 1 mesh on the
	# Charger, which then never got its library model): those stay static and the car is left to the car library.
	for car in per_car.keys():
		if int(per_car[car]) < 10:
			_car_parts = _car_parts.filter(func(p): return p[1] != car)
			_cars_with_parts.erase(car)
			print("world_view: live car %08X: %d stray scene meshes left in place (the car library's model instead)" % [car, per_car[car]])
			per_car[car] = 0
			per_wheel[car] = 0
	for car in _cars:
		var o := car_transform(_cars[car], _live_axes).origin
		print("world_view: live car %08X at (%.2f, %.2f, %.2f): %d meshes attached (%d on its wheels)" % [car, o.x, o.y, o.z,
			per_car.get(car, 0), per_wheel.get(car, 0)])
		if per_car.get(car, 0) == 0 and _car_names.has(car) and not _library_tried.has(car) and not _library_queue.has(car):
			_library_queue.append(car)  # (its name came before this first attach)
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
	var f7 := Input.is_key_pressed(KEY_F7)
	if f7 and not _f7:
		_steer_mode = STEER_MODES[(STEER_MODES.find(_steer_mode) + 1) % STEER_MODES.size()]
		print("world_view: steering wheel: %s" % _steer_mode)
	_f7 = f7
	var tab := Input.is_key_pressed(KEY_TAB)
	if tab and not _live_tab and _live_dirs.size() > 1:
		_live_director = _live_dirs[(_live_dirs.find(_live_director) + 1) % _live_dirs.size()]
		print("world_view: live director %08X%s" % [_live_director, " (the drawn camera)" if _live_director == _live_dirs[0] else ""])
	_live_tab = tab
	# A picture on request: create <out>.shot and the next frame is saved to <out> (the file is removed). Held (up to
	# 10 s) while streamed cars still wait for their library model: on the capture-free CrownJewel the three cars loaded
	# last were missing from live_compare's picture (one load a frame, ~0.4 s each).
	if _out != "" and FileAccess.file_exists(_out + ".shot") and _shot_held_since < 0:
		_shot_held_since = Time.get_ticks_msec()
	if _out != "" and _shot_held_since >= 0 and _cars_pending() and Time.get_ticks_msec() - _shot_held_since < 20000:
		_shot_settle = 3
	elif _out != "" and _shot_settle > 0 and FileAccess.file_exists(_out + ".shot"):
		_shot_settle -= 1  # (a few frames more: what the last load changed, e.g. has_live, is drawn one frame later)
	elif _out != "" and FileAccess.file_exists(_out + ".shot"):
		_shot_held_since = -1
		DirAccess.remove_absolute(_out + ".shot")
		root.get_texture().get_image().save_png(_out)
		print("world_view: saved ", _out)
		if OS.get_environment("FM3_DUMP_LIVE_CUBE") != "":
			# (debug: the live cube's six faces beside the picture, <out>.cube<k>.png, k = +x -x +y -y +z -z in glTF
			# space; for comparing with the game's own car cube)
			for k_ in _live_cube_vps.size():
				(_live_cube_vps[k_] as SubViewport).get_texture().get_image().save_png(_out + ".cube%d.png" % k_)
			print("world_view: live cube faces saved at ", _live_cube_cams[0].global_transform.origin if not _live_cube_cams.is_empty() else "-")
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
	var budget := 4000  # (a frame always ends: after a stall the backlog is caught up over a few frames)
	while _udp.get_available_packet_count() > 0 and budget > 0:
		budget -= 1
		var b := _udp.get_packet()
		if b.size() == 72 and b.slice(0, 4).get_string_from_ascii() == "FM3N":
			# which car (media name, Combo_Colors colour, paint type): cars the glTF lacks come from the car library
			var ncar := int(b.decode_u32(8))
			_car_names[ncar] = {"name": b.slice(20, 64).get_string_from_ascii(), "color": int(b.decode_u32(12)),
				"metallic": b.decode_u32(16) == 1}
			if _car_attached and not _cars_with_parts.has(ncar) and not _library_tried.has(ncar) and not _library_queue.has(ncar):
				_library_queue.append(ncar)  # (loaded after the packets, one a frame: a load takes ~0.3 s)
			continue
		if b.slice(0, 4).get_string_from_ascii() == "FM3E" and b.size() >= 32:
			# The player's engine speed (rpm) and redline: only the player's cockpit is shown, so its tach takes this;
			# v2 also player 1's steering input and the racing wheel's lock (the cockpit steering wheel).
			_engine_rpm = b.decode_float(12)
			if b.decode_u32(4) >= 2 and b.size() >= 40:
				_steer = clampf(b.decode_float(20), -1.0, 1.0)
				_steer_lock = float(b.decode_u32(24))
			if b.decode_u32(4) >= 3 and b.size() >= 40:
				_player_brake = clampf(b.decode_float(28), 0.0, 1.0)
			continue
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
					var v_old := float(_car_speed.get(car, 0.0))
					_car_speed[car] = lerpf(v_old, pos.distance_to(_car_prev[car][0]) / dtk, 0.2)
					_car_accel[car] = lerpf(float(_car_accel.get(car, 0.0)), (float(_car_speed[car]) - v_old) / dtk, 0.15)
					# backwards: the displacement against the car's nose (car space -z is forward: the cockpit's hood)
					var nose := -Vector3(b.decode_float(48), b.decode_float(52), b.decode_float(56))
					var dpos: Vector3 = pos - (_car_prev[car][0] as Vector3)
					_car_back[car] = dpos.dot(nose) < -0.3 * dtk
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
	if not _library_queue.is_empty() and _car_attached:
		_attach_library_car(_library_queue.pop_front())
	_poll_liveries()
	if not _car_attached and _car_first_ms > 0 and Time.get_ticks_msec() - _car_first_ms > 500:
		_attach_cars()
	var main_view := _live_dirs.is_empty() or _live_director == _live_dirs[0]
	if _live_has_drawn and main_view and not _live_frames.is_empty():
		_show_drawn(now)
	else:
		# No drawn frames (an older game build), or another director (Tab: the mirror): its hand-off, newest only.
		if latest.is_empty():
			return
		_set_view(live_transform(latest, _live_axes))
		if _car_attached:
			var mv := {}
			for car in _car_inv:
				var b: PackedByteArray = _cars.get(car, PackedByteArray())
				if not b.is_empty():
					mv[car] = car_transform(b, _live_axes) * (_car_inv[car] as Transform3D)
			var wv := {}
			for car in _wheel_inv:
				if _wheels.has(car):
					var ws := []
					for k in 4:
						ws.append((_wheels[car][k] as Transform3D) * (_wheel_inv[car][k] as Transform3D))
					wv[car] = ws
			_update_live_cars(live_transform(latest, _live_axes), mv, wv, now)
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
	_update_live_cars(cam, moves, s.get("wmoves", {}), now)


# The cars' state each frame from the moves of the moment shown (also from the hand-off path, where the game sends no
# drawn frames, e.g. on the frozen grid: there has_live, the brake lights, the in-car switch and the wheel blur never
# ran, 2026-11-24): cockpit / exterior, lights, the player's live cube, part placement, mirrors.
func _update_live_cars(cam: Transform3D, moves: Dictionary, wmoves: Dictionary, now: float) -> void:
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
	if in_car != _was_in_car and _world_env != null:
		_was_in_car = in_car
		_world_env.environment.tonemap_exposure = _base_exposure * (IN_CAR_EXPOSURE if in_car else 1.0)
	_update_lights(player)
	_update_engine_audio(player, moves)
	if player != _live_player and not _live_cube_cams.is_empty():
		_live_player = player
		for c_ in _car_shader_mats:
			for sm_ in _car_shader_mats[c_]:
				(sm_ as ShaderMaterial).set_shader_parameter("has_live", c_ == player)
	for part in _car_parts:
		var mine: bool = int(part[1]) == player and in_car
		var gi := part[0] as GeometryInstance3D
		if bool(part[5]):
			gi.visible = mine and not (_steer_mode == "off" and part[7] != null and part[7].get("gauge") == "steering")
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
			if int(part[4]) < 2:
				(part[0] as GeometryInstance3D).transparency = (1.0 - blur) if int(part[4]) == 1 else blur
		if wk >= 0 and wmoves.has(part[1]):
			(part[0] as Node3D).global_transform = (wmoves[part[1]][wk] as Transform3D) * (part[2] as Transform3D)
		elif moves.has(part[1]):
			var turn := Transform3D.IDENTITY
			if part[7] != null and (part[0] as Node3D).visible:
				turn = needle_turn(part[7], part[1])
			(part[0] as Node3D).global_transform = (moves[part[1]] as Transform3D) * turn * (part[2] as Transform3D)
	_update_mirrors(player, in_car, cam)
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
	# the cars sampled _car_lead seconds later than the camera (--live-car-lead ms)
	var kc0 := k0
	var kc1 := k1
	var alphac := alpha
	if t != INF and _car_lead != 0.0 and _live_frames.size() > 1:
		var tc := t + _car_lead
		var ic := _live_frames.size() - 1
		while ic > 0 and float(_live_frames[ic]["t"]) > tc:
			ic -= 1
		kc0 = ic
		kc1 = mini(ic + 1, _live_frames.size() - 1)
		var spc := float(_live_frames[kc1]["t"]) - float(_live_frames[kc0]["t"])
		alphac = clampf((tc - float(_live_frames[kc0]["t"])) / spc, 0.0, 1.0) if spc > 0.0 else 1.0
	var moves := {}
	if _car_attached:
		for car in _car_inv:
			var a0 = _car_in_frame(car, kc0)
			var a1 = _car_in_frame(car, kc1)
			if a0 == null or a1 == null:
				continue
			var d0: Transform3D = (a0 as Transform3D) * (_car_inv[car] as Transform3D)
			var d1: Transform3D = (a1 as Transform3D) * (_car_inv[car] as Transform3D)
			d0.basis = d0.basis.orthonormalized()
			d1.basis = d1.basis.orthonormalized()
			moves[car] = d0.interpolate_with(d1, alphac)
	# Each wheel's move, the same way (spin between two frames stays under half a turn up to ~200 km/h at 60 fps).
	var wmoves := {}
	if _car_attached:
		for car in _wheel_inv:
			var w0 = _wheels_in_frame(car, kc0)
			var w1 = _wheels_in_frame(car, kc1)
			if w0 == null or w1 == null:
				continue
			var ws := []
			for k in 4:
				var e0: Transform3D = (w0[k] as Transform3D) * (_wheel_inv[car][k] as Transform3D)
				var e1: Transform3D = (w1[k] as Transform3D) * (_wheel_inv[car][k] as Transform3D)
				e0.basis = e0.basis.orthonormalized()
				e1.basis = e1.basis.orthonormalized()
				ws.append(e0.interpolate_with(e1, alphac))
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
	_exposure_update()
	# the sky dome stays centred on the camera, as FM3 draws it (fm3_track_export.py: skydome_ nodes)
	if _cam != null and _cam.is_inside_tree():
		for sk in _sky_nodes:
			(sk as Node3D).global_position = _cam.global_position
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
