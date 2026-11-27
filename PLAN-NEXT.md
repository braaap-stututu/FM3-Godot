# PLAN-NEXT: the continuation plan (written 2026-11-26 night)

The user's list of 2026-11-26 ~22:50 (to do until 01:30, then a plan for the rest), in their order, with what was done
that night and what is left. Each item says where to start, the files involved and how to measure it. LIVE.md has the
details of everything done; HANDOFF.md the overall state. Updated 2026-11-27 ~01:05 (the in-car fixes: 4).

**Suggested order (by value against the game and how far each is):** (a) done 2026-11-27: the HUD's race values; (b) the crowd's animations (2: the decoder is located);
(c) the driver's hands (3: dump the Granny files through the recomp); (d) done 2026-11-27: RoadAtlanta's exposure;
(e) done: lamps / lenses on the live cube; (f) slip telemetry (8); (g) the menus (6, 7). Ask the user which first.

## 0. The user's list of 2026-11-27 ~14:09 (work until midnight; LIVE.md "The user's notes of 2026-11-27 evening")

Status 2026-11-27 ~22:15: everything on the list has been worked on (HANDOFF top: the summary). Left from it: the
in-car driver's animations (Granny, Oodle1), the crowd's cheers as cars pass, tyre smoke / skid marks / sparks (the
game draws them in its skipped world steps: stage B shows none), the slip telemetry, the live cube's own shadow
draws. The older items below are updated where done (2, 3).

## 1. The cubemap (done for the paint; finish for the other shaders)

Done: the AI cars' paint reflects the per-frame (live) cube (`FM3_AI_LIVE=0` = the static cube). Found by drawing the
game's t7 as panoramas through the shader's own CubeOp lookup (`tools/research/gridterms.ps1` mode 22): on the grid
the AI's "static" slot holds a near-field dynamic cube, not the track's static car cube. Eclipse paint 13.1 -> 11.3.
Left (the AI dampener is done: the game's StaticEnvLightmapDampner 0.5 for AI paint, 13.28 -> 13.10):
- The rebuilt panorama looks vertically inverted against the GL-convention reading of our faces: check which cube the
  game binds there (a capture: t7's address against the player's t6 / the static cube's), and whether every AI car
  reflects the same cube (one shared per-frame cube from the player's position?) or its own.
- AI windows: done (the live cube, `FM3_AI_LIVE_GLASS=0` = before; their sky blue, 27.5 -> 19.3 on the windows).
  Lamps and lenses: done 2026-11-27 (the live cube: lamps 15.53 -> 10.87, lenses 18.93 -> 12.25). Left: `fm3_lensrefl`
  (the old lens chain, off by default) still reads the static cube.
- Where the static cube is really used (menus? other tracks' AI?): the orientation test (mode 22 + scratch
  `cubefit.py`-style per-face matching) once a frame is found that binds it.

## 2. Animated 3D crowd, pit crew, marshals, photographers

**Done 2026-11-27 evening:** the people are animated with the game's own baked animations (decoded from its crowd
buffer; LIVE.md "The crowd's animations") and drawn by crowd class (seated / standing / photographer / marshal / pit
worker; LIVE.md "The crowd's classes"). Left: cheers when cars pass, the game's idle choice per person, the crowd's
shading. The notes below are the research that led there.

**Done that night, static:** the crowd is drawn with the game's own 3D people (seated pose, real textures; LIVE.md
"The 3D crowd, static"; CrownJewel grid 14.36 -> 14.01). Left: the animations below, the crowd's shading (TrackSettings
Crowds dark / light), the far sprites, standing crowds, pit crew / marshals / photographers' placement.

