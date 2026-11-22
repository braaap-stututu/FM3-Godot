# Asset pipeline — v0.1 draft

How assets get from a running game into a form the renderer can use, and how they are
upgraded and replaced. Everything here runs on the user's machine against their own
copy of the game. Nothing produced from game data is distributed.

Inputs come from Frame IR ([SPEC.md](SPEC.md)); outputs feed the Scene API
([SCENE_API.md](SCENE_API.md)). Status: **draft for review**.

---

## 1. Goals

1. **Hash-keyed and local.** Every asset is stored under the 128-bit content hash from
   Frame IR §5, in a per-user database. The same game on two machines produces the same
   keys, so profiles and replacement packs (which contain only keys and original work)
   work everywhere.
2. **Capture first, extractors optional.** The default source is what the game draws.
   Per-game file-format extractors are allowed but never required.
3. **Never block the game.** Anything not converted yet renders through a fast
   fallback; conversion happens in the background.
4. **Reproducible.** Every derived file records the inputs and tool versions that made
   it, so changing a converter invalidates exactly what it affects.

## 2. Tiers

| Tier | What | Made by | Kept |
|---|---|---|---|
| **Raw** | Canonical decoded data exactly as Frame IR delivered it (textures in canonical formats, canonical vertices/indices) | Ingest | Always (source of truth) |
| **Converted** | Renderer-ready: BCn with mips, welded meshes with normals/tangents, lightmap UVs, LODs, assembled worlds and models | Converter (§5) | Rebuilt when converters change |
| **Upgraded** | Optional improvements: upscaled textures, estimated PBR maps, de-lit textures, smoothed meshes | Upgrade passes (§6) | User-controlled |
| **Replacement** | Hand-made assets from packs (§9) | People | Separate packages |

Runtime resolution order for any key: **replacement → upgraded → converted → raw
(converted on the fly with fast settings)**.

## 3. Database

```
assetdb/
  index.sqlite                 # metadata, observations, derived-artifact table
  objects/xx/xxxxxxxx….zst     # raw blobs, zstd, named by content hash
  derived/xx/xxxxxxxx….bin     # converted / upgraded outputs, named by artifact hash
  worlds/<level-id>/           # assembled world manifests + sections
  lighting/<level-id>/<set>/   # bake outputs (lightmaps, probes)
```

One database per user, partitioned by platform and title. SQLite for metadata (one
file, transactional, queryable by tools); blobs as files.

Main tables:

| Table | Key | Holds |
|---|---|---|
| `textures` | content_id | base_id, size, canonical format, native format, flags, first seen |
| `geometry` | content_id | geometry_id, counts, layout, bounds, volatile flag |
| `states` | state_hash | program ids, normalized fixed state, constants snapshot |
| `observations` | (asset, level, session, frame) | category, view, world matrix, instance key, screen coverage — sampled, not every frame |
| `materials` | (state_hash, texture set) | resolved material: archetype, params, texture roles, provenance (rule id / heuristic / manual) |
| `models` | model_id | assembled dynamic models (§4.2): parts, relative transforms |
| `derived` | artifact hash | source keys, tool + version, settings hash, output file |
| `levels` | level_id | name, world manifest version, capture coverage, lighting sets |

`artifact hash = XXH3-128(source keys ‖ tool id ‖ tool version ‖ settings)`. A converter
version bump makes old artifacts unreachable; a sweep deletes them.

## 4. Assembly: from draws to worlds and models

Frame IR gives draws; the renderer wants levels and objects.

### 4.1 Static worlds
1. Observations of draws classified `world_static` (CORE.md §5) are grouped by
   `ENVIRONMENT.level_id`.
2. Instances are deduplicated: same `geometry_id` at the same world matrix (within an
   epsilon) is one placement.
3. Placements are bucketed into spatial **sections** (e.g. 64 m cells) for streaming
   and culling, and merged per section and material where that reduces draw counts.
4. The result is a **world manifest**: sections, placements, materials, bounds, and a
   **coverage map** (which cells have been observed, from which directions).

