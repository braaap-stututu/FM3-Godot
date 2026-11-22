// FM3's static world: albedo x colour lightmap x gain (FM3: albedo x lerp(c247, c248, lightmap)); Godot's own
// lighting adds nothing (no N.L, no ambient): the sun only takes light away where a dynamic object (car, person) shadows the
// surface, as FM3's shadow map does over its baked world.
shader_type spatial;
render_mode cull_disabled, ambient_light_disabled, specular_disabled, diffuse_lambert;

uniform sampler2D albedo_tex : source_color, filter_linear_mipmap_anisotropic, repeat_enable, hint_default_white;
uniform sampler2D light_tex : source_color, filter_linear_mipmap, repeat_enable, hint_default_white;
uniform vec4 albedo_color : source_color = vec4(1.0);
uniform float gain = 1.5;
uniform float shadow_strength = 0.62;
uniform float alpha_cut = -1.0;  // >= 0: cut out below this alpha

void fragment() {
	vec4 a = texture(albedo_tex, UV) * albedo_color;
	vec3 c = a.rgb * texture(light_tex, UV2).rgb * gain;
	ALBEDO = c;
	if (alpha_cut >= 0.0) {
		ALPHA = a.a;
		ALPHA_SCISSOR_THRESHOLD = alpha_cut;
	}
}

void light() {
	// Final = ALBEDO * DIFFUSE_LIGHT (no ambient): the baked colour where the sun reaches, darker by shadow_strength
	// where a dynamic object shadows it. (Only the sun is a light in the viewer.)
	if (LIGHT_IS_DIRECTIONAL) {
		DIFFUSE_LIGHT += vec3(1.0 - shadow_strength + shadow_strength * ATTENUATION);
	}
}
