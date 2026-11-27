// The cockpit's plain surfaces (world_view.gd _cockpit_material): FM3 lights its cabin by a hemisphere of its own,
// TrackSettings SHCockpitTop (0.3 grey) fading to SHCockpitBottom (0) by the surface's facing, no directional light
// (SHCockpitDir 0) and little specular (CockpitSpecularAmount 0.09). Godot's sun and sky reflection gave a blue-tinted,
// sun-lit dash; a top-only directional light left every vertical face black. Fitted on the live CR-X in-car view (the
// game's SH numbers do not carry over as they are: the baked brightness in COLOR is most of the cabin's light):
// top 1, bottom 0.05 -> dash top 19 (game 19), roof liner 17 (16), the vertical faces too dark (A-pillar 3 vs 13);
// in-car 17.5 / 17.9 / 17.3 (sun + sky reflection: 17.4 / 17.8 / 18.6, the dash blue-tinted; flat 23.5; a smoothstep
// hemisphere 17.9 / 18.3 / 17.7).
// The game's own cockpit light (2026-11-27; LIVE.md "The cockpit's light"; its vertex shader 6190a07aa58ac0a9 and pixel
// shader 3bb8846d34e89025 with their constants captured in the CR-X's in-car view): each vertex's baked SH transfer T
// (4 terms, fm3_carbin.sh_transfer) against two SH lights in car space: the cockpit hemisphere (TrackSettings
// SHCockpitTop / Bottom: 5.3174 x (top + bottom) / 2 on T0, -1.535 x (top - bottom) x v(up)) and the sun
// (1.18 x T0 - 2.04 x v(sun), x 1.5 x the track's SHDir colour), v(d) = T1 d.y - T2 d.z + T3 d.x, each clamped at 0;
// colour = the material's colour x (ambient + direct), in gamma space. The vertices carry T0 / T1 in UV2 (env_sh) and
// T2 / T3 in COLOR.rg (+ 0.5, alpha 0.5 = such a vertex; fm3_car_library.py); cars built before keep the old light.
// Opt-in (FM3_COCKPIT_PRT=1): the light is right, the materials' colours are not yet the game's (the CR-X roof liner and
// A-pillar are one untextured 0.24 grey draw in the game; ours: a bright headliner texture, a 0.015 'black').
// fm3_cockpit_prt.gdshader: the same, lit by Godot's sun for its shadow (2026-11-27 ~21:10): in the game the cabin's
// sun term goes through its shadow map (the headliner / dash pixel shader 1074f157fdbf9db8 samples it), so the roof
// stays dark while the dash under the windscreen is sunlit. That shader's sun term is saturate(n.l) through the shadow
// map, not the transfer's (every interior subset's transfer reads as lit from above, the downward headliner too): here
// the vertex transfer's ambient + SHDir x 1.5 x sun_k x n.l x the sun's ATTENUATION.
shader_type spatial;
render_mode cull_disabled, ambient_light_disabled, specular_disabled;

uniform sampler2D albedo_tex : source_color, filter_linear_mipmap_anisotropic, repeat_enable, hint_default_white;
uniform vec4 albedo_color = vec4(1.0);  // (gamma space, as the glTF material's colour)
uniform bool use_vcol = false;  // the baked brightness (COLOR_0, already linear)
uniform vec3 sky_top = vec3(1.0);
uniform vec3 sky_bottom = vec3(0.05);
uniform float gain = 1.0;
uniform float alpha_cut = -1.0;
uniform bool prt_on = false;
uniform vec3 sh_top = vec3(0.3);
uniform vec3 sh_bottom = vec3(0.0);
uniform vec3 sun_world = vec3(0.0, 1.0, 0.0);  // (towards the sun, world space)
uniform vec3 dir_color = vec3(0.78, 0.76, 0.73);  // (the track's SHDir)
uniform float dir_scale = 1.5;
uniform float prt_k = 1.0;  // (the material's colour against ours: tests)
uniform float sun_k = 1.0;  // (the n.l sun term's strength: tests)
// mode 2 (FM3_COCKPIT_PRT=2, ~22:40): the dash / headliner pixel shader 1074f157fdbf9db8 as decoded (LIVE.md "The
// cockpit's light"): colour = 2 tex (0.5 L + 0.5 max(SHDir h, 0.5)), L = the vertex SH light + 1.5 SHDir n.l vis,
// h = (0.5 n.l + 0.5)^2, vis = max(shadow, 0.25) (its specular left out); tex_k = the texture's scale in the game's
// fetch (fitted, unknown)
uniform int mode = 1;
uniform float tex_k = 0.25;
varying vec3 prt_light;
varying vec3 prt_sun;
varying vec3 alb_g;
varying float prt_use;

vec3 to_linear(vec3 c) {
	c = max(c, vec3(0.0));
	return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(0.04045, c));
}

vec3 to_gamma(vec3 c) {
	c = max(c, vec3(0.0));
	return mix(c * 12.92, 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055, step(0.0031308, c));
}

const float SH_DC = 5.3174;
const float SH_LIN = -1.535;

void vertex() {
	prt_use = 0.0;
	if (prt_on && COLOR.a < 0.75) {
		float t0 = (UV2.x + UV2.y) / SH_DC;
		float t1 = (UV2.x - UV2.y) / (2.0 * SH_LIN);
		float t2 = COLOR.r - 0.5;
		float t3 = COLOR.g - 0.5;
		mat3 inv = inverse(mat3(MODEL_MATRIX));
		vec3 up = normalize(inv * vec3(0.0, 1.0, 0.0));
		vec3 sn = normalize(inv * sun_world);
		float vu = t1 * up.y - t2 * up.z + t3 * up.x;
		float vs = t1 * sn.y - t2 * sn.z + t3 * sn.x;
		vec3 amb = max(0.5 * SH_DC * (sh_top + sh_bottom) * t0 + SH_LIN * (sh_top - sh_bottom) * vu, vec3(0.0));
		float dir = max(1.18 * t0 - 2.04 * vs, 0.0);
		prt_light = amb;
		prt_sun = dir_scale * dir_color * dir;
		prt_use = 1.0;
	}
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
	alb_g = to_gamma(a) * prt_k;
	if (prt_use < 0.5) {
		if (use_vcol) {
			a *= COLOR.a < 0.75 ? vec3(COLOR.b) : COLOR.rgb;
		}
		float up = (INV_VIEW_MATRIX * vec4(NORMAL, 0.0)).y * 0.5 + 0.5;
		alb_g = to_gamma(a * mix(sky_bottom, sky_top, up) * gain);  // (cars built before: the old light, unlit by the sun)
	}
	ALBEDO = vec3(1.0);
}

void light() {
	if (LIGHT_IS_DIRECTIONAL) {
		if (prt_use > 0.5 && mode == 2) {
			float nl = dot(NORMAL, LIGHT);
			float h = pow(0.5 * nl + 0.5, 2.0);
			float vis = max(ATTENUATION, 0.25);
			vec3 l1 = prt_light + dir_scale * dir_color * max(nl, 0.0) * vis;
			DIFFUSE_LIGHT += to_linear(2.0 * tex_k * alb_g * (0.5 * l1 + 0.5 * max(dir_color * h, vec3(0.5))));
		} else if (prt_use > 0.5) {
			float ndl = max(dot(NORMAL, LIGHT), 0.0);
			DIFFUSE_LIGHT += to_linear(alb_g * (prt_light + dir_scale * dir_color * sun_k * ndl * ATTENUATION));
		} else {
			DIFFUSE_LIGHT += to_linear(alb_g);
		}
	}
}
