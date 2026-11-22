/*
 * triple_view.h — per-screen views for triple-screen, shared with FM3-ReGPU.
 *
 * The core uses exactly the math FM3-ReGPU uses for REGPU_TRIPLE, so the new renderer's
 * three views match ReGPU's three replays pixel for pixel and their layers can be
 * depth-composited on every screen (CORE.md §9). Kept until a better solution exists.
 *
 * Ported from FM3-ReGPU (https://github.com/braaap-stututu/FM3-ReGPU):
 *   src/hooks/triple_screen.cpp  (layouts, the game's widened frustum, ViewOf)
 *   patches/regpu-triple-geometry.patch  (regpu::triple::View and the vertex-shader formula)
 * MIT License, Copyright (c) 2026 braaap-stututu. Keep this notice with the code.
 *
 * Differences from the original:
 *   - settings come in as a struct instead of getenv (the core reads the same FM3_TRIPLE_*
 *     keys from the launcher's settings and fills it);
 *   - no guest memory access: the caller widens the game camera (profile hook) with
 *     `game_fov_y` from fir_triple_compute and reports the camera's own FOV back in;
 *   - fir_triple_clip_matrix turns a view into a 4x4 for the Scene API.
 *
 * Conventions (same as the original): eye space seen from above with x right and z
 * forward; a screen is turned by `yaw` (right positive), its plane `d` in front of the eye
 * along its own forward, its picture from `l` to `r` across that plane and `half_h` above
 * and below eye height. Screens: 0 left, 1 centre, 2 right. Every screen is 16:9.
 *
 * Header-only C99 / C++.
 */
#ifndef FIR_TRIPLE_VIEW_H
#define FIR_TRIPLE_VIEW_H

#include <math.h>

