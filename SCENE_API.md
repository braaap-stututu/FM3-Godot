# Scene API — v0.1 draft

The Scene API is the only thing a renderer backend implements. The core owns the
scene; the renderer draws it. The renderer never sees Frame IR, platform formats,
original shaders or profiles.

C interface: [`scene_api.h`](scene_api.h). Status: **draft for review**.

---

## 1. Principles

1. **Retained, not immediate.** Meshes, materials, instances, lights and views persist
   until destroyed. A typical frame changes only dynamic instance transforms, a few
   parameters and the cameras. Static worlds are uploaded once.
2. **Batched updates.** The core records changes into an update list and hands it to the
   renderer once per render frame (`apply`), then calls `render`. Backends may consume
   the list on a render thread.
3. **Material types, not shaders.** Every material is one of a small fixed set of
   archetypes (§5) plus parameters. Backends implement each archetype once. This is
   what lets one renderer serve every platform.
4. **The core interpolates; the renderer extrapolates nothing.** The core supplies the
   transform for the render time and the previous one (for motion vectors). The
   renderer does no game-time logic.
5. **Shaped like Godot's RenderingServer.** Handle-based and retained, so the Godot
   backend is a thin mapping. A custom Vulkan backend implements the same calls.

## 2. Objects

| Object | Created from | Lifetime |
|---|---|---|
| **Texture** | Asset DB (canonical/upgraded data, BCn), or a shared image (composite layers, RTT) | Until destroyed; usually per level |
| **Mesh** | Asset DB geometry: submeshes, each with a default material; optional LODs; optional lightmap UVs | Per level (static) or per session (cars, characters) |
| **Material** | Archetype + parameter block + texture slots by role | Until destroyed |
| **Instance** | Mesh + transform + flags + optional material overrides, skinning, morphs | Static: per level. Dynamic: per object |
| **Light** | Directional, point, spot, area; baked or dynamic | Per level or per object |
| **Environment** | Sky, sun, ambient, fog, exposure, baked lighting set, probes | One active per scene |
| **Probe** | Reflection or irradiance probe placement (baked data from the lighting set) | Per level |
| **Effect** | An emitter of a built-in or extension effect type, spawned from `EVENT`s | Short-lived |
| **View** | Camera + projection + output region + render settings | Per output screen / RTT |
| **Layer** | A 2D image composited over a view (original HUD, unclaimed world) | Per frame contents, persistent handle |

All handles are 32-bit, `0` = none, unique per type within a session.

## 3. Frame flow

```
core thread                              renderer (may be its own thread)
-----------                              --------------------------------
scn_begin_update(list)
  create/update/destroy calls ...
scn_end_update(list)
renderer->apply(list)          ───────►  consume changes
renderer->render(&frame)       ───────►  cull, draw every view, composite layers, present
renderer->stats(&s)            ◄───────  timings for PRESENT_FEEDBACK and tooling
```

`scn_frame` carries render time, frame index, per-view jitter (set by the backend's
upscaler and reported back), and the debug mode.

## 4. Views and multi-screen

- Each output screen is a **view** with its own camera pose and projection. For triple
  screens the core builds them with FM3-ReGPU's math (`core/triple_view.h`, CORE.md §9):
  pose = the game camera's, projection = `M · P_wide`. Otherwise from the main `CAMERA`
  plus the user's display layout:
  - **Physical layout**: screen widths, bezel size, angle between screens, eye
    distance. Produces correct off-axis projections for angled monitors (the "true"
    triple-screen look), not one stretched frustum.
  - **Output**: one spanned surface (Surround/Eyefinity) with three viewports, or one
    window per screen.
- Views can share a pass. Backends should render views with identical settings using
  multiview (`VK_KHR_multiview` or equivalent) so the scene is culled and submitted
  once for all three screens.
- **RTT views** render into a texture instead of the screen, for mirrors, rear-view
  mirrors and in-game screens. A material references the RTT texture. The core
  creates these when it recognizes the original game's RTT passes (Frame IR §10).
- Per-view settings: resolution scale, upscaler, max shadow distance, LOD bias,
  whether it receives layers (HUD on the centre screen only, for example).

## 5. Material archetypes (v0)

One parameter block (`scn_material_params`) covers all archetypes; each archetype
reads only the fields listed. Texture slots are by role.

