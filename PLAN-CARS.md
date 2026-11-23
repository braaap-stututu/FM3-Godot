# Plan: car fidelity and all-content phase (2026-11-23)

## Status, 2026-11-23 evening (second PC): what the plan did not know, and what changes

The plan was drafted from GitHub `main` (2026-11-22). The same day the second PC built, in its local copy (now on
branch `live-mirror`; details in `LIVE.md` and `HANDOFF.md` sections 7-8):

- **Finding 6 is out of date:** the game streams its camera, cars and wheels live (FM3-ReGPU `src/hooks/live_camera.cpp`,
  `FM3_LIVE`); `world_view.gd --live` follows them (`live.cmd`, `tools/live/drive.ps1`: the user drives FM3 seen only
  through Godot). **Open question 1 answered.**
- **Placement (phase 2) is solved without any fit:** the car object's body matrix (+0x10) places carbin car space
  exactly (world = F (p M), 0.1-0.4 mm on the fitted cars); `fm3_track_export.py --car-matrices work\fir\grid-cars.json`
  builds all eight grid cars from their carbin (the five far ones included) and drops their captured low-detail
  draws. Far-car paint: the paint-shader material among each car's own draws (finding 1's mis-voted LOD materials).
- **Wheels (phase 2):** the game streams each wheel's matrix as drawn (car object +0x190.., spin and steering), so
  open question 5 is moot: no kinematics. Motion blur: the captured `blur_*` meshes fade in with speed (4-14 m/s), as
  this plan proposed. Still captured wheel meshes, not wheel-zip models.
- **Materials (phase 3), first pass, partly fitted:** `fm3_carpaint.gdshader` from the paint PS's structure and
  constants (c118 x **c119.x** colour scale, Fresnel power c216, highlight c189/c180, metallic by c191); the game's
  cube **is dynamic** (t6/t7 rendered every frame), so the viewer renders a live cube at the player car
  (`--live-cube`). `fm3_carglass.gdshader`: dark body, opacity 0.95, grazing reflections, **fitted** to the grid
  capture (`tools/car_regions.py`), not yet from GlassColor / GlassMaxOpacity / Fresnel*: the CR-X's
  `shadersettings.xml` overrides only `detail_glass_red`, so window glass takes the **fxobj defaults** (phase 0's
  `fm3_fxobj.py` is needed for it).
- **Shadows:** the sun was converted with the wrong mirror (fixed in `fir_world.py`).
- On this PC the CR-X and Eclipse zips are extracted whole (`work\assets\crx`, `eclipse`: `_lod0`, `_cockpit`, brakes,
  `.xds`, `shadersettings.xml`); the other cars only as main carbins (`work\assets\carbins`).

### Progress, 2026-11-23 night (commits 46fb847, 649e767, 81d2350 on `live-mirror`)

- **Phase 1 done:** `tools/fm3_carbin.py` reads every carbin to its last byte (510 car, 567 wheel; corrections in
  `FM3-FORMATS.md`: u32 + 1 byte after the shard indices, 32-bit strip restart 0xFFFFFF, symmetric bounds, vertex
  byte 20 = baked brightness).
- **Phase 2:** cars built from `<car>_lod0.carbin` (all eight grid cars' zips in `work\assets\cars\<car>\`, DLC ones
  out of the DLC packs), main-file LOD 1 only where LOD 0 lacks a part, the file's own normals; unmapped materials
  get the car's own `.xds` (nodamage / lights) and the export lists any left white.
- **Phase 0 (part) + 3 (glass):** `tools/fm3_fxobj.py` reads the 137 constant tables; window glass runs the game's
  formula with captured values (`fm3_carglass.gdshader`), glass diff 28.0 -> 22.1. Paint still partly fitted.
