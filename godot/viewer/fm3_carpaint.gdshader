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
// The player's live cube (has_live) against the static cube the paint was fitted on: brighter (open sky, no cars)
uniform float live_scale = 0.3;  // (fitted live: the CR-X 24.9 at 1.0, 14.0 at 0.5, 10.4 at 0.3; static cube 12.5)
uniform vec3 env_fallback = vec3(0.45, 0.52, 0.56);
uniform vec3 env_flip = vec3(-1.0, 1.0, 1.0);
uniform float env_yaw = 0.0;  // (tests: the static cube turned about the vertical, degrees; FM3_ENV_YAW)  // (this scene's x is the game's mirrored)
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
uniform float spec2_gain = 0.0;
// Metallic flakes (2026-11-24, after the usual three-layer car paint model: pigment, flakes embedded in it, clear coat):
// the flakes give a broad highlight around the sun in the pigment's own colour (flake_gain x pow(r.v, flake_power) x the
// paint colour), and metallic paint 'flops': darker towards grazing views (flop: the base colour x mix(1 - flop, 1,
// cos^flop_power)). Metallic only (glTF metallic 1 = the game's c191 > 0). Fitted on the grid's three metallic cars, offline:
// flake 1.2 / power 6 (the white second lobe spec2 off): Mazda 20.6 -> 17.8 (p10/50/90 20/38/173, game 19/43/172), Eclipse
// 13.1 -> 12.9 (p90 73 vs 72), C4 13.3 -> 12.5, all cars 14.8 -> 14.2. A flop (0.2-0.3) scored worse: left at 0.
uniform float flake_gain = 1.2;
uniform float flake_power = 6.0;
uniform float flop = 0.0;
uniform float flop_power = 1.0;
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
// The game's reflection term (2026-11-25, from ReGPU's translation of ps e41e183a423e6f1b and its vertex shader;
// LIVE.md "Car paint reflection"): refl = saturate(F x (1 - FresnelKill x lum(paint))) x env x CubeScale x 0.368 d
// x (1 - dampener x (1 - track lightmap)), F = clamp((1 - n.v)^FresnelPower, FresnelMin, FresnelMax) (1.5, 0.15, 1),
// added unshadowed to the lit paint. d = the vertex's baked sky visibility (SH transfer . the SHEnvMap hemisphere,
// top 1 / bottom 0.15 on every track), from the library's UV2 (fm3_carbin.env_sh): roof ~1.2, flanks ~0.8, sills ~0.35.
// 0.368 = 0.2125 x sqrt(3) as the shader computes it. Dampener 0.3 for the live cube (player), 0.5 for the static one;
// the sun shadow stands in for the track lightmap under the car. FM3_OLD_PAINT_REFL=1: the older fitted term.
uniform bool game_refl = true;
uniform float game_fresnel_pow = 1.5;
uniform float game_fresnel_min = 0.15;
uniform float fresnel_kill = 0.2;
uniform float env_sh_top = 1.0;
uniform float env_sh_bottom = 0.15;
uniform float lm_dampen_live = 0.3;
uniform float lm_dampen_static = 0.5;
uniform float game_env_gain = 1.0;  // our cube against the game's (1 = the same brightness)
uniform float game_live_scale = 1.0;  // (the live cube in this term: live_scale belongs to the older fit)
// The static cube (staticcarcubemap.xpr, the paint's t7) is stored at half brightness and read x2: its fetch constant's
// exponent adjust is 1 (dword 3 bits 13-18; the live cube's is 3, x8, stored at 1/8). Motegi: our decode of the file has
// sky ~0.3 / road ~0.16, half the game's live cube (0.6 / 0.34). 2026-11-25.
uniform float static_cube_gain = 2.0;
varying vec2 env_ab;
// The game's car ambient (decoded 2026-11-26 from the paint vs a102319a5aef757b / ps e41e183a423e6f1b): the vertex
// shader's o[5].xyz = transfer SH . shHemisphericalLightR/G/B (c38-40), the SH of TrackSettings SHTop / SHBottom per
// channel with the same hemisphere projection as shCubeMapDampnerLight, so per vertex SHTop x a + SHBottom x b with the
// (a, b) of fm3_carbin.env_sh (UV2); the pixel shader adds paint x o[5].xyz unshadowed, in gamma space. game_amb
// replaces the fitted mix(ambient_ground, ambient, up) on meshes with UV2 (world_view.gd FM3_GAME_AMB=0: off).
uniform bool game_amb = false;
uniform vec3 sh_top = vec3(0.33, 0.34, 0.36);
uniform vec3 sh_bottom = vec3(0.0);
uniform float game_amb_k = 1.0;
// ... and its sun: the vertex shader's o[2].w = transfer SH . shDirectionalLightI (c36), measured against the game on
// the CrownJewel grid (its o[2].w output by a live ps edit, per pixel against our n.l: 0.375 + 0.541 n.l, rms 0.09: the
// SH-projected cosine); the pixel shader: paint x SHDir x o2w x smoothstep((o2w SHDir.r - (T - W)) / 2W) (ShaderSettings
// body SHTransition 0.5, Width 0.3), times the shadow max(shadow map, MinShadowValue 0.25) (and the track lightmap's
// smoothstep, ~1 on the road). Replaces the fitted sun x pow(n.l, 2) (world_view.gd FM3_GAME_SUN=0: off).
uniform bool game_sun = false;
uniform vec3 sh_dir = vec3(0.78, 0.76, 0.73);
uniform vec2 sun_sh = vec2(0.375, 0.541);
uniform float sh_transition = 0.5;
uniform float sh_transition_width = 0.3;
uniform float min_shadow = 0.25;
uniform int debug_out = 0;

