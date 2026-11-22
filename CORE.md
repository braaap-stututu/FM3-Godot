# Core internals — v0.1 draft

The core turns a stream of Frame IR frames into a persistent scene, decides what the
new renderer owns, drives the renderer through the Scene API, and composites the
original renderer's leftovers on top.

Related: [SPEC.md](SPEC.md) (input), [PROFILES.md](PROFILES.md) (rules),
[ASSETS.md](ASSETS.md) (database), [SCENE_API.md](SCENE_API.md) (output).
Status: **draft for review**.

---

## 1. Responsibilities

1. Ingest Frame IR and track session state (handles → resources).
2. Determine the camera(s) of each frame.
3. Classify every draw (category, static/dynamic, owning object).
4. Keep a persistent scene: static world from the world manifest, dynamic instances
   from objects and draws.
5. Resolve materials and assets through the database.
6. Decide claims and send `CLAIM_RULES`.
7. Interpolate to render time and build per-screen views.
8. Drive the renderer and composite the original layers.
9. Report pacing back to the frontend.

## 2. Threads

```
ingest thread      reads the forward ring, validates records, updates handle tables,
                   writes captures, produces an immutable FrameSnapshot per frame
scene thread       FrameSnapshot → camera, classification, object association,
                   scene reconciliation, observations, claims (≤ game frame rate)
render thread      at display rate: interpolate, build views, push Scene API updates,
                   render, composite, present, PRESENT_FEEDBACK
worker pool        asset conversion, DB writes, assembly, upgrade passes (background)
```

Hand-off between threads is by immutable snapshots (single-producer queues). The render
thread never waits for the scene thread: it renders the newest scene state it has,
interpolated to its own time.

## 3. Ingest

- **Handle tables** per resource kind, per session. `TEXTURE_CONTENT` and `GEOMETRY`
  bind handles to content ids; the core looks those up in the DB asynchronously.
- **Unknown content** (not in DB): store raw data (worker), schedule fast-path
  conversion, mark the asset pending. Pending assets render as soon as fast conversion
  is done (usually within a frame or two); until then, draws that use them are **not
  claimable** (§8), so the original renderer keeps drawing them.
- **Validation:** records referencing unknown handles, wrong sizes or out-of-range blob
  refs are dropped and counted; a frontend bug must not crash the core.
- **Capture:** the ingest thread can tee the stream to a `.fir` file at zero parse cost.

## 4. Camera determination

Per frame, the main camera comes from the first available source:

1. **Profile `CAMERA` (role main).** Authoritative.
2. **Dominant observed view:** among perspective `VIEW`s used in passes targeting the
   backbuffer (or the largest offscreen target later copied to it), the one with the
   most draws × screen coverage.
3. **Estimated from combined matrices:** when draws are `COMBINED_ONLY`, find the
   view-projection shared by static geometry: for draws whose `geometry_id` is known to
   be static with a known world placement (from the manifest), `combined · model⁻¹`
   gives the frame's view-projection; take the consensus. Decompose into view and
   projection (assuming no skew).

Secondary cameras (mirrors, rear view) come from profile `CAMERA` roles or from views
used in passes whose target is later sampled as a texture (§5).

Recovering `model` for `COMBINED_ONLY` draws: `model = (P·V)⁻¹ · combined`, with P and
V from the chosen camera. Marked estimated.

## 5. Draw classification

Every draw gets: category, `static`/`dynamic`, owning object (if any), and the pass
role it belongs to. Order:

1. **Profile rules** (`rule.draw`, PROFILES.md §9), first match wins.
2. **Annotations:** draws inside an `ANNOTATE` range take its category.
3. **Structural heuristics:**

| Signal | Classification |
|---|---|
| `space == SCREEN`, or orthographic view, or depth test off in the backbuffer pass after the 3D content | `hud` |
| Pass target usage `shadow`, or depth-only target later sampled with comparison | `shadow` (not rendered; the renderer makes its own shadows) |
| Pass target later sampled as a texture by world draws | `reflection` / render-to-texture (secondary view) |
| Full-screen triangle/quad sampling a previous target | `post` (not rendered; native post replaces it) |
| Drawn first, depth write off, huge bounds, centered on camera | `sky` |
| Small camera-facing quads, blended/additive, volatile geometry | `particle` |
| Remaining 3D draws | world candidates → step 4 |

4. **Static vs dynamic:** a `geometry_id` seen at the same world matrix in ≥ N frames
   (and never moving) is `world_static`; otherwise dynamic. Draws in the world manifest
   are static by definition.
5. **Object association** (§6) for dynamic draws: `vehicle`, `character`, … from the
   object kind.
6. Anything left is `unknown`: it stays on the original renderer and counts against
   coverage.

