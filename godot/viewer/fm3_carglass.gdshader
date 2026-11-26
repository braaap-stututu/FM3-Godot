// FM3 car window glass, the game's own formula and values (2026-11-23, PLAN-CARS phase 3; replaces the first, fitted
// version). The 70 window draws of the grid capture all run pixel shader b117fbafcc1fa980 (tools/fir_disasm.py) with the
// same constants, named by its constant table in shaders_v11.fxobj (tools/fm3_fxobj.py):
//   fresnel  f = clamp(FresnelScale c191 * (1 - |N.V|)^FresnelPower c216, FresnelMin c189, FresnelMax c190)
//              x reflectionScaler c192
//   alpha    min(f + GlassColor.a c219.w, GlassMaxOpacity c218)  (x alphaDirtAmount c197)
//   colour   lerp(GlassColor.rgb, reflection, f);  reflection = the environment cube x CubeScale c217, damped towards
//            the track lightmap by StaticEnvLightmapDampner c180 (not reproduced: no track lightmap on the car here)
//   no sun highlight: SpecularAmount c116 = 0 on every window
// Captured values: GlassColor (0, 0.07, 0.06, 0.1), GlassMaxOpacity 1, Fresnel min 0.4 / max 1 / scale 1 / power 1.5,
// CubeScale 1, reflectionScaler 1. So a window is half see-through looking straight at it (alpha 0.5) and opaque at
// grazing angles, dark green-black with 40-100 % of the reflection.
shader_type spatial;
render_mode blend_mix, cull_disabled, depth_draw_opaque, ambient_light_disabled, specular_disabled, unshaded;

uniform vec4 albedo_color = vec4(1.0);  // (the glTF material's colour: unused, the game's GlassColor rules)
uniform samplerCube env_cube : filter_linear_mipmap;
uniform bool has_env = false;
uniform vec3 env_fallback = vec3(0.45, 0.52, 0.56);
uniform vec3 env_flip = vec3(-1.0, 1.0, 1.0);
uniform vec4 glass_color = vec4(0.0, 0.07, 0.06, 0.1);  // GlassColor c219
uniform float max_opacity = 1.0;  // GlassMaxOpacity c218
uniform float fresnel_min = 0.4;  // c189
uniform float fresnel_max = 1.0;  // c190
uniform float fresnel_scale = 1.0;  // c191
uniform float fresnel_power = 1.5;  // c216
uniform float cube_scale = 1.0;  // c217
uniform float reflection_scaler = 1.0;  // c192
// The sun's highlight (SpecularAmount / Power / Color: 0 on windows, 1-4 on lamp lenses), sun_dir = towards the sun.
// Every glass's values come from the game's Media\Cars\ShaderSettings\Normal.xml + the car's shadersettings.xml
// (fm3_track_export.py writes them per mesh, <gltf>_carmaterials.json): the defaults here are the window's.
uniform float spec_amount = 0.0;
uniform float spec_power = 70.0;
uniform vec3 spec_color = vec3(1.0);
uniform vec3 sun_dir = vec3(0.0, 1.0, 0.0);
// A lit lamp behind this lens (the brake lights, world_view.gd _update_lights): the game's lamp is HDR (BrakeColor 7)
// and shines through its lens saturated; here the lens itself glows in its own colour.
uniform float glow = 0.0;
// The one number not from the game: the brightness of what is reflected. The game's cube (and its damping towards the
// track lightmap, c180 / c119) is far darker than the viewer's live cube of its surroundings; with env_scale 1 the
// CR-X's rear glass came out at 178 where the game has 15. Measured on the grid (tools/car_regions.py). 2026-11-24: with
// gamma_blend and the player's own dim reflection (below), the AI windows fit at 0.5 (glass summary 15.6 -> 13.8).
// 2026-11-25: with the display table in the final pass (fm3_exposure.gdshader) the game's own formula fits: the static
// cube x its fetch constant's exponent adjust (static_cube_gain: x1 CrownJewel, x2 the other tracks; envcube.json) x
// CubeScale, no fitted scale (grid glass per car 15.7 at 0.25 -> 13.8 at 1).
uniform float env_scale = 1.0;
uniform float static_cube_gain = 1.0;
// The player's glass (has_live): the game's per-frame cube is rendered from inside the player's car and mostly sees its
// own dark cabin, so its windows reflect little (the CR-X's rear glass 9/15/20 in the game) where the AI cars' windows,
// on the static cube, show the sky (the Eclipse 40/48/57). (Until 2026-11-24 one env_scale 0.2 for every window, fitted
// on the CR-X, darkened the AI cars' glass too.)
// 2026-11-25 evening (since the exposure pass): 0.1 -> 0.5 -> 1.0 (FM3_PLAYER_ENV; the user: the dark band under the RSX's
// rear window is what the glass rests on, hidden in the game by the window's reflection). At 1.0 with the library cabin
// at 0.5: Sebring RSX rear window 10.4 -> 6.6, the band under it 7.9 -> 7.4, roof 51.0 -> 35.2, the car 18.5 -> 17.6;
// CrownJewel CR-X rear window 11.6 -> 11.0, frame 18.9 / 18.5 / 17.8 -> 18.7 / 18.1 / 17.1. (1.0 with the cabin at 1.0:
// RSX window 15.1, the seats show through.)
// The player's glass takes the track's cube gain too (x2 off CrownJewel), as every other glass: RoadAtlanta RSX rear
// window 20.6 -> 9.3, the car 15.5 -> 13.6, whole frame 23.0 -> 21.4 (2026-11-25, 23:00).
uniform float player_env = 1.0;
// The player's windows on the live cube, as the game's (2026-11-25, 23:20; FM3_LIVE_GLASS=0: the static cube x
// player_env x the track's gain above, which fitted RoadAtlanta at 2 and Sebring at 1: the static cubes differ per
// track) x live_glass_scale (FM3_LIVE_GLASS_SCALE; 0.5 worse everywhere). Rear windows against the game: Sebring RSX
// 5.4 (14 / 21 / 27, game 12 / 20 / 26), RoadAtlanta RSX 3.5 (29 / 31 / 28, game 30 / 29 / 25), CrownJewel CR-X
// 11.0 -> 5.7; the RSX's roof (sunroof) 17.6.
uniform bool live_glass = true;
uniform float live_glass_scale = 1.0;
uniform bool player_glass = false;
// A lamp lens drawn with this formula (world_view.gd FM3_LENS=game, 2026-11-25): it faces outwards, so the player's
// own lenses reflect the surroundings like any car's (no player_env dimming).
uniform bool lens = false;
// A lens's tint of what is behind it (gamma_blend only): the scene behind x mix(1, GlassColor, lens_filter). The game's
// RSX tails are pink-red over bright reflectors (G / R 0.55) where the plain formula (15% red head-on) left them
// near white (G / R 0.8). FM3_LENS_FILTER=<k> (world_view.gd).
uniform float lens_filter = 0.0;
// A lens's own colour as lit (GlassColor x lens_light): the CR-X's nearly opaque red lens (GlassColor 0.6, alpha 0.7)
// came out at its full colour (119 / 48 / 36) where the game shows it lit at about a third (60 / 23 / 20 on the
// CrownJewel grid, the car's rear in shade). FM3_LENS_LIGHT=<k> (world_view.gd).
uniform float lens_light = 1.0;
// amber lenses (green > 0.25, blue < 0.2) lit by this instead when >= 0 (FM3_AMBER_LIGHT)
uniform float amber_light = -1.0;
// The sun highlight's weight (SpecularAmount x this; FM3_GLASS_SPEC=<w>): 0.25 from 2026-11-24, 0 since 2026-11-26:
// on the lamps' clear covers (<glass>, SpecularAmount 3.5 at 50; few, curved polygons) it drew saturated white dashes
// the game does not show (the CrownJewel Eclipse's right lamp 34.3 -> 24.7 at 0; 0.1 kept them; the CR-X 12.6 -> 13.0).
uniform float spec_weight = 0.0;
// The game blends its glass in gamma space (the framebuffer is gamma); Godot blends in linear light, which brightens a
// bright reflection over a dark cabin. gamma_blend reads the scene behind and mixes in gamma space.
uniform bool gamma_blend = true;
uniform sampler2D screen_tex : hint_screen_texture, filter_linear;
// (kept so FM3_CARGLASS overrides of the first version do not error; unused)
uniform float opacity = 0.0;  // added to the window's opacity (fitted)
uniform float body_level = 0.0;
uniform float refl_gain = 0.0;
uniform float refl_f0 = 0.0;
uniform float spec_gain = 0.0;
uniform float metallic = 0.0;

