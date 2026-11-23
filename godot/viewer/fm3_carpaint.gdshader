// FM3 car paint (2026-11-23; the game's paint pixel shader e41e183a423e6f1b, tools/fir_disasm.py): the paint colour
// (livery over the c118 colour, composited by fir_world.py into the albedo) lit by an ambient term and the sun, plus a
// Fresnel reflection of the environment and a sun highlight. The game reflects a cube it renders each frame around the
// cars (t6/t7); this uses the layout's static car cube (staticcarcubemap.xpr, as the window glass does). Fitted to the
// game's screenshot of the grid per car (tools/car_regions.py): the game's paint has darker shade and much brighter
// reflections than a plain clear coat.
shader_type spatial;
render_mode cull_disabled, ambient_light_disabled, specular_disabled;

uniform sampler2D albedo_tex : filter_linear_mipmap_anisotropic, repeat_enable, hint_default_white;
uniform vec4 albedo_color = vec4(1.0);
uniform samplerCube env_cube : filter_linear_mipmap;
uniform bool has_env = false;
uniform vec3 env_fallback = vec3(0.45, 0.52, 0.56);
uniform vec3 env_flip = vec3(-1.0, 1.0, 1.0);  // (this scene's x is the game's mirrored)
// Fitted on the grid (tools/car_regions.py, 7 cars): median luminance off by 2.2 on average (14 with the old clear coat).
uniform vec3 ambient = vec3(0.50, 0.51, 0.55);  // gamma-space sky light on surfaces facing up (where the sun does not reach)
uniform vec3 ambient_ground = vec3(0.05, 0.05, 0.05);  // ... and on surfaces facing down (bumpers, sills: the road's shade)
uniform vec3 sun = vec3(1.0, 0.98, 0.94);
uniform float shadow_strength = 0.85;
// The game's paint constants (all cars on the grid): reflection c224 x c217/c218 = 1.5 x 0.3/0.5, Fresnel power c216 = 4,
// the sun's highlight power c189 = 75 and strength c180 = 1.4. (The colour's c119.x scale is in the albedo: fir_world.)
uniform float refl_gain = 1.0;  // environment reflection at grazing angles (x Fresnel), solid paint
uniform float refl_metal = 1.6;  // ... metallic paint (the game's c191.x > 0: the Mazda, the Eclipse; glTF metallic 1;
                                 // 2.5 fitted the grid's highlights but striped the Eclipse's doors with the low-res cube)
uniform float metallic = 0.0;
uniform float refl_f0 = 0.02;  // ... and looking straight at the paint (the game's black paint stays black head-on)
uniform float spec_gain = 1.4;  // the sun's highlight
uniform float spec_power = 75.0;
uniform float fresnel_power = 4.0;

#include "res://viewer/fm3_livecube.gdshaderinc"

vec3 to_linear(vec3 c) {
	c = max(c, vec3(0.0));
	return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(0.04045, c));
}

void fragment() {
	vec4 t = texture(albedo_tex, UV);
	// (the texture is read raw: gamma-space values, as the game's shader works with them)
	ALBEDO = to_linear(t.rgb * albedo_color.rgb);
}

void light() {
	if (LIGHT_IS_DIRECTIONAL) {
		float sh = 1.0 - shadow_strength + shadow_strength * ATTENUATION;
		float ndl = max(dot(NORMAL, LIGHT), 0.0);
		float up = (INV_VIEW_MATRIX * vec4(NORMAL, 0.0)).y * 0.5 + 0.5;
		DIFFUSE_LIGHT += to_linear(mix(ambient_ground, ambient, up) + sun * ndl * sh);
		vec3 r = (INV_VIEW_MATRIX * vec4(reflect(-VIEW, NORMAL), 0.0)).xyz;
		vec3 env = has_live ? live_cube(r) : (has_env ? texture(env_cube, r * env_flip).rgb : env_fallback);
		float cosv = clamp(dot(NORMAL, VIEW), 0.0, 1.0);
		float fres = refl_f0 + (1.0 - refl_f0) * pow(1.0 - cosv, fresnel_power);
		float spec = pow(max(dot(reflect(-LIGHT, NORMAL), VIEW), 0.0), spec_power) * sh;
		SPECULAR_LIGHT += to_linear(env * fres * mix(refl_gain, refl_metal, metallic) * mix(1.0, sh, 0.3) + sun * spec * spec_gain);
	}
}
