// FM3 lamp parts under the lenses (reflectors, textured reflectors, tail-lamp bulbs; 2026-11-26): the lit lamp texture
// (Godot's lighting, as the plain material before) plus the mirror reflection of the static car cube as emission, in
// the OPAQUE pass. The reflection used to be an additive next pass (fm3_reflector.gdshader), drawn in the transparent
// stage after the lenses had already read the screen behind them: it landed on top of the red lens untinted (the RSX's
// bulb domes came out bluish-white, its reflectors grey, where the game's are pink through the lens). Values from
// Media\Cars\ShaderSettings\Normal.xml: <reflector> CubeScale 1.5, <textured_reflector> 1.0, <tail_light> 0.2, Fresnel
// min 0.15 / power 1.5, scaled
// by the car's own settings (<car>_lamps.json, world_view.gd _lamp_settings). Brake / reverse glow (world_view.gd _update_lights) as emission of the texture.
shader_type spatial;
render_mode cull_disabled;

uniform sampler2D albedo_tex : source_color, filter_linear_mipmap_anisotropic, hint_default_white;
uniform vec4 albedo_color = vec4(1.0);
uniform bool use_vcol = false;
uniform samplerCube env_cube : filter_linear_mipmap;
uniform bool has_env = false;
uniform vec3 env_fallback = vec3(0.45, 0.52, 0.56);
uniform vec3 env_flip = vec3(-1.0, 1.0, 1.0);
uniform float static_cube_gain = 1.0;
uniform float cube_scale = 1.5;
uniform float fresnel_min = 0.15;
uniform float fresnel_power = 1.5;
uniform float fresnel_max = 1.0;
uniform float fresnel_scale = 1.0;
uniform float refl = 1.0;
uniform float tint_amount = 0.5;  // the reflection in the lamp texture's colour, this far
uniform float glow = 0.0;  // brake / reverse lamp (emission of the texture)
uniform vec3 glow_color = vec3(1.0, 0.0, 0.0);
uniform float alpha_cut = -1.0;

vec3 to_linear(vec3 c) {
	c = max(c, vec3(0.0));
	return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(0.04045, c));
}

void fragment() {
	vec4 t = texture(albedo_tex, UV);
	vec3 a = t.rgb * albedo_color.rgb * (use_vcol ? COLOR.rgb : vec3(1.0));
	ALBEDO = a;
	vec3 n = FRONT_FACING ? NORMAL : -NORMAL;
	vec3 r = (INV_VIEW_MATRIX * vec4(reflect(-VIEW, n), 0.0)).xyz;
	vec3 env = (has_env ? texture(env_cube, r * env_flip).rgb * static_cube_gain : env_fallback) * cube_scale;
	float cosv = clamp(abs(dot(n, VIEW)), 0.0, 1.0);
	// (the game's min(max(.., FresnelMin), FresnelMax): some cars set min above max, the RSX's textured reflector 2.11 / 0.86)
	float f = min(max(fresnel_scale * pow(1.0 - cosv, fresnel_power), fresnel_min), fresnel_max);
	// (gamma-space reflection, tinted by the texture's own (gamma) colour, then linear as emission)
	vec3 tg = texture(albedo_tex, UV).rgb;  // (sRGB-decoded: back to gamma for the tint)
	tg = mix(tg * 12.92, 1.055 * pow(max(tg, vec3(0.0)), vec3(1.0 / 2.4)) - 0.055, step(0.0031308, tg));
	vec3 c = env * f * refl * mix(vec3(1.0), tg, tint_amount);
	EMISSION = to_linear(c) + glow_color * t.rgb * glow;
	if (alpha_cut >= 0.0) {
		ALPHA = t.a;
		ALPHA_SCISSOR_THRESHOLD = alpha_cut;
	}
}
