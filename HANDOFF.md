# HANDOFF: the FM3 renderer-replacement project, where it stands (2026-11-22)

Read this first on a new machine or in a new session. Then `M1.md` (the detailed log, newest work at the end of
stage 2), `FM3-FORMATS.md` (every file format we decoded) and `ARCHITECTURE.md` (the long-term plan).

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
start); much of the rest is the HUD. Fly through it with `fly-track.cmd`.

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
   `compare: mean |diff| r 20.3 g 19.4 b 18.1`. Then `frame-ir\fly-track.cmd`.

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

- **frame-ir**: all work committed locally (`git log`; ~37 commits this session, latest "Handoff ..."). No remote.
- **FM3-ReGPU recomp**: committed (last `22ff609 NOTES: fix a path`), not pushed since 5e993eb..22ff609 (check
  `git status -sb`). Untracked `FM3 DLC\` and `Project Forza Plus 3\` (game data, never commit).
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

## 8. Open items (next steps, roughly by value)

1. Far grid cars (Beetle, PT Cruiser, Focus, C4, Tuscani) are still the captured low-detail draws: find their LOD
   files or use the full `.carbin` with a fit from the few captured pieces.
2. Car paint reflections: use the same environment cube as the windows (`fm3_glass.gdshader` approach).
3. Road-edge and shoulder-grass recipes are inferred (no captured example); the lake has no animated normals;
   chain-link fences' UVs; props only for Ribbon_04 (other layouts: pick another `.pvs`).
4. Tail-light lens brightness per car; the CR-X headlights/trunk are fitted from the file (movable parts).
5. Bigger plan (ARCHITECTURE.md): stream the scene from ReGPU live (Frame IR) instead of offline glTF, LibGodot
   embedding, triple screen in the core, then other tracks/games.

## 9. How we work (the user's preferences)

- Commit and push only when the user asks (local commits after finished steps are fine and expected here; never push).
- Never commit game data; exports stay in git-ignored `out\`.
- Check that `fm3.exe` is not running before booting or building FM3.
- frame-ir files use LF line endings; the FM3 repo uses autocrlf.
- The user often follows over Remote Control: finish turns with a short report and one clear question.
- Iterate visually: render, compare against the game's screenshot (`compare.gd`), measure regions, then fix.
