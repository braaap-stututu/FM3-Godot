# Game profiles — v0.1 draft

A **profile** is everything game-specific the system needs that a platform frontend
cannot work out by itself: where the camera and cars live in memory, which draws are
the HUD, which shader is car paint, which SPU jobs are render-only, how to switch off
culling for capture, and when it is safe to stop calling the game's own renderer.

This spec closes open question 8 of [SPEC.md](SPEC.md). The code-facing API is in
[`profile_api.h`](profile_api.h).

Status: **draft for review**, nothing implemented.

---

## 1. Goals

1. **Mostly data.** A typical game profile is TOML files: addresses, pointer chains,
   struct layouts, match rules. Code is the exception, for logic data can't express.
2. **Safe to share.** Community profiles must not be able to run arbitrary native code
   or quietly write game memory. Code runs in a sandbox and every patch is declared.
3. **Portable across hosts.** One FM3 profile works in the recomp and in an emulator
   frontend for the same platform, and one ProStreet profile works in the 32-bit proxy.
4. **Layered.** Platform, library and engine knowledge is written once and inherited:
   Sony Edge for many PS3 games, RenderWare for many PS2/Xbox games, the XDK D3D layer
   for every X360 title.
5. **Verifiable.** Every hook claim can be checked automatically against what the GPU
   actually saw, and every "safe to skip" claim against a deterministic replay.
6. **No game data.** Profiles hold addresses, offsets, hashes, rules, original code
   and shaders. Never textures, meshes, audio or copied game code.

## 2. Where a profile runs

A profile has two halves that load from the same package but run in different places:

| Half | Runs in | Contents | Why there |
|---|---|---|---|
| **Frontend half** | The game process (recomp, emulator, or 32-bit proxy) | Builds/addresses, probes, hooks, patches, job skip classes, render stubs | Needs direct access to guest memory and code |
| **Core half** | The core process | Draw/material rules, schemas, claim stages, renderer extensions (shaders), lighting set references | Needs the scene, the asset DB and the renderer |

The halves never talk directly. The frontend half produces Frame IR semantic records
(`CAMERA`, `OBJECT`, …); the core half consumes Frame IR and the rules. Claims are the
only thing the core sends back, via `CLAIM_RULES`.

## 3. Package layout

```
profiles/
  platform/xbox360/            # base for every X360 title
  platform/ps3/
  lib/sony-edge/               # shared middleware knowledge
  lib/xdk-d3d9/
  engine/renderware-3/
  game/fm3/
    profile.toml               # manifest: identity, inheritance, capabilities
    builds.toml                # per-executable addresses / signatures
    probes.toml                # declarative memory reads → Frame IR records
    hooks.toml                 # code hooks, patches, stubs (declarations)
    rules.toml                 # draw classification, materials, jobs, claim stages
    schemas.toml               # parameter block layouts
    hooks/fm3.wasm             # optional sandboxed code (+ src/ alongside)
    shaders/*.slang            # optional renderer extensions
    lighting/                  # references to bake sets (bakes are generated locally)
```

Replacement asset packs (hash-keyed textures/meshes/materials made by people) are a
separate package type and are not part of a profile.

### 3.1 Manifest

```toml
# profile.toml
id       = "game:fm3"
name     = "Forza Motorsport 3"
version  = "0.1.0"
platform = "xbox360"
extends  = ["platform:xbox360", "lib:xdk-d3d9", "engine:forzatech"]
titles   = ["4D5308AB"]              # platform title ids this profile may match

[world]                              # fills SESSION_BEGIN conventions
handedness      = "right"
up_axis         = "+y"
units_per_meter = 1.0

[requires]                           # host capabilities (§7); missing ones disable features
capabilities = ["mem_read", "hook_entry", "patch"]
optional     = ["hook_replace", "hook_exit"]

[code]
module = "hooks/fm3.wasm"            # omit for a data-only profile
```

(The title id and numbers above are placeholders, not real values.)

### 3.2 Inheritance and merging

