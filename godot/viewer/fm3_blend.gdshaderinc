// FM3's multi-texture track shaders (tools/fm3_families.py), lit like fm3_baked.gdshader: the albedo times
// lerp(ambient c247, sun c248, lightmap) on raw (gamma-space) values, converted to linear for Godot's linear tone mapper.
//   mode 1 terrain blend: lerp(t0 * tint0 [* vertex rgb], t1 * lerp(1, tint1, vertex alpha), mask.r)
//        t0 at UV * scale0, t1 at CUSTOM0.xy * scale1 (glTF TEXCOORD_2), mask at CUSTOM0.zw (TEXCOORD_3)
//   mode 2 road: tex1 (the surface, at CUSTOM0.xy = UV0) * 0.34 * grain / grain_mean; grain t0 at UV (world x, z) * scale0
//   mode 3 paint: lerp(0.16 * grain, tint1, tex1.a)
//   mode 4 edge: lerp(dirt (tex2 at CUSTOM0.xy * scale2), road, tex3.r at CUSTOM0.zw); mode 5 mix: lerp(base, layer, mask.r); mode 6 curb: t0 * lerp(tint0, 1, t1.g)
//   mode 7 refl (windows): lerp(t0 lit, environment, t0.a * tint0.x * fresnel)
// (fm3_blend.gdshader: opaque; fm3_blend_alpha.gdshader: FM3_ALPHA, modes 13-14 blend by their opacity)
#include "res://viewer/fm3_fog.gdshaderinc"

uniform sampler2D albedo_tex : filter_linear_mipmap_anisotropic, repeat_enable, hint_default_white;
uniform sampler2D tex1 : filter_linear_mipmap_anisotropic, repeat_enable, hint_default_white;
uniform sampler2D tex2 : filter_linear_mipmap_anisotropic, repeat_enable, hint_default_white;
uniform sampler2D tex3 : filter_linear_mipmap, repeat_enable, hint_default_white;
uniform vec2 scale2 = vec2(1.0);
uniform sampler2D light_tex : filter_linear_mipmap, repeat_enable, hint_default_white;
uniform int mode = 1;
uniform bool has_lightmap = true;
uniform bool vclr = false;
uniform vec2 scale0 = vec2(1.0);
uniform vec2 scale1 = vec2(1.0);
uniform vec3 tint0 = vec3(1.0);
uniform vec3 tint1 = vec3(1.0);
uniform vec3 tint2 = vec3(0.0);  // mode 19: the paint colour added to the grain (P[2])
uniform float paint_chan = 0.0;
// A mip LOD bias on the base / grain texture (FM3_GRAIN_BIAS=<b>): -1 since 2026-11-26. Our box-filtered mips smoothed the
// asphalt's fine speckle away a few metres out; the game keeps it (its road detail, mean neighbour difference, 17.1 / 10.3
// near / ahead on the Sebring grid against our 14.2 / 7.5; with -1 16.9 / 10.0; CrownJewel's whole frame 6.6 -> 8.0, game
// 8.7). Per pixel: Sebring better at -2 (whole 23.9 -> 23.0), CrownJewel slightly worse (15.3 -> 15.7 at -1): added
// detail is never pixel-aligned with the game's.
uniform float grain_bias = -1.0;  // mode 19: the paint mask's channel (P[1].y: 0 = red, else green)
uniform float grain_mean = 0.5;
// mode 3 (track paint): the game's stripes are brighter than tint1 (CrownJewel pit lane white 232 vs 210, orange 231 vs
// 220); x1.1 fitted on the grid (stripe crop 24.0 -> 23.0; coverage below 1 or the asphalt grain through the paint
// scored worse)
uniform float paint_gain = 1.1;
uniform vec3 ambient = vec3(0.14, 0.14, 0.18);  // FM3 PS c247
uniform vec3 sun = vec3(1.58, 1.57, 1.5);  // FM3 PS c248
uniform float unlit_level = 0.6;  // without a lightmap
uniform float shadow_strength = 0.85;  // (linear: FM3 darkens shadowed ground to ~0.42 of its gamma-space value, 0.42^2.2 = 0.15)
uniform vec3 env_zenith = vec3(0.40, 0.58, 0.74);  // mode 7: the reflected environment (gamma space), a sky gradient
uniform vec3 env_horizon = vec3(0.45, 0.52, 0.56);  // (the track's surroundings: hills, trees, haze)
uniform vec3 env_ground = vec3(0.16, 0.16, 0.14);