Found: all in `Media\Spectators\` (FM3-files): `spectators.xml` (models, textures, sprite cells), 31 skinned models
`models\<Name>_{Sit,Stand}.skinbin` (Adam ... Stephanie, plus Marshall_Stand, Photographer_Stand, Pitworker_Stand),
29 animations `anims\{Sit,Stand}_{Cheer,Idle}_NN.anim.bin`, `sprites.xds` (the far crowd's sprites, already used),
`shadow.dds`.
- `.skinbin` (first look, Pitworker_Stand, 94,936 bytes, big-endian): a header of 7 (start, count) u16 pairs after two
  (1, 7) words (sub-meshes or LODs: 0x0fc6/0x08e2, 0x18a8/0x0540, 0x1de8/0x01d4, 0x1fbc/0x0102, 0x20be/0x0075,
  0x2133/0x0027), then 0x870 = 2160 vertices of 36 bytes: u32 1, position 3 x f32, normal 3 x f32, 4 bytes (packed UV?),
  4 bytes bone indices / weights (`06 00 ff 00` = bone 6 at 255). Then the index lists and presumably the skeleton.
- `.skinbin` decoded further the same night: big-endian; header words (1, 7) (1, 7) (1, 0xfc6), then 7 (start, count)
  u16 pairs = **7 LODs** over one index list (4038 / 2274 / 1344 / 468 / 258 / 117 / 39 indices, triangle lists; sum
  8538), at 0x50 the vertex count (2160) and at 0x54 the vertices, 36 bytes: u32 1, position 3 x f32 (model space, bind
  pose: a 1.84 m person, feet at y 0), normal 3 x f32, UV 2 x s16 (full range: scale to check against the texture),
  bone index 0, bone index 1 (0-16: **17 bones**), weight 0, weight 1 (u8, summing to 255). Then u32 1, u32 index count,
  the u16 indices, and two trailing words (vertex count, index count). **No skeleton in the model.**
- `.anim.bin`: CAFF, one `.data` section holding an `animation` record ('animation\0' '00.00.00.0036'): 17 bones (0x11),
  150 frames (0x96), duration 4.966 s (30 fps), compression **'QUAT_BITSTREAM'** (rotations as a packed bitstream),
  a float 1.0, offsets to per-bone data; at the end the bone names with each 4-byte word byte-swapped
  ('R_enoRgelppu_' -> '...Bone_R_UpperLeg...'). The bind pose (bone positions) must come from here too.
  **The game's decoder, found:** the string is at image offset 0xC1F380 of the recomp's decrypted image
  (`FM3-ReGPU recomp/out/fm3.bin`), followed by its codec table: 0x82AABED0 (sample at a time: f1 = time),
  0x82AABE78 and 0x82AABEB0 (setup / decode with r5 = 0 / 1). Their work is in `sub_82AAE048` (176 lines of the
  recompiled C++, `out/ppc-rexenon/ppc_recomp.144.cpp`), `sub_82AADFC8` (77), `sub_82AAD858` (287), `sub_82AADA30`
  (827, calls `sub_82AAD690` x6, `sub_825303A0`, `sub_82A06898`). Port those to Python (`tools/fm3_anim.py`), check by
  decoding Stand_Idle_01 and comparing a bone's rotation against a live dump (the debug server's `peek` on a
  spectator's bone palette), then export glTF animations.
**Found 2026-11-27 ~17:15 (the animation path):** at the CrownJewel grid the game's crowd is **static sprite cards**
(36 rect-list draws, vs 4c93e5152da49ff7, the 2048 x 1024 'crowds' sheet, one 1/32 x 1/8 cell per card; two captures
2 s apart with the world running differ only in the camera constants). The 3D people are a near LOD. The race load
samples every animation of the loaded crowd class through the codec sub_82AABED0 (21 calls of 17-track instances at
~12.6 s; the old log kept only 8 animations, so it missed them): on CrownJewel only the **standing** set (Stand_Idle_01..10
without 02, _Drunk, _Photo, Stand_Cheer_01..11 without 07; spectators.xml crowd classes Sitting / Standing / Drunk /
Photographer / Marshall / PitWorker, each with idle and cheer lists). The instance's own data is at +0x00 (A-range
physical mirror; +0x0C is shared); FM3-ReGPU `anim_dump.cpp` (FM3_ANIM_DUMP=1) now dumps each over its full length
(frames at record +34, durations 2.7-30.4 s) to out/run/anim_dump; copies in `Godot/work/crowd_anim` (game data, not
committed); matched to files by (duration, frames) at record +28 / +34. **The samples are per-bone rotations relative to
the bind pose** (quaternion, translation always 0, scale 1; t = 0 often identity): idles move 0-10 degrees (Stand_Idle_07
up to 41), cheers up to ~70, the photographer up to ~100 (corrected ~19:00: the codec's time is normalized 0..1, the first dumps sampled past 1 and
extrapolated; re-dumped: idles 0-5 degrees, cheers 10-22, the photographer's arms 73 / 93, each loops). **Left: the skeleton** (not in the .skinbin): parents from the
bone names (byte-swapped words at the anim file's end: spine, head, shoulders, upper / lower arm, hand, upper / lower
leg, foot, L / R) or from the models' shared bone weights, joint pivots from the vertices two bones share, and whether
the rotations are in model axes (check on Stand_Idle_Photo: the camera raised to the face). Done since: the hierarchy
from the names and pivots from shared weights (`tools/research/crowd_skeleton.py`: hips 0.93 m, knees 0.54, shoulders
~1.45, wrists 0.94 on Photographer_Stand); posing on CPU (`crowd_pose.py`) with rotations about those pivots in model
axes did not bring the camera to the face with either quaternion convention: the bones' bind frames are still unknown
(next: the skinned crowd draw's bone palette in a capture near a photographer, i.e. the game's final matrices). Then glTF skins +
animations in fm3_spectators.py and the standing people where the game uses them (where its 3D LOD shows them).
Steps: (1) `tools/fm3_skinbin.py`: vertices, indices, bones -> glTF with a Skeleton (check against a frame capture of
the crowd: the captured skinned draws' vertex shader has the bone palette); (2) the anim CAFF: tracks per bone
(rotation quaternions, maybe compressed), frame rate; (3) Godot: the crowd's people (`.crowd` cells, already placed
as captured / sprite silhouettes) as instanced skinned meshes; for thousands of people bake the animations into
vertex-animation textures and draw with MultiMesh; (4) where pit crew / marshals / photographers stand: probably
`CollObjs.xml` / the `.crowd` file's types per person (check a pit-lane frame).

## 3. The driver (first person) and its animations

**Done 2026-11-27 evening (static):** the arms and hands from Driver.skinbin on each car's wheel grips (carbin
anchors), the hands turning with the wheel (LIVE.md "The in-car driver"). Left: the arms' animations (below).

Found: `Media\Cars\Driver\`: `Driver.skinbin` (hands and arms, the same skinbin format as the crowd), `Driver.xds`,
and Granny 3D files (`.gr2`, magic 29de6cc0..., little-endian 32-bit, file format 7): `DriverLOD0.gr2` (2.1 MB: the
skeleton + mesh), `Hands.gr2`, `FlexFingers.gr2`, `Lateral.gr2` / `Longitudinal.gr2` (body sway), `SteerLock2Lock*`
(Large / Small, _B, _ROT: steering animations sampled by the wheel angle), `RotatingPaddleShift*`,
`ShiftStick*Console*` (gear changes), plus `driver.anim.bin` (CAFF). `Media\DriverHands\` too.
Checked that night: every driver .gr2 is Granny file format 7 with its sections compressed by **Oodle1** (compression
type 2; one 1.66 MB section stored plain in DriverLOD0 / Hands): open readers rarely do Oodle1. Easiest route: let the
recomp decompress them (the game's own Granny runtime does at load: hook its section decompressor / GrannyReadEntireFile
and dump the decompressed file), then read the plain GR2 with a documented layout (opengr2 / LSLib). Then: export
skeleton + animations to glTF; in the viewer drive them from the stream: steering (FM3E v2 steer x lock: pick the
SteerLock2Lock frame), gear changes (FM3E gear: paddle or stick by the car's type), lateral / longitudinal sway from
the car-frame acceleration (FM3E v8). Seat position: the cockpit model's driver anchor (find in `_cockpit.carbin`).

## 4. The biggest remaining differences (measured, 2026-11-26 / 27)

CrownJewel grid whole frame 13.92-14.12 (boots vary ~0.2), in-car (live_compare cam3) 19.3 / 18.8 / 17.0.
- In-car: our dash a little darker than the game's (`FM3_COCKPIT_GAIN` for tests: the cockpit shader's light was
  fitted with the old x1.5 in-car exposure, now 1.0), the driver's hands (3), the HUD.
- Done 2026-11-27: RoadAtlanta's exposure. No offset in the game: our W probe ignored the curve's black point
  (RoadAtlanta's alone is nonzero; `tools/research/wsolve.py` now), and the viewer measured L after its exposure pass,
  where the brights are clipped; it now measures the scene before it (a small view of the same world). RoadAtlanta's
  grid 22.9 -> 17.9; LIVE.md has the chain decoded tap by tap.
- The HUD (top corners, speedometer) in every game picture: ~31% of the grid's remaining difference; ours, in the
  game's layout, could be switched on in the comparisons once it shows the real race values (see 5).
- The crowd: static now (2); its animation, the game's dark / light crowd shading (x0.7 fitted), pose / second index.
- Paint reflections' contrast (the player's roof: our live cube's content softer than the game's).
- The distant pit buildings / flags / crowd (CrownJewel), kerb stripes' brightness.
- AI paint 13.3 / player 11.3 / parts ~13 on the CrownJewel grid; the cars' highlights on the SH-lit parts (spec 0).

## 5. HUD (v1 done, customizable)

`godot/viewer/fm3_hud.gd` + `hud_default.json`: tach with redline and gear, speed, throttle / brake bars, a track map
that builds itself from the player's path with a dot per car; each element's anchor / offset / scale / on-off, units
(kmh / mph) in `user://fm3_hud.json` (or `FM3_HUD_CONFIG=<path>`); H toggles; `FM3_HUD=0` off (the test scripts set it).
Done later that night: style "game" (the default) draws the game's own layout, measured from its picture (place
panel top left, laps + lap time top right, the round tach bottom right: 0-10 over 222 degrees clockwise from straight
down, red from the redline, gear, km/h; the map bottom left with a green arrow); style "simple" keeps the free-placed
elements. The HUD is ~31% of the CrownJewel grid's remaining difference, so with real race values it could also be
switched on in the comparisons.
**Done 2026-11-27:** race time, place, laps and last / best / lap times from the game (FM3E v9; LIVE.md "HUD race data"),
checked against the game's HUD to a few ms. Left: the race's lap total, a lap counter for a viewer started mid-race,
and switching the HUD on in the comparisons. Measured 2026-11-27 (CrownJewel, ours on against the game's own): grid
13.9 / chase 14.6 / in-car 17.9 against 14.0 / 14.5 / 17.6 with ours off: within boot noise, so our HUD neither closes
nor widens the gap yet. Seen side by side on the grid: the race time (fixed: held at 0 until the start, the physics
clock runs through the countdown), the lap total ("/-" against "/3"), no minimap on a fresh start (ours is drawn from the
cars' driven path; since 2026-11-27 a whole lap's path is kept in `user://fm3_map_<track>.json` and drawn from the
next start on; the game's own line data `.seg` / `.irt` / `.geo` would give it at once: not decoded), no opponent name tags (the game's red names over the cars ahead), and the tach's style (redrawn
2026-11-27 to the game's shapes: segmented band, fuel arc and pump, small dark centre, short needle; the fuel level
is not streamed: the arc is drawn full). **But the game draws it from its own textures** (found after the user asked,
2026-11-27): the race HUD is the UI scene `Media/UI/scenes/ui4/947_hud.{bgf,bsg,fbf}` (Anark: AnarkBGF), whose .fbf
names `I_Map/I_HUD/I_HUD_Tach_BKG` (the dial's body, 241 x 187), `I_HUD_Tach_RED` (the redline arc, 180 x 180),
`I_HUD_Tach_Needle`, `I_HUD_ICON_Fuel`, `I_HUD_Fuel_Level`, the panels `I_HUD_LapAndPlace_bkgd` /
`I_HUD_RaceTime_{top,mid,btm}_bkgd`, and more (`tools/fm3_hud_textures.py` exports all 81 to out/hud_tex; the needle
decodes with alpha 0: check its format). **Next for the HUD:** draw ours from these textures, the layout read from
947_hud (element names in the .bgf: GAUGE_ANALOG.RPM_ANALOG, FUEL_ANALOG, TEXT_GEAR_ANALOG, Elements.RPM and
MPH.Redline, I_HUD_MiniMap with CUSTREND_MINIMAP = the map is a custom render; the format is not decoded), until
then positions fitted on the game's shots. The fonts are named there too (helvetica63-extendedmedium,
helvetica67-condensedmedium: `Media/UI/Fonts/*.dt`). (The old route, for reference: the HUD's own code reads them; the tach's rpm getter is called
for the HUD from 0x821F2044 (`FM3-ReGPU recomp/src/hooks/live_camera.cpp` notes), so the HUD update function around
that return address also fetches position / lap / lap time: read it in `out/ppc-rexenon` and follow its other getters
to the race object, then stream them in FM3E. (Searching the image for the time format: `%02d.%03d` is at image offset
0x12E708, but image offsets do not map linearly to guest addresses: get the section map from the xex before turning
offsets into addresses.)
Also tried: `tools/research/carobjdump.ps1` (dumps a car object over a race): no car object holds the physics
object's address directly, so the first car was dumped (maybe not the player's): no clean timer or lap counter. The
physics object does hold a clock: **+2704 rises exactly 1 s per second** (18.8 -> 39.3 s over a run; copies per wheel
at +3472 + 1040 i): with the start-line crossing (or the race start) it gives lap times. The HUD function is
`sub_821F19A8` (1710 lines of the recompiled code, ~40 callees; `out/ppc-rexenon/ppc_recomp.1.cpp`).)
the game's own HUD look (its textures and fonts are in `Media\UI*` / the executable's Scaleform-like UI files: find
them, then draw the same gauges); a small in-viewer editor (drag elements, save the JSON).

