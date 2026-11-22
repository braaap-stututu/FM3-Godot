# triple_camera_godot_test.gd — in-engine check of triple_cameras.gd with real Camera3D nodes.
#
# Reads the cases written by triple_camera_test.c (path in the FIR_TRIPLE_CASES environment
# variable), builds a 2560x1440 SubViewport with a Camera3D per case, applies the settings through
# triple_cameras.gd, and checks that Godot projects every point to the NDC ReGPU's triple view gives.
#
#   godot --headless --path frame-ir/godot --script res://tests/triple_camera_godot_test.gd
extends SceneTree

const TripleCameras = preload("res://triple_cameras.gd")
const TOLERANCE := 1e-3


var data
var camera: Camera3D
var done := false


func _initialize() -> void:
	var path := OS.get_environment("FIR_TRIPLE_CASES")
	data = JSON.parse_string(FileAccess.get_file_as_string(path))
	if data == null:
		push_error("cannot read cases from '%s'" % path)
		quit(2)
		return
	var viewport := SubViewport.new()
	viewport.size = Vector2i(int(data.viewport[0]), int(data.viewport[1]))
	root.add_child(viewport)
	camera = Camera3D.new()
	viewport.add_child(camera)
	camera.current = true


# Runs on the first frame, once the camera is inside the tree (get_camera_projection needs it).
func _process(_delta: float) -> bool:
	if done or data == null:
		return true
	done = true
	quit(_run())
	return true


func _run() -> int:
	if not camera.is_inside_tree():
		push_error("camera is not inside the tree")
		return 2
	var failures := 0
	var worst_by_layout := {}
	for c in data.cases:
		var g: Array = c.game
		# row-major 3x4 camera-to-world -> Transform3D (basis columns = matrix columns)
		var game := Transform3D(
				Vector3(g[0], g[4], g[8]), Vector3(g[1], g[5], g[9]), Vector3(g[2], g[6], g[10]),
				Vector3(g[3], g[7], g[11]))
		TripleCameras.apply(camera, game, c.rot_y, c.size, Vector2(c.offset[0], c.offset[1]), c.near, c.far)
		var proj: Projection = camera.get_camera_projection()
		var view := camera.global_transform.affine_inverse()
		for pt in c.points:
			var world := Vector3(pt.p[0], pt.p[1], pt.p[2])
			var cam := view * world
			var clip: Vector4 = proj * Vector4(cam.x, cam.y, cam.z, 1.0)
			var ndc := Vector2(clip.x / clip.w, clip.y / clip.w)
			var err := maxf(absf(ndc.x - pt.ndc[0]), absf(ndc.y - pt.ndc[1]))
			worst_by_layout[c.layout] = maxf(worst_by_layout.get(c.layout, 0.0), err)
			if err > TOLERANCE:
				failures += 1
				if failures <= 5:
					print("FAIL %s screen %d: godot %s expected %s" % [c.layout, c.screen, ndc, Vector2(pt.ndc[0], pt.ndc[1])])

	for layout in worst_by_layout:
		print("%-20s max NDC difference in Godot %.9f" % [layout, worst_by_layout[layout]])
	print("%d cases, %s" % [data.cases.size(), "all passed" if failures == 0 else "%d FAILURES" % failures])
	return 0 if failures == 0 else 1
