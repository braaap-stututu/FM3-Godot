// FM3's final pass (ps 5b7efac9b0c87a00 with its vertex shader 2a342f670b5bb28a, decoded 2026-11-25; LIVE.md "Other
// tracks"): the auto-exposure / tone curve and desaturation, applied to the viewer's picture in gamma space.
//   colour = lerp(Y, S, desat) * tone(0.9874 Y) / max(0.9874 Y, 0.1) + boost
//   tone(y) = pow(max((y - B) / (W - B), (0.1 - B) / (W - B)), 1 / gamma)
// W, B, gamma, boost: the track's dark / light curve (TrackSettings ToneMappingLevels) blended by the adapted luminance
// (world_view.gd _exposure_update). S: the scene in the game's units: our picture is calibrated against CrownJewel's
// final picture, whose exposure is W 0.942 (read from the running game), so S = picture * 0.942 / 0.9874 (s_scale).
shader_type canvas_item;
render_mode unshaded;

uniform sampler2D screen_tex : hint_screen_texture, filter_nearest;
uniform float s_scale = 0.954;
uniform float desat = 1.0;
uniform float black = 0.0;
uniform float white = 0.942;
uniform float gamma_inv = 1.0;
uniform float boost = 0.0;

void fragment() {
	vec3 s = texture(screen_tex, SCREEN_UV).rgb * s_scale;
	float y = dot(s, vec3(0.2, 0.7152, 0.0722));
	float yp = y * 0.9874;
	float wb = max(white - black, 1e-4);
	float x = max((yp - black) / wb, max((0.1 - black) / wb, 0.0));
	float t = pow(max(x, 1e-6), gamma_inv);
	vec3 c = mix(vec3(y), s, desat) * (t / max(yp, 0.1)) + boost;
	COLOR = vec4(c, 1.0);
}
