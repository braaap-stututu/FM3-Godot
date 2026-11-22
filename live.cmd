@echo off
rem Live mirror (stage A, LIVE.md): the Ladera scene in Godot, following the running FM3's camera.
rem Start FM3 with the camera stream on, e.g. in PowerShell from the FM3 repo:  $env:FM3_LIVE='1'; .\play.cmd
rem (or switch it on in a running game: Fm3 "env FM3_LIVE 1"). Tab = next camera (player view, mirror), Esc quits.
rem Extra arguments go to world_view.gd (e.g. --triple godot\bench\g1\layout_auto.json, --size 2560x1440).
set ROOT=%~dp0
"%ROOT%..\Godot_v4.7.2-stable_win64.exe" --path "%ROOT%godot" -s res://viewer/world_view.gd -- --gltf "%ROOT%out\world\ladera.gltf" --out "%ROOT%out\world\live.png" --size 1920x1080 --lit --live 7342 %*
