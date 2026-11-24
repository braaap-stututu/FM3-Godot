// FM3's sun-lit track surfaces without a lightmap (barriers, walls, props: barr_shad_diff_spec_nolm_1 and kin), the game's
// formula from the captured pixel shader 0e7558eb6ace5e51 (2026-11-24): in gamma space
//   colour = albedo x (ambient + (sun - ambient) x n.l x lerp(LightAmbient, 1, sun visibility))
// with ambient c247 (0.14, 0.14, 0.18), sun = TrackSettings LightColor c248 (1.58, 1.57, 1.5) and LightAmbient c240
// (0.32, 0.37, 0.45) where the shadow map says shade. Godot's standard lighting (sun 1.3 linear, flat ambient) left the
// CrownJewel pit wall's sunlit face at 202 where the game has 248.
shader_type spatial;
render_mode cull_disabled, ambient_light_disabled, specular_disabled;

uniform sampler2D albedo_tex : source_color, filter_linear_mipmap_anisotropic, repeat_enable, hint_default_white;
uniform vec4 albedo_color = vec4(1.0);
uniform bool use_vcol = false;
uniform float alpha_cut = -1.0;
uniform vec3 ambient = vec3(0.14, 0.14, 0.18);
uniform vec3 sun = vec3(1.58, 1.57, 1.5);
uniform vec3 shade = vec3(0.32, 0.37, 0.45);
uniform float gain = 1.0;
varying vec3 alb;

vec3 to_linear(vec3 c) {
	c = max(c, vec3(0.0));
	return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(0.04045, c));
}

vec3 to_gamma(vec3 c) {
	c = max(c, vec3(0.0));
	return mix(c * 12.92, 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055, step(0.0031308, c));
}

void fragment() {
	vec4 t = texture(albedo_tex, UV);
	if (alpha_cut >= 0.0 && t.a * albedo_color.a < alpha_cut) {
		discard;
	}
	// (the glTF texture is sRGB: source_color gives linear; the game works on the gamma values)
	alb = to_gamma(t.rgb) * albedo_color.rgb;
	if (use_vcol) {
		alb *= COLOR.rgb;
	}
	ALBEDO = vec3(1.0);
}

void light() {
	if (LIGHT_IS_DIRECTIONAL) {
		float ndl = max(dot(NORMAL, LIGHT), 0.0);
		vec3 vis = mix(shade, vec3(1.0), ATTENUATION);
		DIFFUSE_LIGHT += to_linear(alb * (ambient + (sun - ambient) * ndl * vis) * gain);
	}
}
