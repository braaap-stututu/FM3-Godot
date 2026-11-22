/* triple_camera_test.c — checks godot/triple_camera.h. Exit code 0 = all passed.
 *
 * For several layouts and a non-trivial game camera, every test point is projected two ways:
 *   expected: game clip (widened frustum) -> fir_triple_apply  (what ReGPU draws)
 *   godot:    world -> screen camera (fir_triple_camera_transform) -> Godot's frustum projection,
 *             re-implemented from Godot 4.7.2 Projection::set_frustum (KEEP_HEIGHT, aspect 16:9)
 * and NDC x/y must agree.
 *
 * With an argument (a file path) it also writes the cases as JSON for the in-engine check
 * (tests/triple_camera_godot_test.gd), which repeats the comparison with real Camera3D nodes.
 */
#include "../triple_camera.h"
#include <stdio.h>

static int failures = 0;

/* Godot 4.7.2 Projection::set_frustum(left, right, bottom, top, near, far), applied to a point. */
static void godot_project(float l, float r, float b, float t, float n, float f, const float p[3], float out[4])
{
    const float x = 2 * n / (r - l), y = 2 * n / (t - b);
    const float A = (r + l) / (r - l), B = (t + b) / (t - b);
    const float C = -(f + n) / (f - n), D = -2 * f * n / (f - n);
    out[0] = x * p[0] + A * p[2];
    out[1] = y * p[1] + B * p[2];
    out[2] = C * p[2] + D;
    out[3] = -p[2];
}

/* camera-to-world (row-major 3x4) inverse applied to a world point (rigid transforms only). */
static void to_camera(const float m[3][4], const float w[3], float out[3])
{
    const float d[3] = { w[0] - m[0][3], w[1] - m[1][3], w[2] - m[2][3] };
    for (int j = 0; j < 3; j++)
        out[j] = m[0][j] * d[0] + m[1][j] * d[1] + m[2][j] * d[2];
}

static void local_to_world(const float m[3][4], const float p[3], float out[3])
{
    for (int i = 0; i < 3; i++)
        out[i] = m[i][0] * p[0] + m[i][1] * p[1] + m[i][2] * p[2] + m[i][3];
}

