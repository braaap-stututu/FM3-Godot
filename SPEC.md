# Frame IR — v0.2 draft

**v0.2 changes** (from [CORE.md](CORE.md) §8): `FIR_DRAW_SUPPRESSED` draw flag;
`fir_frame_begin.claim_generation` (record grows 40 → 48 bytes); claim matching and the
safety lease clarified in §11.

Frame IR is the data format between a **platform frontend** (a recomp, emulator tap,
or PC proxy DLL) and the **core** (scene reconstruction, asset DB, material
classification, lighting, interpolation, compositing). The renderer never reads
Frame IR; it reads the core's scene API.

```
frontend (per platform)  --Frame IR forward-->  core  --scene API-->  renderer
          ^                                       |
          +-------------Frame IR reverse----------+   (claims, acks, capture, pacing)
```

The binary layout lives in [`frame_ir.h`](frame_ir.h). This document defines the
meaning; where the two disagree, this document wins and the header is the bug.

Status: **draft for review**. Nothing here is implemented yet. Open questions are
collected in §15.

---

## 1. Scope

**In scope**
- Everything a frontend observes about a frame that the core needs to rebuild it as a
  persistent 3D scene: resources, geometry, material state, views, passes, draws.
- Game-level facts supplied by per-game profile hooks: cameras, objects, environment,
  lights, events.
- Platform work that exists to feed rendering (PS3 SPU jobs, PS2 VU1 programs, PS1 GTE
  ops), so the core can replace it and the frontend can skip it.
- The reverse channel the core uses to steer the frontend: which draws the original
  renderer should stop drawing, which content the core already has, capture control,
  present pacing.

**Not in scope**
- Executing original shaders. Original shader/combiner state is carried only as an
  identity (hash) plus raw bytes for classification and tooling.
- Being a graphics API. There is no command for "set render state"; state arrives as
  immutable, deduplicated state records.
- 2D-only games. A sprite-only frame can be carried (SCREEN space draws), but nothing
  in the core is designed around it.

## 2. Design principles

1. **One format, every platform.** A field exists only if at least two platform tiers
   can fill it, or if one priority target (PS3, PS2, PS1, Xbox, X360) needs it.
2. **Frontends normalize, the core interprets.** Frontends do all platform decoding:
   endian swaps, untiling, palette expansion, packed vertex formats, quads/fans/rect
   lists to triangles, NDC conventions. The core never sees a platform format except
   inside opaque "native" blobs it uses only for hashing and tooling.
3. **Identity is decided once, at the frontend, from native bytes.** Hashes are taken
   over the platform's original data before conversion, so they are stable across runs,
   frontend versions and machines. See §5.
4. **Immutable, deduplicated records.** Geometry, state and views are defined once and
   referenced by handle. Draws are small.
5. **Plain data, no pointers.** Every record is fixed-layout, little-endian, 8-byte
   aligned, with no implicit padding, so the same bytes work in a 32-bit game process,
   a 64-bit core process, and a capture file.
6. **Incremental adoption.** Nothing in Frame IR assumes the new renderer draws
   everything. Claims (§11) let the core take over one category at a time while the
   original renderer keeps drawing the rest.
7. **Optional richness.** A bare frontend that only emits draws must work. Hooks,
   jobs, deform data and semantics make results better but are never required.

## 3. Transport

### 3.1 Packets
All traffic is a sequence of **packets**. A packet is:

```
fir_packet_header | records... | blob area
```

- `direction` is `FIR_DIR_FORWARD` (frontend → core) or `FIR_DIR_REVERSE`.
- Records are back to back; each starts with `fir_record_header {type, flags, size}`
  where `size` includes the header and is a multiple of 8.
- The **blob area** holds variable-length data (texture bytes, vertices, constants,
  arrays). Records point into it with `fir_blob_ref {offset, size}`, offsets relative
  to the start of the blob area, 16-byte aligned. A blob ref with `size == 0` means
  "absent".