Profiles resolve as a chain: `platform → lib/engine (in extends order) → game → build
overrides → user overrides`. Merge rules:

- Tables merge by key; later layers win.
- Rule arrays (`[[rule.*]]`, `[[probe]]`, `[[hook]]`, …) concatenate with the
  **later layer first**, so game rules take priority over engine rules.
- Every array entry has an `id`. A later layer can `disable = ["engine:forzatech/sky-1"]`
  or replace an entry by redefining its `id`.
- User overrides live outside the package (`user/<profile-id>.toml`) and are never
  distributed.

## 4. Builds and symbols

Addresses differ between regions, title updates and PC patches. All addresses in
probes and hooks are **symbolic** and resolved per build.

```toml
# builds.toml
[[build]]
id               = "us-1.0"
executable_hash  = "00000000000000000000000000000000"   # XXH3-128 of the executable
[build.symbols]
camera_manager   = 0x82000000      # placeholder addresses
car_list         = 0x82000100
render_frame     = 0x82100000
physics_step     = 0x82200000
cull_fov_scale   = 0x82300000

[[build]]
id = "pc-1.1"                      # PC builds may use signatures instead of fixed addresses
executable_hash = "…"
[build.symbols]
render_frame = { pattern = "55 8B EC 83 E4 F0 ?? ?? ?? ?? 56 57", offset = 0 }
car_list     = { pattern = "A1 ?? ?? ?? ?? 85 C0 74 ??", offset = 1, deref = true }
```

- A session matches a build by `executable_hash`. If none matches, the host may try a
  build whose symbols are all signatures (PC). Otherwise the profile loads
  **data-only**: rules still apply, probes/hooks are disabled, and the user is told.
- Symbols can be referenced as `addr:<name>` in any address field.

## 5. Probes (declarative memory reads)

Probes cover most semantic data without code: read a structure every frame (or at a
hook), convert it, emit a Frame IR record.

```toml
# probes.toml
[[probe]]
id     = "main-camera"
emit   = "camera"                  # CAMERA record
sample = "frame_begin"             # or "hook:<hook-id>"
role   = "main"
base   = "addr:camera_manager"
chain  = [0x0, 0x40]               # pointer chain: *(*(base+0x0)+0x40) → struct
[probe.fields]
camera_to_world = { at = 0x00, type = "mat4x4", layout = "row_vector", endian = "big" }
fov_y           = { at = 0x40, type = "f32", unit = "degrees", fov = "horizontal" }
near_z          = { at = 0x44, type = "f32" }
far_z           = { at = 0x48, type = "f32" }
cut             = { at = 0x50, type = "u8", flag = "FIR_CAMERA_CUT" }

[[probe]]
id     = "cars"
emit   = "object"
sample = "hook:physics-step-end"   # emit at physics rate, not frame rate
kind   = "vehicle"
# car_list: +0x0 pointer to an array of car pointers, +0x4 count
array  = { base = "addr:car_list", items = { at = 0x0, deref = true },
           count = { at = 0x4, type = "u32" }, stride = 0x4, element = "pointer" }
# element = "pointer": each array slot holds a pointer to the struct; "inline": the struct itself
key    = { at = 0x10, type = "u32" }
[probe.fields]
local_to_world   = { at = 0x100, type = "mat3x4", layout = "row_vector", endian = "big" }
linear_velocity  = { at = 0x140, type = "vec3", endian = "big" }
[probe.params]
schema = "fm3.car.v1"
wheel_spin   = { at = 0x200, type = "f32x4" }
wheel_steer  = { at = 0x210, type = "f32" }
suspension   = { at = 0x220, type = "f32x4" }
damage_zones = { at = 0x240, type = "f32x8" }
```