int main(int argc, char **argv)
{
    FILE *json = argc > 1 ? fopen(argv[1], "w") : NULL;
    if (json) fprintf(json, "{\"viewport\":[2560,1440],\"cases\":[\n");

    /* game camera: yawed 30 deg, pitched -10 deg, at (5, 1.2, -3) — row-major camera-to-world */
    const float yaw = 30.0f * FIR_TRIPLE_D2R, pitch = -10.0f * FIR_TRIPLE_D2R;
    const float cy = cosf(yaw), sy = sinf(yaw), cp = cosf(pitch), sp = sinf(pitch);
    /* R = RotY(yaw) * RotX(pitch) */
    const float game[3][4] = {
        { cy, sy * sp, sy * cp, 5.0f },
        { 0.0f, cp, -sp, 1.2f },
        { -sy, cy * sp, cy * cp, -3.0f },
    };

    fir_triple_layout layouts[4];
    const char *names[4] = { "auto", "auto-fov40-angle60", "physical-facing", "physical-45-50" };
    layouts[0] = fir_triple_layout_default();
    layouts[1] = fir_triple_layout_default();
    layouts[1].fov_deg = 40.0f; layouts[1].angle_deg = 60.0f; layouts[1].bezel_deg = 2.0f;
    layouts[2] = fir_triple_layout_default();
    layouts[2].mode = FIR_TRIPLE_PHYSICAL; layouts[2].bezel_mm = 10.0f; layouts[2].gap_mm = 5.0f;
    layouts[3] = layouts[2];
    layouts[3].angle_left_deg = 45.0f; layouts[3].angle_right_deg = 50.0f;

    const float z_near = 0.05f, z_far = 4000.0f;
    int first_case = 1;
    for (int li = 0; li < 4; li++) {
        fir_triple_result r;
        fir_triple_compute(&layouts[li], 50.0f * FIR_TRIPLE_D2R, &r);
        fir_triple_camera cams[3];
        fir_triple_cameras(&r, z_near, z_far, cams);
        double worst = 0.0;
        for (int s = 0; s < 3; s++) {
            if (fabsf(cams[s].aspect - FIR_TRIPLE_ASPECT) > 1e-4f) {
                printf("FAIL %s screen %d: aspect %.5f is not 16:9\n", names[li], s, cams[s].aspect);
                failures++;
            }
            float screen[3][4];
            fir_triple_camera_transform(game, &cams[s], screen);
            const float half_w = cams[s].size * cams[s].aspect / 2;
            const float l = -half_w + cams[s].offset_x, rr = half_w + cams[s].offset_x;
            const float b = -cams[s].size / 2 + cams[s].offset_y, t = cams[s].size / 2 + cams[s].offset_y;

            if (json) {
                fprintf(json, "%s{\"layout\":\"%s\",\"screen\":%d,\"game\":[", first_case ? "" : ",\n", names[li], s);
                for (int i = 0; i < 3; i++)
                    for (int j = 0; j < 4; j++)
                        fprintf(json, "%s%.9g", (i || j) ? "," : "", game[i][j]);
                fprintf(json, "],\"rot_y\":%.9g,\"size\":%.9g,\"offset\":[%.9g,%.9g],\"near\":%.9g,\"far\":%.9g,\"points\":[",
                        cams[s].local_rot_y, cams[s].size, cams[s].offset_x, cams[s].offset_y, z_near, z_far);
                first_case = 0;
            }

            unsigned seed = 777u + (unsigned)(li * 3 + s);
            int written = 0;
            for (int k = 0; k < 400; k++) {
                /* a point in front of the eye, inside this screen's picture (game-camera local space) */
                seed = seed * 1664525u + 1013904223u; const float fu = ((seed >> 8) / 16777216.0f) * 1.8f - 0.9f;
                seed = seed * 1664525u + 1013904223u; const float fv = ((seed >> 8) / 16777216.0f) * 1.8f - 0.9f;
                seed = seed * 1664525u + 1013904223u; const float dist = 1.0f + ((seed >> 8) / 16777216.0f) * 300.0f;
                const fir_triple_screen *sc = &r.screens[s];
                const float u = sc->l + (fu + 1.0f) * 0.5f * (sc->r - sc->l), v = fv * sc->half_h;
                const float c = cosf(sc->yaw), sn = sinf(sc->yaw);
                /* the picture point in eye space (x right, y up, z forward), scaled along its ray */
                const float ex = (u * c + sc->d * sn), ez = (-u * sn + sc->d * c), ey = v;
                const float scale = dist / sqrtf(ex * ex + ey * ey + ez * ez);
                const float x = ex * scale, y = ey * scale, zf = ez * scale;
                if (zf <= 0.01f) continue;

                /* expected: ReGPU's path */
                float clip[4] = { r.p00g * x, r.p11g * y, zf - 0.1f, zf };
                fir_triple_apply(&r.views[s], clip);
                const float ex_x = clip[0] / clip[3], ex_y = clip[1] / clip[3];

                /* Godot's path: local (Godot looks down -Z) -> world -> screen camera -> projection */
                const float local[3] = { x, y, -zf };
                float world[3], cam[3], gclip[4];
                local_to_world(game, local, world);
                to_camera(screen, world, cam);
                godot_project(l, rr, b, t, z_near, z_far, cam, gclip);
                const float gx = gclip[0] / gclip[3], gy = gclip[1] / gclip[3];

                const double e = fmax(fabs(gx - ex_x), fabs(gy - ex_y));
                if (e > worst) worst = e;
                if (json && written < 24) {
                    fprintf(json, "%s{\"p\":[%.9g,%.9g,%.9g],\"ndc\":[%.9g,%.9g]}", written ? "," : "",
                            world[0], world[1], world[2], ex_x, ex_y);
                    written++;
                }
            }
            if (json) fprintf(json, "]}");
        }
        printf("%-20s max NDC difference %.2e\n", names[li], worst);
        if (worst > 2e-4) failures++;
    }
    if (json) { fprintf(json, "\n]}\n"); fclose(json); }
    printf(failures ? "%d FAILURES\n" : "all passed\n", failures);
    return failures ? 1 : 0;
}
