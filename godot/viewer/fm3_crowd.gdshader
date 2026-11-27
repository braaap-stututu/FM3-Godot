// FM3's 3D crowd, animated as the game does (2026-11-27; LIVE.md "The crowd's animations"): the game's crowd vertex
// shader 6ee601730a7f9f87 skins each person from one buffer of baked animations (every crowd animation, each frame one
// entry per bone: rotation rows r0, r1 and a translation; p' = r0 p.x + r1 p.y + (r0 x r1) p.z + t, relative to the
// bind pose), blended over the vertex's two bones. Here: that buffer as anim_tex (tools/fm3_crowd_anim.py: 3 RGB float
// texels an entry, rows of 2048), the vertex's bones in UV2 (x = bone 0 + weight 0 / 2, y = bone 1; fm3_spectators.py),
// the person's animation in INSTANCE_CUSTOM (first entry, frames, bones, start frame; world_view.gd _crowd3d), 30
// frames a second, looped.
shader_type spatial;
render_mode cull_disabled;

uniform sampler2D albedo_tex : source_color, filter_linear_mipmap, repeat_enable;
uniform vec4 albedo_color = vec4(0.7, 0.7, 0.7, 1.0);  // (the people's brightness under Godot's light, FM3_CROWD3D_K)
uniform sampler2D anim_tex : filter_nearest;
uniform bool anim_on = false;
uniform float fps = 30.0;
uniform int tex_width = 2048;

vec3 entry(int e, int k) {
	int t = e * 3 + k;
	return texelFetch(anim_tex, ivec2(t % tex_width, t / tex_width), 0).rgb;
}

void vertex() {
	if (anim_on && INSTANCE_CUSTOM.y > 0.5) {
		float frame = mod(floor(TIME * fps + INSTANCE_CUSTOM.w), INSTANCE_CUSTOM.y);
		int base = int(INSTANCE_CUSTOM.x + 0.5) + int(frame) * int(INSTANCE_CUSTOM.z + 0.5);
		int b0 = int(floor(UV2.x + 0.0001));
		float w0 = clamp(fract(UV2.x + 0.0001) * 2.0, 0.0, 1.0);
		int b1 = int(UV2.y + 0.5);
		float w1 = 1.0 - w0;
		vec3 p = VERTEX;
		vec3 n = NORMAL;
		vec3 r0 = entry(base + b0, 0);
		vec3 r1 = entry(base + b0, 1);
		vec3 c = cross(r0, r1);
		vec3 acc = w0 * (r0 * p.x + r1 * p.y + c * p.z + entry(base + b0, 2));
		vec3 nacc = w0 * (r0 * n.x + r1 * n.y + c * n.z);
		if (w1 > 0.0) {
			r0 = entry(base + b1, 0);
			r1 = entry(base + b1, 1);
			c = cross(r0, r1);
			acc += w1 * (r0 * p.x + r1 * p.y + c * p.z + entry(base + b1, 2));
			nacc += w1 * (r0 * n.x + r1 * n.y + c * n.z);
		}
		VERTEX = acc;
		NORMAL = normalize(nacc);
	}
}

void fragment() {
	vec4 t = texture(albedo_tex, UV);
	ALBEDO = t.rgb * albedo_color.rgb;
}
