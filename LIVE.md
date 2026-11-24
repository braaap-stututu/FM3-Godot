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
| RB twice (in-car) | 103.92, -1.75, 222.21, fov 45 | 37.6 / 38.6 / 37.5 | geometry lines up exactly; the rest is the HUD, the CR-X's gauges and the driver's hands (not in the carbin parts used), the mirror's picture and darker cabin light |

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
   library wheels / calipers: **20.4 / 20.2 / 18.5**; the crowd from the .crowd files (FM3-FORMATS) 20.4 / 20.1 / 18.5. live_compare's picture waits (up to 10 s) for the library cars. Open: the player's
   custom paint (the livery layer: the car object holds only the database colour, +0x9A0 etc.,
   `FM3_LIVE_DUMP_CARS=1`), crowd sprites, the sky dome's seam line, the sea's colour.
6. Then stage B: ReGPU skips what Godot draws.