#ifdef __cplusplus
extern "C" {
#endif

#define FIR_TRIPLE_PI       3.14159265f
#define FIR_TRIPLE_D2R      (FIR_TRIPLE_PI / 180.0f)
#define FIR_TRIPLE_ASPECT   (16.0f / 9.0f)
#define FIR_TRIPLE_MAX_HALF (83.0f * FIR_TRIPLE_D2R) /* FM3's frustum stays under 166 degrees across */

/* regpu::triple::View: the screen's view of the game's wide frustum, in clip space:
 *   x' = a x + b w,  w' = c x + d w,  y' = e y,  z' = z + (w' - w)
 * (depth exact for a projection with z = w + B, close for far >> near). */
typedef struct fir_triple_view { float a, b, c, d, e; } fir_triple_view;

typedef struct fir_triple_screen { float yaw, d, l, r, half_h; } fir_triple_screen;

typedef enum fir_triple_mode { FIR_TRIPLE_AUTO = 0, FIR_TRIPLE_PHYSICAL = 1 } fir_triple_mode;

/* The launcher's "Triple screens" settings (same names and units as FM3_TRIPLE_*). */
typedef struct fir_triple_layout {
    fir_triple_mode mode;
    /* physical */
    float diag_in;          /* FM3_TRIPLE_DIAG, inches, 16:9 screens (default 27) */
    float dist_cm;          /* FM3_TRIPLE_DIST, eye to the centre screen (default 60) */
    float bezel_mm;         /* FM3_TRIPLE_BEZEL_MM, one screen's bezel */
    float gap_mm;           /* FM3_TRIPLE_GAP_MM, space between two screens' frames */
    float angle_left_deg;   /* FM3_TRIPLE_ANGLE_LEFT, 0 = facing the eye */
    float angle_right_deg;  /* FM3_TRIPLE_ANGLE_RIGHT, 0 = facing the eye */
    /* auto */
    float fov_deg;          /* FM3_TRIPLE_FOV, each screen's vertical FOV; 0 = the camera's own */
    float angle_deg;        /* FM3_TRIPLE_ANGLE, turn to a side screen; 0 = one screen's width */
    float bezel_deg;        /* FM3_TRIPLE_BEZEL, degrees added to the turn */
    /* switches */
    int   narrow;           /* FM3_TRIPLE_NARROW: game keeps the centre screen's FOV (experiment) */
    int   flip;             /* REGPU_TRIPLE_FLIP: negate b and c for a mirrored clip x */
} fir_triple_layout;

static inline fir_triple_layout fir_triple_layout_default(void)
{
    fir_triple_layout l;
    l.mode = FIR_TRIPLE_AUTO;
    l.diag_in = 27.0f; l.dist_cm = 60.0f; l.bezel_mm = 0.0f; l.gap_mm = 0.0f;
    l.angle_left_deg = 0.0f; l.angle_right_deg = 0.0f;
    l.fov_deg = 0.0f; l.angle_deg = 0.0f; l.bezel_deg = 0.0f;
    l.narrow = 0; l.flip = 0;
    return l;
}

static inline float fir_triple_maxf(float a, float b) { return a > b ? a : b; }
static inline float fir_triple_minf(float a, float b) { return a < b ? a : b; }

/* Eye-space tangents of a screen's picture corners (max |x|/z, |y|/z); 0 if a corner is
 * beside or behind the eye. */
static inline int fir_triple_extent(const fir_triple_screen *s, float *tan_x, float *tan_y)
{
    const float c = cosf(s->yaw), sn = sinf(s->yaw);
    const float us[2] = { s->l, s->r };
    for (int i = 0; i < 2; i++) {
        const float x = us[i] * c + s->d * sn, z = -us[i] * sn + s->d * c;
        if (z <= 1e-3f)
            return 0;
        *tan_x = fir_triple_maxf(*tan_x, fabsf(x) / z);
        *tan_y = fir_triple_maxf(*tan_y, s->half_h / z);
    }
    return 1;
}

/* The screen's view of the game's frustum (p00g, p11g: the game projection's x and y scales). */
static inline fir_triple_view fir_triple_view_of(const fir_triple_screen *s, float p00g, float p11g)
{
    const float a = 2.0f * s->d / (s->r - s->l), cs = (s->r + s->l) / (s->r - s->l);
    const float c = cosf(s->yaw), sn = sinf(s->yaw);
    fir_triple_view v;
    v.a = (a * c - cs * sn) / p00g;
    v.b = -a * sn - cs * c;
    v.c = sn / p00g;
    v.d = c;
    v.e = (s->d / s->half_h) / p11g;
    return v;
}

/* Physical layout (metres). turn_l / turn_r: the side screens' turn in from the centre plane. */
static inline void fir_triple__side(float phi, float hinge, float edge, float dist, float w, float h,
                                    fir_triple_screen *s)
{
    s->d = hinge * sinf(phi) + dist * cosf(phi);
    s->l = hinge * cosf(phi) - dist * sinf(phi) + edge;
    s->r = s->l + w;
    s->half_h = h * 0.5f;
}

static inline void fir_triple_physical_screens(const fir_triple_layout *L, fir_triple_screen out[3],
                                               float *turn_l, float *turn_r)
{
    const float diag = L->diag_in * 0.0254f;
    const float w = diag * 16.0f / sqrtf(16.0f * 16.0f + 9.0f * 9.0f), h = w * 9.0f / 16.0f;
    const float dist = fir_triple_maxf(0.2f, L->dist_cm * 0.01f);
    const float bezel = fir_triple_maxf(0.0f, L->bezel_mm * 0.001f);
    const float gap = fir_triple_maxf(0.0f, L->gap_mm * 0.001f);
    const float edge = bezel + gap * 0.5f; /* picture edge to the hinge between two screens */
    const float hinge = w * 0.5f + edge;   /* the hinge's distance from the centre line */

    /* "Facing the eye": the angle that puts the eye on the side screen's centre line (l + r = 0). */
    float lo = 0.0f, hi = 89.0f * FIR_TRIPLE_D2R;
    for (int i = 0; i < 40; i++) {
        const float mid = 0.5f * (lo + hi);
        fir_triple_screen s;
        fir_triple__side(mid, hinge, edge, dist, w, h, &s);
        if (s.l + s.r > 0.0f) lo = mid; else hi = mid;
    }
    const float facing = 0.5f * (lo + hi);
    const float want_l = L->angle_left_deg * FIR_TRIPLE_D2R, want_r = L->angle_right_deg * FIR_TRIPLE_D2R;
    *turn_l = want_l > 0.0f ? fir_triple_minf(want_l, 89.0f * FIR_TRIPLE_D2R) : facing;
    *turn_r = want_r > 0.0f ? fir_triple_minf(want_r, 89.0f * FIR_TRIPLE_D2R) : facing;

    out[1].yaw = 0.0f; out[1].d = dist; out[1].l = -w * 0.5f; out[1].r = w * 0.5f; out[1].half_h = h * 0.5f;
    fir_triple__side(*turn_r, hinge, edge, dist, w, h, &out[2]);
    out[2].yaw = *turn_r;
    fir_triple__side(*turn_l, hinge, edge, dist, w, h, &out[0]);
    out[0].yaw = -*turn_l;
    { /* mirrored: its picture lies left of the hinge */
        const float l = out[0].l, r = out[0].r;
        out[0].l = -r;
        out[0].r = -l;
    }
}

/* Auto layout: all alike, unit distance, turned by `turn`; vs = each screen's vertical FOV. */
static inline void fir_triple_auto_screens(fir_triple_screen out[3], float vs, float turn)
{
    const float half_w = tanf(vs * 0.5f) * FIR_TRIPLE_ASPECT, half_h = tanf(vs * 0.5f);
    for (int i = 0; i < 3; i++) {
        out[i].yaw = (float)(i - 1) * turn;
        out[i].d = 1.0f;
        out[i].l = -half_w;
        out[i].r = half_w;
        out[i].half_h = half_h;
    }
}

typedef struct fir_triple_result {
    fir_triple_view views[3];      /* 0 left, 1 centre, 2 right */
    fir_triple_screen screens[3];
    float game_fov_y;              /* radians: set the game camera to this while it renders (widened) */
    float p00g, p11g;              /* the widened game projection's x and y scales */
    float turn_l, turn_r;          /* radians */
    int   fits;                    /* 0: the outer edges did not fit in 166 degrees and are cut off */
} fir_triple_result;

static inline float fir_triple__hfov(float v) { return 2.0f * atanf(tanf(v * 0.5f) * FIR_TRIPLE_ASPECT); }

/* Everything TripleHandOff computes, without touching game memory.
 * camera_fov_y: the game camera's own vertical FOV (radians) before widening.
 * Returns 0 (and leaves *out untouched) when the FOV is implausible, as the original does. */
static inline int fir_triple_compute(const fir_triple_layout *L, float camera_fov_y, fir_triple_result *out)
{
    if (!(camera_fov_y > 0.05f && camera_fov_y < 3.0f))
        return 0;
    fir_triple_result r;
    r.turn_l = r.turn_r = 0.0f;
    if (L->mode == FIR_TRIPLE_PHYSICAL) {
        fir_triple_physical_screens(L, r.screens, &r.turn_l, &r.turn_r);
    } else {
        const float want_fov = L->fov_deg * FIR_TRIPLE_D2R, want_turn = L->angle_deg * FIR_TRIPLE_D2R;
        const float bezel = L->bezel_deg * FIR_TRIPLE_D2R;
        float vs = want_fov > 0.05f ? want_fov : camera_fov_y;
#define FIR_TRIPLE_TURN_FOR(v) ((want_turn > 0.0f ? want_turn : fir_triple__hfov(v)) + bezel)
        if (FIR_TRIPLE_TURN_FOR(vs) + fir_triple__hfov(vs) * 0.5f > FIR_TRIPLE_MAX_HALF) {
            float lo = 0.05f, hi = vs;
            for (int i = 0; i < 30; i++) {
                const float mid = 0.5f * (lo + hi);
                if (FIR_TRIPLE_TURN_FOR(mid) + fir_triple__hfov(mid) * 0.5f > FIR_TRIPLE_MAX_HALF) hi = mid; else lo = mid;
            }
            vs = lo;
        }
        r.turn_l = r.turn_r = fir_triple_minf(FIR_TRIPLE_TURN_FOR(vs), FIR_TRIPLE_MAX_HALF - fir_triple__hfov(vs) * 0.5f);
#undef FIR_TRIPLE_TURN_FOR
        fir_triple_auto_screens(r.screens, vs, r.turn_r);
    }

    /* The game's frustum: wide enough for every picture corner (16:9, so the wider of the two
     * needs decides), at most 166 degrees across. */
    float tan_x = 0.0f, tan_y = 0.0f;
    int fits = 1;
    for (int i = 0; i < 3; i++)
        fits &= fir_triple_extent(&r.screens[i], &tan_x, &tan_y);
    float tan_h = fir_triple_maxf(tan_x, tan_y * FIR_TRIPLE_ASPECT) * 1.01f;
    if (!fits || tan_h > tanf(FIR_TRIPLE_MAX_HALF)) {
        tan_h = tanf(FIR_TRIPLE_MAX_HALF);
        fits = 0;
    }
    if (L->narrow)
        tan_h = fir_triple_maxf(r.screens[1].r, -r.screens[1].l) / r.screens[1].d * 1.01f;

    r.p00g = 1.0f / tan_h;
    r.p11g = FIR_TRIPLE_ASPECT / tan_h;
    r.game_fov_y = 2.0f * atanf(tan_h / FIR_TRIPLE_ASPECT);
    r.fits = fits;
    for (int i = 0; i < 3; i++) {
        r.views[i] = fir_triple_view_of(&r.screens[i], r.p00g, r.p11g);
        if (L->flip) { r.views[i].b = -r.views[i].b; r.views[i].c = -r.views[i].c; }
    }
    *out = r;
    return 1;
}

/* Apply a view to a clip-space position exactly as ReGPU's vertex shader does. */
static inline void fir_triple_apply(const fir_triple_view *v, float clip[4])
{
    const float x0 = clip[0], w0 = clip[3];
    const float w1 = v->c * x0 + v->d * w0;
    clip[0] = v->a * x0 + v->b * w0;
    clip[1] *= v->e;
    clip[2] += w1 - w0;
    clip[3] = w1;
}

/* The same as a 4x4 (row-major, column vectors): clip' = M * clip.
 * Per-screen projection for the Scene API = M * P_wide, with the camera pose unchanged
 * (P_wide = the widened game projection in canonical NDC, Frame IR §4). */
static inline void fir_triple_clip_matrix(const fir_triple_view *v, float m[4][4])
{
    m[0][0] = v->a; m[0][1] = 0.0f; m[0][2] = 0.0f; m[0][3] = v->b;
    m[1][0] = 0.0f; m[1][1] = v->e; m[1][2] = 0.0f; m[1][3] = 0.0f;
    m[2][0] = v->c; m[2][1] = 0.0f; m[2][2] = 1.0f; m[2][3] = v->d - 1.0f;
    m[3][0] = v->c; m[3][1] = 0.0f; m[3][2] = 0.0f; m[3][3] = v->d;
}

#ifdef __cplusplus
} /* extern "C" */
#endif

#endif /* FIR_TRIPLE_VIEW_H */
