// FM3 car window glass (2026-11-23): far less see-through than a clear pane. In the game's screenshot of the grid a
// car's windows are dark (median luminance ~20 of 255 where Godot's clear glass showed the track at ~50) with bright
// streaks of reflected sky (90th percentile ~90). So: a dark tinted body at a fixed opacity, plus a Fresnel reflection
// of the layout's static car cube (staticcarcubemap.xpr) and the sun's highlight. Fitted with tools/car_regions.py.
shader_type spatial;
render_mode blend_mix, cull_disabled, depth_draw_opaque, ambient_light_disabled, specular_disabled;

uniform vec4 albedo_color = vec4(0.1, 0.12, 0.13, 1.0);  // the glass's own tint (the material's colour)
uniform samplerCube env_cube : filter_linear_mipmap;
uniform bool has_env = false;
uniform vec3 env_fallback = vec3(0.45, 0.52, 0.56);
uniform vec3 env_flip = vec3(-1.0, 1.0, 1.0);
// Fitted on the grid (tools/car_regions.py, 7 cars): the old clear glass (alpha 0.65) showed the track through at a
// median of ~50; these give medians scattered around the game's (15-49 by car: what each window reflects differs, the
// game reflecting a cube of its live surroundings, this the static one).
uniform float opacity = 0.95;  // how little of what is behind shows through
uniform float body_level = 0.04;  // the dark body's brightness (gamma)
uniform float refl_gain = 2.5;
uniform float refl_f0 = 0.0;  // (head-on the game's windows are dark: the CR-X's rear glass)
uniform float spec_gain = 2.0;
uniform float spec_power = 120.0;

vec3 to_linear(vec3 c) {
	c = max(c, vec3(0.0));
	return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(0.04045, c));
}

void fragment() {
	vec3 r = (INV_VIEW_MATRIX * vec4(reflect(-VIEW, NORMAL), 0.0)).xyz;
	vec3 env = has_env ? texture(env_cube, r * env_flip).rgb : env_fallback;
	float cosv = clamp(abs(dot(NORMAL, VIEW)), 0.0, 1.0);
	float fres = refl_f0 + (1.0 - refl_f0) * pow(1.0 - cosv, 5.0);
	vec3 tint = albedo_color.rgb / max(max(albedo_color.r, max(albedo_color.g, albedo_color.b)), 1e-3);
	vec3 c = body_level * tint + env * fres * refl_gain;
	// Reflections stay visible however see-through the pane is: opacity rises with them.
	float a = clamp(opacity + (1.0 - opacity) * clamp(fres * refl_gain, 0.0, 1.0), 0.0, 1.0);
	ALBEDO = to_linear(c) / a;
	ALPHA = a;
}

void light() {
	if (LIGHT_IS_DIRECTIONAL) {
		DIFFUSE_LIGHT += vec3(1.0);  // (the body is its own colour: unlit)
		float spec = pow(max(dot(reflect(-LIGHT, NORMAL), VIEW), 0.0), spec_power) * ATTENUATION;
		SPECULAR_LIGHT += to_linear(vec3(spec * spec_gain));
	}
}