| Archetype | Used for | Reads | Texture roles |
|---|---|---|---|
| `legacy` | **Fallback for anything unclassified.** Looks like the original: texture × vertex color with simple lighting | `base_color`, `vertex_color_mode`, `alpha_mode` | `albedo` |
| `unlit` | Signs, screens, billboards that should not be relit | `base_color`, `emissive_strength` | `albedo` |
| `standard` | Most opaque surfaces: metal/roughness PBR | `base_color`, `metallic`, `roughness`, `normal_scale`, `occlusion_strength`, `emissive` | `albedo`, `normal`, `orm`, `emissive`, `detail` |
| `car_paint` | Vehicle bodies | standard + `clearcoat`, `clearcoat_roughness`, `flake_density`, `flake_scale`, `flake_color` | `albedo` (livery), `normal`, `orm`, `mask` |
| `glass` | Windows, headlight covers | `base_color` (tint), `roughness`, `transmission`, `ior` | `albedo`, `normal`, `mask` (dirt) |
| `foliage` | Trees, grass, bushes | standard + `translucency`, `wind_strength`, two-sided | `albedo` (cutout), `normal` |
| `skin` | Drivers, characters | standard + `subsurface_color`, `subsurface_radius` | `albedo`, `normal`, `orm` |
| `water` | Water, puddles | `base_color`, `roughness`, `depth_fog`, `wave_scale`, `flow` | `normal`, `mask` |
| `terrain` | Blended ground layers | up to 4 layers × (`base_color`, `roughness`) | `albedo0..3`, `normal0..3`, `mask` (splat) |
| `decal` | Tire marks, liveries on separate geometry, posters | `base_color`, `alpha_mode`, `normal_scale` | `albedo`, `normal` |
| `emissive` | Lamps, brake lights, displays | `emissive`, `emissive_strength` | `emissive` |
| `particle` | Smoke, sparks, dust (lit or unlit) | `base_color`, `alpha_mode`, `soft_distance`, `lit` | `albedo` |
| `sky` | Sky domes, skyboxes | `emissive_strength` (intensity) or procedural atmosphere | `albedo` (cube/equirect) |
| `extension` | Profile-supplied shader (PROFILES.md §11) | extension blob | any |

Common fields for every archetype: `alpha_mode` (opaque, cutout with
`alpha_cutoff`, blend, additive, premultiplied), `cull` (back, front, none),
`vertex_color_mode` (ignore, multiply albedo, as ambient occlusion, as baked light),
`uv_transform` (scale/offset/rotation, plus scroll speed for animated textures).

Why `legacy` matters: the classifier will never cover everything on day one. Anything
it cannot place renders as `legacy`, so a scene is never missing geometry. Coverage
(PROFILES.md §12) measures how much of the frame is still `legacy`.

**Legacy environment maps.** Original games often fake reflections with a cube map in a
texture slot. The renderer uses real probes instead; the original env map is kept only
as a hint (`env_hint` role) for probe tinting or as a fallback when no probe exists.

## 6. Lighting

The renderer supports two lighting sources and mixes them:

1. **Baked** (default for static worlds): a lighting set per level and time-of-day
   variant, made offline from the captured world. It holds lightmaps (needs lightmap
   UVs, generated by the asset pipeline), irradiance probes for dynamic objects, and
   reflection probes (for a track, placed along the racing line). `scn_environment`
   names the active set; the core blends between time-of-day variants.
2. **Dynamic**: sun + a few local lights with shadows, for cars, characters and
   anything moving. Original lights extracted via Frame IR `LIGHT` records map here.

Optional later tier: ray-traced reflections/shadows/GI behind a per-view setting. Not a
requirement for any milestone.

## 7. Skinning, morphs, deformation

- `scn_instance_set_skin`: bone palette (3×4 matrices, object space) for this render
  frame plus the previous one for motion vectors. GPU skinning in the backend.
- `scn_instance_set_morphs`: morph target weights; morph targets are extra position/
  normal streams in the mesh.