- In v0, a forward packet carries exactly one frame (`FRAME_BEGIN` … `FRAME_END`),
  optionally preceded by session or resource records. Reverse packets may be sent at
  any time.

### 3.2 Channels
- **In-process** (recomps, emulators): a pair of single-producer/single-consumer rings
  in shared memory; packets are written in place.
- **Out-of-process** (32-bit PC games): the proxy DLL writes packets into a
  cross-process shared-memory ring read by the 64-bit core process. Identical bytes;
  no serialization step. Budget ≤1 frame of latency.
- **Capture files** (`.fir`): the forward packets of a session written verbatim, plus a
  trailing index of packet offsets. The core can replay a capture with no game running.
  This is the basis for the IR viewer, regression tests and offline asset extraction.

### 3.3 Ordering
Within a forward packet, records are processed in order and may only reference
handles defined earlier in the session. Draw order inside a frame is the record order;
`fir_draw.seq` repeats it explicitly for tooling.

## 4. Conventions

| Topic | Convention |
|---|---|
| Endianness | Little-endian everywhere, including blobs in canonical formats |
| Strings | UTF-8, NUL-padded fixed arrays |
| Matrices | Column-vector math (`p' = M · p`), **row-major storage**. `fir_mat3x4` is the top three rows of an affine 4×4 |
| View matrix | World → view. View space is right-handed, +X right, +Y up, looking down −Z |
| Projection | View → clip. Clip/NDC: X right, **Y up**, **Z in [0,1]** (D3D style), reversed-Z allowed if `FIR_VIEW_REVERSED_Z` |
| World space | Whatever the game uses. Handedness, up axis and units are declared in `SESSION_BEGIN` (or by the profile), never converted by the frontend |
| Colors | Linear floats unless the field says otherwise; packed `rgba8` fields are sRGB-encoded |
| Time | `sim_time` and `sample_time` are seconds (double) on the game's simulation clock |
| Angles | Radians |

Frontends convert projection conventions (GL's [−1,1] depth, Vulkan's Y-down,
platform-specific depth encodings) into the canonical NDC. Handedness of view space is
normalized by the frontend as part of producing the view matrix; world space is not.

## 5. Identity and hashing

Everything the asset DB and replacement packs key on is a **128-bit content hash**
(`fir_hash128`), computed with XXH3-128 over **native identity bytes** defined per
resource below. Handles (`fir_handle`, u32) are per-session and never persisted.

### 5.1 Textures
- `content_id` = XXH3-128(native format id ‖ width ‖ height ‖ mip count ‖ native bytes
  of mip 0, *including* the palette for palettized formats).
- `base_id` = same, but *excluding* the palette. Lets a replacement cover every palette
  swap of a texture (team colors, damage tints), à la RTX Remix.
- **Resolved at first use, not at upload.** A texture may be uploaded in pieces or
  rewritten. The frontend emits `TEXTURE_CONTENT` the first time a texture is
  referenced by a draw after any modification. Content that changes every frame
  (render targets, video, procedural) is flagged `FIR_TEX_VOLATILE` and is never
  persisted.

### 5.2 Geometry
Geometry is a *derived* resource: the canonical vertices and indices for one draw's
range of the platform's buffers, under one vertex layout. Frontends do not send raw
buffers.
- `geometry_id` = XXH3-128(native position bytes ‖ native index bytes ‖ topology).
  Stable across changes to colors, UVs or normals — e.g. prelit vertex colors that
  change with time of day (common on PS2/N64/GC).
- `content_id` = XXH3-128(all native attribute bytes ‖ native index bytes ‖ native
  layout ‖ topology).
- The range hashed is the range the draw actually uses (base vertex, index range), not
  the whole buffer; many engines pack many meshes into one buffer.
- Geometry produced on the CPU every frame (particles, CPU skinning output, PS2/DC
  screen-space output) is `FIR_GEOM_VOLATILE`. Volatile geometry is never used as an
  asset identity; such draws should carry an `instance_key` or a `deform` instead.

