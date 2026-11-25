# LIVE: running the game into Godot (ARCHITECTURE.md M5, the live loop)

Three stages, each usable on its own:

| Stage | What | State |
|---|---|---|
| **A, live mirror** | FM3 runs as normal through ReGPU and streams its camera and cars; Godot draws the same view from the scene built from the game files | **camera and cars done 2026-11-23** |
| B, takeover | ReGPU skips what Godot draws (track first, then cars) and draws the HUD and the rest into a layer Godot composites | not started |
| C, speed | measure against ReGPU's triple-screen frame (M6) | not started |

## Stage A: how to run it

1. Build the scene once: `tools\rebuild_ladera.ps1` (HANDOFF.md section 5) makes `out\world\ladera.gltf`.
2. Start FM3 with the stream on: from the FM3 repo, `$env:FM3_LIVE='1'; .\play.cmd` (or in a running game:
   `Fm3 "env FM3_LIVE 1"` after dot-sourcing `tools\fm3ctl.ps1`). The log says `live: camera stream to 127.0.0.1:7342`.
3. `frame-ir\live.cmd` (from the Godot folder: `& '.\frame-ir\live.cmd'`). Tab = the next camera director (the
   player view, the rear-view mirror), Esc quits. Creating `out\world\live.png.shot` saves the next frame to
   `out\world\live.png`. **F7** cycles the cockpit steering wheel (2026-11-24; start with `--steering-wheel
   game|input|off`):
   - `game` (default): as FM3 turns it. Steering input × the car's `SteeringWheelAngleOverride` turns (CR-X 0.206 =
     74°; its in-car pictures show ~73°); cars without one get 90°, a guess (the game's default is not measured).
   - `input`: 1:1 with a real racing wheel. Steering input × half the wheel's lock (`wheel_lock` in FM3's settings,
     streamed); with a pad, `--wheel-lock DEG` (default 900).
   - `off`: no steering wheel.
   The steering input comes in "FM3E" v2 (player 1's `lx` as the game reads it, from `ReadPad`).

**Start the viewer while the game is at the capture's grid** (the test grid event, before the start): Godot attaches
its car meshes to the streamed cars by where they are at that moment (below). Only the Ladera layout `Ribbon_04` has
its props.

## The stream

`FM3_LIVE=1 | <port> | <ipv4>:<port>` (default 127.0.0.1:7342; read twice a second, so it switches live). FM3's camera
hand-off `sub_821E9B50` (r3 = the presentation view, +4 its camera director) sends one UDP datagram per hand-off,
about 360 a second at the 360 fps cap: `src/hooks/live_camera.cpp` in the FM3 repo (96 bytes, layout at the top of
that file): the director's view matrix (+0xD0: world to camera, row vectors, left-handed), vertical field of view
(+0x110, radians) and active camera vtable. Nothing in the game changes; non-blocking send, nobody listening costs
nothing.

**Cars**: the main view's car loop calls `sub_828329C8` once per car per drawn frame (from 0x82837F0C, r4 = the car
object; the hook in `src/hooks/mirror.cpp` calls `LiveCarDrawn`). The car object keeps its body's world matrix at
**+0x10** (rows = the car's axes, row 3 = position; +0x50 the same, +0x90.. the wheels), found with
`FM3_LIVE_CAR_SCAN=1` (logs every world matrix in each car object and one level of the objects it points to). Each car
is one "FM3K" datagram per drawn frame (96 bytes; layout in `live_camera.cpp`), followed by its wheels ("FM3W");
the player's engine speed and redline come as "FM3E" (2026-11-24: car-physics object +324 / +452 rad/s; the
cockpit tach, PLAN-CARS.md phase 4). In Godot (`world_view.gd`
`_attach_cars`), half a second after the first car datagram every mesh smaller than 6 m that lies wholly inside a car's
box (1.5 m sideways, 2 m up/down, 3.2 m along, in the car's frame) is attached to that car with its offset
`A(0)^-1 * node`; each frame it is placed at `A(t) * offset` (A = the car matrix in glTF space; the z mirror cancels).
This needs no per-model knowledge: carbin cars, captured far cars and the shadow blobs all move the same way.

**Game world to glTF** (fitted on the frozen grid with `tools\live_listen.py --compare out\world\grid.gltf`): FM3's
world with z mirrored, F = diag(1, 1, -1), the same F `fm3_track_export.py` places the track with, and the
director's camera axes as they are (the 180 deg screen turn `fir_world.py` undoes lives in the projection, not in the
view matrix). Result: 0.000 m and 0.00 deg from the captured camera, field of view 53.00 deg on both.
`world_view.gd --live-axes sx,sy,sz,sr,su` overrides the signs (default 1,1,-1,1,1).

## Checks (2026-11-23, second PC: RX 6650 XT)

Frozen grid (`FM3_GRID_TEST=1`), Godot `--live` beside the game, the game's own screenshot against Godot's picture
(`compare.gd`, mean |diff| per channel, 0-255; the offline grid render is 20.3):

| Game camera | Godot camera | mean diff | Note |
|---|---|---|---|
| grid (chase) | 104.29, -0.51, 217.17, fov 53 | 20.0 / 19.1 / 17.9 | as the offline render |
| RB once | 104.30, -0.29, 216.82, fov 53 | 20.8 / 19.9 / 18.7 | |
| RB twice (in-car) | 103.92, -1.75, 222.21, fov 45 | 37.6 / 38.6 / 37.5 (2026-11-24: 20.6 / 19.8 / 18.9, see below) | geometry lines up exactly; the rest is the HUD, the CR-X's gauges and the driver's hands (not in the carbin parts used), the mirror's picture and darker cabin light |

