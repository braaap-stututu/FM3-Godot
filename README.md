# GodotRenderOffloadForRecomps

Make static recompilations of console games easier to run and more graphically flexible by offloading their rendering
to a **Godot** implementation that runs the recomp underneath: the game keeps its logic, the renderer gets a scene
(meshes, materials, lights, cameras) instead of emulating the console's GPU command by command.

This repository holds the **general** part: the plan, the specifications, the platform-independent core, the Godot
side, and the Xbox 360 / ReGPU capture tooling. Game-specific work lives in its own repositories that use this one as
their upstream; the first is **[FM3-Godot](https://github.com/braaap-stututu/FM3-Godot)** (Forza Motorsport 3 on the
ReGPU recomp), where the pipeline is being proven end to end.

## Contents

| Path | What |
|---|---|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | goal, structure and roadmap (milestones M0..M6) |
| [`SPEC.md`](SPEC.md) + [`frame_ir.h`](frame_ir.h) | Frame IR: what a platform frontend tells the core about each frame |
| [`SCENE_API.md`](SCENE_API.md) + [`scene_api.h`](scene_api.h) | Scene API: what the core tells the renderer; material archetypes |
| [`PROFILES.md`](PROFILES.md) + [`profile_api.h`](profile_api.h) | per-game profiles: hooks, probes, material rules, verification |
| [`ASSETS.md`](ASSETS.md), [`CORE.md`](CORE.md) | asset database and conversion; core threads, camera, classification, multi-screen, pacing |
| [`core/`](core) | core code (triple-screen view math, tested) |
| [`godot/`](godot) | Godot 4.7 project: triple-screen cameras, the G1 renderer benchmark, `viewer/compare.gd` (image comparison) |
| [`regpu/`](regpu) | patches for ReGPU (Xbox 360 GPU emulator used by the recomps): M0 measuring switches, the stage-1 frame tap |
| [`tools/fir_*.py`](tools) | Xbox 360 frame-capture tooling: read `.fir` captures, run Xenos vertex/pixel shaders (numeric + symbolic), recover camera and object transforms, export glTF with materials |
| [`profiles/fm3/`](profiles/fm3) | an example game profile (FM3's material rules by pixel-shader hash) |

Requirements: Python 3 + numpy for the tools; Godot 4.7.2 for the Godot project.

## Status (2026-11-22)

On FM3 the approach works: a captured frame and, increasingly, the game's own files render in Godot close to the
original (mean pixel difference ~20/255 against the recomp's screenshot of the same frame), and Godot draws the scene on
three 1440p screens at roughly twice the recomp's frame rate. Next for this repository: the live Frame IR stream from
the frontend (instead of offline captures), LibGodot embedding, and a second game.
