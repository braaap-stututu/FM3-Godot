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
// The console's display table (DC_LUT, the title's 256-entry gamma ramp; ReGPU applies it at present): a toe that
// darkens the low end (16 -> 6, 32 -> 16, 64 -> 48, 128 -> 115, 192 -> 185). Measured 2026-11-25 from the game's own
// shots of the same frozen frames with and without it (REGPU_NO_GAMMA; MapleValley and LagunaSeca, every pixel value's
// median). Without it every shader that follows the game's formulas came out too light in shade: a mid-grey road
// (102 -> 88) needed a fitted x0.85, the paint's reflection terms 2x too bright in the darks. world_view.gd
// FM3_NO_TOE=1: off (A/B).
uniform bool display_toe = true;
const float TOE[17] = float[](0.0, 6.0, 16.0, 32.0, 48.0, 65.0, 81.0, 98.0, 115.0, 132.0, 150.0, 167.0, 185.0, 202.0,
	220.0, 238.0, 255.0);

float toe(float v) {
	float x = clamp(v, 0.0, 1.0) * 255.0 / 16.0;  // (points at 0, 16, ..., 240, then 255)
	int i = min(int(x), 15);
	float x0 = float(i) * 16.0, x1 = i == 15 ? 255.0 : float(i + 1) * 16.0;
	float t = clamp((clamp(v, 0.0, 1.0) * 255.0 - x0) / (x1 - x0), 0.0, 1.0);
	return mix(TOE[i], TOE[i + 1], t) / 255.0;
}

void fragment() {
	vec3 s = texture(screen_tex, SCREEN_UV).rgb * s_scale;
	float y = dot(s, vec3(0.2, 0.7152, 0.0722));
	float yp = y * 0.9874;
	float wb = max(white - black, 1e-4);
	float x = max((yp - black) / wb, max((0.1 - black) / wb, 0.0));
	float t = pow(max(x, 1e-6), gamma_inv);
	vec3 c = mix(vec3(y), s, desat) * (t / max(yp, 0.1)) + boost;
	if (display_toe) {
		c = vec3(toe(c.r), toe(c.g), toe(c.b));
	}
	COLOR = vec4(c, 1.0);
}