### 5.3 State and programs
- `state_hash` in `fir_state` = XXH3-128 over the native state block and program ids.
  This is the material classifier's primary key.
- Program ids (`vertex_program`, `pixel_program`) = XXH3-128 of the native microcode,
  combiner configuration, TEV setup, GS blend/test registers — whatever the platform
  calls its shading program. Zero means fixed-function with no program.

### 5.4 Jobs
`job_type` = XXH3-128 of the job's code image (SPU ELF segment, VU microprogram
bytes), so the same job is recognized across sessions and, for shared middleware such
as Sony's Edge libraries, across games.

### 5.5 Deduplication
Frontends may omit a texture's or geometry's data blob (`FIR_CONTENT_DATA_OMITTED`)
only when the core has said it already holds that `content_id`, either via a
`CONTENT_KNOWN` reverse record or a manifest sent at session start. Otherwise data is
always sent the first time.

## 6. Record catalog

Forward records (frontend → core). "Who" says which frontends are expected to emit it.

| Group | Record | Purpose | Who |
|---|---|---|---|
| Session | `SESSION_BEGIN` / `SESSION_END` | Platform, title, executable hash, profile, world conventions | All |
| Frame | `FRAME_BEGIN` / `FRAME_END` | Frame and sim tick bracketing, sim time | All |
| Resources | `TEXTURE_CREATE`, `TEXTURE_DATA`, `TEXTURE_CONTENT` | Texture lifetime, canonical data, identity | All |
| | `GEOMETRY` | Canonical vertices/indices + identity | All |
| | `SHADER` | Native program bytes, for tooling only | Optional |
| | `RESOURCE_DESTROY` | End a handle's life | All |
| Targets | `TARGET`, `PASS_BEGIN`, `PASS_END`, `COPY` | Render targets, passes, resolves/copies | All |
| Drawing | `VIEW` | A view/projection pair as seen by the GPU | All |
| | `STATE` | Normalized fixed state + native program identity | All |
| | `DEFORM` | Skinning palettes, morph weights, opaque deform params | Optional |
| | `DRAW` | One draw call | All |
| Semantics | `CAMERA`, `OBJECT`, `ENVIRONMENT`, `LIGHT`, `EVENT`, `ANNOTATE` | Game facts from profile hooks or fixed-function state | Profiles |
| Jobs | `JOB` | Render-feeding platform jobs (SPU, VU1, GTE, SH4) | PS3/PS2/PS1/DC |
| Compositing | `COMPOSITE_SURFACE` | The original renderer's output layer for this frame | Frontends with an original renderer |

Reverse records (core → frontend):

| Record | Purpose |
|---|---|
| `CLAIM_RULES` | Which draws/jobs the original path should stop doing (§11) |
| `CONTENT_KNOWN` | Content ids the core already has; frontend may omit their data |
| `CAPTURE_CONTROL` | Start/stop full-data capture; ask the profile to disable culling/streaming |
| `PRESENT_FEEDBACK` | Display refresh, presented frame, renderer cost; for pacing |

Record type ranges: `0x0000–0x7FFF` forward, `0x8000–0xEFFF` reverse,
`0xF000–0xFFFF` private (platform- or game-specific; never required).

Private records in use: `0xF101–0xF105`, the Xenos-native records of ReGPU's capture tap stage 1 (registers, draw,
resolve, shader, data), defined in ReGPU `src/gpu/fir_tap.h` and described in [M1.md](M1.md). They carry what the
offline stage-2 converter turns into the canonical records above.

## 7. Coordinate spaces and transform recovery

Every draw declares the space its vertices are in, because platforms differ in how
much of the transform the GPU ever sees.