Field types: `u8/u16/u32/u64`, `i*`, `f32`, `f64`, `vec2/3/4`, `f32xN`, `mat3x4`,
`mat4x4`, `quat`, `hash32` (game-side ids), `cstring`. Every multi-byte field has an
`endian` (defaults to the platform's: big for X360/PS3/GC/Wii/Wii U, little otherwise).

Matrix `layout` options: `row_vector` (D3D style), `column_vector`, plus optional
`storage = "column_major"` and `basis = "<3x3 remap>"`. The host converts to Frame IR's
canonical convention. Unit options: `degrees`/`radians`, `fov = horizontal|vertical`.

Probe rules:
- A probe that hits an unmapped address or a null pointer in the chain emits nothing
  that frame and increments an error counter visible in the tooling. It never crashes
  the game.
- `sample = "hook:<id>"` makes the probe run inside that hook. Several samples per frame
  are emitted with their own `sample_time` (Frame IR §12).
- `when = { at = …, type = "u32", equals = 1 }` gates a probe on a game state value
  (e.g. only during a race).

## 6. Hooks, patches and stubs

Declared in `hooks.toml`. Declarations are data; behaviour is either built in or
provided by the profile's code module.

### 6.1 Hooks

```toml
[[hook]]
id      = "physics-step-end"
at      = "addr:physics_step"
kind    = "exit"                   # entry | exit | replace
action  = "sample"                 # built-in: fire probes with sample = "hook:<id>"
sim_dt  = 0.0027777                # optional: advance sample_time per call (1/360 s)

[[hook]]
id      = "level-load"
at      = "addr:load_track"
kind    = "exit"
call    = "on_level_load"          # function exported by the code module
```

- `entry` runs before the guest function, `exit` after it returns, `replace` instead
  of it (the guest function does not run unless the callback calls through).
- Built-in actions: `sample`, `emit_event` (with a fixed event name and a probe for
  params), `annotate_push`/`annotate_pop` (bracket everything the function draws
  with a category, e.g. around the HUD draw function).
- `call` invokes a code-module export with access to the call's arguments (§8).

### 6.2 Patches

Every write to game memory or code is a named, declared patch the user can see and
toggle.

```toml
[[patch]]
id          = "capture-no-cull"
description = "Disable frustum culling and track streaming for world capture"
when        = "capture_disable_culling"   # toggled by CAPTURE_CONTROL
writes      = [ { at = "addr:cull_fov_scale", type = "f32", value = 1000.0 } ]

[[patch]]
id          = "wide-cull"
description = "Widen culling so off-screen cars still update their draw state"
when        = "always"
writes      = [ { at = "addr:cull_fov_scale", type = "f32", value = 3.2 } ]
```

Code modules can only write memory through declared patches or declared writable
regions (`[[region]] at = … size = … writable = true`). The host enforces this.

### 6.3 Render stubs and job skips

The most dangerous things a profile can do, so they are separate and gated:

```toml
[[stub]]
id       = "skip-world-render"
at       = "addr:render_world"
replaces = "world"               # what the core must now provide
keep     = ["addr:update_streaming", "addr:update_audio_listener"] # side effects to call anyway
requires_claim = "world"          # only active when the core has claimed this stage
verified = false                  # §12: must be true before it is enabled by default
```

Job skip classes (PS3 SPU, PS2 VU1, …) live in `rules.toml` (§9) because the core also
needs them, but they follow the same `verified` rule.

## 7. Host capabilities

Hosts advertise what they can do; profile features that need a missing capability are
disabled with a warning.

| Capability | Static recomp | Emulator | PC proxy |
|---|---|---|---|
| `mem_read` | Yes | Yes | Yes |
| `mem_write` (patches) | Yes | Yes | Yes (with page protection changes) |
| `hook_entry` / `hook_exit` | Yes, via the recomp's function table | Emulator-dependent; may cost a JIT block exit | Yes, via detours |
| `hook_replace` | Yes, trivially | Emulator-dependent | Yes |
| `hook_hot` (cheap enough for thousands of calls/frame) | Yes | Usually no | Yes |
| `signature_scan` | Rarely needed | Yes | Yes |
| `call_guest` (call a guest function from a callback) | Yes | Emulator-dependent | Yes |

## 8. Code modules

When data is not enough (decoding a game's own entity system, computing a parameter
block, deciding at runtime which draw is which), the profile ships a code module.

**Format: WebAssembly (wasm32).** Reasons:
- Sandboxed: a module can only touch its own memory and the host API.
- One binary runs in a 32-bit proxy, a 64-bit recomp and on Linux.
- Any language that targets wasm32 works (C, C++, Rust, Zig). The reference SDK is C.
- Runtime: an embeddable one with AOT or JIT (e.g. WAMR); an interpreter is fine for
  per-frame logic but not for `hook_hot` callbacks.

**Exports** a module may provide (all optional):

| Export | Called |
|---|---|
| `fir_profile_load(build_index)` | Once after the build is resolved. Register dynamic hooks here |
| `fir_on_frame_begin(frame_index)` / `fir_on_frame_end` | Every frame |
| `fir_on_hook(callback_id)` | For hooks declared with `call = …` |
| `fir_on_capture(mode)` | When `CAPTURE_CONTROL` changes |
| `fir_on_unload()` | Session end |

**Imports** (host API, see `profile_api.h`): guest memory reads, writes into declared
regions, enabling/disabling declared patches, hook argument/return access, calling
guest functions (if the host can), emitting Frame IR semantic records, config values,
logging and timing.

Escape hatch: a **native plugin** (DLL/.so with the same exports and imports) for
trusted, performance-critical work. Hosts load native plugins only when the user
explicitly enables them per profile; shared profiles should not need them.

## 9. Rules (core half)

```toml
# rules.toml

# --- draw classification: sets Frame IR category for matching draws
[[rule.draw]]
id    = "hud-ortho"
match = { space = "screen" }
set   = { category = "hud" }

[[rule.draw]]
id    = "shadow-pass"
match = { target_usage = "shadow" }
set   = { category = "shadow" }

[[rule.draw]]
id    = "car-body"
match = { pixel_program = "00000000000000000000000000000000" }   # placeholder hash
set   = { category = "vehicle", instance_from = "object:nearest" }

# --- materials: original state → renderer material type + parameters
[[rule.material]]
id        = "car-paint"
match     = { pixel_program = "…" }
archetype = "car_paint"
textures  = { 0 = "albedo", 1 = "spec_mask", 2 = "env" }
params    = { clearcoat = 1.0, flake_density = 0.3 }
params_from_constants = { base_color = { at = 0x10, type = "vec4" } }

# --- jobs (PS3 SPU, PS2 VU1, ...)
[[rule.job]]
id       = "edge-skin"
match    = { job_type = "…" }
class    = "render_only"
replace  = "skin_linear"          # built-in, or "shader:<name>" from shaders/
inputs   = "lib:sony-edge/skin-v1" # schema describing the job's input block
verified = true

# --- claim stages: what the core takes over, in order
[[claim_stage]]
id     = "world"
claims = [ { category = "world_static" }, { category = "sky" } ]

[[claim_stage]]
id     = "cars"
after  = "world"
claims = [ { category = "vehicle" } ]
```

Match keys: `state_hash`, `vertex_program`, `pixel_program`, `texture` (content or
base id), `geometry` (geometry id), `target_usage`, `space`, `category`, `job_type`,
`annotation` (inside an `ANNOTATE` range with this label). Several keys in one `match`
must all hold. The first matching rule per kind wins (later layers come first, §3.2).

Hash literals are 32 hex characters (the 128-bit content hash, `hi` then `lo`).

## 10. Schemas

Parameter blocks (`OBJECT.params`, `EVENT.params`, `DEFORM.params`, job inputs) are
described so the core, renderer extensions and tooling can read them by name.

```toml
# schemas.toml
[schema."fm3.car.v1"]
fields = [
  { name = "wheel_spin",   type = "f32x4" },
  { name = "wheel_steer",  type = "f32"   },
  { name = "suspension",   type = "f32x4" },
  { name = "damage_zones", type = "f32x8" },
]
```

The Frame IR `schema` field is XXH3-128 of the schema name. Probe `params` are packed in
the schema's field order, little-endian, 4-byte aligned.

## 11. Renderer extensions

For effects the built-in renderer can't infer, a profile can ship shaders (Slang
source, compiled at install time to SPIR-V/DXIL) bound to a schema:

