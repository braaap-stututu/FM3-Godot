// FM3's multi-texture track shaders (tools/fm3_families.py), lit like fm3_baked.gdshader: the albedo times
// lerp(ambient c247, sun c248, lightmap) on raw (gamma-space) values, converted to linear for Godot's linear tone mapper.
//   mode 1 terrain blend: lerp(t0 * tint0 [* vertex rgb], t1 * lerp(1, tint1, vertex alpha), mask.r)
//        t0 at UV * scale0, t1 at CUSTOM0.xy * scale1 (glTF TEXCOORD_2), mask at CUSTOM0.zw (TEXCOORD_3)
//   mode 2 road: tex1 (the surface, at CUSTOM0.xy = UV0) * 0.34 * grain / grain_mean; grain t0 at UV (world x, z) * scale0
//   mode 3 paint: lerp(0.16 * grain, tint1, tex1.a)
//   mode 4 edge: lerp(dirt (tex2 at CUSTOM0.xy * scale2), road, tex3.r at CUSTOM0.zw); mode 5 mix: lerp(base, layer, mask.r); mode 6 curb: t0 * lerp(tint0, 1, t1.g)
//   mode 7 refl (windows): lerp(t0 lit, environment, t0.a * tint0.x * fresnel)
shader_type spatial;
render_mode cull_disabled, ambient_light_disabled, specular_disabled, diffuse_lambert;

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
uniform float grain_mean = 0.5;
uniform vec3 ambient = vec3(0.14, 0.14, 0.18);  // FM3 PS c247
uniform vec3 sun = vec3(1.58, 1.57, 1.5);  // FM3 PS c248
uniform float unlit_level = 0.6;  // without a lightmap
uniform float shadow_strength = 0.62;
uniform vec3 env_zenith = vec3(0.40, 0.58, 0.74);  // mode 7: the reflected environment (gamma space), a sky gradient
uniform vec3 env_horizon = vec3(0.45, 0.52, 0.56);  // (the track's surroundings: hills, trees, haze)
uniform vec3 env_ground = vec3(0.16, 0.16, 0.14);

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
	if (mode == 1) {
		vec3 t0 = texture(albedo_tex, UV * scale0).rgb * tint0;
		vec3 t1 = texture(tex1, uv23.xy * scale1).rgb;
		float m = texture(tex2, uv23.zw).r;
		if (vclr) {
			t0 *= COLOR.rgb;
			t1 *= mix(vec3(1.0), tint1, COLOR.a);
		}
		a = mix(t0, t1, m);
	} else if (mode == 7) {
		a = texture(albedo_tex, UV * scale0).rgb;
	} else if (mode == 6) {
		a = texture(albedo_tex, UV * scale0).rgb * mix(tint0, vec3(1.0), texture(tex1, uv23.xy * scale1).g);
	} else if (mode == 5) {
		a = mix(texture(albedo_tex, UV * scale0).rgb, texture(tex1, uv23.xy * scale1).rgb, texture(tex2, uv23.zw).r);
	} else {
		vec3 grain = vec3(dot(texture(albedo_tex, UV * scale0).rgb, vec3(0.299, 0.587, 0.114))) / max(grain_mean, 0.05);  // (luminance: the game's asphalt is neutral grey)
		vec4 s = texture(tex1, uv23.xy * scale1);
		if (mode == 2) {
			a = s.rgb * 0.34 * grain;
		} else if (mode == 4) {
			vec3 dirt = texture(tex2, uv23.xy * scale2).rgb;
			float m = texture(tex3, uv23.zw).r;
			a = mix(dirt, s.rgb * 0.34 * grain, m);
		} else {
			a = mix(vec3(0.16) * grain, tint1, s.a);
		}
	}
	vec3 light = has_lightmap ? mix(ambient, sun, texture(light_tex, UV2).rgb) : vec3(unlit_level);
	vec3 c = a * light;
	if (mode == 7) {
		vec3 r = (INV_VIEW_MATRIX * vec4(reflect(-VIEW, NORMAL), 0.0)).xyz;
		vec3 env = r.y > 0.0 ? mix(env_horizon, env_zenith, sqrt(r.y)) : mix(env_horizon, env_ground, sqrt(-r.y));
		float k = clamp(texture(albedo_tex, UV * scale0).a * tint0.x, 0.0, 1.0);
		float fres = 0.35 + 0.65 * pow(1.0 - clamp(dot(NORMAL, VIEW), 0.0, 1.0), 3.0);
		c = mix(c, env, k * fres);  // reflective glazing replaces the base where the mask says so
	}
	ALBEDO = to_linear(c);
}

void light() {
	if (LIGHT_IS_DIRECTIONAL) {
		DIFFUSE_LIGHT += vec3(1.0 - shadow_strength + shadow_strength * ATTENUATION);
	}
}
