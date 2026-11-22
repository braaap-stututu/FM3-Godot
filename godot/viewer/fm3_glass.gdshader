// FM3 window glazing (diff_spec_refl_norm_4 / diff_spec_refl_3, tools/fm3_families.py mode "refl"): the base texture lit by
// the baked lightmap (as fm3_baked.gdshader), and where its alpha (x the material's reflection amount) says so, the
// track's static environment cube (staticcarcubemap.xpr, the same map the game reflects), with a Fresnel falloff.
// All in gamma space like the game, then converted to linear for Godot's linear tone mapper.
shader_type spatial;
render_mode cull_disabled, ambient_light_disabled, specular_disabled, diffuse_lambert;

uniform sampler2D albedo_tex : filter_linear_mipmap_anisotropic, repeat_enable, hint_default_white;
uniform sampler2D light_tex : filter_linear_mipmap, repeat_enable, hint_default_white;
uniform samplerCube env_cube : filter_linear_mipmap;
uniform bool has_env = false;
uniform float base_keep = 0.0;  // where reflective: how much of the lit base remains
uniform float env_gain = 1.0;
uniform float body_level = 0.13;
uniform float refl_f0 = 0.15;  // (0.15 fits the captured office glass better than 0.25)
uniform float use_fresnel = 0.0;
uniform vec3 env_flip = vec3(-1.0, 1.0, 1.0);  // (this scene's x is the game's mirrored)
uniform bool debug_env_only = false;
uniform int debug_part = 0;  // 1 lit base, 2 tinted environment, 3 reflection amount k (for fitting)
uniform vec3 env_fallback = vec3(0.45, 0.52, 0.56);
uniform bool has_lightmap = true;
uniform vec2 scale0 = vec2(1.0);
uniform vec3 tint0 = vec3(1.0);  // x: reflection amount (material parameter P[0].x)
uniform vec3 tint1 = vec3(1.0);  // reflection tint (P[2].rgb: (0.5, 1, 1) on the office glass, its teal)
uniform vec3 ambient = vec3(0.14, 0.14, 0.18);  // FM3 PS c247
uniform vec3 sun = vec3(1.58, 1.57, 1.5);  // FM3 PS c248
uniform float unlit_level = 0.6;
uniform float shadow_strength = 0.85;  // (linear: FM3 darkens shadowed ground to ~0.42 of its gamma-space value, 0.42^2.2 = 0.15)

vec3 to_linear(vec3 c) {
	c = clamp(c, 0.0, 1.0);
	return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(0.04045, c));
}

void fragment() {
	vec4 t = texture(albedo_tex, UV * scale0);
	vec3 light = has_lightmap ? mix(ambient, sun, texture(light_tex, UV2).rgb) : vec3(unlit_level);
	float k = clamp(t.a * max(tint0.x, 0.75), 0.0, 1.0);  // (glass panes opaque-ish even where P[0].x is low)
	vec3 r = (INV_VIEW_MATRIX * vec4(reflect(-VIEW, NORMAL), 0.0)).xyz;
	// (this scene's x is the game's mirrored: the cube is looked up with x flipped)
	vec3 env = has_env ? texture(env_cube, r * env_flip).rgb : env_fallback;
	// Glass = a dark body (the unlit interior seen through it) plus a Fresnel reflection of the environment cube, both
	// tinted; fitted to the game's office windows in the captured frame (body 0.105 / 0.13 / 0.13 for tint (0.5, 1, 1)).
	float cosv = clamp(abs(dot(NORMAL, VIEW)), 0.0, 1.0);
	float schlick = refl_f0 + (1.0 - refl_f0) * pow(1.0 - cosv, 5.0);
	vec3 glass = body_level * mix(vec3(1.0), tint1, 0.4) + env * tint1 * schlick * env_gain;
	ALBEDO = to_linear(mix(t.rgb * light, glass, k));
	if (debug_env_only) { ALBEDO = to_linear(env); }
	if (debug_part == 1) { ALBEDO = to_linear(t.rgb * light); }
	if (debug_part == 2) { ALBEDO = to_linear(env * tint1); }
	if (debug_part == 3) { ALBEDO = to_linear(vec3(k)); }
}

void light() {
	if (LIGHT_IS_DIRECTIONAL) {
		DIFFUSE_LIGHT += vec3(1.0 - shadow_strength + shadow_strength * ATTENUATION);
	}
}
