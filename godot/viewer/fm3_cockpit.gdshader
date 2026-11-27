// The cockpit's plain surfaces (world_view.gd _cockpit_material): FM3 lights its cabin by a hemisphere of its own,
// TrackSettings SHCockpitTop (0.3 grey) fading to SHCockpitBottom (0) by the surface's facing, no directional light
// (SHCockpitDir 0) and little specular (CockpitSpecularAmount 0.09). Godot's sun and sky reflection gave a blue-tinted,
// sun-lit dash; a top-only directional light left every vertical face black. Fitted on the live CR-X in-car view (the
// game's SH numbers do not carry over as they are: the baked brightness in COLOR is most of the cabin's light):
// top 1, bottom 0.05 -> dash top 19 (game 19), roof liner 17 (16), the vertical faces too dark (A-pillar 3 vs 13);
// in-car 17.5 / 17.9 / 17.3 (sun + sky reflection: 17.4 / 17.8 / 18.6, the dash blue-tinted; flat 23.5; a smoothstep
// hemisphere 17.9 / 18.3 / 17.7).
shader_type spatial;
render_mode unshaded, cull_disabled;

uniform sampler2D albedo_tex : source_color, filter_linear_mipmap_anisotropic, repeat_enable, hint_default_white;
uniform vec4 albedo_color = vec4(1.0);  // (gamma space, as the glTF material's colour)
uniform bool use_vcol = false;  // the baked brightness (COLOR_0, already linear)
uniform vec3 sky_top = vec3(1.0);
uniform vec3 sky_bottom = vec3(0.05);
uniform float gain = 1.0;
uniform float alpha_cut = -1.0;

vec3 to_linear(vec3 c) {
	c = max(c, vec3(0.0));
	return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(0.04045, c));
}

uniform int cull = 0;  // (0 both faces, as the cockpit; 1 front faces only: the driver, world_view.gd _attach_driver; 2 back only)

void fragment() {
	if ((cull == 1 && !FRONT_FACING) || (cull == 2 && FRONT_FACING)) {
		discard;  // (the driver's arms: the in-car camera sits inside its shoulders)
	}
	vec4 t = texture(albedo_tex, UV);
	if (alpha_cut >= 0.0 && t.a * albedo_color.a < alpha_cut) {
		discard;
	}
	vec3 a = t.rgb * to_linear(albedo_color.rgb);
	if (use_vcol) {
		a *= COLOR.rgb;
	}
	float up = (INV_VIEW_MATRIX * vec4(NORMAL, 0.0)).y * 0.5 + 0.5;
	ALBEDO = a * mix(sky_bottom, sky_top, up) * gain;
}