// The road's sun specular (the shadowed variants of the road shaders, disassembled and run in tools/fir_vs.py against a
// live capture's constants): m = lerp(road_spec.x, road_spec.y, mask) + lerp(road_spec.w, road_spec.z, skid);
// spec = m * max(0, (lightmap.r - road_gloss.z) / (road_gloss.w - road_gloss.z)) * pow(N.H, lerp(road_gloss.x,
// road_gloss.y, m)), added in gamma space (unclamped: it saturates to white facing a low sun). mask = the base texture's
// alpha; skid = a per-shader channel (road_spec_mask below). road_spec = TrackSettings RoadSpecular, RoadSpecular2,
// RoadSkid, RoadSkid2; road_gloss = RoadGlossiness, RoadGlossiness2, RoadLightmapDarkPoint, RoadLightmapLightPoint.
uniform float road1_gain = 1.0;  // (0.85 until 2026-11-25: it stood in for the display table, fm3_exposure.gdshader)
uniform bool road_spec_on = false;
uniform vec4 road_spec = vec4(0.4, 0.7, -2.0, -0.5);
uniform vec4 road_gloss = vec4(10.0, 20.0, 0.5, 0.75);
uniform vec3 sun_dir = vec3(0.0, 1.0, 0.0);  // towards the sun, world space

varying vec4 uv23;  // glTF TEXCOORD_2 (xy) and TEXCOORD_3 (zw), Godot's CUSTOM0 (vertex stage only)

void vertex() {
	uv23 = CUSTOM0;
}

vec3 to_linear(vec3 c) {
	c = clamp(c, 0.0, 1.0);
	return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(0.04045, c));
}

