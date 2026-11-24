// FM3's track decal shaders whose opacity comes from their own textures (modes 13-14): fm3_blend.gdshaderinc, blended.
shader_type spatial;
render_mode cull_disabled, ambient_light_disabled, specular_disabled, diffuse_lambert, depth_draw_never;
#define FM3_ALPHA
#include "res://viewer/fm3_blend.gdshaderinc"
