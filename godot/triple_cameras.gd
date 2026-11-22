# triple_cameras.gd — applies triple-screen camera settings (godot/triple_camera.h,
# fir_triple_camera) to Godot cameras. Godot 4.7.
#
# Each screen is a 16:9 SubViewport with a Camera3D (or a RenderingServer camera RID).
# The core computes, per screen: local_rot_y, size, offset, z_near, z_far (fir_triple_cameras);
# the game camera's transform comes from the profile's CAMERA record.
#
# Usage:
#   const TripleCameras = preload("res://triple_cameras.gd")
#   var screens := TripleCameras.make_screens(self, Vector2i(2560, 1440))
#   TripleCameras.apply(screens[i].camera, game_xform, rot_y, size, offset, near, far)
extends RefCounted


## Applies one screen's settings to a Camera3D.
static func apply(camera: Camera3D, game_camera_transform: Transform3D, local_rot_y: float,
		size: float, offset: Vector2, z_near: float, z_far: float) -> void:
	camera.projection = Camera3D.PROJECTION_FRUSTUM
	camera.keep_aspect = Camera3D.KEEP_HEIGHT
	camera.set_frustum(size, offset, z_near, z_far)
	camera.global_transform = screen_transform(game_camera_transform, local_rot_y)


## The same through RenderingServer, for a backend that drives camera RIDs directly.
static func apply_rid(camera: RID, game_camera_transform: Transform3D, local_rot_y: float,
		size: float, offset: Vector2, z_near: float, z_far: float) -> void:
	RenderingServer.camera_set_frustum(camera, size, offset, z_near, z_far)
	RenderingServer.camera_set_use_vertical_aspect(camera, false) # KEEP_HEIGHT
	RenderingServer.camera_set_transform(camera, screen_transform(game_camera_transform, local_rot_y))


## The screen camera: the game camera turned about its own up axis, same eye point.
static func screen_transform(game_camera_transform: Transform3D, local_rot_y: float) -> Transform3D:
	return game_camera_transform * Transform3D(Basis(Vector3.UP, local_rot_y), Vector3.ZERO)


## Builds three side-by-side SubViewports (left, centre, right) under `parent`, each `screen_size`
## (16:9), sharing the parent's 3D world. Returns [{container, viewport, camera}, ...].
static func make_screens(parent: Node, screen_size: Vector2i) -> Array:
	var row := HBoxContainer.new()
	row.name = "TripleScreens"
	row.add_theme_constant_override("separation", 0)
	parent.add_child(row)
	var screens := []
	for i in 3:
		var container := SubViewportContainer.new()
		container.name = ["Left", "Centre", "Right"][i]
		container.stretch = true
		container.custom_minimum_size = Vector2(screen_size)
		var viewport := SubViewport.new()
		viewport.size = screen_size
		viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
		var camera := Camera3D.new()
		camera.current = true
		viewport.add_child(camera)
		container.add_child(viewport)
		row.add_child(container)
		screens.append({"container": container, "viewport": viewport, "camera": camera})
	return screens