- `scn_instance_set_extension_deform`: binds a profile compute shader (FM damage, a
  skipped PS3 job's effect) to the instance with a parameter block.

## 8. Effects

Built-in effect types: `smoke`, `dust`, `sparks`, `splash`, `debris`, `fire`, `skid`
(skid marks are decals generated over time). The core spawns them from Frame IR `EVENT`
records using profile mappings, with position, direction, intensity, color and a
source instance (so tire smoke follows its car). Profiles may also register extension
effects. Original particle draws remain on the original path until a profile claims the
`particle` category.

## 9. Layers (compositing)

A layer is a texture (usually a shared image from the frontend's original renderer)
placed over one or more views:

- `HUD`: drawn last, in screen space; placement per view (centre screen, or stretched
  across all with safe-zone rules).
- `UNCLAIMED_WORLD`: depth-tested against the renderer's depth when the core says the
  original depth matches the view (same camera); otherwise simple alpha layering.
- `FULL_FRAME`: debug/A-B only.

The renderer waits on the layer's timeline semaphore value before sampling it.

## 10. Debug modes

Every backend implements: normal, original-only (show `FULL_FRAME`), split A/B,
category false-color, archetype false-color (highlights `legacy`), asset id
false-color (hash-stability check), lightmap/probe visualization, wireframe,
overdraw. These are how classification and profiles are debugged.

## 11. Backend notes

**Godot (LibGodot, first backend).**
- The core drives `GodotInstance::iteration()` from its render loop; Godot does not
  own the main loop.
- Mapping: mesh → `RenderingServer` mesh; archetypes → a fixed set of shaders written
  once as Godot `ShaderMaterial`s; instances → instance RIDs on one scenario; lights →
  light RIDs; environment → `Environment` + sky; views → `SubViewport`s/cameras per
  screen; baked lighting → `LightmapGI` data produced by the bake tool; layers → a
  CanvasLayer per view drawing the shared texture.
- Watch: one instance per process; how shared Vulkan images get into Godot textures
  (likely needs a small engine patch or GDExtension).
- **Multi-screen in Godot (checked against the 4.7.2-stable source):**
  - Multiview is capped at **2 views**: `RendererSceneRender::MAX_RENDER_VIEWS = 2`,
    shaders `#define MAX_VIEWS 2`, and `render_camera` only handles 1 or 2 views from an
    `XRInterface`. It is built for VR stereo.
  - The combined culling frustum (`CameraData::set_multiview_camera`) requires exactly 2
    views and assumes two nearly parallel eyes (averaged plane normals, horizon plane).
    It would not give a usable frustum for three screens angled apart, so raising the
    constant alone is not enough.
  - Off-axis per screen *is* possible in stock Godot: `Camera3D` in
    `PROJECTION_FRUSTUM` mode with `frustum_offset` gives an asymmetric frustum; rotate
    each camera to its screen. No custom matrix setter exists.
  - Triple-screen cameras: `godot/triple_camera.h` + `godot/triple_cameras.gd` turn
    the core's per-screen views (CORE.md §9) into frustum-mode cameras, verified in
    Godot 4.7.2 against ReGPU's projection.
  - **Plan:** start with three `SubViewport`s + three frustum-mode cameras on stock
    Godot. Cost: three culls, three submissions, three sets of directional shadow
    cascades and post. Measure in M6. If too slow, either patch Godot for 3-view
    multiview (raise both limits, replace the combined-frustum code with per-view
    culling whose results are merged, audit effects that assume ≤2 views, feed views
    through a custom `XRInterfaceExtension`), or move to the custom Vulkan backend (M9).

**Other engines checked for single-pass multi-screen (2026-11-22):** none does it out
of the box. Unreal's nDisplay supports several off-axis viewports on one machine but
renders them as separate viewports, and Unreal is hard to embed under a recomp's loop.
Unity and Unreal single-pass stereo are two-eye VR paths. Filament (`main`) allows up to
4 stereo eyes with per-eye projections, but with one shared culling frustum and no
post-processing, shadows or punctual lights in stereo, so it is unusable for this. The
APIs themselves support it: Vulkan multiview (`maxMultiviewViewCount` is 6 on an AMD
RX 480 report, 32 on Mesa NVK) and D3D12 view instancing (up to 4 views). True
single-pass triple-screen therefore means a custom renderer or an engine patch.

**Custom Vulkan (M9, only if Godot caps performance).**
- Clustered forward, bindless textures, BC formats, GPU-driven culling over a static
  BVH, multiview for multi-screen, baked lightmaps + probes, one cascaded sun shadow,
  temporal upscaler integration (FSR/DLSS/XeSS) with motion vectors from previous
  transforms.
- Same Scene API; the Godot backend stays useful as the authoring/preview tool.

## 12. Open questions

1. ~~**Godot multiview.**~~ Answered (§11): not in stock Godot (2-view limit). Open
   part: is three separate viewports fast enough, or is a Godot patch cheaper than the
   custom backend? Decided by measurement in M6.
2. **Shared images into Godot.** External-memory Vulkan images as Godot textures:
   GDExtension, engine patch, or a copy (costs bandwidth at 7680×1440)?
3. **Archetype list.** Is 14 right? Candidates to add: `hair`, `cloth`, `tire`
   (rubber with sidewall text could be `standard`), `chrome` (`standard` with metallic
   1 may be enough).
4. **Time-of-day blending.** Blend between baked lighting variants, or bake a small
   number and drive the rest with the dynamic sun?
5. **LOD source.** Use original LODs from captures, generate new ones from the highest
   detail mesh, or both?
