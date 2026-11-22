# LIVE: running the game into Godot (ARCHITECTURE.md M5, the live loop)

Three stages, each usable on its own:

| Stage | What | State |
|---|---|---|
| **A, live mirror** | FM3 runs as normal through ReGPU and streams its camera; Godot draws the same view from the scene built from the game files | **camera done 2026-11-23**; cars next |
| B, takeover | ReGPU skips what Godot draws (track first, then cars) and draws the HUD and the rest into a layer Godot composites | not started |
| C, speed | measure against ReGPU's triple-screen frame (M6) | not started |

## Stage A: how to run it

1. Build the scene once: `tools\rebuild_ladera.ps1` (HANDOFF.md section 5) makes `out\world\ladera.gltf`.
2. Start FM3 with the stream on: from the FM3 repo, `$env:FM3_LIVE='1'; .\play.cmd` (or in a running game:
   `Fm3 "env FM3_LIVE 1"` after dot-sourcing `tools\fm3ctl.ps1`). The log says `live: camera stream to 127.0.0.1:7342`.
3. `frame-ir\live.cmd` (from the Godot folder: `& '.\frame-ir\live.cmd'`). Tab = the next camera director (the
   player view, the rear-view mirror), Esc quits. Creating `out\world\live.png.shot` saves the next frame to
   `out\world\live.png`.

Only the Ladera layout `Ribbon_04` has its props, and the cars are still the grid capture's (they stay where the
capture put them): drive away from the grid and they do not follow yet.

## The stream

`FM3_LIVE=1 | <port> | <ipv4>:<port>` (default 127.0.0.1:7342; read twice a second, so it switches live). FM3's camera
hand-off `sub_821E9B50` (r3 = the presentation view, +4 its camera director) sends one UDP datagram per hand-off,
about 360 a second at the 360 fps cap: `src/hooks/live_camera.cpp` in the FM3 repo (96 bytes, layout at the top of
that file): the director's view matrix (+0xD0: world to camera, row vectors, left-handed), vertical field of view
(+0x110, radians) and active camera vtable. Nothing in the game changes; non-blocking send, nobody listening costs
nothing.

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

Pictures: produced by a scratch script (game shot via `Save-Fm3Shot`, Godot via the `.shot` trigger); rerun the same
way to compare.

## Next for stage A

1. **Cars live**: each car's world transform per frame. Candidates: the game's car objects (a hook beside the
   camera's: car index, position, orientation), or the per-draw object matrices ReGPU already sees (fir_world.py
   recovers them offline from the vertex constants). Then `world_view.gd` moves the matching glTF car nodes.
2. The player car's interior parts (gauges, driver) for the in-car views.
3. Props for the other layouts (another `.pvs`), other tracks.