Cars, an AI-driven race (`FM3_GRID_TEST=1` + `FM3_AI_PLAYER=1`: the race AI drives the player's car too), frozen
with `Fm3 "env FM3_FREEZE_TIME 1"` for each pair of pictures. All 8 cars attached (49-87 meshes each):

| Moment | mean diff | Note |
|---|---|---|
| grid | 20.0 / 19.1 / 17.9 | |
| 6 s into the race (71 km/h) | 21.9 / 22.0 / 21.8 | every car where the game has it, the camera following the moving CR-X |
| 15 s, first corner | 35.4 / 33.2 / 31.8 | cars match; the rest is the grandstand crowd (captured as dark static silhouettes), the HUD, a flag and a curb edge line |

Pictures: `tools\live\live_compare.ps1` (game shot via `Save-Fm3Shot`, Godot via the `.shot` trigger): the camera
table is `-Cameras 2`, the car table `-AiPlayer -Steps 'race6:6,race15:9'`.

**Since 2026-11-24 the game renders at 1280x720** like the viewer (`out\user\settings.ini resolution=1280x720`, the
user's 2560x1440 kept as `settings.ini.bak-2560x1440`): the game's shots are native 720p without MSAA instead of 1440p
scaled down, so the baseline moved: grid 20.7-20.8, chase (RB once) 21.4. Video memory on the 8 GB RX 6650 XT: FM3
~3.7 GB at 720p, the desktop compositor ~1.6-1.8 GB (+ Firefox ~0.65 GB if open); the viewer loads its textures
GPU-compressed (BC1/BC3, `world_view.gd _bind_textures`; uncompressed they were 2.8 GB and the viewer died loading,
Vulkan -2) and peaks at ~2.8 GB. **Monitor off:** with only a virtual display (Sunshine VDD / SudoMaker) both FM3 and
Godot fail at start with Vulkan -13 (surface lost) on this PC (2026-11-24): keep the physical monitor on (or set the
virtual display's render GPU; untested).

## Smoothness (2026-11-23: "the cars/camera is stuttering a lot")

Two causes, both measured and fixed:

1. **Camera and cars from different game steps.** The hand-off camera ("FM3C") comes from the logic thread at 360 Hz;
   a car's matrix changes only once per drawn frame (the game drew 88-123 fps here). Taking the newest of each, the
   car-to-camera offset jumped 6 cm per packet (p95 14 cm): the cars shook against the camera.
   Fix: the car loop's render object (r10) holds the view matrix the frame is drawn with at +0x0 (found with
   `FM3_LIVE_CAM_SCAN=1`); the game sends it as "FM3V" before that frame's cars, and the main view follows only those.
   Offset change against the followed car: **0.06 cm per packet (p95 0.13)**. (`tools/live_record.py` measures this.)
2. **Two frame rates.** The viewer (83-116 fps beside the game on the RX 6650 XT) and the game (84-123 fps; both share
   the GPU) never line up, so the newest frame showed some game frames twice and skipped others. Fix: `world_view.gd`
   buffers the drawn frames with the game's timestamps (host clock mapped by the smallest latency seen), shows the
   moment 1.5 game frames ago (about 18-20 ms here) and blends camera, field of view and each car between the two
   frames around it. `--live-raw` shows the newest frame as before.

Measured with `world_view.gd --live-log <csv>` (per viewer frame: time, shown camera, followed car) and
`tools/live_smoothness.py`, the same AI race:

| | frozen viewer frames | speed jitter median / p95 |
|---|---|---|
| `--live-raw` (newest frame) | 33.0% | 129% / 317% |
| interpolated (default) | 0.8% | 7.7% / 35% |

A full minute (`live_smooth.ps1 -Seconds 60`, interpolated): 6,965 viewer frames at ~113 fps beside the game at ~95,
shown 17.5 ms behind; frozen frames 0.4%, speed jitter median 7.7% / p95 33.9%, car shake median 0.6 cm / p95 2.8 cm.
Per 10 s: frozen 1.9% in the first window (the start, the clock estimate settling), 0.1-0.3% after; jitter median
6.9-8.8%, p95 24-41%; no drift over the minute. The p95 (an occasional uneven step) is the open item; the guess is
the game's own uneven frame times, not checked yet.

### At 60 fps, driving it (2026-11-23, second session)

The user drove the test race through Godot only (`tools\live\drive.ps1`: FM3 at 60 fps with `REGPU_NO_RENDER`, 0
draws; the viewer at 60 fps) and still saw some jitter, guessing the two halves' frame times don't match. Measured
(`live_record.py` "pacing", `live_smoothness.py` "step jitter" = the change of the distance moved per shown frame, what
the eye sees at a fixed refresh):

- The game moves its cars evenly per frame (step change median **0.2%**), but its frames' timestamps (taken on the
  render thread) wobble: 15.2-18.0 ms apart, sd 0.44 ms. Placing frames by those times made the shown motion
  uneven: speed by timestamp changes median 4.2%, p95 16%. The guess was right.
- Fix 1 (`world_view.gd`): game frames on a steady timeline by frame number (one smoothed interval per frame, pulled 2%
  toward the raw time), the viewer's own clock steadied the same way (5% pull), the clock offset a slow average (the
  "smallest seen" estimate crept up 1 ms/s and snapped back).
- What remained is in the game's own motion: on ~12% of frames the step is 4-9% off the trend, often alternating,
  irregularly spaced (no beat between the clocks). Fix 2: `--live-smooth W` (default 1) averages two samples one game
  frame apart around the shown moment, cancelling frame-to-frame alternation, for half a frame more delay.

| 30 s AI race, both at 60 fps | step jitter median / p95 | frames > 4% off the trend | shown behind the game |
|---|---|---|---|
| timestamps as sent (before) | 1.8% / 7.7% | 206 | 27 ms |
| steady timelines | 0.5% / 6.5% | 206 | 27 ms |
| + `--live-smooth 1` (default) | 0.5% / 4.0% | ~75 | 35 ms |

`drive.ps1 -ViewerArgs '--live-smooth 0'` trades the smoothing for 8 ms less delay.

## Test scripts (`tools\live\`)