Categories `shadow` and `post` are never reproduced; they are replaced by the
renderer's own shadows and post-processing once the corresponding world content is
claimed.

## 6. Object association and the persistent scene

### Static world
- When `ENVIRONMENT.level_id` changes, load that level's world manifest (if it exists)
  and its lighting set; create Scene API instances for every placement.
- Without a manifest yet, the static world is built live from observations and
  promoted to a manifest by the assembler later.

### Dynamic instances
- **With profile objects:** each `OBJECT` is a scene object with its model (ASSETS.md
  §4.2). Draws are associated to an object when their `model` matrix equals the object
  transform times a part offset (within an epsilon), or when the draw's `instance_key`
  matches. Matching draws update the model's part list; parts move with their driving
  parameters.
- **Without profile objects:** instances are tracked by `geometry_id` + transform
  continuity (nearest previous transform within a threshold, greedy assignment per
  geometry id). Good enough for props and NPCs until a profile exists.
- **Lifetime:** a profile object lives while its `OBJECT` is reported; a draw-only
  instance is retired after K frames unseen. Objects visible only on side screens stay
  alive because the profile keeps reporting them even when the game culls their draws.

### Materials
Material resolution is cached per `(state_hash, texture content ids)`: profile
`rule.material` first, then archetype heuristics (blend mode, alpha test, texture
count, program family), then `legacy` built from the first texture and vertex colors.

## 7. Interpolation

- Every dynamic object (and the camera) keeps a short ring of samples
  `(sample_time, transform, bones?, params)`.
- The render thread picks `render_time = newest_sample_time − delay`, with `delay` one
  sample interval, and interpolates between the two samples around it: translation
  linear, rotation slerp, scale linear, decomposed per transform; bones per bone.
- Samples flagged `CUT` / `TELEPORTED` are not interpolated across.
- **Latency:** interpolation costs one sample interval. With frame-rate samples (60 Hz)
  that is ~16.7 ms; with physics-rate samples from a profile hook (e.g. 360 Hz) it is
  ~2.8 ms. Racing profiles should sample at physics rate.
- Optional extrapolation mode (`delay = 0`, predict from velocity) for latency-sensitive
  users, at the cost of small corrections on direction changes.

## 8. Claims

Claims decide what the original renderer stops drawing. Two constraints shape them:

1. **The frontend can only match on what it knows at draw time** (state hash, geometry
   id, texture id, target usage, its own annotations and category hint, job type). The
   core's categories are not known there. So the core compiles category-level claims
   into **hash sets**: every `geometry_id` / `state_hash` it has classified into a
   claimed category, resolved and ready. These sets are sent as `CLAIM_RULES`
   (thousands of entries is fine; the frontend keeps a hash set).