// Crash damage (2026-11-27): the vertex's damage amount (CUSTOM0.r, set by world_view.gd _damage_step from the car's
// lattice) blends the car's damage texture in as the game's paint shader e41e183a423e6f1b does: colour x (1 - D.a x a)
// + D.rgb x a (gamma values), and the highlight / reflection x (1 - a).
uniform sampler2D damage_tex : filter_linear_mipmap_anisotropic, repeat_enable, hint_default_transparent;
uniform bool has_damage = false;
uniform float force_amt = -1.0;  // (tests: every vertex at this amount, FM3_SCUFF_TEST=<a>)
varying float dmg_amt;
varying float dmg_light;  // (the same for light(): varyings reach it from fragment())

void vertex() {
	env_ab = UV2;
	dmg_amt = force_amt >= 0.0 ? force_amt : (has_damage ? clamp(CUSTOM0.r, 0.0, 1.0) : 0.0);
}

uniform bool cull_back = false;
// The paint's added light (reflection, highlight; gamma) capped at 1 before it goes linear (2026-11-26, FM3_HDR_CLAMP=<k>):
// a gamma 3 highlight became 3^2.2 = 11 in linear light and, averaged by MSAA, a white speck on panel edges and the cabin's
// headrests where the game's stay grey. CrownJewel grid: whole frame 15.42 -> 15.07, the cars' area 13.66 -> 13.61.
uniform float hdr_clamp = 1.0;  // (tests: FM3_CULL_BACK=1, back faces discarded as the game culls them)

vec3 yaw_dir(vec3 d) {
	float a = radians(env_yaw);
	return vec3(cos(a) * d.x + sin(a) * d.z, d.y, -sin(a) * d.x + cos(a) * d.z);
}

void fragment() {
	if (cull_back && !FRONT_FACING) {
		discard;
	}
	vec4 t = texture(albedo_tex, UV);
	paint_gamma = livery ? mix(albedo_color.rgb, t.rgb, t.a) : t.rgb * albedo_color.rgb;
	dmg_light = dmg_amt;
	if (dmg_amt > 0.0) {
		vec4 dt = texture(damage_tex, UV);
		paint_gamma = paint_gamma * (1.0 - dt.a * dmg_amt) + dt.rgb * dmg_amt;
	}
	// (the texture is read raw: gamma-space values, as the game's shader works with them)
	// (library cars: their badge layer is composited over white by tools/fm3_car_library.py, so the same product)
	ALBEDO = gamma_sum ? vec3(1.0) : to_linear(paint_gamma);
}

