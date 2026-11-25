// FM3 lamp reflectors (2026-11-25, world_view.gd: next_pass of the lamp materials reflector_lights /
// textured_reflector_lights): the game's reflectors are mirror-like (Media\Cars\ShaderSettings\Normal.xml <reflector>:
// CubeScale 1.5, Fresnel min 0.15 / power 1.5, SpecularAmount 4 at power 128; <textured_reflector> CubeScale 1, spec 10
// at 50): behind a clear tail-light lens (the RSX: detail_glass_red, GlassColor alpha 0 = 15% opaque head-on) they show
// the environment, which is what makes the game's lamps bright and pinkish. Drawn as a plain lit textured material
// here they were dark (Sebring RSX tails 21/5/4 vs the game's 111/62/60). This pass adds the reflection over the lit
// texture: the static car cube x the track's cube gain x CubeScale x Fresnel, plus the sun's highlight.
shader_type spatial;
render_mode blend_add, cull_disabled, depth_draw_never, depth_test_default, unshaded, ambient_light_disabled, specular_disabled;

uniform samplerCube env_cube : filter_linear_mipmap;
uniform bool has_env = false;
uniform vec3 env_fallback = vec3(0.45, 0.52, 0.56);
uniform vec3 env_flip = vec3(-1.0, 1.0, 1.0);
uniform float static_cube_gain = 1.0;
uniform float cube_scale = 1.5;
uniform float fresnel_min = 0.15;
uniform float fresnel_max = 1.0;
uniform float fresnel_scale = 1.0;
uniform float fresnel_power = 1.5;
uniform float spec_amount = 4.0;
uniform float spec_power = 128.0;
uniform vec3 sun_dir = vec3(0.0, 1.0, 0.0);
uniform float refl = 1.0;  // fitted overall scale (FM3_REFLECTOR=<refl>)
// the sun highlight's weight: 0 (at 0.25 it left hard white glints along the CR-X's and Eclipse's lamp edges that the
// game does not show; 2026-11-25)
uniform float spec_gain = 0.0;
uniform sampler2D albedo_tex : filter_linear_mipmap;  // (read raw: gamma values, as the reflection is summed here)
uniform bool has_tex = false;
uniform bool tint_by_tex = false;  // the reflection coloured by the lamp texture (a tinted reflector)
uniform float tint_amount = 1.0;  // how far (FM3_REFLECTOR_TINT=<amount>)

void fragment() {
	vec3 n = NORMAL;
	if (!FRONT_FACING) {
		n = -n;
	}
	vec3 r = (INV_VIEW_MATRIX * vec4(reflect(-VIEW, n), 0.0)).xyz;
	vec3 env = (has_env ? texture(env_cube, r * env_flip).rgb * static_cube_gain : env_fallback) * cube_scale;
	float cosv = clamp(abs(dot(n, VIEW)), 0.0, 1.0);
	float f = clamp(fresnel_scale * pow(1.0 - cosv, fresnel_power), fresnel_min, fresnel_max);
	vec3 l = normalize((VIEW_MATRIX * vec4(sun_dir, 0.0)).xyz);
	float spec = pow(max(dot(reflect(-l, n), VIEW), 0.0), spec_power) * spec_amount;
	vec3 c = env * f + vec3(spec) * spec_gain;
	if (tint_by_tex && has_tex) {
		c *= mix(vec3(1.0), texture(albedo_tex, UV).rgb, tint_amount);
	}
	// (the game adds in gamma space: approximated by adding the linearised reflection)
	c = max(c * refl, vec3(0.0));
	ALBEDO = mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(0.04045, c));
}