2. **Exactly-once drawing.** A draw must be drawn by the original renderer or the new
   one, never both and never neither. The frontend marks every draw it suppressed with
   `FIR_DRAW_SUPPRESSED`, and reports the claim generation it applied in
   `FRAME_BEGIN`. The core reproduces exactly the suppressed draws for the main view
   (plus everything outside the game's view for side screens). A draw that newly
   appears is not in any claim set yet, so it is drawn by the original renderer that
   frame and claimed from the next one: no flicker, no gaps.

Stage activation: a profile `claim_stage` is enabled when the user turns it on and its
categories' coverage is above a threshold (e.g. 98 % of their draws resolved). Stubs
that `require_claim` the stage switch on only after that.

**Safety lease:** if the frontend receives no reverse packet for a configured time
(e.g. 250 ms — core crashed or stalled), it drops all claims and stubs and renders
everything the original way. The game stays playable when the core dies.

## 9. Views and multi-screen

**Decision (2026-11-22): the core uses FM3-ReGPU's triple-screen math**, ported to
[`core/triple_view.h`](core/triple_view.h) (MIT, attribution in the header), until a
better solution is found. Tests: [`core/triple_view_test.c`](core/triple_view_test.c).
The port was checked against the original code on seven layouts (identical results) and
against a direct projection onto each screen's plane.

- **Layout settings** are the launcher's existing "Triple screens" settings, unchanged:
  `FM3_TRIPLE_MODE` (`auto` or `physical`); physical: `FM3_TRIPLE_DIAG` (inches),
  `FM3_TRIPLE_DIST` (cm), `FM3_TRIPLE_BEZEL_MM`, `FM3_TRIPLE_GAP_MM`,
  `FM3_TRIPLE_ANGLE_LEFT` / `_RIGHT` (0 = facing the eye); auto: `FM3_TRIPLE_FOV`,
  `FM3_TRIPLE_ANGLE`, `FM3_TRIPLE_BEZEL`; plus `FM3_TRIPLE_NARROW` and
  `REGPU_TRIPLE_FLIP`. The core fills a `fir_triple_layout` from them.
- **Per frame:** `fir_triple_compute(layout, camera_fov_y)` gives the widened game FOV
  (the profile hook sets it on the game camera while it renders, as the FM3 hand-off hook
  does today) and three `fir_triple_view`s (left, centre, right).
- **Scene API views:** each screen's camera pose is the game camera's own pose; its
  projection is `M · P_wide`, where `P_wide` is the widened game projection and `M` comes
  from `fir_triple_clip_matrix`. That is the same clip-space transform ReGPU applies in
  its vertex shaders (`x' = a x + b w`, `w' = c x + d w`, `y' = e y`, `z' = z + w' − w`),
  so both renderers produce the same pixels and the same depth on every screen.
- In Godot, `Camera3D` has no custom-matrix setter. Because `M · P_wide` is an
  asymmetric frustum turned about the eye, it maps exactly onto a frustum-mode camera
  turned about its own up axis by the screen's yaw, with `size = 2 n half_h / d` and
  `frustum_offset = (n (l + r) / 2d, 0)`, `KEEP_HEIGHT`, on a 16:9 viewport. Implemented
  in [`godot/triple_camera.h`](godot/triple_camera.h) (numbers) and
  [`godot/triple_cameras.gd`](godot/triple_cameras.gd) (applies them to a `Camera3D` or a
  RenderingServer camera RID, and builds the three SubViewports). Verified in Godot 4.7.2
  headless: real cameras project test points to within 5e-7 NDC of ReGPU's views.
- Each screen is 16:9 and rendered at a third of the spanned width, as in ReGPU. The HUD
  goes on the centre screen only.
- In the Godot backend each screen is a `SubViewport` with a frustum-mode `Camera3D`
  (SCENE_API.md §11).
- **Consequence for compositing:** a frontend that draws only the game's one view can
  give an `UNCLAIMED_WORLD` layer for the centre screen only; side screens then show only
  claimed content until the world is fully claimed.
- **FM3 is better off (FM3-ReGPU, `REGPU_TRIPLE`, session 39):** the game camera is
  widened at the hand-off so culling covers all three screens (frustum up to 166°), and
  ReGPU replays the main view's draws once per screen with `regpu::triple::View` (a
  turn about the eye plus an off-axis projection; layout from the launcher's physical or
  auto settings). It can therefore emit one `COMPOSITE_SURFACE` per screen, each with
  its own `VIEW`. If the core builds its per-screen views with the same code and
  settings, every screen depth-composites, and triple-screen works at every claim stage.
  Each claim also removes those draws from all three replays, so ReGPU's draw thread
  (the triple-screen bottleneck: ~9,000 draws, ~130 fps vs ~300 centre only in the grid
  test) gets lighter stage by stage.

## 10. Compositing

Per screen, back to front:

1. Renderer output (3D world, effects, post).
2. `UNCLAIMED_WORLD` layer, if this screen's view matches the layer's view: depth-tested
   against the renderer depth after converting both to linear view depth.
3. `HUD` layer on the configured screens, placed per its rect; optional safe-zone
   scaling so the HUD isn't stretched across a 32:9 centre region.

The renderer waits on each layer's timeline semaphore before sampling. Composite cost
target: ≤ 0.1 ms.

## 11. Pacing

- Once the game's own present is stubbed or suppressed, the game must not pace itself
  on vsync. The frontend paces game ticks to the game's native rate (from
  `nominal_tick_hz` or the original present interval) and uses `PRESENT_FEEDBACK` only
  for diagnostics and display refresh.
- The render thread runs at display refresh (or uncapped), independent of game ticks.
- If the scene thread falls behind (e.g. a capture session), the render thread keeps
  interpolating with the samples it has and flags the frame in stats.

## 12. Diagnostics

Per frame, the core exposes: draw counts per category and per resolution state
(resolved / pending / unknown), claimed vs suppressed counts (must be equal),
legacy-material share, camera source used, interpolation delay, sample age, and the
claim generation. The IR viewer and debug views (SCENE_API.md §10) read these.

## 13. Open questions

1. **Thresholds.** N frames for static detection, K frames for retirement, epsilons for
   placement dedupe and object association: tune on FM3 captures.
2. **Claim set size limits.** If a frontend can't afford large hash sets per draw
   (emulators), allow coarser rules (by state hash only) with a coverage check first.
3. **Mirror views.** Rear-view mirrors are secondary cameras with their own claims;
   until claimed they stay in the original HUD/RTT path. Is that acceptable visually
   when the main view is new?
4. **Partial-claim triple-screen.** Show side screens only once a stage covering the
   world is claimed, or show what exists? Probably a user setting.
