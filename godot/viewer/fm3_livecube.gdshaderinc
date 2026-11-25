// The live reflection cube (2026-11-23, world_view.gd _make_live_cube): six viewports rendered each frame around the
// player car, as the game renders its car reflection cube every frame (its paint shader's t6/t7). Face k looks along
// LIVE_DIR[k] with LIVE_UP[k] up (the same table as world_view.gd); r is a world (glTF) direction.
uniform sampler2D live0 : filter_linear, repeat_disable;
uniform sampler2D live1 : filter_linear, repeat_disable;
uniform sampler2D live2 : filter_linear, repeat_disable;
uniform sampler2D live3 : filter_linear, repeat_disable;
uniform sampler2D live4 : filter_linear, repeat_disable;
uniform sampler2D live5 : filter_linear, repeat_disable;
uniform bool has_live = false;
// The faces in floating point (world_view.gd FM3_LIVE_CUBE_HDR): they then hold linear light, values above 1 kept;
// encoded here as the 8-bit faces are (sRGB), so the shaders read the same scale, with the bright clouds no longer
// clipped at 1 (the game's car cube is stored at 1/8 and read x8).
uniform bool live_hdr = false;

vec3 lc_srgb(vec3 c) {
	c = max(c, vec3(0.0));
	return mix(c * 12.92, 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055, step(0.0031308, c));
}

vec3 live_cube_raw(vec3 r) {
	vec3 a = abs(r);
	int k;
	vec3 d;
	vec3 u;
	if (a.x >= a.y && a.x >= a.z) {
		k = r.x > 0.0 ? 0 : 1; d = vec3(sign(r.x), 0.0, 0.0); u = vec3(0.0, 1.0, 0.0);
	} else if (a.y >= a.z) {
		k = r.y > 0.0 ? 2 : 3; d = vec3(0.0, sign(r.y), 0.0); u = vec3(0.0, 0.0, -sign(r.y));
	} else {
		k = r.z > 0.0 ? 4 : 5; d = vec3(0.0, 0.0, sign(r.z)); u = vec3(0.0, 1.0, 0.0);
	}
	vec3 rt = cross(d, u);
	float f = dot(r, d);
	vec2 uv = vec2(0.5 + 0.5 * dot(r, rt) / f, 0.5 - 0.5 * dot(r, u) / f);
	uv = clamp(uv, vec2(0.002), vec2(0.998));
	if (k == 0) return texture(live0, uv).rgb;
	if (k == 1) return texture(live1, uv).rgb;
	if (k == 2) return texture(live2, uv).rgb;
	if (k == 3) return texture(live3, uv).rgb;
	if (k == 4) return texture(live4, uv).rgb;
	return texture(live5, uv).rgb;
}

vec3 live_cube(vec3 r) {
	vec3 c = live_cube_raw(r);
	return live_hdr ? lc_srgb(c) : c;
}
