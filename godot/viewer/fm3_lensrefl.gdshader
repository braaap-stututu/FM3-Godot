// FM3 lamp lenses, second pass (world_view.gd: next_pass of fm3_carlens.gdshader): the lens's own reflection added over
// its colour filter. The filter alone took a lens's blue to 0 where the game's keeps some (CR-X amber corners 90/56/44
// in the game, 80/46/0 here; red tails 50/8/8 vs 78/0/0): the game's lens glass reflects the environment like a window.
// Back faces culled: with both faces the far face's multiply pass took the reflection out again. (The CR-X's red tails
// stay 83/0/0: not reached by this pass, cause not found yet.)
shader_type spatial;
render_mode blend_add, cull_back, depth_draw_never, unshaded, ambient_light_disabled, specular_disabled;

uniform samplerCube env_cube : filter_linear_mipmap;
uniform bool has_env = false;
uniform vec3 env_fallback = vec3(0.45, 0.52, 0.56);
uniform vec3 env_flip = vec3(-1.0, 1.0, 1.0);
uniform float refl = 0.05;  // (fitted on the CR-X's amber corners: summed |diff| 117.5 without, 53 at 0.05, 57.5 at 0.07)
uniform float fresnel_power = 1.5;

void fragment() {
	vec3 r = (INV_VIEW_MATRIX * vec4(reflect(-VIEW, NORMAL), 0.0)).xyz;
	vec3 env = has_env ? textureLod(env_cube, r * env_flip, 2.0).rgb : env_fallback;
	float cosv = clamp(dot(NORMAL, VIEW), 0.0, 1.0);
	float f = 0.4 + 0.6 * pow(1.0 - cosv, fresnel_power);
	ALBEDO = env * f * refl;
}
