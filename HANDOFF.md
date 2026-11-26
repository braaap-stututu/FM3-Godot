# HANDOFF: the FM3 renderer-replacement project, where it stands (2026-11-26)

**Start the next session here (stopped 2026-11-26 ~11:00, after a 2-hour morning session).** Everything is committed
and pushed (frame-ir `live-mirror` = master, FM3-ReGPU `origin/main`). LIVE.md "Next for stage A" has every result.
This morning (all measured live against the game, mostly on the CrownJewel grid):
- **Painted asphalt from the game's code** (`shldr_4clr_blnd_mask`, family 'paint4'): the grain runs through the
  paint; CrownJewel's stripes 28.4 -> 10.5. The CrownJewel scene must be built with **`-Ribbon 04`** (the grid
  race's layout; the default Ribbon_00 lacks the grandstand and garages).
- **Per-vertex light for `*_nolm` track shaders** (fences, walls, the pit wall: texture x lerp(dark, light, vertex
  light)); the pit wall 41.6 -> 11.4.
- **16x anisotropic filtering** and a **-1 mip bias on the road grain** (the asphalt's fine speckle, the user's
  "rough asphalt look"; `FM3_GRAIN_BIAS=0` = before: a judgement call, shown to the user).
- CrownJewel grid whole frame: 18.4 / 17.8 / 16.9 (last night) -> **15.2 / 15.3 / 15.3** (15.7 with the grain bias).
Then (another hour, to ~11:35): car / people shadows in each track's `ShadowColor` (RoadAtlanta 16.9 -> 16.6,
CrownJewel neutral); library cars' per-colour base textures (`tools/fm3_car_basetex.py`, 44 cars: e.g. the R5
Turbo's blue decals); `rdline_diff_opac` road lines dimmed and blended as the game's code (Motegi 15.0 -> 13.5).
Rebuilt today: CrownJewel (-Ribbon 04), RoadAtlanta, Sebring, Motegi. The other tracks need a rebuild for the new
road lines, but first check their `*_nolm` shaders (the per-vertex light rule was verified on CrownJewel only).
Then (12:05, the user: "start with the taillights"): lamp reflectors and bulbs drawn as one opaque material so the
lenses tint their reflection (`fm3_lamp.gdshader`), lens filter 0.45: Sebring RSX tails 33.6 / 30.6 -> 25.2 / 23.2,
CrownJewel CR-X rear 14.8 -> 13.0 (picture sent to the user). Still a little darker / redder than the game's.
Open, in order: RoadAtlanta's car shadows (still too long / dark where the game's are short / faint;
`FM3_NO_SHADOWS=1` gives 16.8 -> 15.9 there); reflection contrast (our reflected clouds have less contrast than the game's); the RSX
lenses less pink; slip ratio / angle for the telemetry. The other tracks were not rebuilt except Sebring and
RoadAtlanta (no paint4 / vertex-lit meshes there).
The evening of 2026-11-25 below has the glass / lamps / Data Out / FM3E v8 / arcanite24 work.

Read this first on a new machine or in a new session. Then **`LIVE.md`** (the current work: running the game live
into Godot), `M1.md` (the detailed log of the offline pipeline, newest work at the end of stage 2), `FM3-FORMATS.md`
(every file format we decoded) and `ARCHITECTURE.md` (the long-term plan).

**Every game file, unpacked (2026-11-25):** `..\..\FM3-files\` (beside `Godot\` and `FM3-ReGPU recomp\`; game data,
never commit it). `game\` is the game's `game:\` drive with Disc 1 and all 8 DLC packs mounted as the game mounts
them (194,424 files, 27.6 GB, every zip member CRC-checked); `manifest.csv` gives each file's source. **Read
`FM3-files\CATALOGUE.md` before looking for any game data:** what every file type is, what reads it, what links to
what (database columns, executable paths), and the traps:
- every `.tga` name means the `.xds`;
- the game's database is `gamedb.slt` + `Media\DB\patch\*`;
- DLC zips mount per `zipmount.xml`.

**Where we stopped (2026-11-23, second PC):** the live mirror (LIVE.md stage A) works: FM3 streams its camera and
cars over UDP (`FM3_LIVE=1`), `live.cmd` draws the same race in Godot, smooth after the fixes of that day (frozen
viewer frames 0.4%, speed jitter median 7.7% over a minute). Open question to the user: chase the remaining uneven
steps (jitter p95 24-41%) or move on (wheels, crowd, then stage B). LIVE.md "Next for stage A" has the list.

**Later the same night: cars, `PLAN-CARS.md`** (its "Progress" section is the current state). Cars come from their
own files (`tools/fm3_carbin.py`, LOD 0 bodies, `.xds` textures), window glass runs the game's shader formula, and
the in-car camera shows the car's cockpit model with working-looking gauges (CR-X matches the game's cluster). The
frame-ir repo now has a remote: GitHub `braaap-stututu/FM3-Godot`, branch `live-mirror` (pushing it is allowed);
FM3-ReGPU and ReGPU are still local only.

**2026-11-24 (second PC), see `PLAN-CARS.md` "Progress, 2026-11-24" and `LIVE.md`:** car materials from the game's
own table (`Media\Cars\ShaderSettings`), brake / reverse lights, wheels and brakes from the files, steering wheel
modes (F7), rpm and steering / brake input in the stream (FM3E); the viewer loads textures GPU-compressed (8 GB card)
and FM3 runs at 1280x720. Other tracks: all 17 parse completely (`tools/fm3_track_audit.py`), any track builds
without a capture (`tools/build_track.ps1 -Track <Name>`), and cars come from a car library named by the game
(FM3N, `tools/fm3_car_library.py`): the live mirror runs on a capture-free scene. Afternoon of 2026-11-24: library
cars match the captured ones (mirrored nodes + Color-to-vec4 linearisation, PLAN-CARS), capture-free tracks get the
game's sky textures and sun (TrackSettings `ShadowLightDirection`), and the live capture-free CrownJewel grid
measured 20.4 / 20.1 / 18.5 against the game by the afternoon.

**2026-11-25 (where we stopped): exposure and the car shaders.** The game's exposure runs in the viewer
(`fm3_exposure.gdshader`), the road shaders and windows follow the game's code, and the car shaders were disassembled
(`Media/Shaders/Cars/shaders_v11.fxobj`; LIVE.md "Car paint reflection"). Car paint now uses the game's exact
reflection term, with the per-vertex sky weight baked in the car vertices (`fm3_carbin.env_sh`, library TEXCOORD_1;
the library was rebuilt). Two viewer bugs behind the player's dark roof were fixed: no live cube on capture-free
tracks, and library cars without its textures. Motegi frame 23.4 -> 22.7; CrownJewel grid 21.1 / 20.1 / 19.5. Next:
our live cube matches the game's (its x8 exponent adjust), the paint terms match per term; per-track car light from SHDir / SHTop (LIVE.md "Car paint reflection").

**2026-11-25 afternoon: moving game systems into Godot** (LIVE.md "Engine sound in Godot", "The game's cameras in
Godot", "Telemetry from the car-physics object", "Physics in Godot: feasibility"):
- display toe (the game's DC_LUT) in the exposure pass; survey 12.7 (Catalunya) to 25.4 (NewYork), RoadAtlanta 33.4
  (sun haze); Tsukuba (Ribbon_01) 17.8 / 17.1 / 20.9, Motegi 15.1;
- engine sound from the game's files (`tools/fm3_engine_audio.py`, `fm3_engine_audio.gd`): FSB loops pitched and
  crossfaded by rpm, live from the stream's rpm and throttle;
- the game's cameras rebuilt in Godot without the game's camera (`FM3_GAME_CAM=chase_near|chase_far|hood|bumper|
  cockpit`), the chase spring from CameraSettings.ini, the deterministic CameraPhysics.xml layers read from the game's
  own file;
- telemetry FM3E v5 (FM3-ReGPU 838763d, local): throttle, brake, gear, clutch, speed, wheel speeds;
- physics: no usable code in the FM2 repository; FM3's data is all readable, its model is only in the recompiled
  code: options and a recommendation in LIVE.md;
- **track fog** (the viewer had none): TrackSettings `<Fog>`'s directional settings, applied by the track shaders as
  the game does (cars unfogged); RoadAtlanta 29.4 -> 21.5 live; a full survey with fog: LIVE.md "Track fog";
- all 451 FSB sound banks decode (the 23 FSB3 'basic header' banks too: `FM3-files\tools\fsb_extract.py`);
- telemetry checked against the game's own telemetry screen (d-pad UP in a race): FM3E v6 tyre temperatures, v7
  suspension positions (FM3-ReGPU f4cb614, local); `tools/fm3_car_physics.py` exports a car's drivetrain, and its
  engine torque / power equal the telemetry page's (145.4 / 151.4 / 150.8 N m); the engine sound's torque inputs use it.

**2026-11-25 evening (to midnight): pushed, arcanite24's ports, lamps, telemetry out.** The user allowed pushing the
FM3-ReGPU commits (pushed to origin/main, 580ecb6..f4cb614 and on). Their question, whether arcanite24's
`pinyon-shift` / `cobalt-shift` help with telemetry: cobalt-shift (FM3) has none; pinyon-shift (FH1) maps the same
car-physics object (engine +324 / redline +452 identical) and sends Forza Data Out packets; its clean-room sibling
`pinyon-shift-native` simulates FH1's cars from the game's own tables within 2% of the real game: the template for
physics in Godot (LIVE.md "arcanite24's Forza ports"). Found in our dumps: world position +2544, velocity +2560,
acceleration +2512; +2672 is not a clutch. **Forza Data Out** from the recomp (FM3-ReGPU `src/hooks/data_out.cpp`,
`FM3_DATA_OUT=1` or the launcher's "Telemetry out (SimHub)": FM7 Dash packets for SimHub / motion rigs, checked on an
AI race). User's list item "glass shininess" (LIVE.md "Next for stage A", all measured against the game): lamp lenses
on the game's glass formula with mirror reflectors / bulbs / black glass behind them (`fm3_reflector.gdshader`; Sebring
RSX tails 67.5 / 56.5 -> 40.4 / 29.9), the player's windows at full reflection and library cabins at 0.5 (the user:
the band under the rear window is hidden in the game by the glass's reflection); finally the player's windows reflect
the live cube as the game's do: rear windows against the game Sebring RSX 5.4, RoadAtlanta RSX 3.5 (was 20.6),
CrownJewel CR-X 5.7 (was 16.6), the RSX's roof / sunroof 58.8 -> 17.6. Paint sharpness: a 256 px / 4x MSAA live cube (the game's size)
changed nothing measurable; the roof's "half as bright" was the dimmed sunroof glass (roof paint now 98-102 against
112). Slip ratio / angle not found yet.
After midnight (the user: 90 more minutes on the known differences): reflection blur is not the cube's clipping
(floating-point faces, `FM3_LIVE_CUBE_HDR`, change nothing) and only partly its size; our reflected clouds have less
contrast than the game's (open, LIVE.md "Next for stage A"). Fixed: the black-glass reflection pass off (the RSX
rear window's bright top border 41.0 -> 11.3, the CR-X 14.6 -> 12.7) and no sun highlight on car glass (the white
dashes on the Eclipse's lamp covers, 34.3 -> 24.7). The viewer can render a car library model alone now
(`--look-from` makes a camera; `FM3_HIDE_PARTS`, `FM3_BG_COLOR` for part hunts).
FM3E v8 streams the car-frame acceleration; the rebuilt cameras' G layers use it (hood camera as good as with the
positions' G, gain 0.6 confirmed: the game's camera answers lateral G at 0.6).

**Night of 2026-11-24/25: the other tracks** (LIVE.md "Other tracks"). All 15 Free Play tracks
build and run live (`tools\live\live_track.ps1`); the car library has all 500 cars incl. Disc 2; track shaders are read
from the game's own `.fxobj` files (`tools/fm3_trackshader.py`) and many recipes written from that code; re-survey
16.8 (Catalunya) to 41.4 (LagunaSeca). Found and decoded the game's auto-exposure / tone curve / bloom (final pass:
desat(scene + bloom) / W with W from the track's tone curve by adapted luminance): the next step, as a full-screen
pass in the viewer. The road's sun specular is in, opt-in (`FM3_ROAD_SPEC=1`) until then. FM3-ReGPU has one more local
commit (FM3N names cars without a colour file).

**Evening of 2026-11-24 (21:00):** the live capture-free CrownJewel grid **19.8 / 18.3 / 17.9** (in-car
17.1 / 17.5 / 17.0), the captured Ladera live **19.8 / 18.8 / 17.7** (in-car 19.2 / 18.9 / 17.6). Done that evening (details in PLAN-CARS "Paint
research" and LIVE.md stage A item 5):
- car paint: the light summed in gamma space like the game, the reflection weighted by how far a surface faces up, the
  sun's diffuse as n.l^2 (fitted from debug normal / albedo renders), metallic's second highlight; per-car paint 16.8 ->
  14.9 offline;
- the player's custom paint: `tools/live_liveries.py` reads every car's livery texture from the running game through
  the debug server and the viewer lays it over the car's colour (the CR-X yellow, 35.0 -> 10.4 live);
- tail-light lenses cloudy (`fm3_lenscloud.gdshader`), the reflection pass at 0.01;
- glass: blended in gamma space (screen texture: ~10% viewer fps, 32 -> 29), the player's glass with the dim
  reflection of the game's per-frame cube, AI glass 0.25;
- **the frozen grid skipped the per-car update** (no drawn-camera frames there): has_live, brake lights, the in-car
  switch and wheel blur now run on both paths (`_update_live_cars`);
- track paint stripes x1.1; plastic2 matte; amber lens cloud desaturated;
- track textures from their own CAFF `_0x<id>.bin` (full size; the `.stx` copy is smaller) and `diff_spec_ovly`'s UV
  scale (the grandstand canopy: smooth fabric instead of blotches); the crowd shaded by TrackSettings' Crowds colour;
- `fm3_dynlit` (the game's formula for unlightmapped track surfaces, with static shadows from a second sun): better
  but 29 -> 23 fps, so opt-in (`FM3_DYNLIT=1`; `=2` the shader alone);
- found: the moving in-car view's cockpit drifts against the camera (not a timing gap, `--live-car-lead`).
Open: the AI cars' windows lack the game's sky blue (the Eclipse 26), the Eclipse's amber signal areas, the pit wall
(barr_*_nolm: face brighter and warmer in the game, cap darker), the distant scene brighter than the game's in the
darks (not the fog: TrackSettings' fog is light blue), the crowd's 3D figures near the camera, the sea's colour
(AmalfiGP), the other multi-texture shaders without a recipe (track_audit.md), Suzuka's tree walls (bush_diff_opac_2_2sd: UVs span
~0-1 over a whole wall, drawn as streaks; the game's tiling unknown without a capture). Keep the physical monitor on (a
virtual display alone gives Vulkan -13 on this PC).

## 1. What the project is

A system that runs as little of an old console game as possible and hands its rendering to a modern renderer through
a scene-level interface. Pilot: **Forza Motorsport 3** (Xbox 360) through the user's static recompilation with its
GPU emulator **ReGPU** (Vulkan fork). Motivation: FM3 on three 1440p screens tops out at ~130-146 fps in ReGPU because
the draw thread translates ~9,000 Xenos draws per frame; the same scene in Godot renders at ~250-290 fps (M0 / M1).

Two ways of getting the scene into Godot exist now:
1. **From a captured frame** (`.fir` files written by ReGPU's fir tap): every draw's geometry, transform, textures and
   shader constants. Used for the camera, the cars' placement and materials, and everything dynamic.
2. **From the game's own files** (`Media\Tracks\<track>\bin.zip`, `.pvs`, `.stx.bin`, `Media\Cars\*.carbin`): the whole
   track complex, its props, sky, lightmaps, and whole cars. This is the direction that scales (no capture needed for
   static content).

Current result: the whole **CrownJewel** complex (Ladera + Montserrat + Iberian circuit, one geometry set; the test
layout is Ladera short reverse = `Ribbon_04`) renders in Godot from the files, textured, with FM3's baked lighting,
window glass with the game's environment cube, and the grid cars rebuilt from their car files. Against the recomp's
own screenshot of the same grid frame the mean pixel difference is **20.3** (per channel, 0-255; it was 70 at the
start); much of the rest is the HUD. Fly through it with `fly-track.cmd`. Since 2026-11-23 it also follows the
running game live (camera and cars, `live.cmd`, LIVE.md): beside the game the same frame differs by 20.0 on the grid
and 21.9 six seconds into an AI-driven race.

## 2. Folder layout

The root was `G:\claude code projects\` on the first PC. On the second PC (from 2026-11-22) G: is taken by another
partition, so the root there is **`C:\claude code projects\handoff-2026-11-22\`** (holding `Godot\` and
`FM3-ReGPU recomp\` side by side). The scripts find each other relative to their own folders (section 4), so any root
works as long as the two folders stay side by side. The table uses the first PC's root.

| Path | What |
|---|---|
| `G:\claude code projects\Godot\` | Godot 4.7.2 (`Godot_v4.7.2-stable_win64.exe`, console exe, mono folder), `CLAUDE.md` |
| `...\Godot\frame-ir\` | **the project repo** (git, local only, no remote): docs, tools (Python), Godot viewer, profiles |
| `...\Godot\frame-ir\out\world\` | generated scene (git-ignored, game-derived): `grid.gltf`, `ladera.gltf` (+ `.bin`, `_tex`), `capmap\` |
| `...\Godot\work\fir\` | the frame captures: `grid-single-1f.fir` (+ `.png` = the game's screenshot of that frame), `grid-triple-*.fir` |
| `...\Godot\work\assets\` | game files extracted with `fm3unzip`: `crownjewel` (bin.zip of the track), `carbins` (510 cars), `wheels` (567), plus Amalfi/Catalunya |
| `...\Godot\work\scratch-scripts\` | throwaway analysis scripts from the sessions (not needed, kept for reference) |
| `G:\claude code projects\FM3-ReGPU recomp\` | the FM3 recomp (git, origin github.com/braaap-stututu/FM3-ReGPU); `build\rel\fm3.exe` |
| `...\FM3-ReGPU recomp\thirdparty\ReGPU\` | ReGPU submodule: **holds the fir tap** (see section 6) |
| `...\reference\rexglue recomp reference\hl360-forza3\game\disc1\Media` | the game's files (Disc 1) |
| `...\hl360-forza3\user\0000000000000000\4D53084D\00000002\*\Media\DLCZips` | Disc 2 / DLC car packs |
| `C:\Users\<you>\.claude\projects\G--claude-code-projects-Godot\memory\` | Claude's memory for this folder (a copy is in the zip: `claude-memory\`) |

## 3. Setting up the other PC

1. Unpack the zips to `G:\claude code projects\` (they contain `Godot\`, `FM3-ReGPU recomp\` and `claude-memory\`).
   Without a G: drive, see section 4.
2. **Python 3** (3.12+; here 3.15.2) with **numpy** (`pip install numpy`). Nothing else is needed (no PIL, no scipy: PNG
   reading/writing is done by hand in the tools).
3. Godot is in the zip (no install). FM3: `build\rel\fm3.exe` is prebuilt; `play.cmd` runs it with the Disc 1 files and
   the saves in `out\user`. Rebuilding FM3 needs its toolchain: `tools\get-toolchain.ps1` in the FM3 repo (portable
   clang-cl / ninja / cmake), see its README and CLAUDE.md.
4. Copy `claude-memory\*` into `C:\Users\<you>\.claude\projects\G--claude-code-projects-Godot\memory\` (the folder
   name follows the working directory `G:\claude code projects\Godot`; create it if missing).
   Second PC (2026-11-23), already set up: Python 3.12.10 + numpy 2.5.5 (user site), VS 2022 Build Tools (MSVC
   14.44, CMake 3.31.6, Ninja 1.12.1), Windows SDK 10.0.26100, LLVM 23.1.6, .NET 9.0.321, Git, gh, 7-Zip, RenderDoc
   1.47, Inno Setup 6 (per user), DXC in the FM3 repo's `thirdparty\dxc` (`tools\get-toolchain.ps1 -Parts dxc`), RGA
   2.15 in `<root>\tools\rga-2.15`; installed by the user: Vulkan SDK 1.4.363.1 with its optional parts
   (`VULKAN_SDK` machine-wide; CMake still prefers `thirdparty\dxc`), AMD Ryzen Master Monitoring SDK
   (`C:\Program Files\AMD\RyzenMasterMonitoringSDK`; nothing uses it yet), Radeon Developer Tool Suite
   2026-10-02-1872 (RGP, RMV, RRA, RGA, Developer Panel) in `<root>\tools\`, as on the first PC.
   **That PC's GPU is an RX 6650 XT (RDNA 2, gfx1032, driver 26.11.2), not the 7900 XTX**: fps and GPU times are not
   comparable with the first PC's numbers, and RGA runs need `-Asic gfx1032`.
5. Check: `powershell -ExecutionPolicy Bypass -File frame-ir\tools\rebuild_ladera.ps1 -Compare` should end with
   `compare: mean |diff| r 20.0 g 18.9 b 17.8` (2026-11-24). Then `frame-ir\fly-track.cmd`.

## 4. Paths (relative since 2026-11-22)

No script hard-codes the drive any more: each finds the FM3 repo as `FM3-ReGPU recomp` beside the `Godot` folder.
- `frame-ir\tools\rebuild_ladera.ps1`: `-Fm3` defaults to `<Godot folder>\..\FM3-ReGPU recomp`; everything else is
  relative to the Godot folder.
- `frame-ir\tools\fm3unzip\build.cmd`, `gamelogic\*.ps1`, `m0\results-2026-11-22\m0.ps1`: same rule.
- `frame-ir\fly.cmd`, `fly-track.cmd`: relative (`%~dp0`).
- FM3 repo scripts (`play.cmd`, `tools\fm3ctl.ps1`, `fm3_route.ps1`, `tour.ps1`, `tools\analysis\*`, ...) are relative
  to their own folder.
- Still absolute: FM3's CMake build folders (`build\rel\CMakeCache.txt` was configured on `G:`). Running the prebuilt
  `fm3.exe` is fine; **rebuilding FM3 elsewhere needs a fresh configure** of `build\rel` (see the FM3 repo's
  README/CLAUDE.md), and the FM3 docs' `G:/claude code projects/tools/...` (RGA, Radeon Developer Tools) were not
  copied to the second PC.

## 5. The pipeline, step by step (what `rebuild_ladera.ps1` runs)

1. **Capture** (only when a new frame is wanted; the current ones are in `work\fir`): run FM3 with the fir tap
   (`play.cmd`, ReGPU's debug server on port 7341), then `m0\results-2026-11-22\fircap.ps1 -Out <file>.fir -Frames 1
   -Mode single -Shot <file>.png` (see M1.md "How to capture"). The game must be at the grid of Ladera short reverse.
2. **`tools\fir_world.py <fir> --gltf out\world\grid.gltf --material-map <dir>`** with `FM3_ASSETS=<carbins>;<wheels>`:
   runs every captured vertex shader numerically and symbolically (`fir_vs.py`), recovers the camera (53.00 deg) and
   each draw's object-to-world matrix, runs the pixel shaders per vertex for texture coordinates and colours, applies
   the material rules (`profiles\fm3\materials.json` by pixel-shader hash, `car_materials.json` by carbin material
   name), and writes the glTF plus a material map (`materials.json`, `fetches.json`, PNGs).
3. **`tools\fm3_track_texmap.py`**: matches captured draws to track meshes by index list, fits their UVs, writes
   `track_materials.json`.
4. **`tools\fm3_track_export.py <bin.zip dir> out\world\ladera.gltf --camera-from --dynamic-from --carbins --texmap --pvs`**:
   the whole track from `.rmb.bin` model files (`fm3_track.py`: every subsection, material table, vertex layouts),
   textures from `.bix` / `.stx.bin` (`fm3_tex.py`), the `.pvs` (`fm3_pvs.py`) for texture links, props and lightmaps,
   shader-family recipes (`fm3_families.py`: terrain blends, road, paint, curbs, road edges, shoulder mix, windows),
   the sky dome, the layout's environment cube (`staticcarcubemap.xpr`), cars rebuilt from `.carbin` (`fm3_car.py`),
   and the capture's people/crowd/far cars.
5. **Viewer** `godot\viewer\world_view.gd` (`--gltf --out --size --lit [--fly] [--look-from x,y,z --look-at x,y,z]
   [--id] [--filmic] [--triple layout.json] [--bench N]`) with shaders `fm3_baked.gdshader` (lightmapped world),
   `fm3_baked_blend.gdshader` (grass decals), `fm3_blend.gdshader` (shader families), `fm3_glass.gdshader` (windows).
   `compare.gd` stacks two images and prints the mean difference.

Debug helpers: `fir_pick.py <fir> x,y` (draws under a pixel), `fir_disasm.py <fir> <shader hash> [--pixel]`,
`world_view.gd --id` (one flat colour per mesh, writes `<out>.ids.txt`), env `FIR_DUMP_CONSTS=seq,...`,
`fm3_shaders.py` (per track shader: which material slot each hardware slot reads, and its UV transform).

## 6. State of every repository (nothing is pushed)

- **frame-ir** = GitHub **[FM3-Godot](https://github.com/braaap-stututu/FM3-Godot)** (remote `origin`, branch `main`,
  public): the FM3 application, full history. Remote **`upstream`** =
  **[GodotRenderOffloadForRecomps](https://github.com/braaap-stututu/GodotRenderOffloadForRecomps)** (public): the general
  framework (specs, core, Godot side, ReGPU patches, `tools/fir_*`, the FM3 profile as an example), imported from here
  and merged back with `-s ours` so the histories are linked. Its local clone: `G:\claude code projects\GodotRenderOffloadForRecomps`
  (first PC only).
  **Workflow:** general changes (specs, core, capture tools, Godot side) are made in the upstream clone, committed and
  pushed there, then `git fetch upstream && git merge upstream/main` here; FM3-specific work (fm3_* tools, FM3 shaders,
  profiles/fm3 tuning, docs about FM3) is committed here and pushed to origin. Game data never goes into either.
  **Second PC (2026-11-23):** the zip copy had no remote; `origin` was added and GitHub's main + the plan branch
  `ccr-f9067cdb-8wxfaw` (PLAN-CARS.md, FM3-FORMATS.md) merged into the day's local work, pushed as branch
  **`live-mirror`**. That work mixes general pieces (`world_view.gd --live`, the live tools, `tools/live/`) and FM3 ones
  (car shaders, fm3_* tools); it has not been split into the upstream repo yet (no clone of it on this PC).
- **FM3-ReGPU recomp**: committed, not pushed: `main` 15+ ahead of `origin/main` (5e993eb on; 2026-11-23 added the
  relative paths `5c4fc3f`, the live stream `9bbdca0`, `c0e0891`, `e428295`, `de95bd4`, `16b833c`, and
  `FM3_INPUT_BACKGROUND` `2396d3e`; check `git status -sb`). Untracked `FM3 DLC\` and `Project Forza Plus 3\` (game
  data, never commit). On the second PC `build\rel` was rebuilt from scratch with the live stream (the first PC's
  build kept as `build\rel-g`).
- **ReGPU** (`thirdparty\ReGPU`): checked out detached at `604dd2b` (what FM3 main pins) **with the fir tap applied
  as uncommitted changes** (`src\gpu\gpu.cpp`, `renderer.cpp` modified; `fir_tap.cpp/.h`, `frame_ir.h` new). The tap
  is also committed on branch **`vulkan`** as `d828ed8` + `d540cb0`, **not pushed** (`origin/vulkan` is 2 behind).
  `build\rel\fm3.exe` contains the tap. Do not push without the user's go-ahead.

## 7. Issues met and how they were fixed (chronological, short; M1.md has the long form)

| Problem | Cause | Fix |
|---|---|---|
| Wireframe mirrored left-right | FM3's scene target reaches the screen rotated 180 deg, not y-flipped | `--flip-scene` rotates x and y |
| "Missing silver car" | the mirrored wireframe of the dark car | (same) |
| No shadows anywhere | the unlit sky dome cast a shadow over everything | sky never casts shadows |
| Hangar see-through | texture alpha is a specular mask, not coverage | alpha test by re-running the pixel shader with alpha 0 and 1 |
| Black plastic trim missing | draws with only runtime-environment textures were dropped | colour from the shader output |
| Wrong track (Amalfi, Catalunya) | shared props matched there too | whole-track match; Ladera = folder CrownJewel |
| Track hills black | `.pvs` atlas ids read as `.bix` ids | lightmap atlases are in `<track>.stx.bin` (CAFF); id-range rule |
| Grey/flat track parts | parser read only the first subsection of each section | sequential reader of every subsection |
| Props missing | placement frame unknown | world = F (R^T p + pos), F = diag(1,1,-1); layout = Ribbon_04 |
| Lightmaps too dark | sRGB decode of gamma-space lightmaps | FM3's formula in gamma space + Godot's linear tone mapper |
| Black infields, gravel-noise roads | multi-texture shaders rendered with slot 0 only | shader families (fm3_families.py) from the capture + disassembly |
| Grid-area seam / checker curbs | captured single textures kept in the captured area; curbs treated as road | families everywhere; curb family |
| Garden "islands" | lightmap tiled 20x (wrong UV pair) | mix family: mask + lightmap at byte 24 |
| Grass tufts flat, striped bush cards | UV0 at byte 12 for these layouts; Godot imports BLEND as alpha+prepass | per-layout UV offsets; `_blended()` in the viewer |
| Building glass flat grey | reflection not drawn | game's `staticcarcubemap.xpr` cube, fitted to the game's pixels |
| Cars: interior reflected on every car | reflection probe placed inside the CR-X | probe above the cars |
| Wiper grey, palette colours | sRGB texel stored as a linear glTF factor | convert to linear |
| Mazda white / Focus grey | carbin match named paint panels "black"/"plastic2" | paint shader wins over carbin names; paint fallback |
| Car pieces missing up close, badges | capture holds only what the frame drew | whole cars from `.carbin` (fm3_car.py), rigid fit to the capture |
| Car shadows invisible | shadow strength applied in linear space | 0.85 linear (= the game's 0.42 displayed) |
| (2026-11-23) FM3 and Godot fail at start: `vkGetPhysicalDeviceSurfaceCapabilitiesKHR` -13 | the DisplayPort monitor slept and dropped off (Windows: no monitor) | wake the monitor; not a code bug (a 70-line Vulkan test failed the same) |
| Live camera axes unknown | director view matrix vs glTF space | fitted on the frozen grid: F = diag(1,1,-1), axes unchanged, 0.000 m / 0.00 deg |
| Live cars and camera shook | the 360 Hz hand-off camera runs ahead of the drawn frame's cars | the drawn camera (render object r10+0x0, "FM3V"): offset jump 6 -> 0.06 cm |
| Live judder (33% frozen viewer frames) | viewer and game frame rates differ | timestamped frame buffer, interpolated 1.5 game frames late: 0.4-0.8% |
| Five far grid cars low-detail | their captured LOD draws are not in the carbin, so no fit | place every carbin car by the game's car matrix (`--car-matrices`, work\fir\grid-cars.json): exact to 0.1 mm |
| Far cars white | their paint draws were named after other carbin materials | the paint-shader material (has a metallic-roughness texture) among the car's own draws |
| Paint colours too light (Mazda near white) | the paint shader scales c118 by c119.x (0.8 solid, 0.6 metallic); and the export never recopied changed capture textures | `color_scale_const` [119,0]; recopy when the source is newer |
| Paint flat, glass clear | Godot clear coat; car glass alpha 0.65 | `fm3_carpaint.gdshader` (lit colour with sky/ground ambient + Fresnel cube reflection + sun highlight, FM3's constants c216/c189/c180, metallic by c191) and `fm3_carglass.gdshader` (dark body, opacity 0.95, grazing reflections), fitted with `tools/car_regions.py`: paint median luminance off 14.2 -> 2.2, glass medians ~50 -> around the game's |

## 8. Open items (next steps, roughly by value)

**Running live (2026-11-23): stage A, the live mirror, works**: FM3 streams its drawn camera and every car
(`FM3_LIVE`), `frame-ir\live.cmd` follows them in Godot with interpolation. Everything about it (how to run, the
stream, the car matrix, the checks, smoothness, test scripts in `tools\live\`, what comes next) is in **`LIVE.md`**.
The items below (the offline scene) still apply.

1. Cars (2026-11-23 the user asked to "fix the cars completely"; done: all eight from their carbin, paint and glass
   shaders, live wheel matrices; then the same day: wheel motion blur, shadows, live reflections, see below). Left: a
   faint stripe on the Eclipse's doors (normals?), the C4's highlights too strong, far cars' glass reflecting the
   player car's cube (one cube for all cars; the game has one per car?), cars not reflected in each other (layer 2 is
   left out of the cube). Not cars: the race's traffic cones (placed by the race, not in the .pvs) are missing, and the
   game's full-screen motion blur at speed.
   - Shadows fell backwards: fir_world.py converted the sun with the capture's x mirror; the sun constants are in the
     game's world (= the paint shader's c136), mapped by F = diag(1,1,-1) like the car matrices. Fixed in the export.
   - Wheel motion blur: the captured `blur_*` wheel meshes are hidden at rest and fade in between 4 and 14 m/s (the car's
     speed from its streamed positions), the sharp ones fade out (GeometryInstance3D.transparency). A frozen game reads
     as speed 0: check it with `tools\live\live_compare.ps1 -NoFreeze`.
   - Live reflections: `--live-cube N` (default 128 px a face, 0 = the static cube): six cameras at the player car render
     viewports every frame (as the game renders its car cube every frame), looked up by the car shaders
     (`fm3_livecube.gdshaderinc`); car meshes on render layer 2, which the cube leaves out. Paint per-pixel diff 18.0 ->
     16.0 on the grid, live race at 12 s 28.2 -> 24.7; glass reflection refitted to 3.5.
2. (done 2026-11-23: car paint reflections, see item 1.)
3. Road-edge and shoulder-grass recipes are inferred (no captured example); the lake has no animated normals;
   chain-link fences' UVs; props only for Ribbon_04 (other layouts: pick another `.pvs`).
4. Tail-light lens brightness per car; the CR-X headlights/trunk are fitted from the file (movable parts).
5. Bigger plan (ARCHITECTURE.md): stream the scene from ReGPU live (Frame IR) instead of offline glTF, LibGodot
   embedding, triple screen in the core, then other tracks/games.

## 9. How we work (the user's preferences)

- Commit locally after finished steps; push FM3-Godot / GodotRenderOffloadForRecomps when a step is done and the user
  wants it shared (they set these repos up on 2026-11-22); FM3-ReGPU and ReGPU only when the user asks.
- Never commit game data; exports stay in git-ignored `out\`.
- Check that `fm3.exe` is not running before booting or building FM3.
- frame-ir files use LF line endings; the FM3 repo uses autocrlf.
- The user often follows over Remote Control: finish turns with a short report and one clear question.
- Iterate visually: render, compare against the game's screenshot (`compare.gd`), measure regions, then fix.