| `space` | Vertices are in | Transforms present | Typical source |
|---|---|---|---|
| `OBJECT` | Model space | `model` (object→world) + `view` | X360/Xbox/PC/GC/PSP/PS3 when matrices are separable |
| `WORLD` | World space | `view` | Pre-transformed world geometry, CPU-skinned output |
| `VIEW` | View space | `view.proj` | PS2/Dreamcast recovered from 1/w; some PC engines |
| `CLIP` | Clip space (x,y,z,w) | none needed | Shaders that only expose a combined MVP |
| `SCREEN` | Pixels + optional depth | none | HUD/UI, PS1 without GTE hooks |

Rules:
- If the GPU only ever sees a combined object→clip matrix (common with shader
  constants), the frontend sets `FIR_DRAW_COMBINED_ONLY`, fills `combined`, and the
  core recovers `model` by factoring out the frame's camera (from a `CAMERA` hook, or
  estimated from the dominant view). Recovered transforms are marked estimated.
- **PS2 / Dreamcast:** GS `Q` / PowerVR `1/w` gives per-vertex 1/w. With the
  projection's focal length (from a profile, or estimated from known geometry), the
  frontend unprojects to view space and emits `VIEW` space draws. World space then
  needs the camera: a `CAMERA` hook, or core-side registration of static geometry
  recognized by `geometry_id` across frames.
- **PS1:** with GTE hooks (RTPS/RTPT in a recomp are function calls), the frontend
  emits the pre-projection vertices and the GTE rotation/translation as `OBJECT`
  space. Without hooks, `SCREEN`.
- `view` and `model` values on draws are what the original GPU saw. Profile `CAMERA`
  and `OBJECT` records are authoritative when present; the core prefers them.

## 8. Semantics from profiles

These records come from per-game hooks (reading game memory, calling recompiled
functions) or from fixed-function hardware state that already means something.

- **`CAMERA`** — authoritative camera pose, FOV and clip planes, with a role (main,
  mirror, rear-view, cutscene). `FIR_CAMERA_CUT` disables interpolation across a cut.
  Multi-screen output is *not* expressed here: the core derives per-screen views from
  the main camera plus the user's display setup.
- **`OBJECT`** — a game object with a stable `instance_key`: kind (vehicle, character,
  prop…), world transform, velocities, parent, and a profile-defined parameter block
  (`schema` + `params`) such as wheel spin/steer/suspension, damage state, livery id.
  Objects let the core draw things the game culled (triple-screen side views) and
  sample motion at sim rate. `FIR_OBJECT_TELEPORTED` disables interpolation.
- **`ENVIRONMENT`** — level/track id, time of day, weather, sun, ambient, fog. Drives
  which baked lighting set the core loads and the renderer's sky/atmosphere.
- **`LIGHT`** — a light with a stable key. Source is fixed-function registers
  (GC/Wii, Xbox, PSP, D3D7–9 FF), a hook, mapped shader constants, or an estimate.
- **`EVENT`** — a named one-shot (tire smoke burst, sparks, splash, muzzle flash) with
  position/direction/params, so the renderer can spawn its own effects instead of
  drawing the original sprites.
- **`ANNOTATE`** — push/pop/mark around draw ranges with a category and label
  ("world", "hud", "post"). Overrides heuristic classification.

Profiles define parameter `schema` ids and their layouts; Frame IR carries them as
opaque blobs.

## 9. Jobs

Some platforms do render work outside the GPU. Frame IR reports that work so the core
can do it natively and the frontend can stop doing it.

| Platform | Unit | Typical render-only work |
|---|---|---|
| PS3 | SPU | Geometry culling, skinning, decompression (e.g. Edge), post-processing (MLAA-style AA, DoF, tonemap), sometimes lighting |
| PS2 | VU1 (also VU0 macro) | Vertex transform, lighting, clipping, GS packet building |
| PS1 | GTE | Perspective transform, lighting |
| Dreamcast | SH4 (`ftrv`) | Vertex transform |

A `JOB` record carries the job type, entry address, its raw input block, the
handles it produced (geometry/deform), a classification hint, and a disposition:

