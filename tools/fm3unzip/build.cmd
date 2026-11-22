@echo off
rem Builds fm3unzip.exe with the FM3 recomp's toolchain (tools\vcenv.cmd) and its zip/LZX sources.
set FM3=G:\claude code projects\FM3-ReGPU recomp
call "%FM3%\tools\vcenv.cmd" clang-cl /nologo /O2 /EHsc /std:c++20 /I "%FM3%\src" "%~dp0fm3unzip.cpp" "%FM3%\src\zip.cpp" "%FM3%\src\lzx.cpp" /Fe"%~dp0fm3unzip.exe" /Fo"%~dp0\"
