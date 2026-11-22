@echo off
rem Free-fly through the captured FM3 grid frame in Godot (frame-ir\out\world\grid.gltf, made by tools\fir_world.py --gltf).
rem WASD move, Q/E down/up, hold right mouse to look, Shift fast, Ctrl slow, Esc quits.
rem Add --triple godot\bench\g1\layout_auto.json (with a triple capture's glTF) for three screens.
set ROOT=%~dp0
"%ROOT%..\Godot_v4.7.2-stable_win64.exe" --path "%ROOT%godot" -s res://viewer/world_view.gd -- --gltf "%ROOT%out\world\grid.gltf" --out "%ROOT%out\world\fly.png" --size 1920x1080 --lit --fly %*