## 6. Front end (menus' scenes: lighting and locations)

The menus' 3D scenes are tracks in the game's files: `Media\Tracks\UILivery`, `UIThumBig`, `UIThumbnail`, `UITrack`,
`UIWhite`, `UIupgrades` (each with TrackSettings lighting, a .pvs layout, models, a static car cube; the static cube
is read x8 there). `tools/build_track.ps1 -Track UIWhite` builds them like any track (fixed that night: small texture
tables in `fm3_pvs.py`, empty mesh groups in `fm3_track_export.py`). Rendered from (6, 2.2, 6) both come out flat dark
grey: the scenes are small (a floor, a backdrop line, the sky dome) and need the menus' exposure (their static cube is
read x8 there: the menus run at another light scale). Left: their exposure / light scale, place a library car where
the menu shows it
(the car's spot: the scene's camera / car transform from a capture of the menu), its turntable, and the menus'
cameras.

## 7. The game and its menus, integrated (kept separate)

**Started 2026-11-27 with stage B (LIVE.md "Stage B"):** option (a) below is built: ReGPU's frame feed brings the
game's frames into the viewer's window while the game is in its menus; the viewer draws the race. Next: the viewer
loads the track the game loads (from the game's file opens), the race's own menus over the viewer (the game's frame
keyed on its flat grey), then the menus' 3D scenes (6).
Before: Options: (a) the viewer shows the game's own frame (ReGPU's final picture) as a texture while the game is
in a menu, switching to its own rendering on the track (needs a frame-sharing path from ReGPU: a shared D3D12 / Vulkan
texture, or the existing screenshot path at lower rate); (b) rebuild the menus' 2D UI in Godot from the game's UI
files (large). (a) first: it keeps the game's menus exactly as they are.

