# PLAN-NEXT: the continuation plan (written 2026-11-26 night)

The user's list of 2026-11-26 ~22:50 (to do until 01:30, then a plan for the rest), in their order, with what was done
that night and what is left. Each item says where to start, the files involved and how to measure it. LIVE.md has the
details of everything done; HANDOFF.md the overall state.

## 1. The cubemap (done for the paint; finish for the other shaders)

Done: the AI cars' paint reflects the per-frame (live) cube (`FM3_AI_LIVE=0` = the static cube). Found by drawing the
game's t7 as panoramas through the shader's own CubeOp lookup (`tools/research/gridterms.ps1` mode 22): on the grid
the AI's "static" slot holds a near-field dynamic cube, not the track's static car cube. Eclipse paint 13.1 -> 11.3.
Left:
- The rebuilt panorama looks vertically inverted against the GL-convention reading of our faces: check which cube the
  game binds there (a capture: t7's address against the player's t6 / the static cube's), and whether every AI car
  reflects the same cube (one shared per-frame cube from the player's position?) or its own.
- The AI paint uses the live dampener (0.3); the game's AI path multiplies by StaticEnvLightmapDampner (0.5): try.
- The same for AI glass, lamps, lenses (`fm3_carglass`, `fm3_lamp_game`, `fm3_lensrefl` read the static cube with
  env_flip (-1, 1, 1)): give them the live cube where the game does (check each shader's bool for t6 / t7).
- Where the static cube is really used (menus? other tracks' AI?): the orientation test (mode 22 + scratch
  `cubefit.py`-style per-face matching) once a frame is found that binds it.

## 2. Animated 3D crowd, pit crew, marshals, photographers

Found: all in `Media\Spectators\` (FM3-files): `spectators.xml` (models, textures, sprite cells), 31 skinned models
`models\<Name>_{Sit,Stand}.skinbin` (Adam ... Stephanie, plus Marshall_Stand, Photographer_Stand, Pitworker_Stand),
29 animations `anims\{Sit,Stand}_{Cheer,Idle}_NN.anim.bin`, `sprites.xds` (the far crowd's sprites, already used),
`shadow.dds`.
- `.skinbin` (first look, Pitworker_Stand, 94,936 bytes, big-endian): a header of 7 (start, count) u16 pairs after two
  (1, 7) words (sub-meshes or LODs: 0x0fc6/0x08e2, 0x18a8/0x0540, 0x1de8/0x01d4, 0x1fbc/0x0102, 0x20be/0x0075,
  0x2133/0x0027), then 0x870 = 2160 vertices of 36 bytes: u32 1, position 3 x f32, normal 3 x f32, 4 bytes (packed UV?),
  4 bytes bone indices / weights (`06 00 ff 00` = bone 6 at 255). Then the index lists and presumably the skeleton.
- `.anim.bin` is CAFF (the container `fm3_tex.py` already reads): one `.data` section (0x9958 bytes for Stand_Idle_01).
Steps: (1) `tools/fm3_skinbin.py`: vertices, indices, bones -> glTF with a Skeleton (check against a frame capture of
the crowd: the captured skinned draws' vertex shader has the bone palette); (2) the anim CAFF: tracks per bone
(rotation quaternions, maybe compressed), frame rate; (3) Godot: the crowd's people (`.crowd` cells, already placed
as captured / sprite silhouettes) as instanced skinned meshes; for thousands of people bake the animations into
vertex-animation textures and draw with MultiMesh; (4) where pit crew / marshals / photographers stand: probably
`CollObjs.xml` / the `.crowd` file's types per person (check a pit-lane frame).

## 3. The driver (first person) and its animations

Found: `Media\Cars\Driver\`: `Driver.skinbin` (hands and arms, the same skinbin format as the crowd), `Driver.xds`,
and Granny 3D files (`.gr2`, magic 29de6cc0..., little-endian 32-bit, file format 7): `DriverLOD0.gr2` (2.1 MB: the
skeleton + mesh), `Hands.gr2`, `FlexFingers.gr2`, `Lateral.gr2` / `Longitudinal.gr2` (body sway), `SteerLock2Lock*`
(Large / Small, _B, _ROT: steering animations sampled by the wheel angle), `RotatingPaddleShift*`,
`ShiftStick*Console*` (gear changes), plus `driver.anim.bin` (CAFF). `Media\DriverHands\` too.
Steps: read the gr2 files (Norbyte's LSLib or opengr2 read Granny 2; sections may be Oodle-0/1 compressed), export
skeleton + animations to glTF; in the viewer drive them from the stream: steering (FM3E v2 steer x lock: pick the
SteerLock2Lock frame), gear changes (FM3E gear: paddle or stick by the car's type), lateral / longitudinal sway from
the car-frame acceleration (FM3E v8). Seat position: the cockpit model's driver anchor (find in `_cockpit.carbin`).

## 4. The biggest remaining differences (measured, 2026-11-26)

- RoadAtlanta's exposure: the game's adapted L sits ~0.13 above its scene mean there (Sebring, Motegi, CrownJewel:
  no offset); our scene matches the game's within 2%. Next: which buffer the luminance pass averages (capture).
- The HUD (top corners, speedometer) in every game picture: the game's own HUD in ours would remove ~1-2 of the frame's
  difference (see 5).
- Paint reflections' contrast (the player's roof: our live cube's content softer than the game's).
- The distant pit buildings / flags / crowd (CrownJewel), kerb stripes' brightness.
- AI paint 13.3 / player 11.3 / parts ~13 on the CrownJewel grid; the cars' highlights on the SH-lit parts (spec 0).

## 5. HUD (v1 done, customizable)

`godot/viewer/fm3_hud.gd` + `hud_default.json`: tach with redline and gear, speed, throttle / brake bars, a track map
that builds itself from the player's path with a dot per car; each element's anchor / offset / scale / on-off, units
(kmh / mph) in `user://fm3_hud.json` (or `FM3_HUD_CONFIG=<path>`); H toggles; `FM3_HUD=0` off (the test scripts set it).
Left: race position, lap counter and lap times (find them in the game's race object and add to the FM3E stream);
the game's own HUD look (its textures and fonts are in `Media\UI*` / the executable's Scaleform-like UI files: find
them, then draw the same gauges); a small in-viewer editor (drag elements, save the JSON).

## 6. Front end (menus' scenes: lighting and locations)

The menus' 3D scenes are tracks in the game's files: `Media\Tracks\UILivery`, `UIThumBig`, `UIThumbnail`, `UITrack`,
`UIWhite`, `UIupgrades` (each with TrackSettings lighting, a .pvs layout, models, a static car cube; the static cube
is read x8 there). `tools/build_track.ps1 -Track UIWhite` builds them like any track (fixed that night: small texture
tables in `fm3_pvs.py`, empty mesh groups in `fm3_track_export.py`). Left: place a library car where the menu shows it
(the car's spot: the scene's camera / car transform from a capture of the menu), its turntable, and the menus'
cameras.

## 7. The game and its menus, integrated (kept separate)

Not started. Options: (a) the viewer shows the game's own frame (ReGPU's final picture) as a texture while the game is
in a menu, switching to its own rendering on the track (needs a frame-sharing path from ReGPU: a shared D3D12 / Vulkan
texture, or the existing screenshot path at lower rate); (b) rebuild the menus' 2D UI in Godot from the game's UI
files (large). (a) first: it keeps the game's menus exactly as they are.

## 8. Telemetry still missing

Slip ratio / angle (FH1's per-wheel +496 / +520 in its 1024-byte blocks: look at FM3's 1040-byte blocks +496..+540),
friction %, camber, tyre pressure (+188 of the wheel block, cold 30 psi) and wear, clutch / handbrake (+3420 / +3424
candidates), race position and laps (for the HUD).