The world is drawn from the manifest, not from what the game submits each frame. That
is what makes side screens and wider FOVs work without fighting the game's culling.

### 4.2 Dynamic models
Cars, characters and props are assembled from draws that the core associates with an
`OBJECT` (CORE.md §6):

- A **model** is the set of geometry ids drawn for one object, with each part's
  transform relative to the object. Parts that move on their own (wheels, doors,
  steering wheel) are recorded as separate parts with the object parameter that drives
  them (from the profile's schema, e.g. `wheel_spin[i]`).
- `model_id = XXH3-128(sorted part ids)`, plus the object kind and profile model name
  if the profile gives one (e.g. car id from game memory).
- Models let the renderer draw an object the game did not draw this frame (outside its
  frustum, i.e. on a side screen), as long as the profile still reports its `OBJECT`.

### 4.3 Coverage and capture sessions
Passive play fills the database over time but leaves holes (areas never looked at,
LODs never used). A **capture session** fills them:

1. The core sends `CAPTURE_CONTROL` with `FULL_DATA | DISABLE_CULLING`; the profile
   switches on its no-cull/no-stream patches (PROFILES.md §6.2).
2. The camera is driven through the level: by the user (free camera, if the profile
   provides one), by replaying a recorded lap, or by a profile hook that flies a spline.
3. The coverage map shows progress; capture stops when the target coverage is reached.

Profiles can declare per-level capture routes so this is one click per level later.

## 5. Conversion (raw → converted)

### Textures
- **Roles first.** Format choices depend on the role a material gives the texture
  (albedo, normal, mask…), so textures are converted after material resolution; until
  then the raw texture is used.
- Mip generation in linear space; alpha-coverage-preserving mips for cutout materials
  (foliage, fences) so they don't vanish at distance.
- Encoding: albedo → BC7 sRGB (BC1 if no alpha and the source was already BC1),
  normal → BC5, single-channel masks → BC4, HDR → BC6H. Sources that were already BCn
  stay BCn unless upgraded.
- Palette swaps: textures sharing a `base_id` share one converted base where the format
  allows (palette applied in the material as a lookup) — optional optimization.

### Geometry
- Weld duplicate vertices; drop degenerate triangles; strips are already lists.
- Normals: keep originals when present and plausible; otherwise generate with a
  smoothing angle (per profile/material).
- Tangents: MikkTSpace, only for materials with normal maps.
- **Lightmap UVs** for `world_static` geometry (xatlas or the backend's unwrapper),
  stored as `uv1`. Packed per section.
- **LODs:** use the original LOD meshes when captures show them (same object, distance-
  dependent geometry ids); otherwise generate with meshoptimizer simplification.
- Vertex cache / overdraw optimization (meshoptimizer), bounds.

### Fast path
On-the-fly conversion for assets seen for the first time this session: no BC encoding
(upload uncompressed), no tangents unless needed, no LODs. Good enough to draw
immediately; the full conversion replaces it when done.

## 6. Upgrade passes (optional)

All local, all opt-in, all recorded as derived artifacts so they can be undone.

| Pass | What | Notes |
|---|---|---|
| Texture upscaling | 2×/4× upscale of albedo and masks | Local models chosen by the user; never automatic downloads of anything game-specific |
| PBR estimation | Roughness/metallic/normal from albedo + material type | Heuristics per archetype first; ML estimators optional |
| De-lighting | Remove lighting painted into textures or prelit vertex colors | Needed because lighting is rebaked; see §7 |
| Normal from height | Normal maps from luminance/height for flat surfaces (asphalt, walls) | Per material, strength in params |
| Mesh smoothing | Subdivision or normal smoothing for very low-poly assets (PS1/PS2) | Per model, opt-in. Visual only; game collision is unaffected |

## 7. Baked-in lighting

Old games often store lighting in the assets: prelit vertex colors (very common on
PS1/PS2/N64/GC), lighting painted into textures, or lightmaps of their own. Since the
new renderer relights the world, double lighting must be avoided:

- **Vertex colors:** the material's `vertex_color_mode` decides: `MULTIPLY_ALBEDO`
  (genuine tint), `AMBIENT_OCCLUSION` (keep only the darkening as AO), `BAKED_LIGHT`
  (ignore for lighting, use as a bake hint), `IGNORE`. Classifier heuristics: vertex
  colors that vary smoothly with position and correlate with sun direction are lighting.
- **Original lightmaps** (a second texture multiplied in the original state): drop
  them, or keep them as an AO/occlusion hint for the new bake.
- **Painted lighting:** the de-lighting pass, or accept it and reduce bake contrast for
  that material. Per-material choice in the profile.

## 8. Lighting bakes

Input: a world manifest, resolved materials, the level's environment (sun per time of
day, sky), extracted lights, and the profile's lighting setup.

1. **Bake set definition** (profile or user): which time-of-day variants, quality,
   lightmap texel density, probe spacing.
2. **Reflection probe placement:** automatic along paths actually traveled in captures
   (camera and car positions — on a track, the racing line), plus a coarse grid.
3. **Bake:** with the Godot backend (decided 2026-11-22), using Godot's lightmap baker
   on a scene generated from the manifest. Outputs: lightmaps per section, irradiance
   probes, reflection probes.
4. Stored under `lighting/<level-id>/<set>/`, keyed by the hash of all inputs, so a bake
   is only redone when the world, materials or settings change.

Bakes run on the user's GPU and can take a while per level and time-of-day variant;
until a bake exists the renderer uses dynamic sun + probes from a quick low-quality bake.

## 9. Replacement packs

Hand-made assets that override game assets by key.

```
packs/hd-cars/
  pack.toml          # id, title(s), priority, compatible converter versions
  textures/<content_id or base_id>.ktx2|.png|.dds
  meshes/<geometry_id or model_id>.glb
  materials.toml     # material overrides by state_hash / texture id
```

- **Keys:** textures by `content_id` or `base_id` (all palette variants), meshes by
  `geometry_id` (positions match) or `model_id` (whole model), materials by
  `state_hash`.
- **Priority** between packs; user can reorder and disable.
- **Original-work check:** the packer refuses any file whose canonical hash matches an
  asset in the packer's own local database, so unmodified game assets can't be
  packaged by accident. (It can't prove originality; it stops the obvious case.)

## 10. Tools

One CLI, `fir-assets`, and the same functions in the IR viewer:

| Command | Does |
|---|---|
| `import <capture.fir>` | Ingest a capture into the database |
| `levels` / `coverage <level>` | List levels, show coverage maps |
| `assemble <level>` | Build or update the world manifest |
| `convert [--all\|<level>]` | Run conversion; `--fast` for the fast path only |
| `upgrade <pass> <scope>` | Run an upgrade pass |
| `bake <level> [--set <name>]` | Bake lighting |
| `materials <level>` | Show material resolution and `legacy` coverage |
| `pack <dir>` / `lint <pack>` | Build and check replacement packs |
| `gc` | Remove unreachable derived artifacts |

## 11. Open questions

1. **Observation volume.** Sampling rate for `observations` so the table stays small
   but assembly still finds every placement (every Nth frame plus every first sighting?).
2. **Hash stability of world geometry with CPU-side batching.** Some engines merge
   static meshes per frame on the CPU; `geometry_id` then changes with what is visible.
   Needs detection (volatile + large) and a fallback: capture-session-only assembly with
   culling disabled.
3. **Model assembly for damage.** If FM damage deforms meshes on the CPU, damaged
   geometry ids differ from intact ones; assemble from the intact state and apply
   damage via `DEFORM` instead.
4. **Bake time budget.** How many time-of-day variants per track are acceptable for a
   first-run experience, and should a low-quality bake run automatically?
5. **Extractor plugins.** Worth defining a plugin interface now, or wait until a game
   needs one?
