// FM3's track fog (2026-11-25), as a full-screen pass over the opaque picture. The game's track vertex shaders compute
// f = clamp(distance * c241.y + c241.z, 0, c241.w) (FogConsts) and the pixel shaders lerp their colour, in gamma space,
// to c242 FogColor by f: linear from NearDensity at Near to FarDensity at Far (TrackSettings.xml <Fog>, blended by the
// camera's heading in world_view.gd _fog_update). The sky's shader has no fog: the sky dome writes no depth, and
// pixels at the far plane (depth 0, reverse z) are left alone.
// The blend: dst is linear (the viewer's shaders convert their gamma-space result with to_linear); the pass outputs
// colour c and alpha f so that the hardware's linear mix gives to_linear(mix(to_gamma(dst), fog, f)) for opaque pixels.
shader_type spatial;
render_mode unshaded, blend_mix, depth_draw_never, depth_test_disabled, cull_disabled, fog_disabled, shadows_disabled;

uniform sampler2D depth_tex : hint_depth_texture, filter_nearest;
uniform sampler2D screen_tex : hint_screen_texture, filter_nearest;
uniform vec3 fog_color = vec3(0.5);  // gamma space
uniform float near_dist = 0.0;
uniform float near_density = 0.0;
uniform float far_dist = 1000.0;
uniform float far_density = 0.0;

vec3 to_linear(vec3 c) {
	c = clamp(c, 0.0, 1.0);
	return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(0.04045, c));
}

vec3 to_gamma(vec3 c) {
	c = clamp(c, 0.0, 1.0);
	return mix(c * 12.92, 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055, step(0.0031308, c));
}

void vertex() {
	POSITION = vec4(VERTEX.xy * 2.0, 1.0, 1.0);
}

void fragment() {
	float depth = texture(depth_tex, SCREEN_UV).x;
	if (depth <= 0.0) {
		discard;
	}
	vec4 v = INV_PROJECTION_MATRIX * vec4(SCREEN_UV * 2.0 - 1.0, depth, 1.0);
	float dist = length(v.xyz / v.w);
	float k = (far_density - near_density) / max(far_dist - near_dist, 1e-3);
	float f = clamp(dist * k + (near_density - near_dist * k), 0.0, far_density);
	if (f <= 0.001) {
		discard;
	}
	vec3 dst = texture(screen_tex, SCREEN_UV).rgb;
	vec3 want = to_linear(mix(to_gamma(dst), fog_color, f));
	ALBEDO = (want - (1.0 - f) * dst) / f;
	ALPHA = f;
}