Both boot FM3's test grid themselves (minimized; the game must be closed and the monitor awake) and close it after.
- `live_compare.ps1 [-AiPlayer] [-Steps 'race6:6,race15:9'] [-Cameras 2]`: the game's screenshot against Godot's
  picture at frozen moments (grid, camera views with RB, race moments); pictures in `out\live\compare\`.
- `live_smooth.ps1 [-Seconds 60] [-Tag t] [-ViewerArgs '--live-raw'] [-NoGodot]`: an AI race with the viewer logging
  what it shows, then `tools\live_smoothness.py --window 10`; `-NoGodot` runs `tools\live_record.py` on the stream.
- `drive.ps1 [-Fps 60] [-KeepGameRendering] [-ViewerArgs '...'] [-AiPlayer -Seconds N -Log csv]`: the user drives the
  test race seen only through Godot (game rendering off, both at 60 fps, `FM3_INPUT_BACKGROUND=1` so keyboard and
  wheel work while the viewer is in front); `-AiPlayer -Seconds 30 -Log x.csv` is the unattended version.

## Other tracks (2026-11-24 night)

- **`tools\live\live_track.ps1 -Index N -Gltf <abs>\out\world\<track>.gltf [-FreezeAfter 11]`**: boots FM3 through the
  recomp's tour route (`tools\tour.ps1`: Free Play > Quick Race > Acura RSX Type-S > environment N, its first layout),
  starts the race, freezes the world in the countdown (FreezeAfter 11 = the chase view; 8 = the car intro), starts the
  viewer beside it and compares (`out\live\tracks\<name>-{game,godot,cmp}.png`). Environments: 0 AmalfiGP, 3 Catalunya,
  7 LeMans, 8 MapleValley, 9 LagunaSeca, 10 Mugello, 11 NewYork, 15 RoadAmerica, 16 RoadAtlanta, 17 Sebring,
  20 Silverstone, 21 SunsetInfield, 22 Suzuka, 23 Tsukuba, 24 Motegi (1/2/18/19 Autopark). Free Play's opponents and
  grid slot change every boot, so each run is a new picture.
- **Every car the game can field is in the car library** (500: disc 1's 305 + Disc 2's 199 from the recomp's installed
  packages, `out\user\dlc\*\Media\DLCZips\*_pri_65.zip`, `tools\add_cars.ps1`; ~33 GB in `out\cars`); Disc 2 cars'
  colours come from the packages' `*_merge.slt` databases. The viewer's picture waits for the cars to attach.
- **Track shaders from the game's own code:** `tools\fm3_trackshader.py <track>\shaders\track\<NAME>.fxobj`
  disassembles any track shader (FM3-FORMATS "The track shaders themselves"); recipes written from it in
  `tools/fm3_families.py` (overlay, three-layer value blend, the road blends, road lines, edge decals, shoulder and
  terrain blends) and single-texture shaders' UV scale / gain read from their code (`simple_terms`). Per track:
  TrackSettings DarkColor / LightColor as the static light (`<track>_track.json`), the sky scaled by skyScale / tone
  white point, crowds from the shared `Media\Spectators.zip` sprites where a track has no crowd sheet, `OCCLUD_*`
  occlusion meshes skipped.
- First survey (before most of the fixes): AmalfiGP 49.3, Catalunya 16.6 (fixed first), LeMans 22.6, MapleValley 46.0,
  LagunaSeca 40.3, RoadAmerica 68.0, RoadAtlanta 44.5, Sebring 39.2, Silverstone 24.0, SunsetInfield 26.4, Suzuka
  25.1, Tsukuba 20.2, Motegi 49.0 (player car unnamed); Mugello (viewer stalled) and NewYork (boot route stuck before
  the pre-race menu) gave no picture. **Re-survey (2026-11-24/25, all recipes so far; each boot a new grid slot):**
  AmalfiGP 27.3, Catalunya 16.8, LeMans 22.2, MapleValley 37.7, LagunaSeca 41.4, Mugello 26.3, NewYork 34.2,
  RoadAmerica 26.2, RoadAtlanta 37.3, Sebring 25.3, Silverstone 30.0, SunsetInfield 24.4, Suzuka 25.1, Tsukuba 21.6,
  Motegi 36.2 (r channel; the palette props, LeMans' dual-mix verges and the base-slot fix came during it).
- **Road sun specular (opt-in `FM3_ROAD_SPEC=1`):** the road shaders' shadowed variants add a sun highlight, read
  exactly by running their code in `tools/fir_vs.py` with a live capture's constants (debug server `capture`, boot with
  `REGPU_NO_PACKED_CONSTANTS=1`): c223/c224 are TrackSettings' RoadSpecular/2, RoadSkid/2, RoadGlossiness/2,
  RoadLightmapDark/LightPoint as written; formula in `fm3_blend.gdshaderinc`. Off by default: on MapleValley facing the
  sun it overshoots (glare 253 vs the game's 176; without it 66 vs 193); the reason is still open.
- **Display gamma (measured 2026-11-24):** FM3's display table (ReGPU applies it at present; live switches
  `REGPU_NO_GAMMA` / `REGPU_NO_GAMMA_PWL`) is a fixed toe curve, the same on MapleValley and LagunaSeca: 16 -> 9-12,
  48 -> 33, 80 -> 60, 112 -> 95-98, 144 -> 132-137, 240 -> 244-247. It is not the per-track brightness difference, nor
  highlight compression; our calibration (on the game's shots) already includes it.
- **The game's auto-exposure and tone curve (found 2026-11-25, MapleValley capture):** after the scene, FM3 runs
  a bloom chain (bright pass ps 58dc46c8b0b963ea on a 320x192 copy with c4 = (bloomCutoff, bloomScale), blurs
  c8e364190753a770 / b9c3764fc70c9819, down to 32x32), a luminance pass (ps 4a17014edfabf5f0: the 32x32 bloom
  buffer's average luminance, blended with the previous value by 0.02 a frame = adaptation L), and the final pass
  (vs 2a342f670b5bb28a + ps 5b7efac9b0c87a00): colour = desat((scene + bloom), 0.85) / W + boost/255, where
  W = lerp(DarkCurveWhitePoint, LightCurveWhitePoint, k) / 255 (- 0.0006), k = saturate((L - LumMin/255) * 255 /
  (LumMax - LumMin)); vertex constants vc2 = (LumMin/255, -0.0006, 0, 255/(LumMax-LumMin)), vc3 / vc4 = the dark /
  light curve (black/255, white/255, gamma, boost/255), vc254 = (1,0,0,0), vc255 = (0.1, 1280, 720, 0.5). Verified
  by running the final ps in fir_vs: a linear exposure from 1/W (MapleValley 1.96x dark to 0.88x bright: the 0.88
  caps its glare near 224). The shaders' code: the recomp's `out\user\static_shaders.bin` (pixel shaders, by
  ReGPU's FNV hash) and the debug server's `hlsl <hash>` (vertex shaders). **Next:** the bright pass's formula (it
  also takes its own vertex shader's interpolants) to compute L as the game does, then exposure + bloom as a
  full-screen pass in the viewer, relative to CrownJewel's (our calibration includes its exposure). L is not the
  scene's mean luminance (that estimate contradicts the measurements), and reading the 32x32 texture from guest memory
  gave zeros (resolves stay on the GPU; FM3_WRITEBACK=32x32 did not reach it).
- **The exposure in the viewer (2026-11-25, `fm3_exposure.gdshader`, on for tracks with 'Tone' in their
  `<track>_track.json`; `FM3_NO_EXPOSURE=1` off):** the final pass's formula as a canvas pass over the picture.
  The luminance chain, decoded: the scene is downsampled 1280x720 -> 320x192 -> 64x32 -> 32x32 (plain averages,
  ps c244a21ac3a9be63 / 98c51b1e094205eb), the luminance pass averages it and adapts 2% a frame. The viewer reads its
  own picture back every 10 frames (64x36), undoes the current curve and adapts the same way. Calibration: our
  picture matches CrownJewel's final picture, so S = picture x W_cj / 0.9874 with W_cj = 0.942, read from the running
  game on the test grid by replacing the final pass's output with its interpolant r1.y = 0.1/W (debug server
  `ps 5b7efac9b0c87a00 float4(r1.y * 4.0, ...)` with `REGPU_NO_GAMMA` on; tools/research `wread.ps1`). LagunaSeca:
  game W 0.756, predicted 0.82 from its shot; the whole-frame mean fits, a centre strip did not. **LagunaSeca live
  41.4 -> 18.4.**
- **2026-11-25 morning (exposure on; each boot a new grid view):** LagunaSeca 41.4 -> 18.4, RoadAtlanta 37.3 -> 24.8,
  LeMans 22.2 -> 21.7, Motegi 36.2 -> 46.9 (one run without exposure differences: a stray scene mesh had blocked
  the player's car, fixed; the rest is a too-light road and greyer pit building), MapleValley 38.6, Catalunya 20.9 (its
  FTO unnamed in that run: fixed since, see below). Also fixed: NewYork's road lines (opacity map) and LED ticker
  (UV at byte 12), MapleValley's Castrol barriers (`*_vert_*` UV at byte 20; 16 is a vertex colour), windows coloured
  by their Diffuse texture (slot 2) instead of the SPEC mask (CrownJewel rebuild 19.6 / 18.3 / 17.4), the game's
  name re-send for every car once a second (FM3-ReGPU 8093bc0) and an 8 MB UDP buffer in the viewer.
  Later that morning: road_blnd_2 from its code with a fitted x0.85 (Motegi 46.9 -> 23.4; CrownJewel rebuild
  19.3 / 17.8 / 16.8), car glTFs without NaN (MIT_FTO_98, FER_250GTO_64, FER_GTO_84 had been unreadable: the "B.Giese"
  car missing on three tracks), windows combine as the game does (diffuse + reflection, lit: MapleValley's office
  front), the road sun specular on by default (MapleValley 36.1 -> 25.8). Still open: the road_blnd_2 x0.85's cause,
  the glare's texture (smoother than the game's), the player car's roof darker than the game's (its live cube
  reflection: Motegi 47 vs 104), `VW_BoraVR6_03` in no unpacked archive (a DLC pack?).
- **Car paint reflection (2026-11-25, the car shaders disassembled):** `Media/Shaders/Cars/shaders_v11.fxobj` holds
  every car shader (144 containers: 99 pixel, 45 vertex; `tools/fm3_trackshader.py` reads them): paint = container
  47 (ps e41e183a423e6f1b), window glass = 60 (b117fbafcc1fa980). ReGPU's HLSL translations
  (`FM3-ReGPU recomp/out/rga/ps_*.hlsl`) are the readable form. The paint's reflection, exactly:
  `saturate(F x reflectionScaler x (1 - FresnelKill x lum(paint))) x env x CubeScale x 0.368 d x (1 - dampener x (1 -
  track lightmap))`, F = clamp(FresnelScale x (1 - n.v)^FresnelPower, FresnelMin, FresnelMax) = (1, 1.5, 0.15, 1);
  CubeScale 1.5, FresnelKill 0.2, dampener 0.3 (live cube, player) / 0.5 (static cube); added to the lit paint
  unshadowed. d is per vertex: the vertex shader's `dp4(transfer SH, shCubeMapDampnerLight)`, where the transfer SH
  is the car vertex's 4 x s16 at byte 20 (stride 40), stored as lo + (s/32767 + 1)/2 x range with (lo, range) at
  0x19C of the carbin header's 0x1AC block (CR-X -0.3378 / 0.6887), and shCubeMapDampnerLight is the SH of a
  hemisphere of TrackSettings SHEnvMapTop / SHEnvMapBottom (1 / 0.15 on every track): dc 5.3174 x (top + bottom)/2,
  linear -1.535 x (top - bottom) (fits vc37-40 exactly). 0.368 = 0.2125 x sqrt(3), as the shader computes it. On the
  CR-X body d is ~1.2 facing up, ~0.8 sideways, ~0.35 facing down: the older fit's up^3 weighting (8:1 roof to
  flanks, offset by a 2.25x gain and Fresnel power 4 with no floor) was far steeper than the game's 1.4:1.
  Built: `fm3_carbin.env_sh` (per vertex (a, b), d = top a + bottom b; checked against the vertex shader run in
  fir_vs: max error 0.0008), the library writes it as TEXCOORD_1, `fm3_carpaint.gdshader` game_refl (on;
  `FM3_OLD_PAINT_REFL=1` = the older term; `FM3_PAINT_ENV=<static gain>,<live scale>` for fitting). Glass (container 60) needs no change: lerp(glass, env x CubeScale x
  lightmap dampener, clamp(c191 (1 - n.v)^c216, c189, c190)), the form fm3_carglass already has.
  **Two viewer bugs found on the way (the real cause of the player's dark roof):** (1) the live cube was made only
  when the scene glTF had cars, so on every capture-free track (all but CrownJewel) the player reflected the static
  cube; (2) its six face textures went only to the car materials existing at that moment, so library cars (attached
  later) had unbound samplers: a flat env of 1, a grey haze over the player's car. Both fixed in world_view.gd
  (`_live_cube_texs`, has_live set at registration). **Motegi, same game view (RSX, black; boxes game / before /
  after):** roof 100 / 51 / 62, deck lid 43 / 33 / 54, tail panel 8 / 9 / 17, bumper 6 / 5 / 14, flank 47 / 26 / 35;
  frame 23.4 -> 22.7. CrownJewel grid: 21.1 / 20.1 / 19.5 against 21.3 / 20.2 / 19.7 with the older term (same boot
  conditions).
  **Cubes compared (Motegi, `tools/research/cubecmp.ps1`, same frozen moment):** the game's car cube is t6 at
  1832E000 (six 256x256 faces 0x40000 apart, 2_10_10_10, resolve dumps `<addr>_256x256_v0.png`). Two traps: ReGPU's
  dump writes A2B10G10R10 texels as RGBA8 with alpha forced to 255 (red and green are recoverable, blue's top bits
  are lost), and **the fetch constants carry an exponent adjust** (dword 3 bits 13-18): the live cube is stored at
  1/8 and read x8, the static cube (t7) is read x2, the lightmap x1. With the x8 the game's cube and ours match
  (road 0.34 both, sky 0.5-0.7 both). The static cube's x2 is already absorbed in the older fit's gains; in game_refl
  the static path uses game_env_gain 1: check the AI cars against it.
  **Term by term (`tools/research/paintdbg.ps1`: the game's paint ps edited live to output r7.x x r4, r7.x or r4,
  the viewer with `FM3_PAINT_DEBUG=1|2|3`):** the angle factor and the environment part look the same in both
  (rear faces at the 0.15 floor, edges and the grazing bumper white); box means still differ because the cars sit a
  few pixels apart on screen. Seen but not modelled: the angle factor is x (1 - e1.w), a per-vertex value from the
  vertex data at byte 28 and the damage stream (const 94), clamped by damageClamps; the game's lower body reflects a
  darker ground (its cube sees the car's shadow).
  **Car light per track:** the paint's sun is the game's c179 = TrackSettings SHDir (Motegi 0.8, CrownJewel
  0.78/0.76/0.73, MapleValley 0.9/0.88/0.85), the sky SHTop. `<track>_track.json` now has 'SH' (fm3_track_export.py;
  the existing files patched), and the viewer scales the paint's CrownJewel-fitted sun and sky by them
  (`FM3_NO_TRACK_CAR_LIGHT=1` off). The sun's direction was already right (game psLightDirWS = ours with the glTF's
  z mirror; shadows agree). Godot's own sun light (props, trim, rims) stays one fixed colour on every track.
- **Display table, sky, static cube (2026-11-25 afternoon):**
  - **Display table.** The console's display table (DC_LUT, a toe: 16 -> 6, 32 -> 16, 64 -> 48, 128 -> 115,
    192 -> 185, 240 -> 238) is now applied by `fm3_exposure.gdshader` after the exposure:
    - The table was taken from the game's own shots of the same frozen frames with and without it (REGPU_NO_GAMMA),
      as the median per pixel value.
    - It was found by having the game's paint output constants (live ps edits, `tools/research/gridterms.ps1`):
      0.1 / 0.25 / 0.5 came out 13 / 52 / 119 in the game, 25 / 65 / 129 in ours.
    - Everything that copies the game's formulas had been too light in shade. The road_blnd_2 x0.85 "cause unknown"
      was this table (102 -> 88): `road1_gain` is 1 now.
    - With the table, the final pass takes our picture as the game's scene (`s_scale` 1; before it was W_cj / 0.9874,
      a no-op on CrownJewel).
    - `FM3_NO_TOE=1` turns it off; `FM3_EXPO_SSCALE` overrides the scale.
  - **Sky.** `fm3_track_export.py` gave the sky dome skyScale x 275 / LightCurveWhitePoint: the exposure, from
    before the viewer had the final pass. That exposed the sky twice (Motegi's 1.19x the game's). The sky gain is
    skyScale only (existing scenes patched in place).
  - **Results, live:**
    - CrownJewel grid **19.6 / 17.8 / 16.1** (this morning 21.1 / 20.1 / 19.5; the best yet).
    - Motegi **23.4 -> 14.7**: its open sky 132/174/214 against the game's 132/175/214.
  - **Static car cube scale.** The static car cube's own scale: each `staticcarcubemap.xpr` carries its fetch
    constant, whose exponent adjust the game applies:
    - x1 on CrownJewel, x2 on every other race track, x8 in the menu scenes;
    - our decode of Motegi's file is half the brightness of the game's live cube there;
    - the export writes `<scene>_tex/envcube.json` (`gain`), which the paint's game term uses (`static_cube_gain`).
  - **Checked on the grid** (`tools/research/gridterms.ps1`, `gridcap.ps1`):
    - the game's static cube sampled at face centres matches our decode;
    - the per-car `shCubeMapDampnerLight` varies only with heading;
    - `o[1].w` = 0;
    - the track lightmap under the cars is ~0.9.
  - **Per-car paint on the captured grid:** older fit without the table 14.4, the game's own term with the table
    14.7 (equal).
  - **AI window glass:** now the game's own formula too: the static cube x its gain x CubeScale, the fitted
    env_scale 0.25 retired. Grid glass per car 15.7 at 0.25 -> 13.8, and 14.6 before the table. The player's glass
    keeps its fit (player_env 0.1): the game's live cube sees the player's dark cabin from inside, ours leaves the
    cars out.
- **Engine sound in Godot (2026-11-25, first version):**
  - **Decoding.** FM3's FMOD banks decode: `FM3-files/tools/fsb_extract.py` gives each sound a RIFF/XMA1 header
    (as the game's own .xma music has) and FFmpeg 8.1 (the recomp's thirdparty build, xma1 / xma2 decoders) makes
    PCM with exactly the declared sample counts. Check: every Gallardo exhaust loop's fundamental is exactly
    2.30 x its rpm label / 60.
  - **Converter.** `tools/fm3_engine_audio.py <car> [--preview]` follows the game's chain: Data_Car -> stock engine
    -> `EngineTuning/<engine>_ET.xml` (idle, redline, volumes, the L0 upgrade's layers) -> `HarmonicTuning/*_HT.xml`
    (loops: wavebankindex, rpm_min / rpm_sample / rpm_max, volume; DSP gain curves) -> `Soundbanks/LOD1/*.fsb`. It
    writes the loops (WAV) + `engine.json` to `out/audio/<car>/`; `--preview` renders an idle -> redline sweep.
  - **Player.** `fm3_engine_audio.gd` plays the recipe as FMOD's harmonic engine does (crossfades over the rpm
    ranges' overlaps, pitch = rpm / rpm_sample, the gain curves: PhysicsCoeff weights -> three-point curve).
    `world_view.gd` attaches it to the player's car once FM3N names it and drives it with the stream's rpm and the
    car's own throttle (FM3E v4+). The gain curves' torque inputs (PosTorque / NegTorque) come from the engine's own
    torque curves since the evening (`engine.json` 'torque', from `fm3_car_physics.py`: throttle x full-throttle
    torque / its peak, (1 - throttle) x |engine braking| / its value at the redline); the normalisation is our
    assumption (FMOD's parameter ranges not read yet).
  - **Not yet:** the DSP blocks (expander, load PEQs), burbles / backfires, intake chuff, transmission / turbo /
    tyre / wind / collision sounds (the other .fev families), and the AI cars.
  - **FM2's port** (zer0ducksgiven, MIT): `tools/xmadecode.cpp` (FSB3 XMA decoding) and `tools/mkloops.py`
    (seamless-loop fixes) are worth reading; it has no FMOD reimplementation.
    `FM3-files/research/fm2-decomp-report.md` has the full research.
- **The game's cameras in Godot (2026-11-25, first version, `FM3_GAME_CAM`):**
  - **Sources.** `Media\Camera\CameraSettings.ini` has the in-race cameras' parameters (FollowLowCam / FollowHighCam:
    height above the ground, radius / target offsets, FOV against speed, yaw and height springs; HoodCam, BumperHigh /
    LowCam, CockpitCam, WheelCam). `CameraPhysics.xml` has 29 G-force / slip driven sway and shake layers per camera.
    The database adds per-car `CameraOverrides` and `CarPartPositions` (part 4 = the driver's eye).
    `CarRelativeCams.xml` holds the replay / TV cameras (bounding-box-space keys, 155 cams in groups).
  - **Measured on the running game** (`tools/research/camrec.ps1`: the race AI drives the player's CR-X, RB cycles
    the views, `tools/camrec.py` records the drawn camera + cars, `tools/camfit.py` gives the camera in the car's
    frame), per camera class:

    | Class | Camera | Offset in the car's frame (z = backwards) | FOV |
    |---|---|---|---|
    | 82001C74 | chase near | 4.83 m behind, 1.82 up (2.08 above the ground = HeightMinAboveGround) | 55 -> 58.7 deg, 5 -> 50 m/s |
    | 82001DB4 | chase far | 5.24 behind, 2.03 up (2.29) | as near |
    | 8200206C | cockpit | 0.361 / 0.815 / 0.127 = part 4 + CamCockpitOffset in x and y | 51.3 deg |
    | 82001FF4 | hood | 0.78 ahead, 0.797 up | 53 fixed (HoodCam FOV0) |
    | 82001F7C | bumper | 1.225 ahead, 0.859 up (1.15 above the ground = BumperHighCam RestHeightAboveGround 1.1) | varies with speed |

    The chase cameras swing out +-0.6 m in corners (the yaw spring).
  - `world_view.gd _game_cam` builds them from the player car's pose (still from the stream, until the physics runs
    in Godot) with the INI's springs.
  - **The game's camera layers** (`Media/Camera/CameraPhysics.xml`, read by `_gc_load_layers` from the game's own
    file, `FM3_CAMERA_XML` = another copy, e.g. a mod; `FM3_GAME_CAM_NO_LAYERS=1` off): per camera (FollowCam =
    chase_near, FollowCam2 = chase_far, DriverCam = cockpit, Hood, BumperHigh) the deterministic layers are applied:
    Gs_Longitudinal / Gs_Lateral (the car's acceleration in its own frame, in G) through the three-point curve
    (mirrored = odd), x Param into a car-space offset (metres) or car / camera-space yaw-pitch-roll (degrees), through
    the layer's spring (K, D). The chase cams have only one such layer (a 2.5-4.75 cm lift under acceleration): their
    roll layers are Simplex noise, so the chase gap is not sway. Hood / bumper / cockpit get pitch under acceleration
    (up to ~2 deg), yaw / roll in corners (0.35-2 deg). Left out: noise shakes, slip, collision impulses, surface
    bumps, the speed FOV layer. The game's frames are left-handed: yaw and pitch turn around into Godot's, roll does
    not. **Measured live on the hood camera** (`FM3_GAME_CAM_LOG=1` prints the game's drawn camera and ours as
    pitch / yaw / roll in the stream's car frame with the car's G; 208 moving samples): the game's pitch does not follow
    the longitudinal G there, yaw and roll follow the lateral G at ~0.6 of our G estimate. With those gains
    (`FM3_GAME_CAM_GGAIN`, default `0,0.6`) yaw rms 0.25 -> 0.19 deg, roll 0.13 -> 0.07, pitch unchanged 0.55.
    Whole-frame diffs can't show this: two runs with the same settings differ by up to 5 (the race's positions).
    (The offline recordings, `tools/camrec.py`, fitted in the car's frame, said the in-car cameras look up 0.7-0.95
    deg per G of forward acceleration; in the viewer's frame the live log shows none: open.)
  - **A second car** (the Acura RSX Type-S on Catalunya's Free Play race, the race AI driving, `tools/camrec.py`):
    chase near 4.95 m behind / 1.89 up, far 5.29 / 2.09, against the CR-X's 4.83 / 1.82 and 5.24 / 2.03 (car frames,
    medians). The RSX is 0.6 m longer and 0.11 m taller but also drove faster (median 33 against 21 m/s): size and
    speed are not separated, and the fixed rig is within 0.12 m for both cars.
  - **Open:** a per-car rule if a bigger car shows one (a truck or a long GT), the replay cameras.
- **Telemetry from the car-physics object (FM3E v4, FM3-ReGPU b213457):**
  - Dumping the player's physics object while the AI drove found throttle +3408, brake +3412, steering +3416 (the
    block repeats at +2744 / +2780), gear byte +1937, clutch +2672. Engine speed +324 and redline +452 are FH1's
    ICarDynamics offsets; FM3's controls are elsewhere than FH1's +3904.
  - The stream sends them (56-byte packet); the engine sound uses the throttle.
  - **v5 (FM3-ReGPU, 76 bytes):** + the car's speed, m/s (+2792: within 3% of the speed from its positions) and four
    wheel speeds (+4164 + 1040 x i: four 1040-byte wheel blocks; FH1's are 1024 from +3936). In each block, +284 after the speed: the wheel's
    position in the car (CR-X: wheels 0, 1 front at z +0.874, 2, 3 at -1.426: wheelbase 2.30 m = the real car's;
    x -0.731 / +0.731 / +0.725 / -0.725, so 0 and 3 share a side), +108: radius 0.295. The own chase camera's FOV uses that speed when present.
  - **Checked against the game's own telemetry screen** (d-pad UP in a race opens it, RIGHT cycles GENERAL / FRICTION
    / SUSPENSION / BODY ACCELERATION / TIRES, MISC. / HEAT; tools/research/telepage.ps1-style run: shot + 8 KB dump
    per page): GENERAL's speed 74 km/h / 6,135 rpm / gear 2 = the stream's 74.4 / 6,122 / 2. The wheels' order is
    FL, FR, RR, RL (wheel 0 at x -0.731 = left). **v6 (FM3-ReGPU, 92 bytes):** + the tyres' temperatures, deg C: each
    wheel has three zones in deg F at +3492 + 1040 x i, whose mean is the page's value (53.99 / 52.94 / 49.08 / 49.48
    against 54.0 / 52.9 / 49.1 / 49.5 on the same frame). Power / torque are not floats in the first 8 KB (another
    object). Other page values to find the same way: friction % of peak, suspension travel, camber, pressure (cold
    setting 30 psi at +188 of the wheel block), wear.
  - Next: the FRICTION / SUSPENSION pages' fields, the car's G (for the camera layers).
- **Track fog (2026-11-25 evening; the viewer had none):** TrackSettings.xml `<Fog>` holds up to 8 settings (Enabled,
  Angle = a heading in degrees, Color, Near / NearDensity, Far / FarDensity; parser `sub_8283CE78`, stored from +816 of
  the settings object). The track vertex shaders compute f = clamp(distance x c241.y + c241.z, 0, c241.w) (FogConsts:
  linear from NearDensity at Near to FarDensity at Far, capped there), the pixel shaders lerp their gamma-space colour
  to c242 FogColor by f; the sky's shader and **the car shaders have no fog** (no fog constant in
  `Media/Shaders/Cars/shaders_v11.fxobj`). The viewer: `fm3_track_export.track_fog` writes the enabled settings into
  `<track>_track.json` 'Fog' (all 17 existing files patched in place), `world_view.gd _fog_update` blends the two
  settings around the camera's heading each frame into the global shader parameters `fm3_fog_color` / `fm3_fog_k`
  (project.godot `[shader_globals]`), which the track shaders apply (`fm3_fog.gdshaderinc`: fm3_baked, fm3_baked_blend,
  fm3_blend, fm3_glass). The heading convention was measured on the live RoadAtlanta grid (settings at 30 / 170 / 270 /
  305 deg, the 170 one blue): atan2(forward.x, forward.z) of the viewer's world gave 21.5 / 19.5 / 17.8, the other
  three sign conventions 24.4-27.1, no fog 29.4 / 27.1 / 26.6. Strong fogs: RoadAtlanta 0.4-0.6, Mugello 0.54,
  Silverstone 0.5, NewYork 0.4; CrownJewel's is weak (0.13 / 0.05). `FM3_NO_FOG=1` off, `FM3_FOG_HEADING=sx,sz,offset`
  another convention, `FM3_FOG_PASS=1` a full-screen pass instead (`fm3_fog.gdshader`, fogs the cars too).
  **Survey with fog** (live, each track's Free Play grid; before -> after): RoadAtlanta 33.4 -> 21.7 / 21.2 / 19.5,
  Tsukuba 17.8 -> 15.8, AmalfiGP 24.8 -> 23.0, Catalunya 12.7 -> 11.9, SunsetInfield 19.6 -> 18.9, LeMans 16.4 -> 16.1,
  LagunaSeca 17.2 -> 17.1, Mugello 18.0 -> 17.8, Silverstone 17.0 -> 16.9, RoadAmerica 22.1 -> 21.7, NewYork 25.4 ->
  24.7, Motegi 15.1 -> 15.4, Suzuka 15.9 -> 17.0, Sebring 22.2 -> 23.7, MapleValley 24.0 -> 30.5. MapleValley is the
  same without fog (30.6: the grid slot differs between runs, "3/8" here, which moves a track by several points):
  there the road's sun specular comes out as a hard-edged white patch where the game has a broad grey sheen (with the
  specular off: 39.5, the road dark brown): the specular's shape / mask is wrong on that road: open (the skid lerp's
  ends swapped: 33.3, worse; MapleValley's RoadSkid2 2.01 makes m up to ~3.4 where the skid channel is 0).
- **The crowd** (NewYork's sidewalk people black in ours): the crowd cards are a lit material at TrackSettings' Crowds
  dark factor (0.5), so cards with the sun behind them get only ambient; the game picks between its dark (0.5) and
  light (1.25) factors per person (probably from where they stand). Its crowd shader is in the executable, not found
  yet: open.
- **Open:** bloom (bright pass: exposed scene + 0.42 x last frame's bloom - 1/255 - bloomCutoff, x bloomScale, on
  the HDR scene: needs values above 1, our picture is clipped at 1), the road specular's overshoot (re-check with the
  exposure), one opponent per race without an FM3N name (Silverstone's B.Giese: not the colour-file case); the palette barriers (`diff_clr_spec_2`: a per-model
  palette row, ModelData c148), LeMans' `shldr_blnd_spec_vclr_dualmix_4`, reflective glass `diff_spec_opac_refl_3`,
  MapleValley's Castrol banners and asphalt tone, Catalunya's grass 25% dim.

## Physics in Godot: feasibility (2026-11-25)

The user asked whether zer0ducksgiven/Forza-Motorsport-2-ReGPU (`FM2-decomp` and its other branches) could help run
FM3's physics in Godot with FM3's physics files. Findings (full report: `FM3-files\research\fm2-decomp-report.md`):

- **No branch has physics, FMOD or camera code.** `FM2-decomp` is a Ghidra decompilation pipeline with 13 small
  replaced functions (C runtime, a name hash, one matrix product); its author keeps decompiled game code out of the
  repository on purpose. Useful bits: FM2's physics timing notes (fixed substeps), the XMA / FSB handling through
  FFmpeg (we decode FM3's FSBs the same way now), loop tooling. MIT licence.
- **FM3's physics data is all readable:** `Media\Physics\PhysicsSettings.ini` (~200 tunables: friction scales,
  TCS / ABS / ACS, gravity, shifting), `surfaceTypes.xml` (per-surface friction, rolling resistance, bumps),
  `CollObjects.xml`, per car `physics\maxdata.xml` (collision box + spheres), and the database (`gamedb.slt`:
  `Data_Car`, `Data_Engine`, `List_TorqueCurve`, `List_TireFrictionCurve`, the 47 `List_Upgrade*` tables: mass,
  weight split, springs, dampers, anti-roll bars, gearing, aero, tyre compounds). The executable reads them with the
  SQL strings at 820F7FEE onwards; the physics step runs at `CarPhysicsUpdateHz` 359 (set in `sub_827C9B50`).
- **What the data does not give:** the model itself (how tyre curves, load, slip, camber, temperature and pressure
  combine; the drivetrain and differential; aero). That lives only in the recompiled PowerPC code
  (`out/ppc-rexenon`, thousands of functions, no names).
- **Two ways:**
  1. Reverse-engineer FM3's own model from the recompiled code (find the 359 Hz step, follow it into the tyre / engine
     functions, rewrite them in GDScript / C++ for Godot, check against the live telemetry stream: the FM3E packet
     already carries rpm, throttle, brake, gear, clutch, speed and wheel speeds). Exact, but weeks of work per
     subsystem.
  2. Write a new Godot vehicle model (Godot's own `VehicleBody3D` is too simple; a custom raycast-wheel model with a
     Pacejka-like tyre fitted to FM3's friction curves) fed by FM3's data. Drives like a Forza-ish car within days,
     but not like FM3.
  Recommended: 2 for a playable prototype, with 1 used subsystem by subsystem (engine torque and gearing first: the
  easiest to verify against the stream's rpm / gear / speed).
- **First check of the data against the running game** (`tools/camrec.py` now also records the FM3E telemetry,
  'eng' rows; 9,691 packets over 45 s of the AI driving the test grid's CR-X): the database's units are SI (redline
  `SimRedlineAngVel` 837.76 rad/s = 8000 rpm; tyre 195/60 R14 -> radius 0.2948 m = the wheel block's 0.295). Speed
  from rpm through the stock gearbox (`List_UpgradeDrivetrain` Ordinal 320 -> `List_UpgradeDrivetrainTransmission`
  DrivetrainID 73: 3.166 / 2.052 / 1.416 / 1.103 / 0.87, final 4.266): second gear within 3.4% of the stream's speed
  (729 samples), third 11% off, the gears' ratio 1.35 against the stock 1.45: the Baseline save's CR-X is probably
  tuned (the profile's tuning setup, not in the database). The four wheel speeds follow the car's speed within 3%.
- **The engine's torque is exact** (`tools/fm3_car_physics.py <car> [--out json] [--check camrec.npz]`, any of the
  510 cars): the stock camshaft row (`List_UpgradeEngineCamshaft`: redline, stall, TorqueCurveMaxRPM 9500,
  96 entries) picks a full-throttle and a zero-throttle (engine braking) curve in `List_TorqueCurve` (values x
  TorqueScale N m, 100 rpm apart; peak at 7,100 rpm = `SimPeakTorqueAngVel`). Against the game's own telemetry page:
  145.4 / 151.4 / 150.8 N m at 6,135 / 6,826 / 7,346 rpm (page: 145.4 / 151.4 / 150.8) and 93.4 / 108.2 / 116.0 kW
  (page: 93 / 108 / 116). Not yet: how throttle blends the two curves, the drivetrain losses / GameTorqueScale, drag
  units, the tyres. A longitudinal fit (torque through the gearing against the stream's acceleration) needs a
  recording with long full-throttle stretches: the race AI rarely holds full throttle (84 usable samples).

## Next for stage A (where to continue)

The user's last question was whether to chase the remaining uneven steps or call it good enough: ask.
1. Smoothness left: the speed jitter's p95 (24-41%): check against the game's own frame times (the FM3V timestamps'
   spacing, `live_record.py`) before changing the viewer; the 17-20 ms delay could shrink to ~1 frame if the jitter
   allows.
2. Wheels: spin and steering (the car object's wheel matrices at +0x90.., four placed and their spun/steered copies).
3. The crowd and people: animated in the game, static captured silhouettes here.
4. The player car's interior parts (gauges, driver) for the in-car views.
5. Props for the other layouts (another `.pvs`), other tracks; attaching cars without starting at the capture's grid.
   **Done in a first form (2026-11-24):** `tools/build_track.ps1 -Track <Name> [-Ribbon NN]` builds any track's scene
   from its files; "FM3N" names each car (media name, Combo_Colors colour, paint type: car object +0xC44) and the
   viewer attaches the car library's model (`tools/fm3_car_library.py` -> `out\cars`) to any car the scene lacks.
   Test: `tools\live\live_compare.ps1 -Gltf out\world\crownjewel.gltf` (capture-free CrownJewel: all eight cars from
   the library). Library cars as bright as the captured ones since 2026-11-24 (PLAN-CARS). Capture-free scenes have
   the game's sky (the sky dome's textures: the last .pvs texture entries with flags 1) and sun (TrackSettings.xml
   ShadowLightDirection): live CrownJewel grid vs game 46.0 / 36.0 / 27.1 (grey sky, default sun) -> 21.7 / 21.7 / 20.0
   (captured Ladera: 20.7-20.8); then crowd cards without lightmaps, road lines blended by their mask (fitted colour 0.6),
   library wheels / calipers: **20.4 / 20.2 / 18.5** (game and Godot pictures line up within 1 px in all three views:
   the rest is shading and content: HUD, the player's paint, crowd, lighting); the crowd from the .crowd files (FM3-FORMATS) 20.4 / 20.1 / 18.5; the paint summed in gamma space with refitted
   reflections (PLAN-CARS) 20.2 / 19.9 / 18.2; the game's liveries (below) 19.9 / 18.6 / 18.2.
   **The frozen grid skipped the per-car update (found 2026-11-24):** there the game sends no drawn-camera frames, so the
   viewer took its hand-off path, which only placed the cars: has_live (the player's live cube), brake lights, the
   in-car switch and wheel blur never ran in grid pictures (they did after an RB press and in races). Now both paths run
   `_update_live_cars`. With it: the player's paint on the live cube at x0.3 (CR-X 10.4), its glass dim (the game's
   per-frame cube sees its own cabin: CR-X glass 17.1 -> 12.4), AI glass blended in gamma space at reflection 0.25.
   live_compare's picture also waits for the liveries and 3 frames more, and keeps the viewer's stderr (godot.err.log).
   Live: captured Ladera 19.8 / 18.8 / 17.7 (in-car 19.2 / 18.9 / 17.6), capture-free CrownJewel 19.9 / 18.4 / 18.0.
   **In-car while moving (open):** at 71 km/h our right A-pillar sits left of the game's (race6 in-car 25.9 / 28.2 /
   28.7). The camera's offset from the car grows with speed (-0.23 m at 5-10 m/s, -0.11 m at 30-45 m/s: the game's head
   lean easing as acceleration drops); sampling the cars later or earlier than the camera (`--live-car-lead` ms, new;
   `live_compare.ps1 -ViewerArgs`) does not help (-9 / 0 / 4.5 / 9 ms: 26.2 / 25.9 / 26.5 / 26.9): not a timing gap.
   Next: compare the cockpit's yaw against the camera's in the stream (head turn into corners?).
   **Liveries (custom paint):** `tools/live_liveries.py <FM3 run dir> <gamedb.slt> out\cars\live_liveries <viewer log>`
   while a race is loaded: one traced frame through the debug server, every car-paint draw's t0 read from guest memory
   (peek) and decoded, named by its paint colour (c118 = the car's Combo_Colors RGB, the cars from the viewer's FM3N
   log); the viewer polls the folder and lays each livery over its car's paint colour. 8 cars in ~8 s; the player's
   yellow CR-X 35.0 -> 12.5. Needs ReGPU's debug server (play.cmd has it on).
   Viewer speed there (RX 6650 XT, 720p, MSAA 4x, game uncapped beside it; `live_smooth.ps1 -Gltf`, 30 s): 32 fps,
   the same as the captured Ladera (33); the live reflection cube costs ~40%: `--live-cube-faces 2` 40 fps, `1` 45,
   `--live-cube 0` 52 (faces not rendered keep their last picture: reflections lag; default stays 6). With the game
   capped (`-GameEnv FM3_MAX_FPS=60`) 36 fps and speed jitter median 1.0% / p95 5.2% (uncapped 4.1% / 17.6%), but
   35 ms behind the game instead of 11.
   In-car (2026-11-24, `live_compare.ps1 -Cameras 2`): the cockpit's windows as the game's cockpit_glass (clear, a
   highlight only), the cockpit unlit by the sun (FM3: SHCockpitDir 0; render layer COCKPIT_LAYER) and the in-car
   exposure x1.5 (the game shows the outside brighter from the cockpit), gauges at gain 0.25: capture-free CrownJewel
   34.8 / 36.3 / 36.7 -> 17.0 / 17.6 / 18.4, captured Ladera 37.6 / 38.6 / 37.5 -> 20.6 / 19.8 / 18.9. Left: the HUD,
   the driver's hands, the cluster housing (bluish grey, the game's black).
   Mirrors (`fm3_mirror.gdshader`, `--mirrors 0` = dark glass): one 512x256 viewport per cockpit mirror, rendered
   only in-car; the glass looks itself up through a camera at the reflected eye framing it, the picture comes from a
   rear camera (40 deg, 6 deg up from level, fitted; the middle mirror straight back), as FM3 renders its mirror as a separate scene. The CR-X's
   middle mirror then shows the stands and the run-off behind like the game's, framed a little lower; in-car vs game
   17.4 / 17.8 / 18.6 (dark glass 16.8 / 17.4 / 18.3: a framing offset costs more pixel difference than flat glass).
   Their cost in-car (`live_smooth.ps1 -Cameras 2`, capture-free CrownJewel, 30 s): no mirrors 33 fps, three every frame
   26, one a frame in turn 29, plus a 300 m far plane 30 (kept: one a frame, 300 m). The cabin's plain surfaces: `fm3_cockpit.gdshader` (unshaded: albedo x baked
   brightness x a hemisphere by facing, top 1 / bottom 0.05 fitted; no sun, no sky reflection, which had tinted the dash
   blue): capture-free in-car 17.5 / 17.9 / 17.3; captured Ladera grid 20.0 / 19.2 / 18.1, in-car 19.1 / 18.9 / 17.6.
   Vertical cabin faces still too dark (A-pillar 3 vs the game's 13); tried: the game's SH numbers as a top light (all
   black) and a flat light (roof liner 88 vs 16). live_compare's picture waits (up to 10 s) for the library cars. Open: the player's
   custom paint (the livery layer: the car object holds only the database colour, +0x9A0 etc.,
   `FM3_LIVE_DUMP_CARS=1`), crowd sprites, the sky dome's seam line, the sea's colour.
6. Then stage B: ReGPU skips what Godot draws.
