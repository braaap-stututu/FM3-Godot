/*
 * triple_camera.h — Godot camera settings for the triple-screen views of core/triple_view.h.
 *
 * Godot 4.7's Camera3D (and RenderingServer camera) has no custom projection matrix setter.
 * A triple screen's projection is an off-axis frustum on a plane turned about the eye, which
 * Godot expresses exactly as:
 *   - the game camera's transform turned about its own up axis by the screen's yaw, and
 *   - frustum mode: set_frustum(size, offset, near, far) with keep_aspect = KEEP_HEIGHT.
 *
 * From Godot 4.7.2's Projection::set_frustum(size, aspect, offset, near, far, flip_fov=false)
 * (core/math/projection.cpp) with aspect = the viewport's width / height:
 *   left = -size*aspect/2 + offset.x, right = +size*aspect/2 + offset.x,
 *   bottom = -size/2 + offset.y,      top = +size/2 + offset.y      (near-plane units)
 * A screen's picture spans l..r across its plane at distance d and ±half_h vertically, so at the
 * near plane n: left = n l / d, right = n r / d, bottom/top = ∓ n half_h / d. Hence
 *   size = 2 n half_h / d,  offset = (n (l + r) / (2 d), 0)
 * which is exact when the viewport's aspect equals (r - l) / (2 half_h), i.e. 16:9 for every
 * FM3 layout (fir_triple_camera.aspect says which aspect the viewport must have).
 *
 * The same screen's projection in ReGPU (fir_triple_apply on the widened game frustum) gives the
 * same x/w and y/w; see tests/triple_camera_test.c. Depth differs (Godot uses its own near/far),
 * so compositing compares linear view depth along each screen's forward, which both renderers
 * share (CORE.md §10).
 *
 * REGPU_TRIPLE_FLIP is not used here: these settings come from the screens' geometry in Godot's
 * own convention (+X right, +Y up, looking down -Z), not from a clip-space view.
 *
 * Header-only C99 / C++. Needs core/triple_view.h.
 */
#ifndef FIR_GODOT_TRIPLE_CAMERA_H
#define FIR_GODOT_TRIPLE_CAMERA_H

#include <math.h>
#include "../core/triple_view.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct fir_triple_camera {
    float yaw;          /* radians, the screen's turn (right positive), as in fir_triple_screen */
    float local_rot_y;  /* radians, rotation about the camera's local +Y to apply in Godot (= -yaw) */
    float size;         /* Camera3D.size / RenderingServer.camera_set_frustum size (near-plane height) */
    float offset_x;     /* Camera3D.frustum_offset.x (near-plane units) */
    float offset_y;     /* Camera3D.frustum_offset.y */
    float z_near, z_far;
    float aspect;       /* the viewport aspect (width / height) this frustum needs, 16:9 for FM3 */
} fir_triple_camera;

/* Godot settings for one screen. z_near / z_far: the renderer's clip planes (the game's or our own). */
static inline fir_triple_camera fir_triple_camera_of(const fir_triple_screen *s, float z_near, float z_far)
{
    fir_triple_camera c;
    c.yaw = s->yaw;
    c.local_rot_y = -s->yaw; /* Godot: rotating by +t about +Y turns -Z (forward) toward -X (left) */
    c.size = 2.0f * z_near * s->half_h / s->d;
    c.offset_x = z_near * (s->l + s->r) / (2.0f * s->d);
    c.offset_y = 0.0f;
    c.z_near = z_near;
    c.z_far = z_far;
    c.aspect = (s->r - s->l) / (2.0f * s->half_h);
    return c;
}

/* All three screens of a computed layout (0 left, 1 centre, 2 right). */
static inline void fir_triple_cameras(const fir_triple_result *r, float z_near, float z_far, fir_triple_camera out[3])
{
    for (int i = 0; i < 3; i++)
        out[i] = fir_triple_camera_of(&r->screens[i], z_near, z_far);
}

/* A screen camera's camera-to-world transform from the game camera's (row-major 3x4, column
 * vectors, Frame IR §4 convention: columns 0..2 = basis X Y Z, column 3 = origin):
 *   screen = game * RotY(local_rot_y)   (turn about the camera's own up axis, same eye point) */
static inline void fir_triple_camera_transform(const float game[3][4], const fir_triple_camera *c, float out[3][4])
{
    const float cs = cosf(c->local_rot_y), sn = sinf(c->local_rot_y);
    /* RotY(t) = [[cs,0,sn],[0,1,0],[-sn,0,cs]] */
    for (int row = 0; row < 3; row++) {
        const float gx = game[row][0], gy = game[row][1], gz = game[row][2];
        out[row][0] = gx * cs - gz * sn;
        out[row][1] = gy;
        out[row][2] = gx * sn + gz * cs;
        out[row][3] = game[row][3];
    }
}

#ifdef __cplusplus
} /* extern "C" */
#endif

#endif /* FIR_GODOT_TRIPLE_CAMERA_H */
