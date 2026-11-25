@echo off
rem Builds fm3unzip.exe with the FM3 recomp's toolchain (tools\vcenv.cmd) and its zip reader, with this folder's
rem lzx_fixed.cpp (the recomp's src\lzx.cpp + one fix, 2026-11-25: an odd-length uncompressed LZX block that spans
rem chunks has no pad byte; the recomp's decoder failed on 2 of the game's 193,042 zip members).
for %%I in ("%~dp0..\..\..\..\FM3-ReGPU recomp") do set "FM3=%%~fI"
call "%FM3%\tools\vcenv.cmd" clang-cl /nologo /O2 /EHsc /std:c++20 /I "%FM3%\src" "%~dp0fm3unzip.cpp" "%FM3%\src\zip.cpp" "%~dp0lzx_fixed.cpp" /Fe"%~dp0fm3unzip.exe" /Fo"%~dp0\"
