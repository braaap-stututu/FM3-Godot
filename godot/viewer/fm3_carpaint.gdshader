// FM3 car paint (2026-11-23; the game's paint pixel shader e41e183a423e6f1b, tools/fir_disasm.py): the paint colour
// (livery over the c118 colour, composited by fir_world.py into the albedo) lit by an ambient term and the sun, plus a
// Fresnel reflection of the environment and a sun highlight. The game reflects a cube it renders each frame around the
// cars (t6/t7); this uses the layout's static car cube (staticcarcubemap.xpr, as the window glass does). Fitted to the
// game's screenshot of the grid per car (tools/car_regions.py): the game's paint has darker shade and much brighter
// reflections than a plain clear coat.
shader_type spatial;
render_mode cull_disabled, ambient_light_disabled, specular_disabled;

uniform sampler2D albedo_tex : filter_linear_mipmap_anisotropic, repeat_enable, hint_default_white;
uniform vec4 albedo_color = vec4(1.0);
uniform samplerCube env_cube : filter_linear_mipmap;
uniform bool has_env = false;
// The static cube (the other cars: only the player's car reflects the live cube) blurred: at its sharpest level the
// track's stripes and stands shimmered as streaks along curved doors, where the game's reflections are soft.
uniform float env_lod = 2.5;
uniform vec3 env_fallback = vec3(0.45, 0.52, 0.56);
uniform vec3 env_flip = vec3(-1.0, 1.0, 1.0);  // (this scene's x is the game's mirrored)
// Fitted on the grid (tools/car_regions.py, 7 cars). Refitted 2026-11-23 for the LOD 0 bodies with the file's own
// normals (they face the sky more than the old rebuilt ones): sky 0.5 -> 0.24; CR-X mean colour then 135 vs the game's
// 136. The highlights are still weaker than the game's (CR-X 90th percentile 150 vs 187).
uniform vec3 ambient = vec3(0.302, 0.315, 0.340);  // gamma-space sky light on surfaces facing up (where the sun does not reach)
uniform vec3 ambient_ground = vec3(0.05, 0.05, 0.05);  // ... and on surfaces facing down (bumpers, sills: the road's shade)
uniform vec3 sun = vec3(1.35, 1.323, 1.269);
uniform float sun_pow = 2.0;  // the sun's diffuse falloff (pow(n.l, sun_pow))
// (2026-11-24: the game's paint lighting by surface direction, from debug normal / albedo renders of the captured grid,
// rises much faster with n.sun than a linear term: ~2.4x albedo facing the sun vs ours 1.1, and is darker at moderate
// facing. n.l^2 with sun x1.5, ambient x1.4: per-car paint 16.0 -> 14.9, Mazda p10/50/90 19/37/163 (game 19/43/172),
// Eclipse 7/17/63 (7/17/72).)
uniform float shadow_strength = 0.85;
// The game's paint constants (all cars on the grid): reflection c224 x c217/c218 = 1.5 x 0.3/0.5, Fresnel power c216 = 4,
// the sun's highlight power c189 = 75 and strength c180 = 1.4. (The colour's c119.x scale is in the albedo: fir_world.)
uniform float refl_gain = 1.0;  // environment reflection at grazing angles (x Fresnel), solid paint
uniform float refl_metal = 1.0;  // ... metallic paint (the game's c191.x > 0: the Mazda, the Eclipse; glTF metallic 1;
                                 // 2.5 fitted the grid's highlights but striped the Eclipse's doors with the low-res cube)
uniform float metallic = 0.0;
uniform float refl_f0 = 0.02;  // ... and looking straight at the paint (the game's black paint stays black head-on)
uniform float spec_gain = 1.4;  // the sun's highlight
uniform float spec_power = 75.0;
// Metallic paint's second, broad sun highlight (Metallic.xml SpecularAmount2 4 / SpecularPower2 4 = the capture's c191.x /
// c216.x; Normal.xml has none): the game's amount saturated our cars (p90 255), so scaled: 0.1 fitted on the captured
// grid (summary 16.8, with the metallic reflection boost refl_metal 1.6 -> 1.0; before 16.9). The game's reflection is
// the same for both finishes.
uniform float spec2_gain = 0.1;
uniform float spec2_power = 4.0;
uniform float fresnel_power = 4.0;
uniform bool game_fresnel = true;
uniform float game_fresnel_power = 4.0;
uniform float fresnel_min = 0.0;
uniform float fresnel_max = 1.0;
uniform float cube_scale = 1.5;
uniform float env_scale = 1.5;

