// FM3's track fog (2026-11-25), in the track shaders as the game has it (its car shaders have none): the vertex shader's
// f = clamp(distance * c241.y + c241.z, 0, c241.w) (FogConsts), the pixel shader's lerp of its gamma-space colour to
// c242 FogColor by f. The values: TrackSettings.xml <Fog>, blended by the camera's heading (world_view.gd _fog_update)
// into the global parameters (project.godot [shader_globals]): fm3_fog_k = (slope, offset, max density, on).
global uniform vec3 fm3_fog_color;
global uniform vec4 fm3_fog_k;

vec3 fm3_fog(vec3 c, vec3 view_pos) {
	float f = clamp(length(view_pos) * fm3_fog_k.x + fm3_fog_k.y, 0.0, fm3_fog_k.z) * fm3_fog_k.w;
	return mix(c, fm3_fog_color, f);
}
