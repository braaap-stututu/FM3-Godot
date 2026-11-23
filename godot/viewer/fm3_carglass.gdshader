// FM3 car window glass, the game's own formula and values (2026-11-23, PLAN-CARS phase 3; replaces the first, fitted
// version). The 70 window draws of the grid capture all run pixel shader b117fbafcc1fa980 (tools/fir_disasm.py) with the
// same constants, named by its constant table in shaders_v11.fxobj (tools/fm3_fxobj.py):
//   fresnel  f = clamp(FresnelScale c191 * (1 - |N.V|)^FresnelPower c216, FresnelMin c189, FresnelMax c190)
//              x reflectionScaler c192
//   alpha    min(f + GlassColor.a c219.w, GlassMaxOpacity c218)  (x alphaDirtAmount c197)
//   colour   lerp(GlassColor.rgb, reflection, f);  reflection = the environment cube x CubeScale c217, damped towards
//            the track lightmap by StaticEnvLightmapDampner c180 (not reproduced: no track lightmap on the car here)
//   no sun highlight: SpecularAmount c116 = 0 on every window
// Captured values: GlassColor (0, 0.07, 0.06, 0.1), GlassMaxOpacity 1, Fresnel min 0.4 / max 1 / scale 1 / power 1.5,
// CubeScale 1, reflectionScaler 1. So a window is half see-through looking straight at it (alpha 0.5) and opaque at
// grazing angles, dark green-black with 40-100 % of the reflection.
shader_type spatial;
render_mode blend_mix, cull_disabled, depth_draw_opaque, ambient_light_disabled, specular_disabled, unshaded;

uniform vec4 albedo_color = vec4(1.0);  // (the glTF material's colour: unused, the game's GlassColor rules)
uniform samplerCube env_cube : filter_linear_mipmap;
uniform bool has_env = false;
uniform vec3 env_fallback = vec3(0.45, 0.52, 0.56);
uniform vec3 env_flip = vec3(-1.0, 1.0, 1.0);
uniform vec4 glass_color = vec4(0.0, 0.07, 0.06, 0.1);  // GlassColor c219
uniform float max_opacity = 1.0;  // GlassMaxOpacity c218
uniform float fresnel_min = 0.4;  // c189
uniform float fresnel_max = 1.0;  // c190
uniform float fresnel_scale = 1.0;  // c191
uniform float fresnel_power = 1.5;  // c216
uniform float cube_scale = 1.0;  // c217
uniform float reflection_scaler = 1.0;  // c192
// The one number not from the game: the brightness of what is reflected. The game's cube (and its damping towards the
// track lightmap, c180 / c119) is far darker than the viewer's live cube of its surroundings; with env_scale 1 the
// CR-X's rear glass came out at 178 where the game has 15. Measured on the grid (tools/car_regions.py).
uniform float env_scale = 0.2;
// (kept so FM3_CARGLASS overrides of the first version do not error; unused)
uniform float opacity = 0.0;
uniform float body_level = 0.0;
uniform float refl_gain = 0.0;
uniform float refl_f0 = 0.0;
uniform float spec_gain = 0.0;
uniform float spec_power = 0.0;
uniform float metallic = 0.0;

#include "res://viewer/fm3_livecube.gdshaderinc"

vec3 to_linear(vec3 c) {
	c = max(c, vec3(0.0));
	return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(0.04045, c));
}

void fragment() {
	vec3 r = (INV_VIEW_MATRIX * vec4(reflect(-VIEW, NORMAL), 0.0)).xyz;
	vec3 env = (has_live ? live_cube(r) : (has_env ? texture(env_cube, r * env_flip).rgb : env_fallback)) * cube_scale * env_scale;
	float cosv = clamp(abs(dot(NORMAL, VIEW)), 0.0, 1.0);
	float f = clamp(fresnel_scale * pow(1.0 - cosv, fresnel_power), fresnel_min, fresnel_max) * reflection_scaler;
	float a = min(f + glass_color.a, max_opacity);
	ALBEDO = to_linear(mix(glass_color.rgb, env, f));
	ALPHA = a;
}
