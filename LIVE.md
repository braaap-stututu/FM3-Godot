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
    **2026-11-25 evening: the game's own acceleration** (FM3E v8, the physics object's +2512 in the car's frame) now
    feeds the layers (`FM3_GAME_CAM_ACC=derived` = the positions' second difference as before; `FM3_ACC_LOG=1` logs
    both). Lateral: the two agree (slope 0.91-0.98, r 0.9); longitudinal: the positions' value is noise (r 0.1). Three AI
    races on the hood camera: derived G at gain 0.6 yaw / roll / pitch rms 0.080 / 0.068 / 0.381 deg, the game's G at
    0.6 0.106 / 0.044 / 0.379, at 1.0 0.319 / 0.193 / 0.475: the 0.6 is the game camera's own response, not an
    over-estimate of ours.
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
    object). **v7 (108 bytes):** + the suspension's position, m, FL FR RR RL (+3440 + 1040 x i, about -0.15 at
    rest): 8 SUSPENSION-page shots with dumps a second apart (the readouts cropped into one picture and read), the
    page's travel (cm) = (value - rest) x 100 (slopes 0.0095-0.0103 m per cm on all four wheels, correlation
    0.85-0.99 with the shot ~0.2 s from the read). Other page values to find the same way: friction % of peak
    (no single-sample match), camber, pressure (cold setting 30 psi at +188 of the wheel block), wear.
  - Not found (8 page samples each, `telepage.ps1`-style runs with the readouts read): BODY ACCELERATION's total G
    (0.34-0.69 G; no vector in the first 8 KB has that magnitude in G or m/s2, the best correlation needs a scale of
    18.9 and an offset: the page probably shows a smoothed value), FRICTION's % of peak per tyre (best fields near
    +4080 + 1040 x i correlate 0.56-0.94 across the wheels: not conclusive).
  - Next: the car's G (for the camera layers: our G from the stream's positions runs ~1.6x the game's), friction.
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
  (729 samples), third 11% off. **Not a tuned gearbox but wheel slip** (corrected the same evening): the Free Play
  RSX (stock) shows the same, speed from rpm / real speed 1.17 / 1.09 / 1.04 in gears 2 / 3 / 4 on Le Mans (falling
  with the gear, as the driven wheels' slip under torque does; a wrong radius or final drive would be one factor),
  and the telemetry page's own rpm / speed pairs give 1.05 (2nd) / 1.03 (3rd) for the CR-X. The stream's wheel
  speeds follow the car's speed within 3% (ground speed at the contact, not the wheels' spin).
- **The engine's torque is exact** (`tools/fm3_car_physics.py <car> [--out json] [--check camrec.npz]`, any of the
  510 cars): the stock camshaft row (`List_UpgradeEngineCamshaft`: redline, stall, TorqueCurveMaxRPM 9500,
  96 entries) picks a full-throttle and a zero-throttle (engine braking) curve in `List_TorqueCurve` (values x
  TorqueScale N m, 100 rpm apart; peak at 7,100 rpm = `SimPeakTorqueAngVel`). Against the game's own telemetry page:
  145.4 / 151.4 / 150.8 N m at 6,135 / 6,826 / 7,346 rpm (page: 145.4 / 151.4 / 150.8) and 93.4 / 108.2 / 116.0 kW
  (page: 93 / 108 / 116). Not yet: how throttle blends the two curves, the drivetrain losses / GameTorqueScale, drag
  units, the tyres. A longitudinal fit (torque through the gearing against the stream's acceleration) needs a
  recording with long full-throttle stretches: the race AI rarely holds full throttle (84 usable samples).
  With every throttle level (three recordings, 2,365 samples in gears 2-3 away from shifts and brakes): torque =
  closed + throttle x (full - closed) through the gearing explains 62% of the measured acceleration with sensible
  values (drivetrain factor 0.73, drag 67 N at 30 m/s, rolling 858 N); throttle x full alone explains 61% but needs a
  negative drag. Residual 1.2 m/s2 (corners, slopes, wheelspin). With the database's gear ratios (torque is
  multiplied by the gear, not by the slip) and a second car (the stock RSX, 75 s at Le Mans incl. the Mulsanne,
  2,721 samples): the blend again gives physical values on both cars (drivetrain factor 0.63 RSX / 0.75 CR-X,
  drag 79 / 94 N at 30 m/s, R2 0.47 / 0.62), throttle x full alone needs negative drag on both. The drag and
  losses are not settled (the fitted drag is small next to real cars'; `BodyAeroLongitudinalDrag` 170 / 134 not yet
  related).
  (The stream's "clutch" field, +2672, sits at ~0.13 while driving: not a plain pedal value.)

## arcanite24's Forza ports: what they give us (2026-11-25 evening)

The user asked whether arcanite24's `pinyon-shift` / `cobalt-shift` recomps help with telemetry. Read-only clones
(not kept in the repo): `github.com/arcanite24/{cobalt-shift, pinyon-shift, pinyon-shift-native}`.

- **cobalt-shift** (FM3, Xbox 360, performance first; 65 files, ports some FM3-ReGPU hooks under MIT): no telemetry,
  physics, camera or audio work. Nothing to take for this project.
- **pinyon-shift** (FH1 recomp, the FM4-era engine): telemetry out over UDP in Forza's Data Out layouts (FM7 Dash 311 B
  / FH4-5 324 B, `telemetry_udp_target` 127.0.0.1:5300, for SimHub etc.) from the car's `ICarDynamics` (car +0x2D90),
  documented in `site/findings/objects.toml` ("Car dynamics"). **FM3's physics object is the same kind of object:**
  engine speed +324 and redline +452 (rad/s) are at the same offsets in both games. FH1's other fields (from +1228 on)
  have moved in FM3 (FH1 idle +1228, limiter +456, gear +2240, speed +3128 read 12 rpm / 1 rpm / - / - in FM3 dumps),
  but the layout carries over: FH1's controls block (+3904: gas, brake, steer, clutch, handbrake) = FM3's +3408
  (throttle, brake, steer +3416; +3420 / +3424 stay 0 while the AI drives: clutch / handbrake candidates, unconfirmed);
  FH1's four 1024-byte wheel blocks (+3936; per wheel +0 suspension position, +12 wheel speed rad/s, +496 slip ratio /
  peak (1 = peak grip), +520 slip angle / peak, +796 ground contact, +337 surface index, +860 spring rest, +828 rate)
  = FM3's 1040-byte blocks (our +4164 wheel speed, +3440 suspension, +3492 tyre temps per 1040). Also FH1: ABS active
  +3020, TCS amount +3004, the game's own rumble inputs. **Our "+2672 clutch" is not a clutch**: 0.12 in 2nd, 0.5-1.0
  in 1st under wheelspin, 0.02-0.14 in 3rd (four recordings): a slip / traction value.
  **Done the same evening: Forza Data Out from the recomp** (FM3-ReGPU `src/hooks/data_out.cpp`, `FM3_DATA_OUT=1` or
  the launcher's "Telemetry out (SimHub)"; FM7 Dash packets on 127.0.0.1:5300, checked on an AI race with
  `tools/analysis/dataout_listen.py` there). New physics-object fields: +2544 position, +2560 velocity, +2512
  acceleration (world; the body matrix's z axis points to the rear). Not found yet: slip ratio / angle. The FRICTION
  page shows each tyre's grip use in % (eight shots with dumps, readings in `out\research\telepage5\
  friction_readings.txt`): no per-wheel field fits (best +3480 + 1040 i, r 0.74). +4140 / +4152 + 1040 i behave like
  tyre loads (front-heavy, up under braking and on the outside in corners). The FM3E stream (Godot) could carry the
  new fields too.
- **pinyon-shift-native** (a clean-room FH1 engine, C++20 / Vulkan; written from specs, not from game code): a full
  car simulation from the game's own data, validated against the real game within 2% (R34: 0-100 km/h 5.83 vs
  5.84 s, braking 8.42 vs 8.57 m/s2, a lap +1.08%, top speed 147.6 vs 147.5 km/h; `docs/SPEC_QUESTIONS.md` Q20-Q40).
  This is the template for "physics in Godot" (option 2 above, but with the game's own rules):
  - Steps: 120 Hz outer step, `CarPhysicsUpdateHz` (359) substeps for tyres / drivetrain / body; semi-implicit Euler.
  - Tyres: the game's own `List_TireFrictionCurve` arrays (no Pacejka): two curves per direction (light / heavy load,
    kgf, blended between `MinLoadCurve` / `MaxLoadCurve`), slip ratio `(w r - vx) / max(|vx|, 1)`, slip angle in
    degrees, combined slip `hypot(sx, sy)` of the peak-normalised values; sidewall stretch from tyre size.
  - Engine: `T = closed + throttle x (full - closed)` (our fit found the same blend); they synthesise the closed curve
    (FH1's DB has only a scalar), FM3's DB has a real zero-throttle curve (`fm3_car_physics.py`). Upgrade TorqueScales
    add, not multiply; `GameTorqueScale` scales only the wheels' torque.
  - Units: aero coefficients are kgf at 150 mph (x 9.80665 / 67.056^2 -> N per (m/s)^2); springs, dampers, bump stops
    and anti-roll bars are per kg of mass; `RelVelClamp` in rpm; `List_UpgradeCarBodyWeight.Mass` in kg (FM3's
    `Data_Car.CurbWeight` in kN, as found here).
  - Clutch / gearbox state machine (`ClutchInTime`, `GearShiftTime`, `ClutchOutTime`), open diffs and LSDs, ABS / TCS,
    brakes (`BrakeTorqueSlider`, bias), suspension with bump stops, aero, all with the tables and columns they read
    (their `libs/cars/src/database.cpp` 550-731: the SQL join chain; `libs/drive/src/from_physics.cpp`).
  - Cameras: they read `CameraSettings.ini` + `CameraPhysics.xml` as we do (same layer types and curves), spring
    damping `SpringDPercent x 2 sqrt(K)`, implicit spring step.
  - Engine sound: loops crossfade by rpm (`log2(1 + t)` on overlaps), pitch from rpm_sample with pitchMin / pitchMax,
    load parameters `a n + b throttle + c posTorque + d |negTorque|` through 3-point curves (posT = T / T_full,
    negT = T / T_closed): the same inputs as our `fm3_engine_audio.gd` recipe.
  How to use it: their source is BSD/clean-room but written for FH1; FM3's tables differ in places (check each column in
  `gamedb.slt`). A Godot car model following their structure, fed by `fm3_car_physics.py`, checked against the FM3E
  stream (rpm, gear, speed, wheel speeds, suspension, tyre temps) is the next physics step.

## Next for stage A (where to continue)

**User's list (2026-11-25 evening): glass shininess / reflections.** The user, comparing the live pictures: the
RSX's rear window and tail lights are not as reflective as the game's (on the Sebring / RoadAtlanta grids the game's
tail lenses look bright and pinkish, ours dark red: `fm3_carlens.gdshader` is only a multiply filter over the lamp, the
game's lens also adds a reflection; the rear window, `fm3_carglass.gdshader`, player_env 0.1). The paint is close now,
but the reflections in it are blurrier than the game's: check the live cube's resolution / mip level used for the
paint lookup against the game's cube (the paint's term: LIVE.md "Car paint reflection").

**Done the same evening (lamps and black glass):** measured on the Sebring RSX (Free Play, chase view, boxes on each
tail lamp) and the CrownJewel grid's CR-X / Eclipse, one boot per track with several viewer variants (scratch scripts:
`live_track.ps1` / `live_compare.ps1` with a loop over environment settings, one Godot start each).
- The game's settings (`Media\Cars\ShaderSettings\Normal.xml`) explain the look: the lamps' **reflectors** are
  mirror-like (`<reflector>` CubeScale 1.5, Fresnel min 0.15) and the RSX's red lens is nearly clear (GlassColor alpha
  0 = 15% opaque head-on); the CR-X's red lens is nearly opaque (GlassColor (0.6, 0, 0, 0.7), max 0.9).