void light() {
	if (LIGHT_IS_DIRECTIONAL) {
		float sh = 1.0 - shadow_strength + shadow_strength * ATTENUATION;
		float ndl = max(dot(NORMAL, LIGHT), 0.0);
		float up = (INV_VIEW_MATRIX * vec4(NORMAL, 0.0)).y * 0.5 + 0.5;
		bool has_ab = !(env_ab.x == 0.0 && env_ab.y == 0.0);
		vec3 amb = (game_amb && has_ab) ? max(sh_top * env_ab.x + sh_bottom * env_ab.y, vec3(0.0)) * game_amb_k : mix(ambient_ground, ambient, up);
		vec3 diff = amb + sun * pow(ndl, sun_pow) * sh;
		if (game_sun) {
			float o2w = max(sun_sh.x + sun_sh.y * dot(NORMAL, LIGHT), 0.0);
			float x = clamp((o2w * sh_dir.r - (sh_transition - sh_transition_width)) / (2.0 * sh_transition_width), 0.0, 1.0);
			sh = max(ATTENUATION, min_shadow);
			diff = amb + sh_dir * o2w * x * x * (3.0 - 2.0 * x) * sh;
		}
		vec3 r = (INV_VIEW_MATRIX * vec4(reflect(-VIEW, NORMAL), 0.0)).xyz;
		vec3 env = has_live ? live_cube(r) * live_scale : (has_env ? textureLod(env_cube, yaw_dir(r) * env_flip, env_lod).rgb : env_fallback);
		float cosv = clamp(dot(NORMAL, VIEW), 0.0, 1.0);
		// the game's Fresnel (ShaderSettings body: FresnelMin 0.15, Max 1, Power 1.5, CubeScale 1.5), the reflected
		// brightness at the windows' measured env_scale (the same, darker, game cube): replaces the fitted f0 0.02 /
		// power 4, under which the grid's paint lacked its bright top tenth (CR-X p90 138 where the game has 189)
		float fres = game_fresnel ? clamp(pow(1.0 - cosv, game_fresnel_power), fresnel_min, fresnel_max) * cube_scale * env_scale
			: refl_f0 + (1.0 - refl_f0) * pow(1.0 - cosv, fresnel_power);
		float rl = max(dot(reflect(-LIGHT, NORMAL), VIEW), 0.0);
		float spec = pow(rl, spec_power) * sh + pow(rl, spec2_power) * sh * spec2_gain / spec_gain * metallic;
		vec3 pg = paint_gamma * mix(1.0, mix(1.0 - flop, 1.0, pow(cosv, flop_power)), metallic);
		vec3 flake = pg * sun * pow(rl, flake_power) * sh * flake_gain * metallic;
		vec3 dbg = vec3(0.0);
		vec3 add = flake + env * fres * mix(env_bottom, env_top, pow(up, env_up_power)) * mix(refl_gain, refl_metal, metallic) * mix(1.0, sh, 0.3) + sun * spec * spec_gain;
		if (game_refl) {
			// (no UV2 = a mesh without the baked weight: the CR-X body's median d by facing, 0.82 + 0.40 n.y)
			float d = (env_ab.x == 0.0 && env_ab.y == 0.0) ? 0.82 + 0.40 * (up * 2.0 - 1.0) : env_sh_top * env_ab.x + env_sh_bottom * env_ab.y;
			float fg = clamp(pow(max(1.0 - cosv, 0.0), game_fresnel_pow), game_fresnel_min, 1.0);
			fg = clamp(fg * (1.0 - fresnel_kill * dot(paint_gamma, vec3(0.2125, 0.7154, 0.0721))), 0.0, 1.0);
			float damp = has_live ? lm_dampen_live : lm_dampen_static;
			vec3 envg = has_live ? live_cube(r) * game_live_scale : env * (has_env ? static_cube_gain : 1.0);
			vec3 refl = envg * fg * cube_scale * 0.368 * max(d, 0.0) * (1.0 - damp * (1.0 - sh)) * game_env_gain * mix(refl_gain, refl_metal, metallic);
			add = flake + refl + sun * spec * spec_gain;
			// (debug, FM3_PAINT_DEBUG=n: one term alone, as the game's paint shows it with a live ps edit: 1 the
			// reflection r7.x x r4, 2 its angle factor r7.x, 3 its environment part r4)
			if (debug_out == 1) { dbg = refl; }
			if (debug_out == 2) { dbg = vec3(fg); }
			if (debug_out == 3) { dbg = refl / max(fg, 1e-4); }
			if (debug_out == 13) { dbg = amb; }  // (the ambient: the game's o[5].xyz)
			if (debug_out == 14) { dbg = vec3(ndl * 0.5); }  // (n.l, halved: against the game's o[2].w x 0.5)
			if (debug_out == 15) { dbg = vec3(0.25 + 0.25 * dot(NORMAL, LIGHT)); }  // (signed n.l mapped to 0..0.5)
			if (debug_out == 16) { dbg = vec3(env_ab * 0.5, 0.0); }  // (the baked sky pair a, b, halved)
			if (debug_out >= 10 && debug_out <= 12) { dbg = vec3(debug_out == 10 ? 0.1 : (debug_out == 11 ? 0.25 : 0.5)); }  // (the picture's response to known values)
		}
		add *= 1.0 - dmg_light;  // (the game: its highlight x (1 - amount))
		if (debug_out > 0) {
			DIFFUSE_LIGHT += to_linear(dbg);
		} else if (gamma_sum) {
			DIFFUSE_LIGHT += to_linear(pg * diff + add);
		} else {
			DIFFUSE_LIGHT += to_linear(diff);
			SPECULAR_LIGHT += to_linear(min(add, vec3(hdr_clamp)));
		}
	}
}
