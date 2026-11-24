// A cockpit mirror (world_view.gd _update_mirrors): the view from the driver's eye reflected in the mirror's plane,
// rendered into a viewport; each fragment looks itself up through that camera (mirror_vp: projection x view), so the
// picture sits on the glass wherever the mesh's UVs point. Dark glass while the viewport is not running.
shader_type spatial;
render_mode unshaded, cull_disabled;

uniform sampler2D view_tex : source_color, filter_linear, repeat_disable;
uniform mat4 mirror_vp;
uniform bool active = false;
uniform vec3 tint = vec3(0.55);
varying vec3 wpos;

void vertex() {
	wpos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	if (!active) {
		ALBEDO = vec3(0.01, 0.012, 0.015);
	} else {
		vec4 c = mirror_vp * vec4(wpos, 1.0);
		vec2 uv = c.xy / c.w * 0.5 + 0.5;
		uv.y = 1.0 - uv.y;
		ALBEDO = texture(view_tex, clamp(uv, vec2(0.0), vec2(1.0))).rgb * tint;
	}
}
