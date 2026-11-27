// FM3's car light on a car's plain opaque parts (trim, plastic, grilles, badges, undercarriage; 2026-11-26): every car
// vertex shader in Media/Shaders/Cars/shaders_v11.fxobj carries the same SH constants as the paint's
// (shHemisphericalLightR/G/B c38-40, shDirectionalLightI c36), so the parts are lit like the paint without its reflection
// (fm3_carpaint.gdshader game_amb / game_sun, LIVE.md "The car paint's light, decoded"), in gamma space:
//   colour = albedo x (SHTop a + SHBottom b + SHDir x o2w x smoothstep(..) x max(shadow, 0.25)) [+ a small highlight]
// o2w = 0.375 + 0.541 n.l (measured on the paint), (a, b) = the vertex's baked sky pair (library UV2). Replaces Godot's
// lighting (a flat grey ambient and the sun) on these parts; world_view.gd FM3_CAR_SH=0: off. Wheels stay on Godot's
// lighting (FM3_CAR_SH_WHEELS=1 includes them; their rims are metal and take the old path anyway).
shader_type spatial;
render_mode cull_disabled, ambient_light_disabled, specular_disabled;

uniform sampler2D albedo_tex : filter_linear_mipmap_anisotropic, repeat_enable, hint_default_white;  // (raw: gamma)
uniform vec4 albedo_color = vec4(1.0);  // (sRGB, as the glTF's base colour shows)
uniform bool use_vertex_color = false;
uniform vec3 sh_top = vec3(0.33, 0.34, 0.36);
uniform vec3 sh_bottom = vec3(0.0);
uniform vec3 sh_dir = vec3(0.78, 0.76, 0.73);
uniform vec2 sun_sh = vec2(0.375, 0.541);
uniform float sh_transition = 0.5;
uniform float sh_transition_width = 0.3;
uniform float min_shadow = 0.25;
uniform float spec_amount = 0.0;  // (a sun highlight: SpecularAmount; 0 = none)
uniform float spec_power = 32.0;
uniform float alpha_cut = -1.0;
// The badges' and emblems' reflection (2026-11-27, user: "the logos / badges not as prominent, as if sunken into the
// model"): their ShaderSettings (Normal.xml badge: SpecularAmount 4, power 128, Fresnel 0.15 .. 1 x (1 - cos)^1.5,
// CubeScale 1; emblem: 1, 75, power 1) make them polished; without it they were matte against the glossy paint. The
// game's Fresnel form as the lamps' (fm3_lamp_game.gdshader): min(max(scale (1 - cos)^power, min), max) x the cube,
// in shade x (1 - StaticEnvLightmapDampner (1 - shadow)).
#include "res://viewer/fm3_livecube.gdshaderinc"
uniform bool refl_on = false;
uniform float fresnel_min = 0.15;
uniform float fresnel_max = 1.0;
uniform float fresnel_scale = 1.0;
uniform float fresnel_power = 1.5;
uniform float cube_scale = 1.0;
uniform float env_damp = 0.5;
uniform vec3 env_fallback = vec3(0.45, 0.52, 0.56);
varying vec3 v_env;
varying float v_f;

varying vec3 base_gamma;
varying vec2 env_ab;

vec3 to_linear(vec3 c) {
	c = max(c, vec3(0.0));
	return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(0.04045, c));
}

void vertex() {
	env_ab = UV2;
}

void fragment() {
	vec4 t = texture(albedo_tex, UV);
	base_gamma = t.rgb * albedo_color.rgb * (use_vertex_color ? COLOR.rgb : vec3(1.0));
	ALBEDO = vec3(1.0);
	v_env = vec3(0.0);
	v_f = 0.0;
	if (refl_on) {
		vec3 n = FRONT_FACING ? NORMAL : -NORMAL;
		vec3 r = (INV_VIEW_MATRIX * vec4(reflect(-VIEW, n), 0.0)).xyz;
		float cosv = clamp(abs(dot(n, VIEW)), 0.0, 1.0);
		v_f = min(max(fresnel_scale * pow(1.0 - cosv, fresnel_power), fresnel_min), fresnel_max);
		v_env = (has_live ? live_cube(r) : env_fallback) * cube_scale * v_f;
	}
	if (alpha_cut >= 0.0) {
		ALPHA = t.a * albedo_color.a;
		ALPHA_SCISSOR_THRESHOLD = alpha_cut;
	}
}

void light() {
	if (LIGHT_IS_DIRECTIONAL) {
		vec3 amb = max(sh_top * env_ab.x + sh_bottom * env_ab.y, vec3(0.0));
		float o2w = max(sun_sh.x + sun_sh.y * dot(NORMAL, LIGHT), 0.0);
		float x = clamp((o2w * sh_dir.r - (sh_transition - sh_transition_width)) / (2.0 * sh_transition_width), 0.0, 1.0);
		float sh = max(ATTENUATION, min_shadow);
		vec3 lit = amb + sh_dir * o2w * x * x * (3.0 - 2.0 * x) * sh;
		float rl = max(dot(reflect(-LIGHT, NORMAL), VIEW), 0.0);
		vec3 spec = sh_dir * pow(rl, spec_power) * spec_amount * sh;
		vec3 refl = v_env * (1.0 - env_damp * (1.0 - sh));
		DIFFUSE_LIGHT += to_linear(base_gamma * lit * (1.0 - v_f) + spec + refl);
	}
}
