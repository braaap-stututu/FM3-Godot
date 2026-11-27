// FM3's 3D crowd, animated as the game does (2026-11-27; LIVE.md "The crowd's animations"): the game's crowd vertex
// shader 6ee601730a7f9f87 skins each person from one buffer of baked animations (every crowd animation, each frame one
// entry per bone: rotation rows r0, r1 and a translation; p' = r0 p.x + r1 p.y + (r0 x r1) p.z + t, relative to the
// bind pose), blended over the vertex's two bones. Here: that buffer as anim_tex (tools/fm3_crowd_anim.py: 3 RGB float
// texels an entry, rows of 2048), the vertex's bones in UV2 (x = bone 0 + weight 0 / 2, y = bone 1; fm3_spectators.py),
// the person's animation in INSTANCE_CUSTOM (first entry, frames, bones, start frame; world_view.gd _crowd3d), 30
// frames a second, looped.
// Cheering (2026-11-27 ~20:25): INSTANCE_CUSTOM holds two animations (idle first entry, frames; cheer first entry,
// frames: the class's idle and cheer lists in spectators.xml, one of each picked per person), the bones per draw in
// `bones`; a person cheers while a car is within cheer_r of them (car positions in cars_tex, 16 x 1, w > 0 = a car;
// the game's own distance rule is in its code, not its files). Each person starts at a frame of its own (INSTANCE_ID).
// Light (2026-11-27 ~20:30): the game's crowd pixel shader b32f44c528968ecc, its constants captured on the grid:
// colour = albedo x (dark + (light - dark) x saturate(n.l)) in gamma space, dark / light = TrackSettings <Crowds>
// (CrownJewel 0.49 / 0.51 / 0.54 and 1.19 / 1.15 / 1.08), l = the sun direction; no shadow term (then the track fog).
shader_type spatial;
render_mode cull_disabled, unshaded;

uniform sampler2D albedo_tex : source_color, filter_linear_mipmap, repeat_enable;
uniform vec4 albedo_color = vec4(1.0, 1.0, 1.0, 1.0);  // (a factor for tests, FM3_CROWD3D_K)
uniform vec3 crowd_dark = vec3(0.492, 0.512, 0.541);
uniform vec3 crowd_light = vec3(1.194, 1.154, 1.084);
uniform vec3 sun_dir = vec3(0.0, 1.0, 0.0);  // (world space, toward the sun)
varying vec3 wnorm;
uniform sampler2D anim_tex : filter_nearest;
uniform bool anim_on = false;
uniform float fps = 30.0;
uniform int tex_width = 2048;
uniform int bones = 17;
uniform sampler2D cars_tex : filter_nearest;
uniform float cheer_r = 60.0;

vec3 to_linear(vec3 c) {
	c = max(c, vec3(0.0));
	return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(0.04045, c));
}

vec3 to_gamma(vec3 c) {
	c = max(c, vec3(0.0));
	return mix(c * 12.92, 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055, step(0.0031308, c));
}

vec3 entry(int e, int k) {
	int t = e * 3 + k;
	return texelFetch(anim_tex, ivec2(t % tex_width, t / tex_width), 0).rgb;
}

void vertex() {
	if (anim_on && INSTANCE_CUSTOM.y > 0.5) {
		vec3 me = (MODEL_MATRIX * vec4(0.0, 0.0, 0.0, 1.0)).xyz;
		bool cheer = false;
		for (int k = 0; k < 16; k++) {
			vec4 c = texelFetch(cars_tex, ivec2(k, 0), 0);
			if (c.w > 0.0 && distance(c.xyz, me) < cheer_r) {
				cheer = true;
			}
		}
		vec2 an = cheer && INSTANCE_CUSTOM.w > 0.5 ? INSTANCE_CUSTOM.zw : INSTANCE_CUSTOM.xy;
		float ph = fract(sin(float(INSTANCE_ID) * 12.9898) * 43758.5453) * 200.0;
		float frame = mod(floor(TIME * fps + ph), an.y);
		int base = int(an.x + 0.5) + int(frame) * bones;
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
	wnorm = (MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz;
}

void fragment() {
	vec4 t = texture(albedo_tex, UV);
	float ndl = clamp(dot(normalize(wnorm), normalize(sun_dir)), 0.0, 1.0);
	ALBEDO = to_linear(to_gamma(t.rgb) * albedo_color.rgb * (crowd_dark + (crowd_light - crowd_dark) * ndl));
}
