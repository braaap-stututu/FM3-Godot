# Architecture and roadmap — v0.1 draft

The goal: run as little of an old game as possible, and hand everything visual to a
modern renderer with converted assets and redone lighting. "Close to the original" is
the visual bar; improving on it is welcome. One system, many platforms: X360 first,
then PC (D3D9), PS3, Xbox, PS2, PS1.

This document ties the specs together and holds the plan. Specs:

| Spec | Defines |
|---|---|
| [SPEC.md](SPEC.md) + [`frame_ir.h`](frame_ir.h) | Frame IR: what frontends tell the core about each frame |
| [PROFILES.md](PROFILES.md) + [`profile_api.h`](profile_api.h) | Per-game profiles: hooks, probes, rules, verification |
| [SCENE_API.md](SCENE_API.md) + [`scene_api.h`](scene_api.h) | Scene API: what the core tells the renderer; material types |
| [ASSETS.md](ASSETS.md) | Asset DB, world/model assembly, capture sessions, conversion, upgrades, bakes, replacement packs |
| [CORE.md](CORE.md) | Threads, camera determination, classification, persistent scene, interpolation, claims, multi-screen views, compositing, pacing |
| [M1.md](M1.md) | The capture tap: stages, stage 1's Xenos-native records, first capture results, stage 2 (geometry, transforms, camera, glTF) |
| [GAME-LOGIC.md](GAME-LOGIC.md) | Game-logic CPU today, tracing tools, Pinyon Shift's findings, the route to native replacement |

---

## 1. Components and processes

```
┌──────────────── game process ────────────────┐      ┌──────────────── core process ─────────────────┐
│ recomp / emulator / 32-bit PC game            │      │                                               │
│   frontend (per platform)                     │      │  core                                         │
│     ├─ GPU/API tap  ──► Frame IR ─────────────┼─────►│   ├─ scene rebuilder (identity, cameras,      │
│     ├─ original renderer (ReGPU, D3D9, …)     │ ring │   │   categories, RTT detection)              │
│     │    draws unclaimed + HUD ─► shared img ─┼─────►│   ├─ asset DB (hash-keyed, local)             │
│     └─ profile frontend half                  │      │   ├─ material classifier                      │
│          probes, hooks, patches, stubs (wasm) │◄─────┼── ├─ claims → CLAIM_RULES                     │
│                                               │claims│   ├─ interpolation                            │
└───────────────────────────────────────────────┘      │   ├─ profile core half (rules, schemas)       │
                                                       │   └─ compositor                               │
                                                       │        │ Scene API                            │
                                                       │        ▼                                      │
                                                       │  renderer backend (Godot, later custom Vulkan)│
                                                       └───────────────────────────────────────────────┘
offline tools: IR viewer · capture/extract · asset converter · bake · profile check/verify/replay
```

- **Same process or split.** For recomps and emulators the core can live in the game
  process (rings are just memory). For 32-bit PC games it must be a separate 64-bit
  process. The interfaces are identical either way, so start split everywhere; merge
  later only if latency demands it.
- **Licensing.** Core, specs and SDKs under a permissive license (MIT) so frontends
  can live inside GPL emulators. Frontends inherit their host's license.

## 2. What runs where, per frame

1. Game ticks. Profile probes and hooks emit `CAMERA` / `OBJECT` / `ENVIRONMENT` etc.
2. The frontend taps the GPU/API stream and emits draws, states, views, passes, jobs.
3. The frontend's original renderer draws everything **not** suppressed by claims
   (eventually just the HUD) into a shared image.
4. The core updates its persistent scene from the frame, resolves assets from the DB,
   classifies materials, and records object samples for interpolation.
5. At its own rate (decoupled from 1–4), the core interpolates to render time, pushes
   scene updates through the Scene API, and the renderer draws every view.
6. The compositor lays the original renderer's layers (HUD, unclaimed world) over the
   renderer's output and presents.

## 3. Pilots

| # | Pilot | Proves |
|---|---|---|
| 1 | **FM3 recomp (X360)**, FM4 once its optimization settles | Core, Frame IR, compositor, renderer; claim stages end to end |
| 2 | **NFS ProStreet PC (D3D9c)** | Proxy DLL, 32→64-bit split, static world from DB, true triple-screen without fighting the game's culling |
| 3 | **GT6 recomp (PS3)** with the ReGPU team | Dual RSX + SPU tap, skipping render-only SPU jobs, Edge-style job identity |
| 4 | Xbox (original) | XDK D3D8 symbol detection reused from the X360 approach |
| 5 | PS2 | View-space recovery from 1/w, VU1 microprogram profiles |
| 6 | PS1 | GTE hooks |

Rule for every pilot after the first: **the core must not need a redesign.** If it
does, the spec was wrong; fix the spec, bump the version, and record why.

## 4. Milestones