- Lenses now use the game's glass formula (`fm3_carglass.gdshader` with `lens`: no player dimming, no highlight
  glints) instead of the fitted multiply / cloud / reflection chain (`FM3_LENS=filter` = the old chain), plus two
  fitted terms: the lens tints what is behind it (`lens_filter` 0.65; 0.8 matched the RSX's colour, 0.65 scores
  better on both grids' whole frames, Sebring 22.7 -> 21.9) and its own
  colour is lit at 0.35 (`lens_light`: the CR-X's opaque lens 60 / 23 / 20 in the shade of its rear).
- Reflectors, tail-lamp bulbs and black glass get a reflection pass over their lit texture (`fm3_reflector.gdshader`,
  `_add_reflector_pass`): the static car cube x CubeScale x the game's Fresnel (reflector 1.5, bulbs 0.2, black glass
  0.53 / min 0.4), half tinted by the lamp texture (the CR-X's red reflector panel). Switches: `FM3_REFLECTOR`,
  `FM3_BULB`, `FM3_BLACK_GLASS` (scales, 0 = off), `FM3_REFLECTOR_TINT`, `FM3_LENS_FILTER`, `FM3_LENS_LIGHT`,
  `FM3_REFLECTOR_SPEC` (the reflectors' sun highlight, 0: it left hard glints).
- Results (mean |diff| against the game in the region): Sebring RSX tail lamps 67.5 / 56.5 -> 40.4 / 29.9, its whole
  rear 29.7 -> 19.8 (lamps 21 / 5 / 4 -> 69 / 37 / 32, game 114 / 65 / 63: the reflectors and bulbs now show through
  red lenses as in the game; `out\live\rsx_lamps_game_old_new.png`); CrownJewel CR-X rear 16.7 -> 17.6 (its clear
  corner lenses 44.8 -> 29.8, the red bar the same), Eclipse rear 22.8 -> 23.1, whole grid frame 18.6 / 18.0 / 17.3 ->
  18.5 / 18.2 / 17.5. Rejected on the way: an untinted reflector reflection (the CR-X's red panel grey), the bulbs' and
  lenses' sun highlights (glints), lens light 1 (CR-X lens 2x too bright; the RSX's tails liked it slightly).
- **The player's windows reflect more** (`fm3_carglass.gdshader` player_env 0.1 -> 0.5, `FM3_PLAYER_ENV`; the 0.1 was
  fitted before the exposure pass): CrownJewel CR-X rear window 16.6 -> 10.9 (21 / 25 / 23, game 20 / 25 / 29), the
  car 15.9 -> 15.1; Sebring RSX sunroof strip on the roof 58.8 -> 48.2 (it is player glass), rear window 13.6 -> 13.9,
  the car 19.4 -> 19.2.
- **The player's windows at full reflection** (player_env 1.0, after the user pointed out that the dark band under the
  RSX's rear window is what the glass rests on, hidden in the game by the window's reflection): with the cabin at 0.5,
  Sebring RSX rear window 10.4 -> 6.6, the band 7.9 -> 7.4, roof 51.0 -> 35.2, the car 18.5 -> 17.6; CrownJewel CR-X rear
  window 11.6 -> 11.0, whole frame 18.9 / 18.5 / 17.8 -> 18.7 / 18.1 / 17.1. Both are needed: 1.0 with the cabin at 1.0
  gives the RSX window 15.1 (the seats show through). So the player's glass is no longer dimmed (the 0.1 of 2026-11-24
  was fitted before the exposure pass).
- **The player's windows reflect the live cube** (23:20, the final step): a scale on the static cube fitted each track
  differently (RoadAtlanta wanted 2, Sebring 1: the static cubes differ), the game reflects its per-frame cube. With the
  live cube at 1 (`FM3_LIVE_GLASS=0` = static, `FM3_LIVE_GLASS_SCALE`): rear windows Sebring RSX 5.4 (14 / 21 / 27,
  game 12 / 20 / 26), RoadAtlanta RSX 20.6 -> 3.5 (29 / 31 / 28, game 30 / 29 / 25), CrownJewel CR-X 11.0 -> 5.7; the
  RSX's roof (sunroof) 17.6 (was 51 at the start of the evening). **Measuring note:** whole-frame diffs between
  viewer variants carry the viewer's auto-exposure state (it adapts over time; a Sebring pair differed by 1.2 over half
  of all pixels where only the player's glass changed): judge such changes by regions.
- **The dark band round the RSX's rear window** (found by hiding library parts, `FM3_HIDE_PARTS=<name part>,...`): the
  black trim inside the window framed a cabin that was too bright (grey seats; the game's window reads as one dark
  tint). Library cabins now at `CABIN_K` 0.5 (was 1.0; `FM3_CABIN_K`): Sebring RSX rear window 14 -> 10.5, CrownJewel
  CR-X 10.8 -> 11.5, Mazda 19.9 -> 19.7.
- The live cube's faces (`FM3_DUMP_LIVE_CUBE=1`, Sebring) hold the horizon's clouds and buildings and a clear sky
  with the sun overhead; from the chase camera the roof reflects the horizon (grazing angle), so the roof's dimmer
  reflection is not missing sky. Their down face (the road seen from above in sun) is near white (248).
- The roof: with the player's glass at full reflection the RSX's roof paint is 98-102 against the game's 112 (rows
  410-416 of the Sebring chase view); the "half as bright" roof above was mostly the dimmed sunroof glass.
- **Reflection sharpness** (the user, 23:15: ours reflects the clouds, too blurry to recognise): the roof paint's detail
  (mean neighbour difference, Sebring chase view, game 13.7) with the live cube at 128 / 256 / 512 px a face (4x MSAA
  for the larger two, `FM3_LIVE_CUBE=<size>,6,4`): 6.1 / 7.2 / 8.5, the region's difference from the game 13.2 / 13.8 /
  14.0. Size helps partly; even at twice the game's 256 the contrast is half the game's, so the cube's content is
  softer than the game's. Next: the sky dome's texture as the cube's small views render it (its resolution / mip /
  compression: `_bind_textures` compresses to BC1), whether the game's paint also sharpens with the static cube, and
  what a 256 px cube costs in frame rate before making it the default (default stays 128).
  Checked after midnight's start: the sky textures are 2048 px (not the cause); the game's roof has both more spread
  (p5 / p95 69 / 128 against our 72 / 111) and more fine detail per unit of spread (0.039 against 0.021). Floating-point
  cube faces (`FM3_LIVE_CUBE_HDR=1`, values above 1 kept, re-encoded to sRGB in `fm3_livecube.gdshaderinc` so the scale
  stays): p95 111 -> 114 only, so clipping is not it (read without the re-encoding the linear values doubled the
  contrast: spread 77-86, median 100 -> 77). With 256 / 512 px faces the detail is 1.1 / 1.4 (game 2.2). Left: why our
  reflected clouds have less contrast than the game's (the cube's content: fog in the cube views, the sky dome's own
  look in a 90-degree view, the paint's diffuse base), and a frame-rate measurement of the 256 px cube (the test runs
  share the GPU with the game: 1-2 fps logged, meaningless). (Normals are not it: the car library uses the files'
  own 11:11:10 normals, `smooth_normals` only where a mesh has none.)
- **Black glass without reflection again** (2026-11-26, 00:05): the top rows of the RSX's rear window, brighter than the
  game's, were the `black_glass` border under its reflection pass; that region 41.0 -> 11.3 with the pass off
  (`FM3_BLACK_GLASS=<scale>` turns it back on), the car 17.7 -> 16.7. Plain, it is still lighter than the game's
  (32 / 35 / 40 against 18 / 27 / 39). CrownJewel: CR-X rear window 5.9 -> 4.7, the CR-X 14.6 -> 12.7, Eclipse 18.2 ->
  17.9, Mazda 19.8 -> 19.7.
- Lens pinkness, tried and rejected: doubling the reflectors, less texture tint, a lighter lens filter all bring the
  tails' mean closer (up to 104 / 87 / 82, game 114 / 64 / 63) but per pixel worse (36.2 / 29.2 -> 44-57): they add grey
  as fast as red, and our bulbs keep dark centres where the game's lamps are evenly pink.
- **White specks along the Eclipse's tail lamps** (CrownJewel grid, AI car; the right lamp's region 34.5 against the
  game): not a lamp material. They stay with the lenses, bulbs, reverse lamps or the reflection passes hidden
  (`FM3_HIDE_PARTS`, `FM3_REFLECTOR=0`), and sit where the white kerb is behind the car: most likely gaps in the
  library model round the lamp housings (seams / missing parts) showing the background. The grid's car is
  `MIT_EclipseGTS_03`. Rendered alone (world_view.gd now makes a camera for `--look-from` / `--look-at` when a glTF
  has none, e.g. `--gltf out\cars\mit_eclipsegts_03.gltf --lit --look-from 0,1,5 --look-at 0,0.6,0`;
  `FM3_HIDE_PARTS` now also works on such a plain load; `FM3_BG_COLOR=r,g,b` for the unlit background): the specks
  are short white dashes left of the right lamp's big lens, present with each of that lamp's five parts hidden in
  turn (lenses, reflectors, bulb): not holes. **Found and fixed (00:25):** they are the lamp's clear outer cover
  (`glass_1`, material `<glass>`: SpecularAmount 3.5 at power 50): its sun highlight on few, curved polygons drew
  saturated white dashes. The glass highlight weight is now 0 (`fm3_carglass.gdshader` spec_weight, was 0.25;
  `FM3_GLASS_SPEC=<w>`): the Eclipse's right lamp 34.3 -> 24.7, the Eclipse 17.9 -> 17.3, the CR-X 12.6 -> 13.0
  (0.1 kept the dashes).
- The CrownJewel grid's largest differences otherwise: the game's lap counter overlay (top right, not ours to fix) and
  the white kerb stripes on the right, brighter and crisper in ours (141-163 against 115-136): the road-lines item.
- **Done 2026-11-26 morning: the stripes are painted asphalt, now with the game's formula.** The CrownJewel kerb
  stripes are not road lines but `shldr_4clr_blnd_mask` meshes (Asphalt_White / _Orange / ...), drawn by a fitted
  flat-colour recipe (family 'paint'). Disassembled (`SHLDR_4CLR_BLND_MASK_2.fxobj`): g' = grain + mask x P[2] (the
  paint is added to the asphalt grain), colour = g' x P[0] + v x (g' + P[4] - g' x P[0]) x the lightmap; grain at world
  xz x P[1].x, mask (red / green by P[1].y) at UV 16 x P[3].xy, blend value v at the lightmap UV x P[5].xy. New family
  'paint4' (`fm3_families.py`, `fm3_blend.gdshaderinc` mode 19; only CrownJewel's files use this shader). The scene
  rebuilt (`build_track.ps1 -Track CrownJewel -Ribbon 04`: Ribbon_04 is the grid race's layout, the default
  Ribbon_00 lacks most of its props: the grandstand, garages; whole frame 23.2 that way). Live CrownJewel grid against
  last night's final: right stripes 28.4 -> 10.5 (ours 94 / 92 / 84, game 93 / 93 / 89), left stripes 24.1 -> 20.0,
  road 9.8 -> 9.0, the CR-X 12.9 -> 11.4, the grandstand 16.1 -> 16.7; **whole frame 18.4 / 17.8 / 16.9 -> 16.8 /
  16.7 / 16.3** (the rebuild also carries every exporter change since 2026-11-24).
- **Tail lights, the user's first point (2026-11-26, 12:05):** close up, the game's RSX lamps read evenly pink-red with
  the bulb domes as pink chrome; ours had dark maroon domes with white chrome rims. Two causes: (1) the lamp
  reflections were an additive pass drawn in Godot's transparent stage, after the lenses had read the screen behind
  them, so they landed on top of the red lens untinted (also why last night's brighter reflectors looked grey, not
  pink); (2) the bulbs' reflection was tinted by their own dark dimpled texture. Now the reflectors and bulbs are one
  opaque material each (`fm3_lamp.gdshader`: the lit texture + the cube reflection as emission, brake / reverse glow
  as emission too; `FM3_LAMP_PASS=1` = before), bulbs untinted at 15 x <tail_light>'s CubeScale 0.2, and the lens
  filter refitted to 0.45. Sebring RSX tails (one boot): 33.6 / 30.6 -> **25.2 / 23.2** (74 / 45 / 40 -> 83 / 53 / 48,
  game 114 / 64 / 62), rear 18.5 -> 16.7; CrownJewel CR-X rear 14.8 -> 13.0, its red panel 10.4 -> 9.4, Eclipse
  18.7 -> 19.5. Still darker than the game's overall; the amber corners read yellow where the game's are orange. A
  separate light for amber lenses (`FM3_AMBER_LIGHT`, test switch; default = the 0.35 of all lenses): 0.7 / 1.0 gave
  mixed small changes (corner 33.7 -> 32.6 / 36.5, whole frame 22.2 -> 22.5 / 23.5): left as is.
  Brighter reflectors (`FM3_REFLECTOR` 1.5 / 2) with the opaque lamps: tails 23.5 / 24.3 -> 23.3 / 24.8 / 25.3 / 27.3,
  flat: the lamps' remaining darkness (85 / 55 / 49 against 114 / 65 / 63) is not the reflectors' strength. Next to
  try: the bulb texture itself (dark dimpled red: what the game's tail_light shader does with it) and the lens's own
  reflection (lerp(GlassColor, env, f)) at the game's cube brightness.
- **Per-car lamp values** (2026-11-26, the user asked whether taillights differ per car: they do). 393 cars carry
  their own `shadersettings.xml` over `Media\Cars\ShaderSettings\Normal.xml`: `tail_light(_lod0)` BrakeColor in 124
  cars (75 values, 2.6 .. 15 against the default 3.6 / lod0 7), `detail_glass_red` in 148 (43 colours, 27 opacities;
  most CubeScale 1.0 / Fresnel max 0.4 against 1.5 / 1.0), reverse colours in ~120, `textured_reflector` in 14 (9 with
  the RSX's set: CubeMultiplier 2.2, Fresnel min 2.11 > max 0.86, power 7). The lenses already took them
  (`_carmaterials.json`); the lamp parts and glow did not. Now `<car>_lamps.json` (`tools/fm3_car_lamps.py` for built
  libraries, `fm3_car_library.py` for new ones; `fm3_track_export.lamp_params`): reflection scale over the default's,
  the car's Fresnel (the game's min(max(.., min), max)), glow colour over the default's (capped at 4x,
  `FM3_LAMP_GLOW_MAX`). Viewer: `_lamp_settings` / `_lamp_glow`; `FM3_LAMP_DEFAULTS=1` = before. On the RSX the own
  textured-reflector values at x1 made the tails 137 / 102 / 101 (game 114 / 64 / 62): gain `TEXTURED_REFL` 0.3 fitted
  (tails 24.8 / 25.1 against the defaults' 26.0 / 24.5, whole frame 22.5 both): neutral there. The brake glow
  differences (the bulk of the per-car values) show only on braking cars: not yet measured against the game.
- **Black plastic and the tail lamps from the game's shaders** (2026-11-26 afternoon, the user: "fix the taillights
  ..., make the black plastic actually black"). Flat near-black library materials (black, plastic2, frames, rubber,
  undercarriage, tyres) had Godot's default specular 0.5, which lit them grey from the sky: now 0 (`PLASTIC_SPEC`;
  `FM3_PLASTIC_SPEC` / `_K` / `_ROUGH` test switches). Capture-free CrownJewel grid, those pixels 21 / 21 / 21 ->
  14 / 13 / 13 (game 15 / 15 / 15), |diff| 13.2 -> 9.4 and 13.0 -> 8.7 (two boots). NB the default `ladera.gltf` grid
  scene has capture-built cars: library-car tests need `-Gltf out\world\crownjewel.gltf`.
  Lamp shaders read from `shaders_v11.fxobj` (`fm3_trackshader.containers`): tail_light = container 92 (BrakeColor
  c218, brakeReverseAmount c198), reverse = 93, lit glass = 96, detail glass / windows = 60. The tail lamp is
  lerp(lit texture, env x CubeScale, F), F = clamp(FresnelScale x (1 - n.v)^FresnelPower, FresnelMin, FresnelMax) x
  reflectionScaler, the brake colour added x brakeReverseAmount. **No shader has a CubeMultiplier**: dropped from
  `lamp_params`; `TEXTURED_REFL` refitted to 0.6 (RSX tails 24.2 / 24.0 -> 23.2-23.9 / 24.0-24.9). Tried and not kept:
  a self-lit bulb floor (`FM3_LAMP_SELF`, bulbs only: barely visible through the lens; on all lamp parts the grid's
  lamps went 15.4 -> 21.5), a stronger lens filter (0.6 / 0.75 / 0.9: green goes, red does not come: 82 / 32 / 27),
  lens_light 0.6 (RSX tails 22.7 / 23.5 but the grid's lamps 14.5 -> 24.7), amber light 0.15 (amber pixels 22.3 ->
  21.3, whole frame +0.2). The RSX's tails stay less red / bright than the game's (88 / 58 / 53 vs 114 / 64 / 62)
  while the grid cars' lamps are slightly brighter than the game's (73 / 42 / 32 vs 66 / 34 / 32): the difference is
  per car / per light, not one global term. Next: decode container 92's lighting term (r0.x: track lightmap + 0.4?)
  exactly and render the bulbs with it, and the lens (container 60) the same way.