- `deform`: a compute shader implementing `FIR_DEFORM_PARAMS` (e.g. FM damage) or a
  skipped job's effect, reading the schema's params and the source geometry.
- `material`: a custom material for an archetype the renderer lacks.
- `effect`: an event-driven effect (tire smoke, sparks) spawned from `EVENT` records.

Extensions run on the GPU with no access to anything but their bound inputs, so they
fall under the same sharing rules as data.

## 12. Verification

Profiles make claims about the game; tooling checks them. A profile cannot set
`verified = true` on a stub or job skip without passing the relevant check.

| Check | What it compares | Catches |
|---|---|---|
| **Probe sanity** | Probes against a `.fir` capture: values finite, matrices orthonormal-ish, counts plausible | Wrong offsets, wrong endianness |
| **Camera agreement** | Hooked `CAMERA` vs the dominant observed `VIEW` per frame | Wrong layout/basis/FOV convention |
| **Object agreement** | Hooked `OBJECT` transforms vs `model` matrices of draws assigned to that object | Wrong struct, wrong key, wrong space |
| **Classification coverage** | Share of draws (and of pixels) classified per category | Missing rules before claiming a stage |
| **Replay determinism** | Recorded input replay with and without a stub/job skip; compare a game-state hash per tick | Skipped work that gameplay actually depended on |