| # | Milestone | Exit criteria |
|---|---|---|
| M0 | **Triple-screen cost breakdown** on FM3 (single 1440p already hits the 360 fps engine cap; triple falls to ~127): profile ReGPU CPU, GPU and game render code at triple settings, plus a stubbed-submission run | Known share of the triple-screen frame the new renderer removes; game render code cost for the wide view measured |
| M1 | **Read-only capture tap in ReGPU** (opt-in, compiled out by default) + `.fir` writer | One full race frame captured; capture replays deterministically |
| M2 | **IR viewer** | Step through a capture: draws, hashes, spaces, views, passes, categories |
| M3 | **Core v0**: scene rebuilder + asset DB + classifier, running on captures | Captured track becomes a persistent scene with stable ids across 1000 frames |
| M4 | **Renderer v0** (Godot backend) behind the Scene API | Captured FM3 track renders standalone with `legacy` + `standard` materials |
| M5 | **Live loop**: profile probes (camera, cars), claims, compositor | FM3 playable: new track, original cars and HUD composited |
| M6 | **Cars + interpolation + multi-view + baked lighting** | FM3 beats its old ~127 fps triple-1440p ceiling and looks "close or better" |
| M7 | **ProStreet frontend** | ProStreet at M5 level with no core redesign; triple-screen from DB world |
| M8 | **GT6 frontend** (when the recomp reaches a race) | GT6 at M5 level; at least one SPU job class skipped and verified by replay |
| M9 | **Custom Vulkan backend** if Godot capped M6 | Same scenes, higher fps, same Scene API |
| M10+ | Xbox, PS2, PS1 frontends | Each at M5 level on one game |

**M0 done 2026-11-22: go.** FM3's triple frame (7680×1440, 4x MSAA, frozen grid) runs at ~146 fps and is bound by
ReGPU's draw thread alone: the same with no GPU work (R6) or a quarter of the pixels (R4). With ReGPU's drawing removed
(R7) FM3 reaches the 360 cap (347 fps on 2 cores). G1: Godot draws three 2560×1440 views of 10,000 instances at ~427 fps.
Hyper cull as a cheap alternative dropped triple to 93 fps. Raw data and scripts: `m0/results-2026-11-22/`; table and
decision in the FM3 plan doc's M0 tab. Consequence for M1: claimed draws must leave ReGPU's draw thread before
translation (~0.75 µs each today), and the tap's own cost per draw must stay well below that.

**M1 stage 1 done 2026-11-22** (M1.md): ReGPU captures FM3's frames to `.fir` files (Xenos-native records); first
capture verified, 98.6-100 % of draws stable across frames by content, draw order not stable, no cost when off.

**M1 stage 2 transforms done 2026-11-22** (M1.md): vertex shaders run offline give 94.5 % of a frame's draws their
clip positions (matching a screenshot); one camera (53.00 deg, exact rotation) and per-object world matrices recovered;
the frame exports as glTF and renders in Godot from the captured camera. FM3's scene target reaches the screen rotated 180 deg. Materials from the pixel shaders plus first FM3 material rules
(profiles/fm3/materials.json); a lit Godot render looks like the game. Triple screen from a triple capture: Godot draws the
grid frame on three 1440p screens at ~289 fps with 4x MSAA and shadows (merged meshes; ReGPU 146) - see M1.md.

M0–M2 do not touch FM4 work and can start immediately. M1's tap is passive, so it
cannot slow ReGPU when disabled.

## 5. Performance budget (FM3, 7680×1440 @ 360 fps target)

2.78 ms per rendered frame for the renderer, on the user's GPU. Indicative split, to be
replaced by measurements in M6:

| Item | Budget | How |
|---|---|---|
| Scene update from core | 0.2 ms CPU | Retained scene; only dynamic instances change per frame |
| Culling + submission, 3 views | 0.3 ms CPU | Static world in a BVH; multiview (one pass, 3 view matrices) where possible |
| Opaque + shadows | 1.2 ms GPU | Baked lighting for the static world; one cascaded sun shadow for cars |
| Transparent, particles | 0.4 ms GPU | |
| Upscaler + post | 0.6 ms GPU | Render below output resolution, temporal upscale |
| Composite + present | 0.1 ms GPU | |

The game itself (logic, physics, probes, original HUD rendering) runs on its own
threads at its own rate and is measured separately in M0.

## 6. Key risks

| Risk | Mitigation |
|---|---|
| Hash instability (dynamic vertices, streamed textures, palette swaps) | `geometry_id`/`base_id`, volatile flags, anchors via `OBJECT` keys |
| Logic depending on the render path (streaming, camera update, readbacks) | `keep` lists on stubs; replay determinism checks |
| Skipping gameplay-relevant jobs (PS3/PS2) | `verified` gate + replay checks |
| Effects built on framebuffer tricks | Rebuild natively; leave on the original path until then |
| Renderer performance at 7680×1440 high fps | Scene API keeps the backend swappable (M9) |
| PS2 VU1 diversity | 1/w fallback works without per-game work; profiles for quality |
| Scope creep across platforms | Pilot order; no new platform before the previous reaches M5 level |

## 7. Decisions

| Date | Decision | Why |
|---|---|---|
| 2026-11-22 | **Godot stays the first and main renderer backend.** Triple-screen starts as three SubViewports with frustum-mode cameras; the custom Vulkan backend stays the M9 fallback, triggered only by M6 measurements | Fastest route to visible results and tooling; no engine does single-pass triple-screen anyway, so measure before committing to a custom renderer. Godot 3-view multiview patch remains the middle option |
| 2026-11-22 | **Triple-screen views use FM3-ReGPU's `regpu::triple::View` math**, ported to `core/triple_view.h`, with the launcher's existing `FM3_TRIPLE_*` settings | Identical views to ReGPU's triple replay, so unclaimed content depth-composites on every screen at every claim stage. Kept until a better solution is found |

## 8. Next planning steps

1. Review all five specs with the ReGPU team (open questions are listed per spec).
2. M0 test plan for FM3, once the recomp source is available in a session.
3. M1 design inside ReGPU: where the capture tap hooks in, and what it costs when on.
