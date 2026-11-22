/* triple_view_test.c — checks for triple_view.h. Exit code 0 = all passed.
 *
 * 1. fir_triple_clip_matrix gives the same clip position as the shader formula (fir_triple_apply).
 * 2. A point projected through the widened game frustum and then a screen's view lands where a
 *    direct projection onto that screen's own plane puts it (x and y in NDC).
 * 3. Physical layout with angles 0: side screens face the eye (l + r = 0).
 * 4. The centre screen's view has no turn (b = c = 0, d = 1).
 */
#include "triple_view.h"
#include <stdio.h>

static int failures = 0;

static void check(int ok, const char *what, double got, double want)
{
    if (!ok) {
        printf("FAIL %s: got %.7f want %.7f\n", what, got, want);
        failures++;
    }
}

static int close_to(double a, double b, double tol) { return fabs(a - b) <= tol * (1.0 + fabs(b)); }

/* Direct projection of eye-space point (x right, y up, z forward) onto screen s, NDC x and y. */
static int direct(const fir_triple_screen *s, float x, float y, float z, float *nx, float *ny)
{
    const float c = cosf(s->yaw), sn = sinf(s->yaw);
    const float u = x * c - z * sn;     /* across the screen plane */
    const float depth = x * sn + z * c; /* along the screen's forward */
    if (depth <= 1e-3f) return 0;
    const float up = s->d * u / depth, vp = s->d * y / depth;
    *nx = (2.0f * up - (s->r + s->l)) / (s->r - s->l);
    *ny = vp / s->half_h;
    return 1;
}

static void run_layout(const char *name, const fir_triple_layout *L, float camera_fov_y)
{
    fir_triple_result r;
    if (!fir_triple_compute(L, camera_fov_y, &r)) {
        printf("FAIL %s: compute refused\n", name);
        failures++;
        return;
    }
    printf("%-22s game fov %.2f deg, turns %.2f / %.2f deg, fits %d\n", name,
           r.game_fov_y / FIR_TRIPLE_D2R, r.turn_l / FIR_TRIPLE_D2R, r.turn_r / FIR_TRIPLE_D2R, r.fits);

    /* 4. centre view */
    check(fabsf(r.views[1].b) < 1e-6f && fabsf(r.views[1].c) < 1e-6f && fabsf(r.views[1].d - 1.0f) < 1e-6f,
          "centre view has no turn", r.views[1].c, 0.0);

    unsigned seed = 12345u;
    for (int i = 0; i < 3; i++) {
        float m[4][4];
        fir_triple_clip_matrix(&r.views[i], m);
        for (int k = 0; k < 2000; k++) {
            /* a random point in front of the eye, inside the game frustum */
            seed = seed * 1664525u + 1013904223u; float fx = ((seed >> 8) / 16777216.0f) * 2.0f - 1.0f;
            seed = seed * 1664525u + 1013904223u; float fy = ((seed >> 8) / 16777216.0f) * 2.0f - 1.0f;
            seed = seed * 1664525u + 1013904223u; float fz = 0.5f + ((seed >> 8) / 16777216.0f) * 200.0f;
            const float z = fz, x = fx * z / r.p00g, y = fy * z / r.p11g;
            const float zc = z - 0.1f; /* a projection with z = w + B, B = -0.1 */
            float clip[4] = { r.p00g * x, r.p11g * y, zc, z };
            float viaM[4];
            for (int row = 0; row < 4; row++)
                viaM[row] = m[row][0] * clip[0] + m[row][1] * clip[1] + m[row][2] * clip[2] + m[row][3] * clip[3];
            fir_triple_apply(&r.views[i], clip);
            /* 1. matrix == shader formula */
            for (int c = 0; c < 4; c++)
                check(close_to(viaM[c], clip[c], 1e-5), "matrix matches shader formula", viaM[c], clip[c]);
            /* 2. matches a direct projection onto the screen's plane */
            float nx, ny;
            if (L->flip == 0 && direct(&r.screens[i], x, y, z, &nx, &ny) && clip[3] > 1e-3f) {
                check(close_to(clip[0] / clip[3], nx, 1e-4), "x matches direct projection", clip[0] / clip[3], nx);
                check(close_to(clip[1] / clip[3], ny, 1e-4), "y matches direct projection", clip[1] / clip[3], ny);
                /* depth: z' - w' stays z - w, the property ReGPU relies on */
                check(close_to(clip[2] - clip[3], zc - z, 1e-4), "z - w preserved", clip[2] - clip[3], zc - z);
            }
        }
    }

    /* 3. physical, angles 0: side screens face the eye */
    if (L->mode == FIR_TRIPLE_PHYSICAL && L->angle_left_deg == 0.0f && L->angle_right_deg == 0.0f) {
        check(fabsf(r.screens[0].l + r.screens[0].r) < 1e-4f, "left screen faces the eye", r.screens[0].l + r.screens[0].r, 0.0);
        check(fabsf(r.screens[2].l + r.screens[2].r) < 1e-4f, "right screen faces the eye", r.screens[2].l + r.screens[2].r, 0.0);
    }
}

int main(void)
{
    fir_triple_layout L = fir_triple_layout_default();
    run_layout("auto, camera fov", &L, 50.0f * FIR_TRIPLE_D2R);

    L.fov_deg = 40.0f; L.angle_deg = 60.0f; L.bezel_deg = 2.0f;
    run_layout("auto, set fov/angle", &L, 50.0f * FIR_TRIPLE_D2R);

    L = fir_triple_layout_default();
    L.mode = FIR_TRIPLE_PHYSICAL; L.diag_in = 27.0f; L.dist_cm = 60.0f; L.bezel_mm = 10.0f; L.gap_mm = 5.0f;
    run_layout("physical, facing eye", &L, 50.0f * FIR_TRIPLE_D2R);

    L.angle_left_deg = 45.0f; L.angle_right_deg = 50.0f;
    run_layout("physical, 45/50 deg", &L, 50.0f * FIR_TRIPLE_D2R);

    L.narrow = 1;
    run_layout("physical, narrow", &L, 50.0f * FIR_TRIPLE_D2R);

    printf(failures ? "%d FAILURES\n" : "all passed\n", failures);
    return failures ? 1 : 0;
}