void fragment() {
	vec3 a;
	float alpha_v = 1.0;
	float spec_mask = -1.0;  // >= 0: this mode has the road specular (the base texture's alpha)
	float spec_skid = 0.0;
	if (mode == 1) {
		vec3 t0 = texture(albedo_tex, UV * scale0, grain_bias).rgb * tint0;
		vec3 t1 = texture(tex1, uv23.xy * scale1).rgb;
		float m = texture(tex2, uv23.zw).r;
		if (vclr) {
			t0 *= COLOR.rgb;
			t1 *= mix(vec3(1.0), tint1, COLOR.a);
		} else {
			t1 *= tint1;  // (the second layer's own tint: shldr_blnd_3's P[1]; 1 in the older recipes)
		}
		a = mix(t0, t1, m);
	} else if (mode == 16) {
		// shldr_blnd_spec_vclr_dualmix_4 (disassembled, simplified): lerp(A * tint0, B * tint1, v.g) * vertex colour
		vec3 la = texture(albedo_tex, UV * scale0, grain_bias).rgb * tint0;
		vec3 lb = texture(tex1, uv23.xy * scale1).rgb * tint1;
		a = mix(la, lb, texture(tex3, uv23.zw).g) * COLOR.rgb;
	} else if (mode == 15) {
		// palette props (diff_clr_spec_2, disassembled): t0 * gain * lerp(t0, palette colour, mask.a)
		vec3 t0 = texture(albedo_tex, UV * scale0, grain_bias).rgb;
		a = t0 * tint0.x * mix(t0, tint1, texture(tex1, uv23.xy * scale1).a);
	} else if (mode == 13) {
		// rdedg_diff_opac_2 (road-edge decals, disassembled): t0 at UV * scale0, opacity = t1.a at CUSTOM0.xy * scale1
		a = texture(albedo_tex, UV * scale0, grain_bias).rgb;
		alpha_v = texture(tex1, uv23.xy * scale1).a;
	} else if (mode == 18) {
		// road_blnd_2 (disassembled): g * tint0 + v * (g + tint1 - g * tint0)
		vec4 g = texture(albedo_tex, UV * scale0, grain_bias);
		vec3 v = texture(tex1, uv23.xy * scale1).rgb;
		// (2026-11-25: the 1.11-1.22x was the console's display table, now in fm3_exposure.gdshader; road1_gain is 1)
		// x road1_gain: FITTED, not from the code: with the formula alone the road came out 1.11-1.22x the game's on both
		// CrownJewel's grid and Motegi (cause open: the grain's sampling?)
		a = (g.rgb * tint0 + v * (g.rgb + tint1 - g.rgb * tint0)) * road1_gain;
		spec_mask = g.a;
		spec_skid = v.r;
	} else if (mode == 19) {
		// shldr_4clr_blnd_mask (painted asphalt, disassembled): g' = grain + mask * P[2],
		// g' * P[0] + v * (g' + P[4] - g' * P[0]) (fm3_families.py paint4)
		vec3 g = texture(albedo_tex, UV * scale0, grain_bias).rgb;
		vec4 mk = texture(tex1, uv23.xy * scale1);
		vec3 gp = g + (paint_chan == 0.0 ? mk.r : mk.g) * tint2;
		vec3 v = texture(tex2, uv23.zw * scale2).rgb;
		a = gp * tint0 + v * (gp + tint1 - gp * tint0);
	} else if (mode == 17) {
		// rdline_blnd_diff_spec_opac_3 (disassembled): lerp(tint0, t0, t1) * tint1.x, opacity = tex2.a at UV * scale2
		vec4 t0 = texture(albedo_tex, UV * scale0, grain_bias);
		a = mix(tint0, t0.rgb, texture(tex1, uv23.xy * scale1).rgb) * tint1.x;
		alpha_v = texture(tex2, UV * scale2).a;
	} else if (mode == 14) {
		// rdline_blnd_diff_opac_2 (road lines, disassembled): lerp(tint0, t0, t1) * tint1.x, opacity t0.a
		vec4 t0 = texture(albedo_tex, UV * scale0, grain_bias);
		a = mix(tint0, t0.rgb, texture(tex1, uv23.xy * scale1).rgb) * tint1.x;
		alpha_v = t0.a;
	} else if (mode == 11 || mode == 12) {
		// road_2blnd_uv3_3 (11) / road_2blnd_3 (12), disassembled
		vec4 g = texture(albedo_tex, UV * scale0, grain_bias);
		vec3 c = texture(tex1, uv23.xy * scale1).rgb;
		float v = texture(tex2, uv23.zw * scale2).g;
		a = mode == 11 ? mix(g.a * tint0, (g.rgb + tint1) * c, v) : g.rgb * tint0 + v * c * (g.rgb + tint1 - g.rgb * tint0);
		spec_mask = g.a;
		spec_skid = mode == 11 ? c.g * v : v;
	} else if (mode == 10) {
		// road_3clr_blnd_2 (disassembled): grain * tint0 + v * (grain + tint1 - grain * tint0), v = t1.rgb * t1.a
		vec3 g = texture(albedo_tex, UV * scale0, grain_bias).rgb;
		vec4 t1 = texture(tex1, uv23.xy * scale1);
		a = g * tint0 + t1.rgb * t1.a * (g + tint1 - g * tint0);
		spec_mask = texture(albedo_tex, UV * scale0, grain_bias).a;
		spec_skid = t1.r * t1.a;
	} else if (mode == 9) {
		// three layers by a value texture (terr_blnd_spec_norm_5, disassembled): lerp(lerp(A, B, v.g), C, v.b) * v.r * tint0
		vec3 v = texture(tex2, uv23.zw).rgb;
		vec3 la = texture(albedo_tex, UV * scale0, grain_bias).rgb;
		vec3 lb = texture(tex1, uv23.xy * scale1).rgb;
		vec3 lc = texture(tex3, UV * scale2).rgb;
		a = mix(mix(la, lb, v.g), lc, v.b) * v.r * tint0;
	} else if (mode == 8) {
		// overlay blend (road_diff_spec_ovly_2, disassembled): t1 < 0.5 ? 2 t0 t1 : 1 - 2 (1 - t0)(1 - t1)
		vec3 t0 = texture(albedo_tex, UV * scale0, grain_bias).rgb;
		vec3 t1 = texture(tex1, uv23.xy * scale1).rgb;
		a = mix(2.0 * t0 * t1, 1.0 - 2.0 * (1.0 - t0) * (1.0 - t1), step(0.5, t1));
		spec_mask = texture(albedo_tex, UV * scale0, grain_bias).a;
		spec_skid = t1.r;
	} else if (mode == 7) {
		a = texture(albedo_tex, UV * scale0, grain_bias).rgb;
	} else if (mode == 6) {
		a = texture(albedo_tex, UV * scale0, grain_bias).rgb * mix(tint0, vec3(1.0), texture(tex1, uv23.xy * scale1).g);
	} else if (mode == 5) {
		a = mix(texture(albedo_tex, UV * scale0, grain_bias).rgb, texture(tex1, uv23.xy * scale1).rgb, texture(tex2, uv23.zw).r);
	} else {
		vec3 grain = vec3(dot(texture(albedo_tex, UV * scale0, grain_bias).rgb, vec3(0.299, 0.587, 0.114))) / max(grain_mean, 0.05);  // (luminance: the game's asphalt is neutral grey)
		vec4 s = texture(tex1, uv23.xy * scale1);
		if (mode == 2) {
			a = s.rgb * 0.34 * grain;
			spec_mask = texture(albedo_tex, UV * scale0, grain_bias).a;
			spec_skid = s.r;
		} else if (mode == 4) {
			vec3 dirt = texture(tex2, uv23.xy * scale2).rgb;
			float m = texture(tex3, uv23.zw).r;
			a = mix(dirt, s.rgb * 0.34 * grain, m);
		} else {
			a = mix(vec3(0.16) * grain, tint1 * paint_gain, s.a);
		}
	}
	vec3 light = has_lightmap ? mix(ambient, sun, texture(light_tex, UV2).rgb) : vec3(unlit_level);
	vec3 c = a * light;
	if (road_spec_on && spec_mask >= 0.0 && has_lightmap) {
		float m = mix(road_spec.x, road_spec.y, spec_mask) + mix(road_spec.w, road_spec.z, spec_skid);
		float gate = max(0.0, (texture(light_tex, UV2).r - road_gloss.z) / max(road_gloss.w - road_gloss.z, 1e-4));
		vec3 l = normalize((VIEW_MATRIX * vec4(sun_dir, 0.0)).xyz);
		vec3 h = normalize(VIEW + l);
		float nh = max(dot(normalize(NORMAL), h), 0.0);
		c += vec3(max(m, 0.0) * gate * pow(nh, max(mix(road_gloss.x, road_gloss.y, m), 1.0)));
	}
	if (mode == 7) {
		vec3 r = (INV_VIEW_MATRIX * vec4(reflect(-VIEW, NORMAL), 0.0)).xyz;
		vec3 env = r.y > 0.0 ? mix(env_horizon, env_zenith, sqrt(r.y)) : mix(env_horizon, env_ground, sqrt(-r.y));
		float k = clamp(texture(albedo_tex, UV * scale0, grain_bias).a * tint0.x, 0.0, 1.0);
		float fres = 0.35 + 0.65 * pow(1.0 - clamp(dot(NORMAL, VIEW), 0.0, 1.0), 3.0);
		c = mix(c, env, k * fres);  // reflective glazing replaces the base where the mask says so
	}
	ALBEDO = to_linear(fm3_fog(c, VERTEX));
#ifdef FM3_ALPHA
	ALPHA = alpha_v;
#endif
}

void light() {
	if (LIGHT_IS_DIRECTIONAL) {
		DIFFUSE_LIGHT += vec3(1.0 - shadow_strength + shadow_strength * ATTENUATION);
	}
}
