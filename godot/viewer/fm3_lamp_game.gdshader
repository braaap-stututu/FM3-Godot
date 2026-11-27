// FM3 lamp parts (tail-lamp bulbs, reflectors, textured reflectors, reverse lamps) with the game's own formula (decoded
// 2026-11-26 from ReGPU's HLSL of the grid's tail_light PS 7f4b46775654ee5b = shaders_v11 container 92, textured_reflector
// 0c88abdd1c499126, reverse a56fcadd0575d570; constants mapped back by register order), in gamma space:
//   colour = lerp(tex x (0.4 + 0.6 x saturate(hl^2)) x lerp(1, lm, alpha) + spec x SpecColor,
//                 env x CubeScale x (1 - damp x (1 - lm)), F) + tex x BrakeColor x brakeReverseAmount
//   hl = N.L x 0.5 + 0.5 (L = psLightDirWS, towards the sun); spec = saturate(R.L)^SpecularPower x SpecularAmount;
//   F = clamp(FresnelScale x (1 - N.V)^FresnelPower, FresnelMin, FresnelMax) x reflectionScaler; opaque (alpha =
//   GlassMaxOpacity, 1). lm = the track lightmap under the car (t10): here Godot's sun shadow stands in for it,
//   lm = mix(lm_shade, 1, shadow attenuation). No sun colour or intensity: the texture shows at 40-100 % of its value.
// The earlier fitted lamp (fm3_lamp.gdshader) stays for FM3_GAME_LAMP=0.
shader_type spatial;
render_mode cull_disabled, ambient_light_disabled;

uniform sampler2D albedo_tex : filter_linear_mipmap_anisotropic, hint_default_white;  // (raw: the game's values are gamma)
uniform samplerCube env_cube : filter_linear_mipmap;
uniform bool has_env = false;
uniform vec3 env_fallback = vec3(0.45, 0.52, 0.56);
uniform vec3 env_flip = vec3(-1.0, 1.0, 1.0);
uniform float static_cube_gain = 1.0;
uniform float cube_scale = 1.0;
uniform float fresnel_min = 0.15;
uniform float fresnel_max = 1.0;
uniform float fresnel_scale = 1.0;
uniform float fresnel_power = 1.5;
uniform float spec_amount = 4.0;
uniform float spec_power = 128.0;
uniform vec3 sun_dir = vec3(0.0, 1.0, 0.0);
uniform float lm_shade = 0.5;  // the track lightmap's value in shade (fitted; FM3_LAMP_SHADE)
uniform float env_damp = 0.5;  // StaticEnvLightmapDampner (the windows' captured 0.5)
uniform float lamp_gain = 1.0;
uniform float glow = 0.0;
uniform vec3 glow_color = vec3(1.0, 0.0, 0.0);
uniform float alpha_cut = -1.0;
uniform float hdr_clamp = 1.0;  // (as the paint's: highlights capped at 1 in gamma before going linear; FM3_HDR_CLAMP)

#include "res://viewer/fm3_livecube.gdshaderinc"

varying vec3 v_env;  // the reflection term (linear), damped in light() by the shadow

vec3 to_linear(vec3 c) {
	c = max(c, vec3(0.0));
	return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(0.04045, c));
}

void fragment() {
	vec4 t = texture(albedo_tex, UV);
	vec3 n = FRONT_FACING ? NORMAL : -NORMAL;
	vec3 nw = normalize((INV_VIEW_MATRIX * vec4(n, 0.0)).xyz);
	vec3 r = (INV_VIEW_MATRIX * vec4(reflect(-VIEW, n), 0.0)).xyz;
	vec3 l = normalize(sun_dir);
	float hl = clamp(dot(nw, l) * 0.5 + 0.5, 0.0, 1.0);
	float sp = pow(clamp(dot(normalize(r), l), 0.0, 1.0), spec_power) * spec_amount;
	float cosv = clamp(abs(dot(n, VIEW)), 0.0, 1.0);
	float f = min(max(fresnel_scale * pow(1.0 - cosv, fresnel_power), fresnel_min), fresnel_max);
	vec3 env = (has_live ? live_cube(r) : (has_env ? texture(env_cube, r * env_flip).rgb * static_cube_gain : env_fallback)) * cube_scale;
	ALBEDO = to_linear(min(t.rgb * (0.4 + 0.6 * hl * hl) + vec3(sp), vec3(hdr_clamp))) * (1.0 - f) * lamp_gain;
	v_env = to_linear(min(env * f, vec3(hdr_clamp))) * lamp_gain;
	EMISSION = glow_color * to_linear(t.rgb) * glow;
	if (alpha_cut >= 0.0) {
		ALPHA = t.a;
		ALPHA_SCISSOR_THRESHOLD = alpha_cut;
	}
}

void light() {
	if (LIGHT_IS_DIRECTIONAL) {
		float lm = mix(lm_shade, 1.0, ATTENUATION);
		// (gamma lm on a gamma colour: x lm^2.2 in linear light)
		DIFFUSE_LIGHT += vec3(pow(lm, 2.2));
		SPECULAR_LIGHT += v_env * pow(1.0 - env_damp * (1.0 - lm), 2.2);
	}
}
