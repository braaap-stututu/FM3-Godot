@echo off
rem Free-fly the whole Ladera track from FM3's own files (frame-ir\out\world\ladera.gltf, made by
rem tools\fm3_track_export.py <extracted CrownJewel bin.zip> out\world\ladera.gltf --camera-from out\world\grid.gltf).
rem WASD move, Q/E down/up, hold right mouse to look, Shift fast, Ctrl slow, Esc quits.
set ROOT=%~dp0
"%ROOT%..\Godot_v4.7.2-stable_win64.exe" --path "%ROOT%godot" -s res://viewer/world_view.gd -- --gltf "%ROOT%out\world\ladera.gltf" --out "%ROOT%out\world\fly.png" --size 1920x1080 --lit --fly %*