- `RAN` — the frontend ran it normally; the core may use the inputs for better
  identity (hash the job's *input* mesh, not its per-frame culled output) and the
  outputs as usual.
- `SKIPPED_REPLACED` — the frontend did not run it because a claim rule said so; the
  core must reproduce its effect (e.g. GPU skinning from the same inputs).
- `SKIPPED_IGNORED` — skipped, no replacement needed (e.g. original post-processing
  the new renderer does natively).

Classification (`RENDER_ONLY`, `GAMEPLAY`, `MIXED`, `UNKNOWN`) is profile data. A job
must never be skipped unless the profile marks it `RENDER_ONLY`; skipping gameplay
work breaks the game silently. Replay testing (§13) exists largely to catch this.

## 10. Targets, passes and copies

- `TARGET` declares a render target with a usage guess (backbuffer, offscreen color,
  depth, shadow, reflection, environment cube, post).
- `PASS_BEGIN` / `PASS_END` bracket draws into a set of targets, with clears.
- `COPY` covers resolves and copies: X360 EDRAM resolves, RSX surface copies, PS2 GS
  local-to-local transfers, PC `StretchRect`/`UpdateSurface`.

The core uses these to tell world rendering from shadow maps, reflections,
render-to-texture (mirrors, in-car screens) and post chains. Draws inside passes the
core does not reconstruct stay with the original renderer.

## 11. Claims and compositing

The core decides what the new renderer owns and tells the frontend with
`CLAIM_RULES`. Each rule matches on one of: category, `state_hash`, `geometry_id`,
texture `content_id`, target usage, or `job_type`; actions are `SUPPRESS_ORIGINAL`,
`KEEP_ORIGINAL`, or `SKIP_JOB`. Rules apply atomically at the next frame boundary
(`generation` increments).

- **Matching uses only what the frontend knows at draw time.** A category rule
  matches the draw's `category_hint` (set by frontend-side profile annotations), not
  the core's classification. The core turns its own category decisions into hash-set
  rules (CORE.md §8).
- **Exactly-once drawing.** The frontend sets `FIR_DRAW_SUPPRESSED` on every draw a
  rule suppressed and reports the generation it applied in
  `FRAME_BEGIN.claim_generation`. The core reproduces exactly those draws.
- **Safety lease.** If the frontend receives no reverse packet for a configured time
  (default 250 ms), it drops all claims, stubs and job skips and renders everything the
  original way.

The frontend's original renderer draws whatever is not suppressed and publishes it as
a `COMPOSITE_SURFACE`: a shared GPU image (OS handle), optional depth, the `VIEW` the
depth corresponds to, and a timeline semaphore value to wait on. Layers:

- `HUD_OVERLAY` — usually 2D, composited last.
- `UNCLAIMED_WORLD` — 3D content the core has not taken over; depth-tested against
  the new renderer's depth when the views match, layered otherwise.
- `FULL_FRAME` — the whole original frame (A/B comparison, fallback).

For PC proxies the original renderer is the real D3D9 runtime (or DXVK) drawing into a
shared surface.

## 12. Timing and interpolation

- `FRAME_BEGIN` carries the frame index, sim tick index and sim time. A frame
  normally corresponds to one presented original frame.
- `CAMERA`, `OBJECT` and `LIGHT` carry their own `sample_time`, so a profile can
  report physics-rate state (e.g. a 360 Hz car simulation) without tying it to the
  original frame rate.
- The renderer renders at its own rate. The core interpolates objects by
  `instance_key`, decomposing transforms into translation/rotation/scale, and never
  across `CUT` / `TELEPORTED` flags.
- `PRESENT_FEEDBACK` reports display refresh and what was presented, so frontends that
  paced on vsync can pace on something real once the original present is gone.

## 13. Frame lifecycle (example)

```
SESSION_BEGIN   platform=XBOX360 title=… profile=fm3
FRAME_BEGIN     frame=1042 tick=1042 sim_time=17.366
  ENVIRONMENT   level=<hash> tod=14.5
  CAMERA        role=MAIN pose=… fov=…
  OBJECT ×8     cars, with wheel/damage params
  TEXTURE_CONTENT ×3   (first use after upload)
  TARGET / PASS_BEGIN  shadow map
    STATE, GEOMETRY, DRAW …
  PASS_END
  COPY          resolve shadow → texture
  PASS_BEGIN    backbuffer
    VIEW
    ANNOTATE push "world"
      STATE, DRAW ×1800 (space=OBJECT)
    ANNOTATE pop
    ANNOTATE push "hud"
      DRAW ×120 (space=SCREEN)
    ANNOTATE pop
  PASS_END
  COMPOSITE_SURFACE layer=HUD_OVERLAY
FRAME_END
```

Replay: a `.fir` capture fed into the core must produce the same scene every time.
Comparing core output for a capture before and after a change is the main regression
test, and comparing game state with and without a claim set (with input replay) is how
skipped jobs are validated.

## 14. Platform coverage (pilots and priority targets)

| | X360 recomp | ProStreet PC (D3D9 proxy) | PS3 recomp (GT6) | Xbox | PS2 | PS1 |
|---|---|---|---|---|---|---|
| Hook point | Statically linked XDK D3D | `d3d9.dll` proxy, 32→64-bit bridge | RSX command stream + SPU job dispatch | XDK D3D8 (symbol DB) | VIF/VU1 + GS | GTE ops + GPU |
| Typical draw space | OBJECT / CLIP | OBJECT / CLIP | OBJECT (after SPU jobs) | OBJECT (FF) / CLIP | VIEW via 1/w, OBJECT with VU1 profiles | OBJECT via GTE hooks |
| Program identity | Xenos microcode hash | SM3 bytecode hash | RSX VP/FP hash | NV2A VP + register combiners | GS state + VU1 program hash | Fixed (GPU modes) |
| Lights | Shader constants (profile) | Shader constants (profile) | Shader constants / SPU (profile) | Fixed-function registers + constants | VU1 data (profile) | GTE light matrix |
| Jobs | — | — | SPU (essential) | — | VU1 (essential) | GTE |
| Copies | EDRAM resolves | StretchRect etc. | Surface copies | Surface copies | GS transfers | VRAM copies |
| Original renderer for compositing | ReGPU | Real D3D9 / DXVK | Recomp's RSX backend | Recomp/emu backend | Emulator GS | Emulator GPU |

## 15. Open questions

1. **Morph targets.** Carry morph target geometry as extra `GEOMETRY` handles listed
   in `DEFORM.params`, or a dedicated record? Needs a real case (facial animation, FM
   damage if it is morph-based).
2. **Hardware instancing.** v0 has `instance_count` + an array of `fir_mat3x4`.
   Enough for X360/PS3/PC; is per-instance color/params needed?
3. **Camera registration for PS2/DC.** Core-side or frontend-side? Core-side keeps
   frontends simple but needs `VIEW`-space geometry with stable `geometry_id`s, which
   per-frame VU1 output may not give without VU1 profiles.
4. **Multiple frames per packet / partial frames.** Do any targets need draws streamed
   before `FRAME_END` for latency (e.g. split the 32-bit bridge ring)?
5. **Compute / non-draw GPU work.** PS3 has none in the GPU sense, X360 memexport is
   rare; skipped for v0. Revisit if a target uses memexport for rendering.
6. **Shared-surface interop for D3D9.** D3D9Ex shared handles vs running the original
   path on DXVK and exporting Vulkan memory. Decide during the ProStreet pilot.
7. **Hash cost.** XXH3-128 on every first use is cheap, but large dynamic textures
   updated each frame must be flagged volatile by the frontend, or hashing will show
   up in profiles. Need a policy (size threshold + update frequency) per frontend.
8. ~~**Profile hook ABI.**~~ Specified in [PROFILES.md](PROFILES.md) and
   [`profile_api.h`](profile_api.h).
