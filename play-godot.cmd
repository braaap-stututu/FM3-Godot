@echo off
rem Starts FM3 and the Godot viewer together, with stage B on (LIVE.md "Stage B", 2026-11-27): the game draws its menus
rem (shown in the Godot window), Godot draws the races. Stage B and the live stream are switched on for this run only
rem (no settings.ini change). Extra arguments go to live.cmd (e.g. --size 2560x1440).
rem Needs the FM3 build beside this folder: ..\..\FM3-ReGPU recomp\build\rel\fm3.exe.
setlocal
set "ROOT=%~dp0"
set "FM3=%ROOT%..\..\FM3-ReGPU recomp"
tasklist /fi "imagename eq fm3.exe" 2>nul | find /i "fm3.exe" >nul
if not errorlevel 1 (
    echo FM3 is already running: close it first.
    pause
    exit /b 1
)
if not exist "%FM3%\play.cmd" (
    echo The FM3 build was not found at "%FM3%".
    pause
    exit /b 1
)
set "FM3_LIVE=1"
set "FM3_STAGE_B=1"
call "%FM3%\play.cmd"
start "FM3 Godot viewer" cmd /c ""%ROOT%live.cmd" %*"