- **Phase 4 done for the in-car view:** `cockpit_<car>_...` nodes from `<car>_cockpit.carbin`, shown for the player
  car when the game's camera is the driver / cockpit one, with the exterior's no-shadow meshes (its own low-detail
  dash) hidden. Gauges on an opaque copy of `interior_lod0` (dark faces, white markings: alpha 0 there, which Godot's
  import would overwrite), unlit. CR-X in-car compare 37.8, dash crop 23.7: the cluster matches. **Needles turn**
  (commit 42d5212): each `<gauge>_min/_mid/_max` triple is one rigid rotation (export: `<out>_needles.json`, with
  carattribs.xml's TickMarks, param 0..1 <-> value: speed m/s, tach rpm); speed from the car's streamed speed (AI
  race: game ~88 km/h, Godot ~85), fuel full. **Next: rpm** in the stream (find it in the car object, add it to
  FM3K; FM3-ReGPU `live_camera.cpp`), then the tach follows (`needle_turn` in world_view.gd, NEEDLE_IDLE_RPM
  now). **rpm found and streamed, 2026-11-24:** the car-physics object keeps the engine speed at **+324** and the
  redline at **+452** (rad/s, as FH1R's ICarDynamics); found through the getters that multiply by 60/2pi (constant
  0x82000BEC; `sub_821ED218` = redline, the HUD's call returning to 0x821F2044 gives the player's object). FM3-ReGPU
  sends **"FM3E"** (player rpm + redline, `live_camera.cpp`); `world_view.gd` turns the tach with it (AI race,
  in-car: game and Godot both ~7,000 rpm). Dead ends on the way: **(earlier search, kept for the record)** the car object (vtable 0x820035A4 =
  `TRefCountedObjectThreadSafe<CCarPresentation@Presentation_Unified>`) holds no rpm in its first 0x2000 bytes;
  `CCarPresentation::SetGaugeInformation` (vtable slot 10 = `sub_8258D9D8`, args gauge index r4, pivot frame, value v1,
  forwards to the object at +0x1308 via `sub_8281CBE8`) was hooked and **never ran** in the in-car view (so not the
  per-frame needle path; maybe setup only). Whole-memory float scans while revving on the grid (clutch LB + right
  trigger, the HUD tach did move) gave only buffers and noise. Next ideas: the HUD tach (`CAnalogGauge@ForzaUI`,
  `CTelemetryHud@ForzaUI`) getters; the engine audio's rpm (strings `rpm_sample`, `audio_rpm_redline`); or read
  the drawn needle's transform. Not done: steering wheel turning (carattribs SteeringWheelAngleOverride), driver's hands / arms, mirror
  render targets.

**Revised order from here:** phase 1 (structural reader) first, with LOD0 bodies and the file's normals as its first
use (finding 1-2, and a likely cause of the paint's stripe on the Eclipse); then phase 0's fxobj and shadersettings
reading to replace the fitted glass and paint numbers; then the cockpit (phase 4); wheel-zip models and lights after.
Open questions 2-4 still stand.

Drafted by a planning agent from `HANDOFF.md`, `M1.md`, `FM3-FORMATS.md`, the tools, the Godot viewer and the
ForzaStudio-EVO research. Steps run on the PC with the game files. Findings 1 and 5 were spot-checked in the code.

## 0. Findings that shape the plan

1. **`fm3_car.parse` only sees LOD 1 of the main file.** `_SUB` (`tools/fm3_car.py:23`) ends in a literal
   `\x00\x00\x00\x01` (the LOD word), and `build_cars` (`tools/fm3_track_export.py:99`) opens only `<car>.carbin`, never
   `_lod0` or `_cockpit`. Near cars are LOD 1, not LOD 0. The far cars' captured LOD 2-5 index buffers find no
   entry, so they stay captured draws. M1's note that lower-detail models are "not in these files" is wrong.
2. **The parser is a regex scan, not a structural read.** It has no draw lists (see-through vs opaque pass), no
   HasTransparentMeshes, no normals (`smooth_normals` recomputes them), no UV1, lighting, damage word or bitangent.
   `_header_offset` is an `rfind` heuristic.
3. **Part selection is guessed.** `stock_parts` uses the captured variant, else `a`. `group_of` exempts `glass*`, `head*`,
   `tail*`, `mirror*` and `seat*`, so pairs like `headlightRdown` / `headlightRup` are both kept.
4. **Materials are not the game's.** They come from capture votes or flat colours in `profiles/fm3/car_materials.json`.
   `window` / `glass` are blue (0.006, 0.016, 0.03) at a constant alpha 0.5. `detail_glass_*` are flat colours with no
   texture. Everything is double-sided with culling off. Paint is a `StandardMaterial3D` with clearcoat 0.3 and one
   reflection probe updated once. No `.xds`, `textures.xml`, `shadersettings.xml` or `.fxobj` is read.
5. **Wheels:** `build_cars` skips `wheel` (`fm3_track_export.py:158`). Wheels stay captured world-space draws, and
   per-car meshes are merged per material, so there is no car node hierarchy.
6. **This repo has no live, driving or cockpit-camera code** (`world_view.gd` is a static viewer).
7. **ForzaStudio-EVO evidence, to verify on FM3 files:**
   - `shadersettings.xml` carries GlassColor, GlassMaxOpacity, Fresnel*, Cube*, BrakeColor and ReverseLightColor.
   - FM3 wheel LOD 0 has no `tire` mesh; the tyre is in the wheel's LOD 1+.
   - `Data_CarBody` has ModelWheelbase, ModelFront/RearTrackOuter, ModelFront/RearStockRideHeight and
     BottomCenterWheelbasePos*.
   - Samplers include LightsSampler, damageSampler and DamageGlassSampler.

## Phase 0: file-structure map and manifest (2-3 days, first)

These scripts in `tools/` are read-only on the game files and write to `out\manifest\`:

- `fm3_zip.py`: lists and reads zip members (method 21 via `fm3unzip` or ctypes), so nothing needs pre-extracting.
  Reads `Media\zipmanifest.xml` and the DLC `zipmount.xml`.
- `fm3_inventory.py`: walks Disc 1 `Media\` and the DLC zips and writes `media_tree.json`. Also generates
  `FM3-FILES.md`: each folder, what it holds, the tool that reads it, and its status. Covers Cars, Wheels, Brakes,
  Shared.zip, Shaders, Tracks, UI, DB, DigitalGauges, StringTables, Physics, Audio and the INI files.
- `fm3_db.py`: reads `gamedb.slt` plus the DLC merges. For each `Data_Car`:
  - MediaName, `Data_CarBody`, stock wheel (`List_Wheels`: zip, IsStock);
  - tyre width / aspect / rim (front and rear);
  - brakes, and which body-part variant is stock;
  - `CarPartPositions`, `CameraOverrides`.
- `fm3_fxobj.py`: reads `shaders_v11.fxobj` into technique, passes, VS/PS, the constant table (samplers, parameters,
  registers, defaults) and render states. Reuses `fir_xenos.py` / `fir_disasm.py`.
- `fm3_car_manifest.py`: one `cars/<MediaName>.json` per car, holding:
  - the three carbins and, per part, variant group, LODs, meshes (material, LOD, pass, transparent flag);
  - the brakes;
  - each material resolved as technique, then samplers, then `textures.xml`, then the file (per loadFlag);
  - `shadersettings.xml` over the fxobj defaults;
  - wheels, tyres, brakes and wheel positions from the database, plus the cockpit eye and livery masks;
  - a `problems` list.

**Acceptance:** every car gets a manifest, a summary counts what is unresolved, and `FM3-FILES.md` is committed (no game
data in it). Later phases read only the manifest.

## Phase 1: structural carbin reader (2-3 days; blocks 2-6)

Rewrite `fm3_car.py` as a sequential parser following `FM3-FORMATS.md`: header by type, emitters, anchors, draw lists,
parts, meshes, both vertex buffers. Per mesh it returns LOD, pass, primitive and UnpackingData. Per vertex it returns
position, UV0, UV1, normal, lighting, damage word and bitangent. It handles strides 16, 40 and 44, and keeps `kabsch` and
`triangles`.

**Checks:**
- Every car, wheel and brake carbin parses to the last byte (EVO reports 3,930). Skip the two parts with 1.7e38 bounds.
- Every index buffer that `CarLibrary.identify` matched is still found.
- **Settle the position formula** on parts with min != -max, using captured positions and c190.
- The see-through draw lists match the eight materials with no exceptions.

## Phase 2: car assembly (issues 3, 5, 7; 3-4 days)

`fm3_car_export.py` writes one scene per car from the manifest, with no capture involved:

- **Body:** always `_lod0.carbin`. Fall back to main-file LOD 1 only where LOD 0 lacks a part, and never mix LODs.
- **Variants:** use the stock variant from the database's body-upgrade tables (a-g and `race` are upgrade kits, not
  damage; verify on the grid capture). Export the other variants as hidden nodes. Movable parts (pop-up headlights,
  hood, trunk, doors) become separate nodes.
- **Hierarchy:** `Car/Body`, `Car/Wheel{FL,FR,RL,RR}/Steer/Spin/{rim, tyre}`, `Car/Brake*` (not spinning),
  `Car/Cockpit`, `Car/Glass`.
- **Wheel placement:** from `Data_CarBody`, checked against the grid capture for all 8 cars.
- **Wheel motion:** spin = distance / tyre radius; steer from input.
- **Tyres:** the `tire` mesh from the wheel's LOD 1, scaled to the database tyre size. Aftermarket rims scale from the
  15-inch reference.
- **Rims:** wheel LOD 0 plus `wheel?_lod0.xds`. `blur_rim` / `chrome_blur_rim` are motion-blur stand-ins: switch them by
  wheel speed and never draw them with the static rim (the likely cause of the rims looking wrong).
- **Captured grid:** only fit one transform per captured car (any LOD's index buffers identify it), so far cars also
  get full models. Captured car draws are always dropped.

**Issue 5 (far cars).**
- Look for the "damage" in this order:
  1. LOD 3-5 captured meshes with wrong voted materials;
  2. `damage.xds` bound instead of `nodamage`;
  3. duplicate variants.
- The damage word is not applied anywhere yet.
- See-through lead car: opaque parts got a blended material from the vote. Fix by taking the pass from the draw lists.

**Issue 7 (separating LODs and damage).** Exporter flags `--lod N`, `--damage` (binds `damage*.xds` and
DamageGlassSampler; exports the damage word as a vertex attribute and glass shards as hidden nodes) and
`--variants all`. A contact sheet per car shows LOD 0-5, cockpit and damage.

**Acceptance:**
- Batch: 4 wheels within 1 cm of the database positions; tyre radius within 2 %; every part has a material; no LOD mix.
- Grid frame: wheel centres within 2 cm of the capture; mean difference no worse than 20.3.
- Moving test: the wheels stay in the arches.

## Phase 3: materials from the game's shaders (issues 1, 2, 4, 9; 5-6 days)

One root cause: flat colours and capture votes instead of technique, textures and parameters. Replace
`car_materials.json` with a generated `profiles/fm3/car_techniques.json` (technique to family, plus parameters), and
write one Godot shader per family. Each formula comes from the PS disassembly, not from fitting.

- **`fm3_car_glass`** (window, glass, red_glass, detail_glass_*; issues 1 and 2):
  - Colour from GlassColor (the green tint).
  - Opacity rises towards GlassMaxOpacity by Fresnel; cube reflection.
  - Single-sided with the fxobj's cull state, drawn after opaque with no depth pre-pass. Double-sided blending at 0.5
    is the likely cause of the cockpit opacity.
  - The lights under the lenses get their real textures (LightsSampler, car-zip textures). Check the CRX tail bar in
    its manifest.
- **`fm3_car_paint`** (issue 4):
  - The file's normals and bitangents, `nodamage` as sRGB, the baked vertex lighting.
  - The track's `staticcarcubemap.xpr` with the Cube* and Fresnel parameters.
  - Check whether the game also blends a dynamic cube.
- **`fm3_car_generic`:** chrome, plastics, rims, tyre, interior, badges, carbon.
- **`fm3_car_light`** (issue 9): BrakeColor and ReverseLightColor as emission, driven by brake / reverse / headlight
  uniforms. Find the register by diffing PS constants between two captures (brake held / released). FM3 has no flares;
  optional Godot spot lights.

**Acceptance:**
- Per-family error vs the game within 5 % mean luminance, and glass hue within tolerance.
- Mean difference below 20.3, with the car region reported separately.
- New cockpit and chase captures as extra references.
- Batch: every material of every car maps to a family, and all its textures decode (`fm3_tex.py` gains `.xds`).

## Phase 4: cockpit (issue 6; 2 days)

**Root cause:** `_cockpit.carbin` is never loaded.

**Evidence:** capture one cockpit-view frame. With all three carbins indexed, list which file and part each draw comes
from: what the game hides from the exterior model in this view, and which glass it draws.

**Fix:**
- A Cockpit node with `cockpit_` + technique materials and `Interior_LOD0.xds`.
- A view switch that toggles node sets as the capture shows.
- The eye at `CarPartPositions` part 4 + CamCockpitOffset.
- Later: gauges and the steering-wheel pivot from the header anchors.

**Acceptance:**
- Pixel difference vs the cockpit capture.
- Batch: every car's eye point lies inside its bounds.

## Phase 5: other tracks (issue 10; 3-5 days, alongside phases 2-4)

- **`fm3_track_audit.py`** over every track and ribbon reports:
  - the `.rmb.bin` parse rate;
  - shaders that `fm3_families.py` does not handle;
  - (shader, stride) pairs whose UV0 or lightmap offset is unknown;
  - `.pvs` version and instance counts;
  - stx atlas resolution;
  - whether the cube and `TrackSettings.xml` are there.
- **Capture-free export:** make `--camera-from`, `--dynamic-from` and `--texmap` optional; take the start camera from the
  ribbon via `--ribbon`.
- **Batch render:** 4-6 overview cameras per track go into a contact sheet. Flag fallback-material area automatically
  (`world_view.gd --id`).
- **Captures:** grid captures on 2-3 structurally different tracks (city, Nürburgring-size, test oval).
- **Acceptance:** above 99 % of files parse, fallback area below 1 %, and the capture difference on validated tracks is
  comparable to Ladera's.

## Phase 6: user decals (issue 8; design only, 0.5 day now)

The paint shader takes a per-car decal layer list (texture, part group, UV-space or projected transform, blend), stored
in a user JSON beside the manifest. Use the livery UVs (UV1, `masks.xml`, `liverymasks`) where they are unique, and
Godot `Decal` nodes elsewhere.

## Order, effort, risks

- **Order:** 0, then 1, then 2 and 3 in parallel, then 4. Phase 5 can start after 0. Issue 11 (fixes for all cars and
  tracks) is met by design: everything is driven by the manifest and checked in batch, with no per-car tables.
- **Effort:** about 3-4 weeks.
- **Risks:**
  - The fxobj constant-table layout is only "assumed for FM3" by EVO. Fallback: sampler order from captured draws.
  - A dynamic environment cube.
  - AI cars on the grid may carry upgrade parts that differ from stock.
  - DLC cars come in through the merge databases.
  - Godot sorting of glass inside glass.
  - EVO is GPL: read it as documentation and copy nothing.

## Open questions for the user

1. Where is the live, driving and cockpit-camera code (issues 3 and 6)? It is not in this repo.
2. Can you take three more Ladera captures (cockpit view; chase view with brake held; chase view released), plus grid
   captures on 2-3 other tracks?
3. Are DLC and Disc 2 cars in the first batch, or Disc 1 only?
4. Lights: brake and reverse only, as FM3 has, or real headlight beams too?
5. Before live streaming exists, are simple wheel kinematics enough (spin from speed, steer from input)?
