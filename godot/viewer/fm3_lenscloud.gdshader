// FM3 lamp lenses, cloudy layer (world_view.gd: between fm3_carlens.gdshader's colour filter and fm3_lensrefl's
// reflection): the game's tail-light lenses are diffusing plastic, a smooth dark red through which the lamp's
// reflectors and bulbs barely show (Eclipse lenses 26/12/13 in the game; the filter alone showed bright red bulbs, the
// amber signal lamp and speckles: 41/15/16). An unlit, alpha-blended layer of the lens's own colour, thinned while the
// lamp shines (glow: brake / reverse) so a lit lamp still glows through. Fitted on the grid's tail lamps (5 boxes: Eclipse,
// Mazda, CR-X): 14.3 -> 10.9 with cloud 0.9, tint 0.15, grey 0.01 and the reflection pass at 0.01. (A blurred copy of
// the lamp behind, from the screen texture, in the layer: 11.2-14.5, and a screen copy each frame: dropped. Open: the
// Eclipse's amber signal areas show amber where the game's are dark red-grey: amber_desat 0.6 brings the left one from
// 34/24/8 to 26/23/16, game 24/13/12.)
shader_type spatial;
render_mode blend_mix, cull_back, depth_draw_never, unshaded, ambient_light_disabled, specular_disabled;

uniform vec4 glass_color = vec4(0.75, 0.0, 0.0, 0.0);  // GlassColor (ShaderSettings)
uniform float cloud = 0.9;  // opacity of the diffusing layer
uniform float tint = 0.15;  // how much of the lens colour it carries ...
uniform float grey = 0.01;  // ... over this grey (gamma)
uniform float glow = 0.0;
uniform float amber_desat = 0.6;  // amber lenses (green > 0.25): the plastic's colour towards grey

vec3 to_linear(vec3 c) {
	c = max(c, vec3(0.0));
	return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(0.04045, c));
}

void fragment() {
	vec3 gc = glass_color.rgb;
	if (gc.g > 0.25 && gc.b < 0.2) {
		gc = mix(gc, vec3(dot(gc, vec3(0.333))), amber_desat);
	}
	ALBEDO = to_linear(gc * tint + vec3(grey));
	ALPHA = cloud * (1.0 - 0.8 * clamp(glow, 0.0, 1.0));
}
