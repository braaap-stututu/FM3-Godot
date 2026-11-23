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

vec3 live_cube(vec3 r) {
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