#include "res://viewer/fm3_livecube.gdshaderinc"

vec3 to_linear(vec3 c) {
	c = max(c, vec3(0.0));
	return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(0.04045, c));
}

// The sum in gamma space (2026-11-24): the game adds paint x light, the reflection and the highlight in gamma space and
// the screen shows that; linearised one by one and added in linear light, a bright surface came out at ~146 where the
// game's is ~204 (a 0.5 lit paint + a 0.3 reflection), the cause of the grid cars' missing bright tenth. With
// gamma_sum the albedo goes to light() as a varying (ALBEDO stays white) and the whole sum is linearised once.
uniform bool gamma_sum = true;
// A livery from the running game (tools/live_liveries.py: the paint draw's t0): laid over the paint colour by its alpha,
// as the game's shader does (its custom paint is in there; albedo_color = the database colour x PaintScale).
uniform bool livery = false;
// TrackSettings SHLighting SHEnvMapTop / SHEnvMapBottom: the reflection weighted by how far the surface faces up
uniform float env_top = 1.0;
uniform float env_bottom = 0.0;
uniform float env_up_power = 3.0;
// Fitted with gamma_sum on the captured grid (2026-11-24): reflection 1.5 x Fresnel pow(1 - cos, 4) (no floor) x up^3,
// diffuse x 0.9: per-car paint 16.8 -> 16.0, brightest tenth Mazda 101 -> 131 (game 172), Eclipse 43 -> 56 (72).
// Matching the game's bright end fully (up^4, env 1.5, pow 2: Mazda p90 155, Eclipse 75) put highlights where the game
// has none (20.5): the game's sun-facing flanks are brighter and its top surfaces softer than ours.
varying vec3 paint_gamma;

void fragment() {
	vec4 t = texture(albedo_tex, UV);
	paint_gamma = livery ? mix(albedo_color.rgb, t.rgb, t.a) : t.rgb * albedo_color.rgb;
	// (the texture is read raw: gamma-space values, as the game's shader works with them)
	// (library cars: their badge layer is composited over white by tools/fm3_car_library.py, so the same product)
	ALBEDO = gamma_sum ? vec3(1.0) : to_linear(paint_gamma);
}

void light() {
	if (LIGHT_IS_DIRECTIONAL) {
		float sh = 1.0 - shadow_strength + shadow_strength * ATTENUATION;
		float ndl = max(dot(NORMAL, LIGHT), 0.0);
		float up = (INV_VIEW_MATRIX * vec4(NORMAL, 0.0)).y * 0.5 + 0.5;
		vec3 diff = mix(ambient_ground, ambient, up) + sun * pow(ndl, sun_pow) * sh;
		vec3 r = (INV_VIEW_MATRIX * vec4(reflect(-VIEW, NORMAL), 0.0)).xyz;
		vec3 env = has_live ? live_cube(r) : (has_env ? textureLod(env_cube, r * env_flip, env_lod).rgb : env_fallback);
		float cosv = clamp(dot(NORMAL, VIEW), 0.0, 1.0);
		// the game's Fresnel (ShaderSettings body: FresnelMin 0.15, Max 1, Power 1.5, CubeScale 1.5), the reflected
		// brightness at the windows' measured env_scale (the same, darker, game cube): replaces the fitted f0 0.02 /
		// power 4, under which the grid's paint lacked its bright top tenth (CR-X p90 138 where the game has 189)
		float fres = game_fresnel ? clamp(pow(1.0 - cosv, game_fresnel_power), fresnel_min, fresnel_max) * cube_scale * env_scale
			: refl_f0 + (1.0 - refl_f0) * pow(1.0 - cosv, fresnel_power);
		float rl = max(dot(reflect(-LIGHT, NORMAL), VIEW), 0.0);
		float spec = pow(rl, spec_power) * sh + pow(rl, spec2_power) * sh * spec2_gain / spec_gain * metallic;
		vec3 add = env * fres * mix(env_bottom, env_top, pow(up, env_up_power)) * mix(refl_gain, refl_metal, metallic) * mix(1.0, sh, 0.3) + sun * spec * spec_gain;
		if (gamma_sum) {
			DIFFUSE_LIGHT += to_linear(paint_gamma * diff + add);
		} else {
			DIFFUSE_LIGHT += to_linear(diff);
			SPECULAR_LIGHT += to_linear(add);
		}
	}
}
