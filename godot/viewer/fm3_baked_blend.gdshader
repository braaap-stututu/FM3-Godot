// fm3_baked.gdshader with alpha blending (grass decal cards). FM3's static world, lit as the game lights it: albedo x lerp(ambient c247, sun c248, colour lightmap), computed on
// the raw (gamma-space) texture values as the Xbox 360 does, then converted to linear for Godot (with the linear tone
// mapper the screen gets exactly that value). Godot's own lighting adds nothing (no N.L, no ambient): the sun only
// takes light away where a dynamic object (car, person) shadows the surface, as FM3's shadow map does over its baked world.
shader_type spatial;
render_mode cull_disabled, depth_draw_never, ambient_light_disabled, specular_disabled, diffuse_lambert;
#include "res://viewer/fm3_fog.gdshaderinc"
#include "res://viewer/fm3_carshadow.gdshaderinc"

uniform sampler2D albedo_tex : filter_linear_mipmap_anisotropic, repeat_enable, hint_default_white;
uniform sampler2D light_tex : filter_linear_mipmap, repeat_enable, hint_default_white;
uniform vec4 albedo_color = vec4(1.0);
uniform vec3 ambient = vec3(0.14, 0.14, 0.18);  // FM3 PS c247 (Ladera)
uniform vec3 sun = vec3(1.58, 1.57, 1.5);  // FM3 PS c248
uniform float gain = 1.0;
uniform float shadow_strength = 0.85;  // (linear: FM3 darkens shadowed ground to ~0.42 of its gamma-space value, 0.42^2.2 = 0.15)
// The shadowed light per channel (linear), when set: the track's ShadowColor (gamma) ^ 2.2 (world_view.gd
// _apply_track_light); shadow_tint.r < 0 = the single shadow_strength above.
uniform vec3 shadow_tint = vec3(-1.0);

vec3 to_linear(vec3 c) {
	c = clamp(c, 0.0, 1.0);
	return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(0.04045, c));
}

void fragment() {
	fm3_wpos = (INV_VIEW_MATRIX * vec4(VERTEX, 1.0)).xyz;
	vec4 a = texture(albedo_tex, UV) * albedo_color;
	vec3 lm = texture(light_tex, UV2).rgb;
	ALBEDO = to_linear(fm3_fog(a.rgb * mix(ambient, sun, lm) * gain, VERTEX));
	ALPHA = a.a;
}

void light() {
	// Final = ALBEDO * DIFFUSE_LIGHT (no ambient): the baked colour where the sun reaches, darker by shadow_strength
	// where a dynamic object shadows it. (Only the sun is a light in the viewer.)
	if (LIGHT_IS_DIRECTIONAL) {
		DIFFUSE_LIGHT += shadow_tint.r >= 0.0 ? mix(shadow_tint, vec3(1.0), fm3_car_shadow(ATTENUATION)) : vec3(1.0 - shadow_strength + shadow_strength * fm3_car_shadow(ATTENUATION));
	}
}
