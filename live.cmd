@echo off
rem Live mirror (LIVE.md): the CrownJewel scene in Godot, following the running FM3's camera and cars.
rem Start FM3 with the camera stream on, e.g. in PowerShell from the FM3 repo:  $env:FM3_LIVE='1'; .\play.cmd
rem (or switch it on in a running game: Fm3 "env FM3_LIVE 1"). Tab = next camera (player view, mirror), Esc quits.
rem Stage B (2026-11-27): with the launcher's "Godot renders races (stage B)" on (settings.ini stage_b=1), the game
rem stops drawing races itself and this window shows the game's own frames while it is in its menus, then draws the
rem race. It starts on CrownJewel's scene (out\world\crownjewel.gltf) and follows the track the game loads
rem (out\world\<track>.gltf, built by tools\build_track.ps1); to start on another track:
rem   live.cmd --gltf <abs path>\out\world\<track>.gltf   (the last --gltf wins)
rem Extra arguments go to world_view.gd (e.g. --triple godot\bench\g1\layout_auto.json, --size 2560x1440).
set ROOT=%~dp0
set SCENE=%ROOT%out\world\crownjewel.gltf
if not exist "%SCENE%" set SCENE=%ROOT%out\world\ladera.gltf
"%ROOT%..\Godot_v4.7.2-stable_win64.exe" --path "%ROOT%godot" -s res://viewer/world_view.gd -- --gltf "%SCENE%" --out "%ROOT%out\world\live.png" --size 1920x1080 --lit --live 7342 %*