## 8. Telemetry still missing

Tried that night (`tools/research/physdump.ps1`: the AI driving; `physdrive.ps1`: the debug pad's throttle, brake and
full steering lock, 2084 dumps of the 8 KB physics object; analysis like scratch `slipfind2.py`): the slip computed
from the +2792 car speed and the +4164 wheel speeds stays ~0 even at a full-throttle launch (traction control, or
+4164 is not the wheel's rotation speed), so it cannot identify the field. Candidates by behaviour (wheel block i at
+1040 i): **+4172 lateral** (0 driving straight, 1.7 -> 3.8 front-left and -1.5 -> -7.5 rear-right at full lock at
16 m/s: a slip angle in degrees or a lateral force, sign by side / axle), **+3444 longitudinal** (-0.24 at full
throttle, +0.40 braking hard), **+4176** (rises through braking 0.11 -> 0.49). Settle them with the game's telemetry
FRICTION page beside the same dumps (`telepage.ps1`-style shots while `physdrive.ps1`'s inputs run). The body matrix
was not found as three orthonormal rows between +2300 and +2800 (needed for the car's own slip angle).

Slip ratio / angle (FH1's per-wheel +496 / +520 in its 1024-byte blocks: look at FM3's 1040-byte blocks +496..+540),
friction %, camber, tyre pressure (+188 of the wheel block, cold 30 psi) and wear, clutch / handbrake (+3420 / +3424
candidates), race position and laps (for the HUD).
