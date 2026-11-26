// The cars' shadows on the track as far as the game draws them (2026-11-26). The game has no sun shadow map of the
// track: its static shadows are baked into the lightmaps, and each car's shadow is a 256 x 256 depth map from the sun
// projected onto the ground nearby only (hooks/car_shadows.cpp; the track PSs fd6b3d2a... / 9e50ba14... read it, t11),
// so a low sun's long car shadow ends near the car (RoadAtlanta). Here Godot's sun shadow on the track counts only
// within fm3_car_k.y .. .z metres (faded) of a car: fm3_cars holds the cars' world x, z (world_view.gd
// _update_car_shadow_tex), fm3_car_k = (count, full radius, zero radius, on).
global uniform sampler2D fm3_cars : filter_nearest;
global uniform vec4 fm3_car_k;
varying vec3 fm3_wpos;

float fm3_car_shadow(float att) {
	if (fm3_car_k.w < 0.5) {
		return att;
	}
	float w = 0.0;
	int n = int(fm3_car_k.x);
	for (int i = 0; i < n; i++) {
		vec4 c = texelFetch(fm3_cars, ivec2(i, 0), 0);
		w = max(w, 1.0 - smoothstep(fm3_car_k.y, fm3_car_k.z, length(fm3_wpos.xz - c.xy)));
	}
	return mix(1.0, att, w);
}