- **Tail lamps and lenses with the game's own formulas** (2026-11-26, decoded from ReGPU's HLSL dumps:
  `REGPU_DUMP_HLSL=1` writes `FM3-ReGPU recomp\out\run\out\hlsl\ps_<hash>.hlsl`; ReGPU packs the constants, `pc[i]` =
  the i-th used register in order, checked against the literals c254 (0.6, 1.5) / c255 (0, 1, 0.4, 0.5)). Which
  shader each car material draws with, from the grid capture (`work\capmap\fetches.json` index lists matched to the
  carbin subsections): tail_light 7f4b46775654ee5b, textured_reflector 0c88abdd1c499126, reverse_light
  a56fcadd0575d570, detail_glass_* **f7841c0a8245eabf** (not the windows' b117fbafcc1fa980), black_glass
  07b55736eed1d328, head_light 588abe1ef63580d2. Lamp parts: lerp(tex x (0.4 + 0.6 x saturate(hl^2)) x lerp(1, lm,
  alpha) + spec, env x CubeScale x (1 - damp (1 - lm)), F) + tex x BrakeColor x brake, hl = N.L / 2 + 1/2, lm = the
  track lightmap under the car (t10), opaque. Lenses: colour = **the lights texture x GlassColor** lit the same way,
  opacity clamp(spec + F + max(texture alpha, GlassColor.a), 0, GlassMaxOpacity), lerp(colour, env, F),
  alpha-blended. Built: `fm3_lamp_game.gdshader` (lamp parts incl. reverse lamps; Godot's sun shadow stands in for
  lm: `lm_shade` 0.3 in shade, `FM3_LAMP_SHADE`), `fm3_carglass.gdshader` game_lens (the car's `lights_lod0.png` on
  the lens UVs), `lamp_params` now exports each lamp's CubeScale / Fresnel / highlight; `FM3_GAME_LAMP=0` = the
  fitted lamps before. Sebring RSX (one boot, the game at 4x MSAA): tails 22.2 / 23.4 -> **19.4 / 18.3**, amber corner
  22.8 -> 16.3, rear 15.9 -> 15.0, colour 105 / 65 / 62 (game 109 / 60 / 59; fitted 86 / 56 / 51). CrownJewel grid
  lamps: without the shadow term 14.6 -> 22.9 (the grid is in the grandstand's shade), with it 15.3 -> 15.9 (shade
  0.3; 0.7 16.4). The fitted gains (BULB_REFL, TEXTURED_REFL, LENS_LIGHT, LENS_FILTER) only serve FM3_GAME_LAMP=0.
- **The game at the viewer's MSAA for comparisons:** the user's settings run FSR 3 (temporal AA; FM3 forces MSAA 1x with
  it); the viewer draws 4x MSAA. Live comparisons now boot FM3 with `FM3_UPSCALER=off FM3_MSAA=4 FM3_AA=off`
  (the log: "ReGPU at 1280x720, msaa 4"). The user's own settings.ini is unchanged.
- **White specks along the cars' panel edges** (the user, 2026-11-26): tested on the capture-free CrownJewel grid
  (game at 4x MSAA). Not back faces (`FM3_CULL_BACK=1`: 1182 -> 1145 specks), not MSAA (`FM3_VIEW_MSAA=1`: more,
  1718), not the windows / lenses / chrome (hidden: 100 / 7 / 50 of ~1180 gone), not broken normals (none in the
  library). They are the paint's own highlight and reflection (off: 58% / 34% gone) on curved edges: added in gamma
  and converted to linear, a gamma 3 highlight became 11 and MSAA averaged it into a white pixel. Now capped at 1
  (gamma) before going linear (`hdr_clamp`, paint and game lamps; `FM3_HDR_CLAMP`): whole frame 15.42 -> 15.07, the
  headrest glints through rear windows gone. (The game has edge highlights too: 1650 by the same count, ours ~1150;
  ours remain more pointed on a few edges.)
- **The PT Cruiser's grey tail lamps** (the user, 2026-11-26): its lamps are a red lens (detail_glass_red) over a
  chrome textured reflector (its own override: Fresnel min 2.41 > max 1, a pure mirror) under a clear outer cover
  (material `glass`, 561 triangles in front of the lens). Lenses drawn magenta (`FM3_LENS_DEBUG=1`) showed only their
  rims: our glass shaders blend by reading the screen as it was before Godot's transparent pass (gamma_blend), so of
  two overlapping transparent parts the later one replaces the earlier; the cover drew after the lens. Lamp covers
  (`_lamp_cover`: `<glass>` on the body model) now blend normally and draw last (`render_priority` 1;
  `FM3_COVER_BLEND=0` = before): the PT's lamps red / pink as in the game, those pixels 28.7 -> 23.6. The capture's
  blend state (`RB_BLENDCONTROL` 0x07060706 = source alpha / one minus source alpha for lenses, lamps and windows;
  depth test greater-or-equal, lenses mostly without depth writes) confirmed plain alpha blending. A lens lift
  (`FM3_LENS_LIFT`, metres along the normal) had no effect: 0.
- The user's own `out\user\settings.ini` now runs FM3 at 4x MSAA with no upscaler (the user: "fsr3 barely works in
  regpu anyway"), the same as the viewer.
- **Car shadows as the game draws them** (2026-11-26, RoadAtlanta's long dark car shadows; open item 1). Decoded:
  `Media\Shaders\Cars\DropShadow.fxobj` (a quad per body / wheel with a soft blob, c_shadowColor, GlobalCarAttribs.xml
  DropShadowSettings; in the capture PS d44a5b5aed142674, 64 x 64 blob, alpha 160 / 255 over the middle) and, from the
  recomp's notes (hooks/car_shadows.cpp), the real car shadows: a 256 x 256 depth map from the sun per car, read by the
  car materials (self-shadowing) and by the track pixel shaders (fd6b3d2a..., 9e50ba14...: two lookups into the
  512 x 512 car shadow image, then min(lit, base x ShadowColor), as our shadow_tint), projected near each car only.
  Tried: drop shadow quads instead of the cars' sun shadows (`FM3_DROP_SHADOW=1`, `fm3_dropshadow.gdshader`): the cars
  lost their self-shadowing (the RSX's rear 72 -> 152, game 89), whole frame 21.1 -> 23.9: opt-in only. Kept: the
  track's received sun shadow counts only within `CAR_SHADOW_R` 2 m (full) .. 3 m (none) of a car
  (`fm3_carshadow.gdshaderinc`, global `fm3_cars` texture of the cars' x / z and `fm3_car_k`, filled each live frame;
  the static shadows are baked in the lightmaps; `FM3_CAR_SHADOW_R=<full>,<zero>`, 0 = before). RoadAtlanta: the changed
  pixels 38.9 -> 28.9, the lower half 17.76 -> 17.42, whole 19.98 -> 19.82 (3 / 4.5 m and 5 / 7 m hardly cut).
- **The exposure adapts by time, and on the game's view** (2026-11-26 evening, Sebring's darkness). Measured first:
  the game's W at Sebring is 0.953 (`tools/research/wtrack.ps1`: the final pass edited live to output its interpolant
  o[1].y = 0.1 / W, display gamma off; a 0.5 constant reads 128), so its adapted L = 0.566, which equals its own scene's
  plain mean luminance (0.58 from the game's shot with the display table and curve undone): the luminance chain's
  decode holds. The viewer adapted 2% a *viewer* frame (it runs at 2 fps beside the game in the tests, so it hardly
  moved before the picture) and started from its start-up camera (an aerial view 262 m up). Now 1 - 0.98^(seconds x 60)
  like the game's 2% a game frame, restarted on the first live packet; world_view.gd logs `exposure: L .. k .. W ..`
  every fifth update. `FM3_EXPO_OLD=1` = before. Viewer W at Sebring 0.946 / 0.966 (two boots; game 0.953).
  CrownJewel grid **15.1 / 15.2 / 15.1 -> 14.8 / 14.7 / 14.3** (same boot). Sebring varies by boot (the frozen moment):
  17.1 on the last one.
  Ruled out on the way: **bloom** (the final pass's t4, read alone: < 1% of the top third at Sebring; it only adds where
  the scene is above ~1.5, 0.2% of pixels; bloomCutoff 2.01 / bloomScale 2), and **the sky's scale** (the game's sky
  shader `SKY_DIFF_1` is the texture alone; `FM3_SKY_K` 1.1 / 1.2 on top of skyScale: 17.1 -> 17.2 / 21.5, the top third
  13.3 -> 12.3 / 21.7: ours is right). Ours still has darks lighter (0-31: 20 vs 15) and highlights darker (192-255:
  ~20 under) than the game's in tone bins (scratch `tonebins.py`): the content's contrast, not the exposure.
  In-car: with the exposure adapting, the fitted in-car x1.5 (`IN_CAR_EXPOSURE`, now `FM3_IN_CAR_EXPOSURE` for tests)
  is taken back by the adaptation (as the game's own adaptation brightens its cockpit view): CrownJewel in-car x1.5
  and x1.0 give the same picture statistics (15.68 both; x1.2 14.53, its picture taken mid-adaptation). So pictures
  taken soon after a camera change carry the adaptation's state: compare after it settles (~3 s of game time).
  **Correction (2026-11-27 00:50):** that test was not in-car. The scratch grid script's camera switch never left the
  chase view (the viewer only saw camera vtable 82001C74, not the in-car 8200206C / 82034FC4), so the x1.5 never
  applied and nothing was "taken back". Use `tools/live/live_compare.ps1 -Cameras 2` for in-car pictures.
  **In-car exposure from the game's cockpit limits (2026-11-27 00:55):** the in-car view had drifted to 40.8 / 35.6 /
  30.9 (CrownJewel, live_compare cam3; 17-18 on Nov 24): the dark cabin pulls the adapted L below TrackLumLimits' 60,
  so the curve sat at its brightest (W 0.57) and the outside burned white. The game adapts in-car within
  TrackSettings `TrackCockpitLumLimits` (CrownJewel 30-117, every track lower than its outside minimum):
  `fm3_track_export.track_tone` writes Tone 'cockpit_lum' (all scenes patched), `_expo_k` uses it in-car
  (`FM3_NO_COCKPIT_LUM=1` = before). In-car **29.3 / 27.4 / 22.8** (W 0.739), grid and chase views unchanged. Still
  in-car: our cabin is near black where the game's dash is grey (the cockpit shader's light), the hands.
  Then the fitted in-car x1.5 (`IN_CAR_EXPOSURE`, from before the exposure pass) set to 1.0: in-car **23.2 / 22.5 /
  19.5** (grid and chase unchanged).
  Then a regression of the same night found and fixed: the SH-lit car parts (`fm3_carsolid`) had taken the library
  cockpit's parts too, before `_register_part` gives them fm3_cockpit.gdshader; their light comes with the directional
  sun only, which the cockpit's render layer leaves out, so the cabin went black. Cockpit parts are excluded now:
  in-car 23.2 / 22.5 / 19.5 -> **19.3 / 18.8 / 17.0** (grid 14.3 / 13.9 / 13.4). Over the last hour: in-car 40.8 / 35.6 /
  30.9 -> 19.3 / 18.8 / 17.0.
- **The car paint's light, decoded** (2026-11-26 evening; the user: "are we using the game's GI?"). The paint (ps
  e41e183a423e6f1b, vs a102319a5aef757b; register names from shaders_v11.fxobj container 47 and the car vertex
  shaders' tables) computes, in gamma space:
  `out = (paint x sunSH + highlights) x shadow + paint x o[5].xyz + reflection`
  - o[5].xyz, the **ambient**: transfer SH . shHemisphericalLightR/G/B (c38-40), the SH of TrackSettings SHTop /
    SHBottom per channel with the same hemisphere projection as shCubeMapDampnerLight (c37): per vertex
    `SHTop x a + SHBottom x b`, (a, b) = `fm3_carbin.env_sh`, already in the library as UV2. Unshadowed.
  - o[2].w, the **sun**: transfer SH . shDirectionalLightI (c36); the pixel shader takes SHDir (c179) x o2w x
    smoothstep((o2w x SHDir.r - (SHTransition - Width)) / 2 Width) (body: 0.5 / 0.3; n.l only with
    UseDiffuseInsteadOfSH). Measured, not derived: the game's o[2].w output by a live ps edit on the grid
    (`tools/research/gridterms.ps1` modes 13 / 14, with the 0.1 / 0.25 / 0.5 patches to undo the display) against
    our n.l per pixel: **o2w = 0.375 + 0.541 n.l** (rms 0.09; the SH-projected cosine; self-occlusion adds little).
  - shadow = min(track-lightmap smoothstep (trackLightMapParams), max(shadow map, MinShadowValue 0.25)), on the
    sun and the highlights.
  - Our decoded ambient against the game's o[5] on the grid: x1.05 median (0.96-1.11 per pixel).
  In `fm3_carpaint.gdshader` (game_amb, game_sun; world_view.gd sets SHTop / SHBottom / SHDir from the track's
  `_track.json`; `FM3_GAME_AMB=0` = the old fitted ambient and sun, `FM3_GAME_SUN=0` = the fitted sun only,
  `FM3_GAME_AMB_K` a test scale; `FM3_PAINT_DEBUG` 13 ambient, 14 n.l, 15 signed n.l, 16 the (a, b) pair). CrownJewel
  grid, paint pixels (the game's own paint mask from the probe): **14.98 -> 12.31**, the player's CR-X 15.6 -> 11.7,
  the AI cars 13.3 -> 14.0, whole frame 14.63 -> 14.39. The ambient alone (with the old fitted sun) was 16.5: the old
  sun x1.35 n.l^2 had been fitted together with a lower ambient.
  Sebring (the RSX is black): the pixels it changes 35.97 -> 34.05, the RSX 12.91 -> 12.92.
  **The other car parts** (trim, plastic, grilles, badges: opaque, not metal, with the baked pair) lit the same way
  (`fm3_carsolid.gdshader`; every car vertex shader carries the same SH constants), instead of Godot's flat grey
  ambient and sun: Sebring, the pixels it changes 50.8 -> 29.7 (they were grey, 77 against the game's 29), the RSX
  12.91 -> 12.70; CrownJewel grid 17.41 -> 12.91 (dark trim 25 -> 14, game 15), whole frame 14.21 -> 14.18.
  `FM3_CAR_SH=0`: off. No highlight on them yet (spec_amount 0; the game's per-material SpecularAmount).
  **Measuring:** the live tests now give the same picture run to run (two identical CrownJewel runs: 0.00, Sebring 0.12;
  before, 11 levels apart): the viewer's exposure updated every 10 frames, 5-10 s at the tests' 1-2 fps, so a picture
  could carry the start-up view's exposure. It now updates every 0.2 s on a slow viewer, the test picture waits for
  three updates on the game's view, and `FM3_EXPO_INSTANT=1` (set by live_compare / live_track) adapts at once, the
  frozen game's settled state. Whole-frame numbers from before this evening carry up to ~1-5 levels of that noise.
  The readback lags the curve by a frame or two, so L converges over several updates (RoadAtlanta 0.41 -> 0.395 ->
  .. 0.362): the picture now waits until L changes by < 0.002 an update. RoadAtlanta (identical runs 0.01 apart),
  old car light -> decoded paint + parts: whole frame 17.1 / 17.7 / 18.9 -> 17.0 / 17.5 / 18.7, the pixels it changes
  23.96 -> 20.30, the RSX 13.82 -> 13.66 (the same scene measured 20.2-22 before the exposure waited: that was noise).
  **The adaptation speed per track:** TrackSettings `ToneMapeDelay` is the luminance pass's blend a frame (MapleValley
  0.02 = the 2% measured in its capture): CrownJewel 0.05, RoadAtlanta 0.023, LeMans 0.15, NewYork 0.1, SunsetInfield /
  Tsukuba 1 (no adaptation lag), RoadAmerica 0.01. `fm3_track_export.track_tone` writes it as Tone 'delay' (all 17
  scenes patched); the viewer adapts by it (frozen-frame tests unaffected: they adapt at once).
  **RoadAtlanta's exposure (solved 2026-11-27, see below: the probe's formula, then our measurement's clipping):** the game's W there is 1.024 (`wtrack.ps1 -Index 16`), ours settles at 0.80 on the
  same moment: the game's scene before the exposure is ~1.15-1.25x ours (per pixel, uniform over sky / road / walls,
  more in the darks: an offset of ~0.07 fits as well as a scale), while Sebring's matched (0.953 vs 0.946-0.966). A
  x1.25 scene scale made RoadAtlanta worse (23.8 -> 24.8, another boot): not a plain scale. Our darks there are ~14
  levels too light (the black RSX's paint reflects bluer and brighter than the game's: rear window 54 / 55 / 51 vs
  46 / 42 / 37; the HUD's dark gauges). Next: which of RoadAtlanta's values differs (skyGain 0.15, DarkColor -0.1,
  LightCurveBlackPoint 10 / Boost -1 are its unusual ones).
  **Then measured directly (same boot):** the game's scene texture (the final pass's t0, output x0.25 by a live ps
  edit, display gamma off) against our picture without the exposure pass (`FM3_NO_EXPOSURE=1`), per block and per
  brightness band: **RoadAtlanta 0.341 vs ours 0.346, Sebring 0.539 vs 0.550 (ratios 0.98-1.01 almost everywhere)**:
  our scene is the game's. The gap is the game's L: Sebring's W 0.923 gives L = 0.539 = its scene mean; RoadAtlanta's
  W 0.764 gives L 0.433 = 1.27x its scene mean, and another boot read W 1.024 at what should be the same moment. So
  the frozen game's L depends on what came before the freeze (likely: FM3_FREEZE_TIME stops the luminance pass's
  time-scaled adaptation, leaving L where the intro camera left it). The earlier "scene x1.25" inversion was this.
  Read twice 30 s apart while frozen, RoadAtlanta's W stays 0.8127 (L 0.464, its scene mean 0.38-0.42): settled or
  stuck, not adapting. Over three RoadAtlanta boots L ~ 0.89 x mean + 0.13; Sebring (two boots) and CrownJewel (game
  0.398, ours 0.409) have no such offset, nor Motegi: scene 0.437 vs ours 0.442 (ratios 0.97-1.00), game W 0.906 vs
  ours 0.900 (both at the light curve's end), frame 14.1. A screen-region crop does not explain it (top-weighted
  fits RoadAtlanta, overshoots Sebring by 9%). **Open:** what lifts RoadAtlanta's L (its unusual values: skyGain
  0.15 (CrownJewel has 0.1 without an offset), DarkColor -0.1, LightCurveBlackPoint 10 / Boost -1, TrackLumLimits
  80-160); next, the luminance pass's input buffer itself (which pass writes the 32x32 it averages, from a capture).
  Our scene matches the game's on three tracks, so the remaining picture differences there are exposure, HUD and
  content, not the lighting.
  **The luminance chain, from a RoadAtlanta capture (2026-11-27, `tools/research/expo.ps1 -Index 16`):** the scene
  (1280 x 720 at the final pass's t0 address) -> `c244a21ac3a9be63` (four bilinear taps at +-1 texel, summed, x pc0.x
  = 1) -> 320 x 192 -> `c244` again -> 64 x 32 (four taps per 5 x 6 block: a regular subsample) -> `98c51b1e094205eb`
  (a loop of taps summed, x 1) -> 32 x 32 -> the luminance pass `4a17014edfabf5f0` (pc0 = 0.2126 / 0.7152 / 0.0722, the
  Rec. 709 weights; pc1.x = **0.023 = RoadAtlanta's ToneMapeDelay**, confirming the adaptation rate), then the bloom's
  bright pass (vc0 = LumMin / 255 0.3137, 255 / (LumMax - LumMin) 3.1875; vc1 = the dark curve's white 145 / 255). Every
  pass scales by 1: the sums are brought back by the resolves' exponent bias (RB_COLOR_INFO). So the game's L is a
  plain average of the scene, as decoded; RoadAtlanta's L ~0.13 above our measured scene mean stays open. Next: the
  intermediate formats (2_10_10_10: a clamp of bright areas?), the subsample's coverage, and reading the 32 x 32 result
  directly (a ps edit of the bright pass, which reads it as vs:t17).
  **Solved the same morning.** The shaders, read whole: `98c5` takes 16 bilinear taps per row of the 64 x 32 (u = k /
  16 + 1 / 32: columns 1-2 of every 4) and averages them (its constant is pc255 = 0.0625 / 0 / 0.03125 / 1, not pc0);
  the luminance pass takes 16 taps down the middle column (v = k / 16 + 1 / 32: every row pair), averages, weights by
  Rec. 709 and blends into last frame's L (t1, k_32_FLOAT at 18C25000) by ToneMapeDelay. The chain simulated on the
  game's own scene (`rap-p6`): 0.3995 against a plain mean of 0.410. A live test (scratchpad `lumstuck.ps1`): the
  luminance pass edited to output its fresh mean (`ps 4a17014edfabf5f0 float4((r0.x + r0.y).xxx, 1)`): the game's L
  0.4009 = the simulation. **Two errors were ours:** (1) the W probe: the final pass's vertex shader makes
  `o[1].y = (0.1 - B) / (W - B)`, not 0.1 / W; B (the curve's black point) is 0 on every track but RoadAtlanta's light
  curve (10 / 255), so only RoadAtlanta's L read ~0.03-0.06 high (the "offset"). `tools/research/wsolve.py` solves a
  probe shot for k / W / L with the track's curves. (2) The viewer measured L on its picture *after* the exposure
  pass, where everything above the white point is clipped: RoadAtlanta's game scene clipped at W averages 0.3666, the
  viewer read 0.367, the game 0.400. Now (world_view.gd `_expo_vp`) a 128 x 72 SubViewport of the same world through a
  copy of the camera, drawn once per measurement (every 10 frames), gives the scene before the pass, as the game's
  chain reads it (`FM3_EXPO_POST=1`: the old way). RoadAtlanta's grid, one boot: game L 0.371 (W 0.661), ours 0.377
  (W 0.670), before 0.334 (W 0.600); whole frame 22.9 -> 17.9. Sebring (little between W 0.97 and 1): both ways L
  0.580, frame 18.7 = 18.7 (game L 0.551, frozen before it settled); Motegi: both at the light curve's end, W 0.900 =
  the game's, 14.3 = 14.3; CrownJewel (two boots) grid 14.0 / chase 14.5 / in-car 17.6 against 14.3 / 14.6 / 18.2.
  The viewer is faster with it (CrownJewel offline, 900 frames x 2: 80.5 vs 77.0 fps): the old way read the whole
  1280 x 720 picture back every 10 frames. Also: while the world is frozen (FM3_FREEZE_TIME) the
  game's L stops adapting (0.390 for 10 s with the fresh mean at 0.401), so a frozen game keeps the L of the moment it
  froze: the live tests' FM3_EXPO_INSTANT is right only once the view has been still a few seconds (RoadAtlanta's
  freeze at 8 s lands on a close-up right after a cut, the game's L still at the top of its curve: use 11 s).
  The same-boot probe: scratch `lensiter.ps1 -Probe` (t0 / W / 0.5 shots after the variants); `wtrack.ps1` numbers
  repeated modes (w1, w1-1).
- **The AI cars' static-cube reflection is looked up wrongly** (2026-11-26 late; the user: the game's Eclipse shows
  a faint white line and blue higher up that ours lacks). Not screen-space: AI cars reflect the track's static car
  cube (their bool word 0x14 sets useStaticCubeMap, b130; the player's 0x13 reads the per-frame cube). The paint's
  reflection term alone (`gridterms.ps1` mode 3 against `FM3_PAINT_DEBUG=3`) shows it: the game's Eclipse flank
  reflects a bright white / yellow band (the grid stripes and kerb), ours is dark there, and ours puts an orange kerb
  on the rear bumper where the game's is grey. Lookup variants on the term (Eclipse paint |d|, all cars): as is 30.2 /
  18.8; x unflipped (`FM3_ENV_FLIP=1,1,1`) 28.7 / 18.0; yaw 90 / -90 (`FM3_ENV_YAW`) worse; yaw 180 (= a z mirror
  instead of x) 26.5 / 17.7; sharper (`FM3_ENV_LOD=1`) 31.2. Full render with the z mirror: Eclipse paint 13.10 ->
  12.87 but the AI cars 14.18 -> 14.48, whole frame unchanged, the flank too orange: no single flip is right.
  The game's cube drawn as tiles over the paint (`gridterms.ps1` mode 20: TFetch(7) at cube coordinates (1 + s,
  1 + t, face) in 64 px tiles) matched against our six faces under 8 orientations: mostly weak (0.2-0.3; few
  pixels per tile), but **the game's face 3 (-Y) correlates 0.66 with our face 2 (+Y, the sky)**: the face order or
  the face images are not what the lookup assumes. **Next:** probe the game's t7 with explicit directions (the
  shader's own CubeOp path, e.g. the six axes and diagonals, one constant colour per shot or one per screen region)
  and sample ours with the same game direction; that fixes face order, flips and env_flip together, and applies to
  every shader reading the static cube (carglass, glass, lamp, lamp_game, lensrefl all use env_flip (-1, 1, 1)).
  **Resolved the same night: it is not the static cube.** The game's t7 drawn as panoramas through the shader's own
  CubeOp lookup (`gridterms.ps1` mode 22: 128 x 64 px tiles of directions, x0.3; the picture repeats at exactly 128 /
  64 px, so the probe works) shows a dark near-field view (road lines, a car body, low sky), not CrownJewel's static
  car cube (mountains, stands, the grid's white stripes): on the grid the AI cars' "static" slot holds a per-frame
  dynamic cube. So the AI paint now reflects our live cube too (`FM3_AI_LIVE=0` = the static cube): the Eclipse's
  reflection term 30.2 -> 22.6, the Eclipse's paint 13.1 -> 11.3, all AI paint 14.3 -> 13.3, whole frame 14.20 ->
  14.17; its flank shows the near lines as in the game (`out/live/eclipse_ai_livecube.png`). Its dampener stays the
  live one (0.3; the game's AI path uses the static 0.5, not tried). The panorama also looks vertically inverted
  against our GL-convention reading, which needs checking before the same change goes to AI glass and lamps.
- **Race HUD** (2026-11-26 night; the user: "add the HUD elements, maybe customizable"): `godot/viewer/fm3_hud.gd`,
  drawn on a CanvasLayer above the exposure pass, fed by world_view.gd `_hud_feed` each live frame: a tachometer
  (rpm against the stream's redline, red zone, gear, speed), throttle / brake bars, a track map that builds itself from
  the player's path (no track file) with a dot per car, a digital speed readout and a debug line (both off by
  default). Each element: enabled, anchor (tl / tr / bl / br), offset, scale, colours; units kmh / mph. Defaults in
  `godot/viewer/hud_default.json`, overridden by `user://fm3_hud.json` or `FM3_HUD_CONFIG=<path>`; H toggles it;
  `FM3_HUD=0` off (live_compare / live_track and the scratch test scripts set it: the game's own HUD stays in its
  picture). `godot/viewer/hud_test.gd` draws it with made-up data. Trap found: a Control under a CanvasLayer has no
  size from its anchors (0 x 0): elements are placed from the viewport's size. Not yet: race position and laps (not in
  the stream), the game's own HUD look.
- **The menus' 3D scenes** are tracks in the game files (`Media/Tracks/UILivery, UIThumBig, UIThumbnail, UITrack,
  UIWhite, UIupgrades`): `build_track.ps1 -Track UIWhite` / `UIupgrades` build now (`fm3_pvs.py`: texture tables of
  one or two entries; `fm3_track_export.py`: empty mesh groups skipped). Rendered they are flat dark grey so far (a
  floor, a backdrop and the sky dome; the menus' light scale differs: their static cube is read x8). PLAN-NEXT.md 6.
- **The 3D crowd, static** (2026-11-26 night; the user: "the animated 3D crowd"): the game's own seated people
  instead of the dark crowd cards. `tools/fm3_spectators.py <FM3-files\game\Media\Spectators> out\spectators` writes
  every model (`models\<Name>_{Sit,Stand}.skinbin`: 14 crowd figures, and the photographer, pit worker and marshal
  standing) with each of its two textures as glTF, at detail levels 0, 2 and 3 (the skinbin's 7 levels); the UVs are
  unsigned 16-bit (u / 65536: checked on all 14 seated figures, faces / shirts / shoes in place; signed + 0.5 or a
  flipped v put faces on chests). `tools/fm3_crowd3d.py <..._track_NN.crowd> out\world\<scene>.gltf` writes the
  layout's people (figure, second index, position, facing) to `<scene>_crowd.json` (done for CrownJewel Ribbon_04,
  Sebring / RoadAtlanta / Motegi Ribbon_00). The viewer (`_crowd3d`, on where the file exists, `FM3_CROWD3D=0` off)
  hides the `crowd_people` cards and draws one MultiMesh per figure and texture (the figure modulo the 14 seated ones,
  the second index modulo 2 picks the texture), facing as the cards (`FM3_CROWD3D_YAW` for tests; 180 is worse),
  level 2 by default (448 triangles; level 3 above 8,000 people: Motegi has 24,299; `FM3_CROWD3D_LOD`). CrownJewel grid
  (one boot): off / level 2 / level 0: the pixels it changes 41.08 / 35.33 / 34.77, whole frame 14.36 / **14.01** /
  14.23 (the first boot: the stands 17.29 -> 15.41). Sebring (few people in view, 3,239 pixels): 41.0 -> 42.0, whole
  16.60 -> 16.62. Not yet: the animations (PLAN-NEXT 2), the game's
  crowd shading (TrackSettings Crowds dark / light: Godot's lighting here), the far crowd's sprites (the 'crowds'
  cards stay), pit crew / marshals (placement unknown).
  Then (00:00): the people's brightness x0.7 (fitted; the game's dark / light crowd shading not decoded) and every
  person in 3D (the game switches to sprites past TrackSettings' SpriteDistance, 150 m on CrownJewel, but its sprites
  are renders of these people; our only far "sprites" are the track's card sheet: `FM3_CROWD3D_SPRITES=1` does the
  switch, cards faded in past the distance). CrownJewel grid, one boot: cards 14.35, people x0.7 + sprites 14.12,
  the track's dark colour unshaded 14.19, **x0.7, all 3D 13.92** (the people's pixels 38.8 -> 29.3, mean 70 / 64 / 58
  against the game's 70 / 65 / 61). Viewer speed with the crowd (live_smooth, 30 s): 23 -> 22 fps.
  Tried: the person's second index as the pose (0 seated, else the standing model; figure 14 = the photographer,
  standing): worse on both (CrownJewel people 30.66 -> 32.99, Sebring 49.9 -> 50.9; `FM3_CROWD3D_POSE=1`). What the
  second index (0-5) and figure 14 mean is open: maybe animation variants (PLAN-NEXT 2).
  Measuring note: two boots' viewer pictures differed by 1.44 on average with the same settings (247 pixels by more
  than 10): a small whole-frame shift between boots; compare variants within one boot.
- **HUD race data from the game** (2026-11-27 morning): race time, place and laps on our HUD, from the game.
  - How they were found (all on the frozen CrownJewel grid race with the AI driving the player, the game's own HUD read
    off shots as the reference): the eight car objects hold no race position (`tools/research/allcars.ps1`: the only
    offset where the cars hold a permutation of 1..8 never changes: a car index at +2316); no float in memory follows
    the wall clock (the game ran ~85% real time minimized); the debug server got **`findf LO HI`** and **`findu LO HI`**
    (FM3-ReGPU `thirdparty/ReGPU/src/debug.cpp`, recorded as `patches/regpu-debug-findf-findu.patch`): on a frozen
    frame, `findf` around the HUD's race time (e.g. 24.293) gave a handful of floats; the one that equalled the HUD again
    after the race ran on is in **each car's physics object at +2772** (24.293 / 33.311 / 42.327 / 51.342 / 60.358 /
    69.378 against the HUD's 24.293 / 33.312 / 42.328 / 51.345 / 60.361 / 69.381). `findhex <physics>` listed the
    objects pointing at the physics object; dumped at two moments, one of them holds the **race position at +280 from
    its pointer** (1-based: 6 -> 5, then 4, with the HUD) and a **track segment at +92** (245 -> 548 along the lap,
    140 right after the line). Its class: the word 500 bytes before the pointer is 0x8286B06C. No lap counter was found
    within 2 KB of it, nor the race's lap total. Scripts: `tools/research/raceclock.ps1`, `allcars.ps1`.
  - The stream: FM3E **v9** (FM3-ReGPU 478cd0f): race clock, place, segment (the recomp finds the participant by a heap
    scan once per physics object). The viewer counts laps from the segment's drops (the first crossing after the grid
    starts lap 1, as the game's "LAPS 0" -> "1"), and from them last / best / current lap times.
  - Checked live (game and viewer side by side after 70 s of race): place 5/8 = 5/8, laps 2 = 2, race time 01:09.650
    (game) / 01:09.647 (viewer), gear 3, 129 km/h on both. The tach now reads 0-10 for redlines up to 10,000 (the
    game's dial for the CR-X's 9,500). With last / best / lap rows (second run, 70 s): race 01:09.378 / 01:09.375,
    last and best 00:50.396 / 00:50.326 (our lap starts when a packet shows the segment's drop, ~70 ms after the game's
    line), lap 00:14.175 / 00:14.172, place 8/8 both. Not yet: the lap total ("/3": `"total_laps"` in the HUD config), a lap counter
    for a viewer started mid-race (it counts from when it starts).
- **Lamps and lenses on the per-frame cube** (2026-11-27): the game's lamp shaders (tail_light 7f4b46775654ee5b,
  textured reflector, reverse) read t3 under bool 130 (the AI cars: the "static" slot, which on the grid holds a
  dynamic cube, as the paint's t7) and t2 otherwise (the player's per-frame cube): `fm3_lamp_game.gdshader` now takes
  the live cube (bound in `_lamp_material`; `FM3_LIVE_LAMP=0` = the static cube), and the lenses do too
  (`fm3_carglass` live_lens; `FM3_LIVE_LENS=0`). CrownJewel grid, one boot each: the lamps' 4,211 pixels 15.53 ->
  10.87 (61 / 28 / 26 against the game's 62 / 27 / 25), the lenses' 3,620 pixels 18.93 -> 12.25, whole frame 14.10 ->
  14.08 and 14.11 -> 14.08.
- **Road lines without a mask** (`rdline_diff_opac_2`, Motegi's white lines; disassembled 2026-11-26): texture x P[0].z
  (0.6 there) x the lightmap, opacity = the texture's alpha. We cut them out at full brightness: solid white edge
  lines where the game's are dimmed and worn. Now exported dimmed by P[0].z and alpha-blended
  (`fm3_track_export.py`). Motegi (rebuilt): the lines' region 18.7 -> 12.9, whole frame 15.0 -> **13.5** (two boots
  that froze at different spots: not a strict A/B, but the line now looks like the game's in both).
- **Per-colour base textures for library cars** (2026-11-26): each Combo_Colors row names its BaseTexture; 44 of the
  510 cars switch it per colour (REN_5Turbo_80: colour 1 `nodamage` = red decals, 2 / 3 `nodamageblue`, 4
  `nodamageblack`; Shelby GT500s, Saleen S281s, the SSC, Volvo C30 ...). The library exported only `nodamage`, so a
  silver-blue R5 Turbo (colour 3) showed red "TURBO" lettering where the game's is blue (RoadAtlanta). New
  `tools/fm3_car_basetex.py work\assets\cars <gamedb.slt> out\cars` adds the alternative textures and
  `<car>_basetex.json` {colour: stem} beside a built library car (run once after fm3_car_library.py; done for all
  44), and world_view.gd swaps them into the paint and nodamage materials when it attaches the car (log line "uses
  base texture"). Checked in a live RoadAtlanta run (the R5 in colour 2 took `nodamageblue`); the decals were too
  small in that boot's frame to compare by eye.
- **Per-track shadow colour** (2026-11-26, 11:15): a car's / person's sun shadow on the track now darkens it to the
  track's `ShadowColor` (TrackSettings.xml, gamma; in linear per channel) instead of one fitted strength 0.85, which
  was CrownJewel's own value (0.32 / 0.37 / 0.45 -> ~0.11 linear = 1 - 0.85 + a blue tint). The values vary: Sebring
  0.20-0.34 (darkest), RoadAtlanta 0.49-0.53, Motegi 0.53-0.63 (lightest). In `<track>_track.json` (exporter; the 17
  existing side files patched), `shadow_tint` in fm3_baked / fm3_baked_blend / fm3_blend, `FM3_NO_SHADOW_COLOR=1` =
  before, `FM3_SHADOW_K=<s>` a single strength for tests. CrownJewel neutral (whole 15.6 -> 15.7, the CR-X's shadow
  11.1 -> 10.8); RoadAtlanta better everywhere (right road 80.3 -> 70.0, mid road 22.1 -> 20.5, whole 16.9 -> 16.6).
  The shadows' length / extent at RoadAtlanta is still the larger part of that gap (below).
- **RoadAtlanta's car shadows are wrong** (found 2026-11-26, open): our cars throw long, dark sun shadows forward and to
  the right across the road where the game's car shadow is short, under the car; the right side of the road 49 / 48 /
  50 against the game's 130 / 127 / 127 in one boot; with the viewer's sun shadows off (`FM3_NO_SHADOWS=1`, test
  switch; `--no-shadows`) 121 / 119 / 123, whole frame 16.8 -> 15.9 (last night's runs show the same). The viewer
  casts them along TrackSettings `ShadowLightDirection` (RoadAtlanta: (0.787, -0.480, 0.615), 29 degrees high, with
  `OverrideShadowLightDirection` 1; Sebring's is steep, -0.79, and looks right). Next: find which direction the game
  uses for car shadows (the override flag suggests the track's direction is not the cars'; check the sign / axis
  conversion against a game shot with a long shadow), and the shadows' darkness (ShadowColor 0.49 / 0.50 / 0.53).
- **The asphalt's fine grain** (the user's "rough asphalt look"): our road recipes equal the game's code (Sebring's
  `road_2blnd_3` decoded: grain at world xz x P1.x, the second layer at UV x P1.yz, v = the blend value's green;
  colour g x P0 + A x v x (g + P2 - g x P0)), and the grain textures have their full mip chains (BIX0: 512 x 512, 10
  mips), but our box-filtered mips averaged the speckle away a few metres out. A mip bias on the base texture only
  (`fm3_blend.gdshaderinc` grain_bias, default -1; `FM3_GRAIN_BIAS`): road detail (mean neighbour difference) Sebring
  near / ahead / right 14.2 / 7.5 / 6.1 -> 16.9 / 10.0 / 7.7 (game 17.1 / 10.3 / 8.3); CrownJewel whole frame 6.6 ->
  8.0 (game 8.7), stripes 9.7 -> 13.6 (game 14.3). Per pixel: Sebring about the same (-2 better: 23.9 -> 23.0),
  CrownJewel 15.3 -> 15.7 (added detail is never pixel-aligned with the game's). A judgement call for the look:
  `FM3_GRAIN_BIAS=0` = before.
- **Per-vertex light for the `*_nolm` track shaders** (2026-11-26 morning): the CrownJewel pit wall (`facility_R`,
  `barr_shad_diff_spec_nolm_1`) had no lightmap in our scene and fell back to Godot's own lighting (greyer, darker).
  Disassembled: texture x lerp(DarkColor c247, LightColor c248, vertex light), the light baked per vertex as an ARGB8
  colour at byte 20 of the stride-24 vertex (A = 255). `fm3_track_export.py` now writes it as COLOR_0 with
  `fm3_vlit` on the material (48 materials on CrownJewel: walls, fences, poles), `fm3_baked.gdshader` use_vlight draws
  it (`FM3_NO_VLIGHT=1`: the old way). Live CrownJewel grid, one boot: wall face 41.6 -> 11.4 (204 / 159 / 123, game
  210 / 164 / 129), wall top 21.4 -> 17.7, the right-side wall 18.2 -> 9.8, **whole frame 17.0 / 16.6 / 15.9 ->
  15.2 / 15.3 / 15.3**. Checked in the code for the kinds CrownJewel uses most (`FM3_DEBUG_MAT=_` lists them):
  `barr_shad_diff_spec_nolm_1` (188 uses), `diff_spec_vert_nolm_1` (84), `diff_nolm_vclr_1` (35) and
  `chain_diff_spec_opac_2_2sd_nolm` (28) all draw texture x lerp(c247, c248, the vertex value); the see-through ones
  (chain fences) keep Godot's lighting (the viewer branch takes opaque materials only). Sebring / RoadAtlanta have
  no such meshes: their `diff_1_nolm` is lit at run time (texture x lerp(shad_color, 1, shadow) x (N.L x sunColor
  + ambColor), constants set per frame) and covers 0.3% of Sebring's grid view. Also tried: no second block
  compression of the textures (`FM3_NO_COMPRESS=1`, test switch): no change (15.3 both).
- **16x anisotropic filtering** (project.godot; was Godot's 4x; the user: the asphalt lacks its rough look in
  general): the road is seen almost edge-on from the cameras, where 4x falls back to blurred mips. One Sebring boot:
  road regions 20.5 / 20.4 / 20.5 -> 19.9 / 19.6 / 20.1, wall 15.9 -> 15.3, whole frame 22.4 -> 21.8; CrownJewel grid
  17.0 / 16.9 / 16.5 -> **16.7 / 16.5 / 16.0**. A finer mip bias (`FM3_MIPBIAS=-0.5 / -1`, test switch) adds detail
  that is not the game's (per pixel worse); `FM3_ANISO=<n>` overrides the level for tests. Still half the game's
  fine detail on the far road (3.7-4.0 against 7.1-11.3, mean neighbour difference): our mips are Godot's box-filtered
  ones from the top level, the game's files carry their own mip chains (not used yet: `_bind_textures` regenerates).
- (Before that) **Track stripes too clean and bright** (the user, 2026-11-26: they lack the worn, driven-over look of the game's
  and its rough asphalt showing through). Cause in the code: the main road-line shader `rdline_blnd_spec_opac_3` is
  baked by `tools/fm3_track_export.py` (~line 1209) as the line texture alone, alpha = its mask, dimmed by a fitted
  0.6. The game's code (captured ps 94e08de1, PLAN-CARS "Road lines") is `lerp(c0 asphalt grey 0.157, t0 line,
  t1 wear mask)`, t1 = material slot 1 (tyre marks / dirt, mostly white; on CrownJewel's start boxes id 632) at the
  lightmap's UV x P2.xy: the mask is what lets the asphalt through where cars drive. Next: export these meshes as a
  family record like `rdline_blnd_diff_spec_opac_3` (fm3_blend.gdshaderinc mode 17: `mix(tint0, t0, t1) * tint1.x`
  with tex1 at uv23 x scale1), tint0 = the material's P0, scale1 = P2.xy, opacity from the mask; drop the fitted 0.6;
  rebuild CrownJewel / Sebring and compare the stripes (CrownJewel grid's right-side kerb stripes: ours 141-163,
  game 115-136).
- Still open: the RSX's lenses are less pink than the game's (G 37 vs 65); a thin strip at the roof's rear edge is
  dark in ours (46) where the game's is bright (139); the top rows of the rear window are brighter in ours (54-60
  against 14-24).
- Paint sharpness: the game's car cube is six 256 x 256 faces with 4x MSAA, three a frame (NOTES); a 256 px / 4x MSAA
  live cube here (`--live-cube 256 --live-cube-faces 3 --live-cube-msaa 4`, or `FM3_LIVE_CUBE=256,3,4`) changed the
  RSX roof's detail 12.0 -> 12.7 only (game 23.0): resolution is not what makes ours softer. The roof reflects about
  half as bright as the game's (52 vs 108; the same clouds, lower contrast); a 1.5x live-cube reflection gives 80 but
  worsens the whole frame (23.2 -> 24.7): the roof alone is under-lit. Next: the RSX's baked sky weight on its roof
  (library UV2, `fm3_carbin.env_sh`) and the Fresnel at the chase camera's angle against a ps edit of the game's paint.

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

- **The HUD's own files (2026-11-27):** the race HUD is the UI scene `947_hud` (`Media/UI/scenes/ui4`), built from
  the textures of `Media/UI/Textures/I_Map/I_HUD` (`tools/fm3_hud_textures.py`); our tach was first redrawn by eye
  from the game's shot (grid with ours on: 14.3, ours off 14.0-14.3: no whole-frame change). PLAN-NEXT has the list.

## Stage B: the game leaves the race to Godot (2026-11-27, a switch)

- **What the user asked:** boot the game and load into races without the game's own rendering costing the frame rate;
  a switch for now. **How to use it:** `play-godot.cmd` (frame-ir) starts both, stage B on for that run; or launcher Settings "Godot renders races (stage B)" (settings.ini `stage_b=1`; it
  turns the live stream on too), start the game, start `live.cmd` (CrownJewel's scene; another track: `live.cmd --gltf
  <abs>\out\world\<track>.gltf`). The viewer's window shows the game's own frames while the game is in its menus and
  draws the race itself once a stage B race runs. Input still goes to the game (a pad works whichever window has the
  focus).
- **The game's side** (FM3-ReGPU `src/hooks/stage_b.cpp`, NOTES.md 2026-11-27 afternoon): in races it skips the scene
  renderer's world steps, the crowd (`sub_828878C0`), each car's draw after the live stream took it, the mirror, the
  reflection cube and the car shadows, and caps the race at `stage_b_fps` (120). Frozen CrownJewel grid, same boot:
  2,663 -> ~300 draws, 225 -> 360 fps (cap lifted), GPU 1.6 ms a frame left (clears, post-processing, HUD at 4x MSAA).
  The game's window keeps its HUD over a flat grey.
- **The menus in the Godot window:** ReGPU's frame feed (FM3-ReGPU `patches/regpu-frame-feed.patch`, `REGPU_FRAME_FEED`,
  turned on by stage B: `out/run/frame_feed.bin`, ~30 frames a second, read back without waiting for the GPU) with a tag
  (the renderer scenario, stage B active); world_view.gd `_game_feed_update` shows it full-window unless stage B is
  active (`FM3_GAME_FEED=<file>` / `0` off). Checked: the title screen came through; the race was drawn by the viewer.
- **The viewer follows the game's track** ("FM3T", once a second: the last Media/Tracks folder the game opened a file
  in): another track than its scene, with `out/world/<track>.gltf` built, and it starts again on that scene (checked:
  CrownJewel -> RoadAtlanta from Free Play). A track not built is logged with its build command. The game's last frame
  stays up while the game shows nothing new (loading screens).
- **After the user's first drive (2026-11-27):** the game's own HUD and its race menus (pre-race, pause, results) are
  laid over the viewer's race: the game's frame with its flat grey keyed out (the key = the most common colour on a
  sparse grid of the frame; our HUD set aside; `FM3_GAME_HUD=0`: ours instead). The cockpit view shows the player's car
  (the game now streams cars it does not draw). The car shadows' window (2-3 m around each car) follows the cars as
  drawn (interpolated), not their newest packet, which ran a metre ahead at speed: the user's popping shadows under
  moving cars (not checked in motion yet). Behind the game's frames (menus, the pre-race orbit) the viewer draws no 3D
  and no reflection cube (~20 -> 130-290 frames a second, every feed frame shown); a feed read caught mid-write keeps
  what is shown (it flickered to the viewer's own scene). `FM3_SHADOW_HQ=1`: sharper sun shadows (opt-in).
- **Second drive's fixes:** in-car views use a 5 cm near plane (the scenes' 0.3 m cut the roof lining away); the
  pre-race orbit is drawn by the viewer (stage B covers it); the game's overlay treats a grey darker than its key as a
  black layer at that opacity (the pre-race menu's vignette, the HUD's dark panels came out as grey bands), and the key
  only follows mid greys, gradually.
- **Open:** the layout (Ribbon_NN) is not matched (a scene is built for one layout); the race's own menus (pre-race, pause, results) are only in the game's window (the game's flat-grey
  frame could be keyed and laid over the viewer's race); leaving a race back to the menus not yet tested; the game's
  remaining fixed GPU passes in a stage B race.

## The user's notes of 2026-11-27 evening (worked through 14:09-24:00)

- **Wheels not turning (stage B):** the game puts a wheel's spin into its matrix (car +0x190) when it draws the car,
  which stage B skips: the streamed wheels kept steering and suspension only (0-0.6 degrees a viewer frame at 35 m/s).
  The viewer spins them (`_spin_wheels`: about the axle = the car's up x its direction of travel, by distance over a
  0.31 m radius; FM3_WHEEL_SPIN=0 off): 28-85 degrees a viewer frame at 32-41 m/s now. `FM3_WHEEL_LOG=1` logs it.
- **Brake lights:** binary in the game (its own shots: the CR-X's lamps fully lit at a 7% brake, dark at 0). The
  viewer's followed the pedal and faded over 0.25 s, and lit the AI cars' from their deceleration (also when they only
  lifted off): now on / off with no fade, from each car's own brake ("FM3B", FM3-ReGPU live_camera.cpp: every race
  participant's physics object matched to its car).
- **Countdown vignettes:** the overlay's key was the frame's most common grey, which in the countdown is the vignette's
  darkened edge; the undrawn centre then covered the race as a grey ellipse. The key is now the lightest neutral grey
  seen at least 3 times (the game's overlays only darken its undrawn scene): on the game's countdown frame it picks
  the centre grey (0.392, the old rule 0.376); live, the countdown shows the race under the vignette.
- **Badges "sunken":** the game draws them polished (Normal.xml badge: SpecularAmount 4, power 128, Fresnel 0.15 .. 1
  x (1 - cos)^1.5, CubeScale 1; emblem 1 / 75 / power 1); ours were matte (the library's roughness 0.6, no
  reflection) beside the glossy paint. `fm3_carsolid.gdshader` now has the game's Fresnel reflection of the live cube
  (refl_on) with those values for badge* and emblem* (FM3_BADGE_REFL=0: as before). Not yet compared against a game
  close-up.
- **Crash damage (research, next):** the car vertex shaders deform by a 3D damage lattice around the car: the vertex
  position scaled into grid cells (vc4 / vc5 / vc8-10), clamped to the grid (vc7 / vc11), the lattice table at vertex
  fetch 94 (two float4 per entry, interpolated across the cell into one amount), the vertex moved along its own
  direction by it, clamped by vc6 (damageClamps); e.g. vs_0b663c87079d33bf (shadow pass). The damage textures:
  `damage*.xds` / `damagelights*.xds` per car folder.
  **Decoded further (2026-11-27 evening, capture with the game's constant numbers, paint VS a102319a5aef757b):** the
  lattice is 10 x 10 x 10 cells on every car (vc116-118 = 10), fitted to the car: origin vc41 (its back-left-bottom
  corner, e.g. -0.93 / -0.59 / -2.00 m), inverse extent vc42 (0.54 / 0.62 / 0.25 = 1.86 m wide, 1.61 high, 3.98 long),
  the model's position offset vc190, clamps vc58 = 0 .. 1. Table = vertex fetch 94, 1,000 entries x 32 bytes (32,000):
  per cell its 8 corner amounts, blended trilinearly by the position in the cell; the vertex moves by the amount along
  a per-vertex damage direction (vertex stream 95, offset 7, 3 normalized components: not in the car library's export).
  Undamaged: all zero. The game writes the table through the B0000000 mirror of physical memory (e.g. B0DF1000).
  **Not found yet: which table is which car's.** The B pointers sit in allocator-like records (400722xx, stride
  0x40-0x50, no vtable before them) and a render list (460Cxxxx); no pointer to a table, its fetch word (addr | 3) or
  its B address within two levels of the car objects or of the car draw's arguments (r3, r5-r9; scripts in the
  scratchpad: argscan / vbscan / holderscan). Next: hook the call that binds fetch 94 inside the car draw (sub_828329C8)
  and take the address there (with stage B, run that part of the draw and skip the drawing); then stream the 32 KB
  table per car when it changes ("FM3D"), and deform the library car's vertices on the CPU when it does (normals as
  the direction until the direction stream is exported).
- **Crash damage, built (2026-11-27 afternoon):**
  - *Which table is whose:* ReGPU got a fetch watch (`regpu::SetFetchWatch` / `TakeFetchWatch`, FM3-ReGPU patch
    `regpu-fetch-watch.patch`): each draw reading a 32,000-byte vertex fetch 94 records the buffer's address and the
    vertex constants 41, 42, 190, 58 and 11 (vc11 = the draw's world translation), each address once. FM3-ReGPU
    `live_camera.cpp` DamageFrame: while known cars have no table, stage B pauses for 0.5 s (`StageBHold`, the game draws
    its cars), every 2 s; each table goes to the car whose body is nearest vc11 (within 2 m; on the grid 0.75 m off).
    CrownJewel grid: all 8 cars in ~15 s (the first probes see few car draws). Log: `live: car X damage table Y`.
  - *Stream:* "FM3D" v1, 8,080 bytes: car, chunk 0-3, vc41 / vc42 / vc190 / vc58, 8,000 bytes of the table (big-endian
    floats). Tables are hashed 4 times a second; a changed one (and every one every 2 s) is queued and sent one car (4
    packets) a frame, through a 1 MB send buffer: 32 packets at once were mostly dropped (one car's in 15 s).
  - *The formula (paint VS a102319a5aef757b, decoded line by line):* P = car-space position (local x w + vc190);
    g = (P - vc41) x vc42 x 10 per axis; cell = clamp(floor(g), 0, 9), index z x 100 + y x 10 + x, 8 floats: the first
    float4 = the corners at y + 1, the second at y; components (x0 z0), (x1 z0), (x1 z1), (x0 z1); amount =
    lerp(lerp(c.x, c.w, fz), lerp(c.y, c.z, fz), fx) of the y-lerped corners, saturated, clamped to vc58. The vertex
    moves by amount x 2y (x, sqrt(1 - x^2 - z^2), z), (x, y, z) = the stride-40 vertex's damage word at 28 (11:11:10,
    `fm3_carbin.damage_dir`). On the NSX it points inward (cos with the normal -0.2 .. -0.8), 0-30 cm.
  - *Car library:* `<car>_damage.bin` (fm3_car_library.py, `--damage-only` writes just these: 510 cars in ~20 min): per
    body part its positions and directions and the glTF meshes using it. Godot's glTF import drops each mesh's unused
    vertices and keeps positions 16-bit in the mesh box, so the viewer matches by position (0.5 mm grid + neighbours):
    0 of ~70,000 vertices unmatched per car.
  - *Viewer (`world_view.gd` _damage_packet / _damage_update):* a car's new table rebuilds its body meshes' vertices
    (normals unchanged), at most every 0.5 s a car, ~3 ms of work a frame (first time ~0.45 s of work over ~2 s per car,
    including the one-time cell set-up). FM3_DAMAGE=0 off, FM3_DAMAGE_LOG=1 packet counts.
  - *Tested by writing tables* (scratchpad dmgpoke.ps1: grid test + viewer, debug-server `poke` of the cells z 0..2 to
    1.0 on every car): 8 of 8 cars deform, the rear bumpers of the cars ahead push in (374 pixels changed in the view).
    Not yet seen with a real crash; the damage textures (damage*.xds, the scuffs) are not used yet.
  - *A real crash* (scratchpad dmgcrash.ps1: grid test, the virtual pad at full throttle 14 s then full left 4 s into
    the pit wall, frozen, then FM3_STAGE_B 0 live so the game draws its cars): the game's tables changed on 3 cars and
    the viewer applied them (repeat updates ~20 ms of work over ~150 ms; the first ~0.4 s with the cell set-up). The
    game's CR-X lost parts (its rear bumper lies on the ground beside it, two small pieces too) and has scuffs; the
    viewer's CR-X shows neither: **detached parts** are another mechanism (the car's part list / debris objects, not
    the lattice: find which flag hides a part, e.g. by comparing the car's part records before and after) and the
    **scuff texture** (damage*.xds blended by an amount) is not used yet. Shots: scratchpad dmg\crash.png (viewer),
    game-crash-drawn.png (game).
- **Optimizing the viewer (measured, frozen CrownJewel race in stage B, 1280 x 720, vsync off, `FM3_FPS_LOG=1`):** the
  viewer is bound by Godot's draw-call submission on the CPU, not the GPU: 31-36 fps at ~5,800 draw calls; the 3D
  crowd's 36 M of the 43 M triangles, MSAA and the shadows changed nothing. Our own script is ~7 ms a frame (cars 2.7,
  exposure 1.8, feed 1.4, ~135 packets 1.1). The live reflection cube's faces each draw the whole scene: 6 faces a
  frame 31-32 fps, 2 faces 44-46, 1 face 45-51; its far plane at 300 / 150 m ~37. **The cube now renders 2 faces a
  frame** (each renewed every third frame, ~15 times a second; `--live-cube-faces 6` as before). Next (planned):
  fewer draw calls in the main view: the track's meshes are grouped by (shader, texture, lightmap, parameters), 2,454
  on CrownJewel with 842 lightmap textures; packing the lightmaps into atlases in fm3_track_export.py would let the
  groups merge (per material and spatial cell, to keep culling), then rebuild the tracks. The game's per-instance LOD
  distances (.pvs instances, e.g. 80 / 160 / 240 m on ~500 of CrownJewel's 2,635) could then become visibility ranges.
- **Parts knocked off ("FM3P", 2026-11-27 ~16:30-17:00):** after a damage change (1.5 s after it settles) and once when
  all tables are mapped, stage B pauses 0.5 s while ReGPU's fetch watch records, per frame, each vertex buffer read as
  fetch 95 (a car part's vertices) with its size, the draw's translation vc11 and its damage table (fetch 94 = which
  car). In the frame with the most hits, a car's attached parts share its translation exactly (its largest group);
  the rest are loose (hanging / lying; the wheels too). FM3P v2 sends both lists of sizes. The cars at the grid are
  drawn from the main file's LOD 1-5 buffers (24 of 25 / 31 of 32 sizes matched those by part name), so
  `<car>_damage.bin` v3 lists every body part (also those that do not dent: mirrors) with all its buffer sizes. The
  viewer hides a part whose sizes are among the loose ones and not on the car (a mesh, or its triangles in a merged
  mesh: meta src_ranges / idx_now); a part not drawn at all stays (it may be culled or drawn by a shader the probe does
  not see: at the baseline 1-2 parts a car were not found). Crash test (pad into the pit wall): the game lost the front
  bumper and both mirrors; the viewer hid the same three. **The loose parts drawn (FM3P v3, ~17:50):** the probe also
  records c8-c10 (the paint VS's world matrix: P.x c8 + P.y c9 + P.z c10 + c11, game numbering), each loose buffer's
  size goes with its matrix, and the viewer puts a copy of that part (its mesh, or its triangles out of a merged one)
  at it, converted as the streamed car matrices are: the crash test's bumper and mirror lie where the game has them.
  - *The probes' 0.5 s holds and the game feed:* while held the game draws its world, and those frames came to the
    viewer still tagged "stage B" (bit 8): keyed as a HUD over grey, the game's own world would have covered the
    viewer's for the hold. The feed's tag now has bit 9 while held (FM3-ReGPU stage_b.cpp StageBHold); the viewer keeps
    its last overlay for those frames and 0.3 s after (the copies lag a frame or two). Cost: a 0.5 s pause of
  stage B after a crash (the game draws everything for those frames). `FM3_PARTS=0` off, `FM3_PARTS_LOG=1` why a
  report was not applied.
- **Cars that stop being streamed (2026-11-27 ~19:45):** a new race on the same track keeps the viewer (no FM3T
  restart), and the old race's car objects may be gone: their library models and loose parts stayed where they last
  were. Now a car without "FM3K" for 4 s (while others are streamed) is hidden with its loose parts, and shown again if
  it comes back (`_cars_gone_update`). In stage B every known car is sent each frame; in stage A the game sends only the
  cars it draws, so a car out of its view is hidden there until it is drawn again.
- **Every car's own steering (FM3B v2, 2026-11-27 ~19:40):** the AI cars' steering wheels (and now their drivers'
  hands) turned with the player's stick. FM3B now carries each car's steering from its physics object (+3416; the
  player's equals its stick: -1 / -1 at full left), and the viewer turns other cars' wheels by it (FM3_AI_STEER=0: as
  before; FM3_STEER_LOG=1 prints the player's two values).
- **Tyre smoke and skid marks (2026-11-27 ~19:30):** the game draws them in the world steps stage B skips (its stage-B
  frame is plain grey: no particles there). The viewer makes its own from each wheel's lateral slip: the angle between
  the wheel's ground velocity (its centre between viewer frames) and its rolling direction (the axle of its streamed
  matrix, steering included), for every car. Driving checks (`FM3_FX_LOG=1`): AI cars cornering 1-7 degrees, the
  player's handbrake spin 18-90. Smoke from 8 degrees, full at 23, above 5 m/s (the game's threshold is in its code;
  `FM3_FX_SLIP=<from>,<full>`), with the game's tire_smoke parameters (Media\Effects\particles.xml: lifetimes up to
  ~3-4 s, growing, damping 0.6, alpha at most 90 / 255) and texture (the top-left quarter of Effects\smoke.dds);
  skid marks from ~10 degrees, quads of Media\Treadmark.dds laid along the wheel's path (6,000 kept, the oldest
  replaced). `tools/fm3_effects.py` exports the two textures to out\effects. `FM3_FX=0` off, `FM3_FX_TEST=1` every
  wheel smoking (looks: thin wisps at each wheel), `FM3_SHOT_NOW=1` takes a live picture without waiting for the
  exposure. Not yet compared with the game's own smoke in the same moment (its stage-B frame has none; with stage B
  switched off for a shot the slide was over). Not yet: dust / grass / dirt off the track (the atlas's other quarters,
  the surface under the wheel), sparks, the smoke's colour per track (Tracks\<track>\smoke.dds).
- **The crowd's animations (2026-11-27 ~17:45; PLAN-NEXT 2):** the game animates its 3D people on the GPU: its crowd
  vertex shader 6ee601730a7f9f87 (114 draws on the grid: the near people) skins each person from one 1,201,992-byte
  buffer (fetch 94) that the race load builds by sampling every crowd animation through the codec (sub_82AABED0, at
  normalized times). Decoded (`tools/fm3_crowd_anim.py`): the skeletons in spectators.xml order (Sitting 12 bones:
  Sit_Cheer_01..07; Standing 17: Stand_Idle_*, _Drunk, _Photo, Stand_Cheer_*), each animation's frames at 30 a second,
  one entry per bone and frame (the sizes add up to the byte: 11,664 + 88,502 entries); an entry = three 11:11:10
  normalized vectors: rotation rows r0, r1 and a translation t, the bone's skinning transform relative to the bind
  pose: p' = r0 p.x + r1 p.y + (r0 x r1) p.z + (2 t.x, 3.5 t.y, 2 t.z) (constants c255.x / c254.w), blended over the
  vertex's two bones. A draw's c10.w = its animation's first entry, c10.x = the current frame's (Stand_Idle_Photo at
  62035: posed on the CPU, the photographer raises the camera to the face). The buffer is read from a running game
  (`tools/research/crowd_anim_dump.ps1` -> Godot\work\crowd_anim\crowdbuf.bin, game data). The viewer skins the
  same way in `fm3_crowd.gdshader` (the buffer as a 2048 x 147 float texture; bones / weights in the people's UV2,
  `fm3_spectators.py`; per person INSTANCE_CUSTOM = first entry, frames, bones, start frame: its class's idle list,
  one picked per person, looped at 30 a second). Two viewer shots 8 s apart: the pit workers change pose (one arm
  out, as in the game's frame). Not yet: cheering when cars pass (the classes' cheer lists), which idle the game
  picks per person. `FM3_CROWD_ANIM=0` still people. (Earlier dead ends, kept in PLAN-NEXT 2: the skeleton
  reconstructed from names and weights; not needed, the buffer holds the final transforms.)
- **The crowd's classes (2026-11-27 ~17:35):** the .crowd record's second index (0-5, the open question of
  2026-11-26) is the person's crowd class in spectators.xml's crowdclass order: Sitting, Standing, Drunk, Photographer,
  Marshall, PitWorker (CrownJewel Ribbon_04: 1,347 / 1,168 / 0 / 79 / 9 / 24). The viewer draws each class with its
  models (the figure's _Sit / _Stand, Photographer_Stand, Marshall_Stand, Pitworker_Stand); the texture of the figure's
  two is picked per person (not in the record). Before, everyone sat and the class picked the texture. CrownJewel grid:
  the pit wall now shows the game's pit workers and photographer at the same spots; the stands' region against the
  game 15.5 -> 14.8, whole frame the same within noise. `FM3_CROWD3D_CLASS=0` as before.
- **The in-car driver (2026-11-27 ~17:25; PLAN-NEXT 3):** Media\Cars\Driver\Driver.skinbin is the first-person
  driver (arms, hands, legs; 1,156 vertices, 13 bones: the 13-track animations the game samples on the grid; the crowd's
  vertex layout behind a one-level header). `tools/fm3_driver.py` writes it (x mirrored to the library's space,
  triangles reversed, the texture's v flipped: unflipped the hands wore the suit's striped sleeves) as three meshes,
  arms / left hand / right hand. Each car's carbin header (after the exhaust emitters) starts with the driver's anchors:
  the wheel's centre, its axis, the two hand grips, two more points (`tools/fm3_car_anchors.py` -> `<car>_anchors.json`,
  all 510 cars; the CR-X's wheel centre (0.351, 0.546, -0.313) against its cockpit wheel's (0.350, 0.553, -0.280)). The
  viewer adds the meshes to each library car as cockpit parts, moved so the hands' midpoint meets the grips' midpoint;
  both hands turn with the steering needle; the cockpit shader discards their back faces (`cull` 1: the in-car camera
  sits inside the shoulders, double-sided they filled the view). CrownJewel grid in-car against the game: 18.0 (the
  same view without them ~17-19 in earlier runs). Not yet: the arms' steering animation (the Granny SteerLock2Lock
  files, Oodle1). FM3_DRIVER=0 off. The cockpit (gloves included) had gone ~2.5x darker than the game's since its
  2026-11-24 fit (roof liner 7.8 vs 20.0): COCKPIT_GAIN 1.0 -> 2.5 (roof 17.8, dash 19.0 vs 26.9; in-car view 18.0 ->
  16.4; gain 5: 19.9). Vertical faces stay too dark (A-pillar 2.1 vs 14.7).
  **The same driver is in every car (~19:20):** the game draws it once per car (vs 3fd7a3519ea31c8e, 8 draws on the
  grid, its vertex buffer = Driver.skinbin's vertices, 1,156 x 32 bytes, a 512 x 512 DXT5 texture; there is no other
  driver model: no head or torso), so the viewer now adds an outside copy (driver_*, lit as the car's parts, back faces
  culled) to every library car, hidden in the player's own in-car view as the rest of its outside. CrownJewel grid /
  chase / in-car unchanged (14.3 / 15.0 / 16.5).
  The driver's pose (for the arms to follow the wheel): the draw's bone palette is constants vc60 on, 4 rows a bone
  (bone 0 identity with the driver's place in the car, (0.778, -0.150, 0.060)); that value is nowhere in the game's
  readable memory (FM3-ReGPU `tools/analysis/floatscan.py`, the frozen grid): the palette is built in the car's draw and
  written straight into the command ring, so with stage B skipping that draw there is nothing to stream. Left: the
  Granny route (the SteerLock2Lock animations), or running only the driver's part of the car draw.
- **Scuffs (2026-11-27 ~17:00):** the paint VS passes the clamped damage amount on as o[1].w (r3.w is not touched
  after the lattice); the paint PS e41e183a423e6f1b blends texture 2 (the car's damage_lod0, grey scuffs and
  scratches with alpha) as colour x (1 - D.a x a) + D.rgb x a and its highlight x (1 - a). `tools/fm3_car_damage_tex.py`
  writes `<car>_tex/damage_lod0.png` for the library; the viewer puts each vertex's amount in CUSTOM0 when it rebuilds a
  damaged mesh (every vertex in the lattice, also those that do not move) and `fm3_carpaint.gdshader` blends the same
  way (damage_tex, has_damage set only once the mesh carries the amounts). **Not yet seen in a picture:** the poke
  test at 0.6 on the rear cells showed no scuffs in the game either (the game may rewrite the table from its physics
  state), and the chase camera after a crash shows the undamaged rear; the right stick switched to a trackside camera,
  not a look-back. Checked instead with a forced amount on every car (`FM3_SCUFF_TEST=0.6`, ~17:55): the scratches
  and scraped patches sit on the panels where they belong (the texture's UVs are the paint's), paint lightened and
  greyed where scuffed; real crashes apply them only where the lattice has damage.
  (Side finding from that trackside view: near the barrier the game draws standing 3D people, e.g. a photographer
  with a camera, where the viewer has one dark seated figure: PLAN-NEXT 2.)
- **Optimizing, round 2 (2026-11-27 ~16:30; frozen CrownJewel grid, stage B, the game running beside it; scratchpad
  perfab.ps1 starts one game and several viewers in turn, 50 s each; `FM3_FPS_LOG=1` now also prints draw calls by
  pass):** base ~40 fps: main view 2,192 draw calls + 1,314 for its shadows, the live cube ~1,000 + ~230 a frame (2 of
  6 faces). Measured variants: both suns at 2 cascades (`FM3_SUN_SPLITS=2`) ~41, shadows 150 m (`FM3_SHADOW_DIST`)
  ~40, no shadows ~43, 1 cube face a frame ~45, no 3D crowd ~41, MSAA off ~39: the viewer is CPU-bound (our script
  ~7.5 ms of a 25 ms frame: exposure 1.3, feed 1.3, packets 0.9, cars 2.7), not GPU-bound. The objects were the lever:
  8 library cars x ~90 body meshes (+ ~40 wheel / brake). **Car bodies merged by material** (`_merge_car_body`: a car's
  carbin_<car>_<material>_<n> meshes of one glTF material become one, ~54 -> ~13; lamps, glass, lenses, gauges,
  mirrors, badges kept apart; the damage directions follow, meta dmg_src): **~40 -> ~50 fps**, main 2,192 -> 1,828,
  shadows 1,314 -> 898; the picture the same (mean 0.1 between two runs). `FM3_CAR_MERGE=0` off. Visibility ranges
  for small track meshes (`_visibility_ranges`, <= 6 m across, hidden beyond 40 x size; FM3_VIS_K=0 off) hit only 64
  of CrownJewel's 1,928 meshes (the track is already merged into big groups): no measurable change; **off by default
  since ~18:00**: on Sebring they hid 737 of 3,217 meshes, visible scenery among them (live_track against the game
  19.4 / 20.3 / 21.8 without, 22.5 / 23.9 / 25.8 with; FM3_VIS_K=40 to try). Seen in the same Sebring runs: the
  viewer's exposure settles at W ~0.75 (L ~0.38-0.40), the picture brighter than the game's (the 2026-11-26 note had
  W 0.953 matching the game). Most likely the freeze moment, not a fault: this run's frozen view is a close-up with
  the black RSX over half the frame (low L), and a frozen game keeps the L it had adapted to before (the morning's
  note; there L 0.580 both ways). To confirm: `-FreezeAfter 11` or wtrack.ps1 in the same boot.
  Then (~17:30): the cars' lamps, glass, lenses, gauges, mirrors, badges and reflectors cast no sun shadow (each caster
  is drawn again per cascade): shadow draws 898 -> 694, ~50 -> ~52.5 fps, the cars' area identical (0.0);
  `FM3_CAR_SMALL_SHADOWS=1` as before. The in-car driver costs nothing measurable. Left: the live cube's faces draw
  their own sun shadows (~110 calls a face; Godot has no per-viewport switch for directional shadows); 1 face a frame
  would give ~53 (each face then renewed ~8 times a second).
  Then (~18:10): **the exposure's measurement read back asynchronously** (`RenderingDevice.texture_get_data_async`;
  `get_image()` waited for the GPU every 10 frames): live grid ~48 -> ~57 fps (the visibility ranges now off, which cost
  ~3), the same exposure (L 0.4085 both ways) and picture (0.1); `FM3_EXPO_SYNC=1` as before. Godot's separate render
  thread (`--render-thread separate`) gave ~55 with the old read but nothing on top of the async one, and its
  RenderingDevice calls must then come from the render thread (the async read failed): left single-threaded.
  Then (~18:25) **the 3D crowd per 96 m cell** (one MultiMesh's bounds spanned the whole track, so every person was
  drawn in the view, each shadow cascade and the cube faces: Motegi's 24,299 people, 61-81 M primitives -> 9 M), the
  people casting no sun shadow and left out of the reflection cube (CROWD_LAYER): CrownJewel ~55 -> ~59 fps, the stands
  the same but for the poses. Seen on Motegi: the viewer's start is slow, each library car taking 1-2.6 s on the main
  thread (`FM3_ATTACH_TIMING=1`: glTF load ~300 ms, textures ~180, scene 35-850, merge 90-270, set-up 80-270; ~0.45 s
  on CrownJewel), so the live_track picture is taken before the exposure settles (Motegi 30-39 against this morning's
  14.3 is that timing, not the picture). **Library cars now load on a worker thread** (glTF, textures, nodes;
  `_lib_load` / `_library_step`, two at a time; FM3_LIB_THREAD=0 as before): the main thread's share per car ~470 ->
  ~150 ms. And the Motegi live view was 3 fps steady: the 96 m crowd cells made 1,945 MultiMeshes (offline Motegi:
  96 m 161 fps, 256 m 206, **512 m 225 (now the default)**, one cell 245); live Motegi 3 -> 49-59 fps, CrownJewel ~60.
  (This morning's setup, one cell with shadows, gave Motegi 8 fps at 45 M primitives.) Motegi's and Sebring's frozen
  pictures stay brighter than the game's: the frozen close-up of the black RSX, the game's exposure still lagging from
  the shot before (the test's freeze timing), not today's changes.
- **Lightmap atlas in the track export (fm3_track_export.py atlas_lightmaps, on by default, --no-lm-atlas off):** the
  groups were split by their lightmap texture; the lightmaps whose parts keep their UVs in 0..1 (+-0.01, clamped) are
  packed into 4096-wide pages (lmpage_NN.png, 4 px of their own edge around each) and the groups that then differ only
  by page merge. RoadAtlanta: 1,502 of 2,109 lightmaps in 5 pages, meshes 4,569 -> 2,748; the viewer alone (no crowd,
  600 frames) 136 -> 188 fps, 5,943 -> 1,949 draw calls; the same view from both exports differs by 0.5 levels
  (filtering at the padded edges). All tracks rebuilt with it the same evening (CrownJewel -Ribbon 04, the others
  their default layout; Amalfi not in this game folder, unchanged).

