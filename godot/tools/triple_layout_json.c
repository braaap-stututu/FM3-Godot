/* triple_layout_json.c — prints the Godot camera settings for a triple-screen layout as JSON,
 * for the G1 benchmark (--layout=<file>) or any Godot-side test.
 *
 * Arguments are the launcher's FM3_TRIPLE_* settings as key=value (all optional):
 *   mode=auto|physical  diag=27 dist=60 bezel_mm=0 gap_mm=0 left=0 right=0   (physical)
 *   fov=0 angle=0 bezel=0                                                    (auto)
 *   camera_fov=50   the game camera's own vertical FOV in degrees
 *   near=0.05 far=4000
 *
 *   cl /nologo /std:c11 tools\triple_layout_json.c && triple_layout_json.exe mode=physical diag=32 dist=70 > layout.json
 */
#include "../triple_camera.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char **argv)
{
    fir_triple_layout L = fir_triple_layout_default();
    float camera_fov = 50.0f, z_near = 0.05f, z_far = 4000.0f;
    for (int i = 1; i < argc; i++) {
        const char *eq = strchr(argv[i], '=');
        if (!eq) { fprintf(stderr, "bad argument '%s' (want key=value)\n", argv[i]); return 2; }
        const size_t n = (size_t)(eq - argv[i]);
        const char *v = eq + 1;
        const float f = (float)atof(v);
#define KEY(k) (n == strlen(k) && strncmp(argv[i], k, n) == 0)
        if (KEY("mode")) L.mode = strcmp(v, "physical") == 0 ? FIR_TRIPLE_PHYSICAL : FIR_TRIPLE_AUTO;
        else if (KEY("diag")) L.diag_in = f;
        else if (KEY("dist")) L.dist_cm = f;
        else if (KEY("bezel_mm")) L.bezel_mm = f;
        else if (KEY("gap_mm")) L.gap_mm = f;
        else if (KEY("left")) L.angle_left_deg = f;
        else if (KEY("right")) L.angle_right_deg = f;
        else if (KEY("fov")) L.fov_deg = f;
        else if (KEY("angle")) L.angle_deg = f;
        else if (KEY("bezel")) L.bezel_deg = f;
        else if (KEY("narrow")) L.narrow = atoi(v);
        else if (KEY("camera_fov")) camera_fov = f;
        else if (KEY("near")) z_near = f;
        else if (KEY("far")) z_far = f;
        else { fprintf(stderr, "unknown key in '%s'\n", argv[i]); return 2; }
#undef KEY
    }
    fir_triple_result r;
    if (!fir_triple_compute(&L, camera_fov * FIR_TRIPLE_D2R, &r)) {
        fprintf(stderr, "camera_fov out of range\n");
        return 1;
    }
    fir_triple_camera cams[3];
    fir_triple_cameras(&r, z_near, z_far, cams);
    printf("{\n  \"mode\": \"%s\",\n  \"game_fov_y_deg\": %.6f,\n  \"fits\": %s,\n  \"screens\": [\n",
           L.mode == FIR_TRIPLE_PHYSICAL ? "physical" : "auto", r.game_fov_y / FIR_TRIPLE_D2R, r.fits ? "true" : "false");
    for (int i = 0; i < 3; i++)
        printf("    {\"rot_y\": %.9g, \"size\": %.9g, \"offset\": [%.9g, %.9g], \"near\": %.9g, \"far\": %.9g, \"aspect\": %.9g}%s\n",
               cams[i].local_rot_y, cams[i].size, cams[i].offset_x, cams[i].offset_y, cams[i].z_near, cams[i].z_far,
               cams[i].aspect, i < 2 ? "," : "");
    printf("  ]\n}\n");
    return 0;
}
