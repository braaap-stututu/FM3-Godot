// FM3's car drop shadow (decoded 2026-11-26): the game draws no sun shadow of a car; it draws a quad under the body
// (and one per wheel) with a soft blob texture (Media\Shaders\Cars\DropShadow.fxobj; the grid capture's PS
// d44a5b5aed142674, a 64 x 64 near-black texture whose alpha is a rounded rectangle: 0 at the rim, ~160/255 over the
// middle half), coloured c_shadowColor, faded with height. GlobalCarAttribs.xml DropShadowSettings: the body quad 1.05-1.10
// x the body's length and 1.06-1.09 x its width, opacity 0.8 at the ground .. 0.6 at 0.3 m up. Here the blob is
// procedural (no game data in the repository): the ground under it is multiplied towards the track's ShadowColor.
shader_type spatial;
render_mode blend_mul, unshaded, cull_disabled, depth_draw_never, shadows_disabled;

uniform vec3 shadow_color = vec3(0.35, 0.35, 0.38);  // the track's ShadowColor (gamma)
uniform float peak = 0.63;  // the texture's alpha over the middle (160 / 255)
uniform float opacity = 0.8;  // DropShadowSettings OpacityForMinHeightAboveGround
uniform vec2 rim = vec2(0.25, 0.3);  // the blob's falloff from each edge (u, v), as the texture's rows / columns

vec3 to_linear(vec3 c) {
	c = max(c, vec3(0.0));
	return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(0.04045, c));
}

void fragment() {
	vec2 e = min(UV, vec2(1.0) - UV);
	float a = smoothstep(0.0, rim.x, e.x) * smoothstep(0.0, rim.y, e.y) * peak * opacity;
	// (the game blends its near-black blob over the gamma framebuffer: the ground x (1 - a) + colour x a)
	ALBEDO = mix(vec3(1.0), to_linear(shadow_color), a);
}
