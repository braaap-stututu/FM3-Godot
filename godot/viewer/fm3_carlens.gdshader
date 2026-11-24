// FM3 lamp lenses (detail_glass_red / _amber / _clear, red_glass): a colour filter over the lamp behind it. Drawn as the
// window glass (fm3_carglass.gdshader, an unlit colour at GlassColor.a + Fresnel) the red lens covered the lamp in flat
// bright red and looked lit on a car that was not braking; in the game the lamp's reflectors show through a darker red.
// Here: what is behind x the lens colour (multiply blend), the lens's opacity from its ShaderSettings deciding how far
// towards that colour. A lit lamp (world_view.gd _update_lights: the lamp's emission) still shines through in red.
shader_type spatial;
render_mode blend_mul, cull_disabled, depth_draw_never, unshaded, ambient_light_disabled, specular_disabled;

uniform vec4 albedo_color = vec4(1.0);  // (unused: the game's GlassColor rules)
uniform vec4 glass_color = vec4(0.75, 0.0, 0.0, 0.0);  // GlassColor (ShaderSettings)
uniform float max_opacity = 0.7;  // GlassMaxOpacity (unused here)
uniform float lens_mix = 1.0;
// (the glass shader's other parameters, set on every glass material: accepted and unused)
uniform float fresnel_min = 0.0;
uniform float fresnel_max = 1.0;
uniform float fresnel_scale = 1.0;
uniform float fresnel_power = 1.5;
uniform float cube_scale = 1.0;
uniform float spec_amount = 0.0;
uniform float spec_power = 70.0;
uniform vec3 spec_color = vec3(1.0);
uniform vec3 sun_dir = vec3(0.0, 1.0, 0.0);
uniform float glow = 0.0;
uniform float env_scale = 0.2;
uniform float metallic = 0.0;

void fragment() {
	// the filter: the lens colour itself (by its opacity 0.7-0.9 towards it, the lamps behind came out pink: the game's
	// lenses are a saturated darker red); lens_mix < 1 lightens it
	vec3 filt = mix(vec3(1.0), glass_color.rgb, lens_mix);
	ALBEDO = filt;
}