Replay determinism requires the host to record and replay input and to expose a
game-state hash (a profile probe over the relevant state, or a host-provided memory
hash over declared regions).

## 13. Lifecycle

1. **Session start.** The frontend computes the executable hash and title id; the
   resolver picks the profile chain and build.
2. **Load.** Data merges; the code module (if any) instantiates; `fir_profile_load`
   runs; declared hooks and `always` patches install. `SESSION_BEGIN` is emitted with
   the profile id and world conventions.
3. **Each frame.** `frame_begin` probes run, then `fir_on_frame_begin`. During the
   frame, hooks fire (sampling probes, annotating, calling the module). At frame end,
   `fir_on_frame_end`, then `FRAME_END`.
4. **Claims.** When the core claims a stage, it sends `CLAIM_RULES`; stubs whose
   `requires_claim` is now active (and verified) switch on at the next frame.
5. **Capture.** `CAPTURE_CONTROL` toggles capture patches and calls `fir_on_capture`.
6. **Unload.** Stubs and patches are removed, `fir_on_unload` runs.

## 14. Distribution rules

- Allowed in a profile package: TOML, wasm modules (with source), shader source,
  documentation, hashes, addresses, signatures.
- Not allowed: anything extracted from a game (textures, meshes, audio, video, strings
  tables, copied code). The packager rejects binary files other than `.wasm`, and
  rejects wasm modules over a size limit without source.
- Lighting bakes and extracted assets are generated on the user's machine from their
  own copy and stored in the local asset DB, keyed by hash.

## 15. Open questions

1. **WASM runtime choice and `hook_hot` cost.** Need a measurement of call overhead
   for a hook fired a few thousand times per frame in the recomp, AOT vs interpreter.
2. **Emulator hooks.** Execution hooks in JIT emulators (RPCS3, PCSX2, Dolphin) range
   from cheap to very expensive. Per-emulator notes needed before relying on `exit`
   hooks for physics-rate sampling there.
3. **Game-state hash for replay.** Which regions count as gameplay state per game, and
   is a host-level hash of declared regions enough?
4. **Signature format.** Plain byte patterns with wildcards, or something richer
   (relative call following, multiple anchors) for PC titles with many patch versions?
5. **Profile identity for emulator users.** Emulators know title ids but not always a
   stable executable hash (e.g. PS2 ELF inside an ISO). Define the identity rule per
   platform.
