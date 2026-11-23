// FM3 cockpit gauges (the cockpit carbin's gauge_emissive / gauge_needle / digital_gauge on interior_lod0.xds): dark
// dial faces with white markings in the texture's colour (its alpha is 0 there; the export writes an opaque '_rgb'
// copy, fm3_track_export.py). The game lights them (GaugeEmissiveScale, shadersettings.xml): unshaded here.
shader_type spatial;
render_mode unshaded, cull_disabled;

uniform sampler2D tex : source_color, filter_linear_mipmap_anisotropic;
uniform float gain = 1.0;

void fragment() {
	ALBEDO = texture(tex, UV).rgb * gain;
}