#include "res://viewer/fm3_livecube.gdshaderinc"

vec3 to_gamma(vec3 c) {
	c = max(c, vec3(0.0));
	return mix(c * 12.92, 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055, step(0.0031308, c));
}

vec3 to_linear(vec3 c) {
	c = max(c, vec3(0.0));
	return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(0.04045, c));
}

void fragment() {
	vec3 r = (INV_VIEW_MATRIX * vec4(reflect(-VIEW, NORMAL), 0.0)).xyz;
	vec3 env = (has_env ? texture(env_cube, r * env_flip).rgb : env_fallback) * cube_scale * ((has_live || player_glass) && !lens ? player_env : env_scale) * (has_env ? static_cube_gain : 1.0);
	if (has_live && live_glass && !lens) {
		// the player's windows reflect the per-frame cube rendered at the car, as the game's do (its t6)
		env = live_cube(r) * cube_scale * live_glass_scale;
	}
	float cosv = clamp(abs(dot(NORMAL, VIEW)), 0.0, 1.0);
	float f = clamp(fresnel_scale * pow(1.0 - cosv, fresnel_power), fresnel_min, fresnel_max) * reflection_scaler;
	float a = min(f + glass_color.a + opacity, max_opacity);
	vec3 l = normalize((VIEW_MATRIX * vec4(sun_dir, 0.0)).xyz);
	float spec = pow(max(dot(reflect(-l, NORMAL), VIEW), 0.0), spec_power) * spec_amount;
	// (a lens's highlight left hard white glints along the CR-X's lamp edges that the game does not show: off for lenses)
	if (lens) {
		spec = 0.0;
	}
	vec3 c = mix(glass_color.rgb * (lens ? ((amber_light >= 0.0 && glass_color.g > 0.25 && glass_color.b < 0.2) ? amber_light : lens_light) : 1.0), env, f) + spec_color * spec * spec_weight;
	vec3 lamp = glass_color.rgb / max(max(glass_color.r, glass_color.g), max(glass_color.b, 0.001));
	c = mix(c, lamp, clamp(glow, 0.0, 1.0));
	float al = clamp(max(a + spec * spec_weight, glow * 0.95), 0.0, 1.0);
	if (gamma_blend) {
		vec3 bg = to_gamma(texture(screen_tex, SCREEN_UV).rgb);
		if (lens) {
			bg *= mix(vec3(1.0), glass_color.rgb, lens_filter);
		}
		ALBEDO = to_linear(mix(bg, c, al));
		ALPHA = 1.0;
	} else {
		ALBEDO = to_linear(c);
		ALPHA = al;
	}
}
