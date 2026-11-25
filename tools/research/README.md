# tools/research: the 2026-11-24/25 night's working scripts (other tracks, shaders, exposure)

Kept as written during the session (not polished): they write to a temporary folder (`$sp` / the first argument), which
you can point anywhere. Run from `frame-ir` (Python ones import `tools/`). LIVE.md "Other tracks" has the findings.

| Script | What it does |
|---|---|
| `survey.ps1 [-Only A,B] [-NoBuild]` | rebuilds each track (`build_track.ps1`) and runs `tools/live/live_track.ps1` on it; one line per track to `survey.log`. ~10 min a track |
| `idat.ps1 -Track <name> -Points "x,y;..."` | renders a track offline from its last live camera (`out/live/tracks/<name>-godot.log`), lit and as material ids, and names the material under each point |
| `capconsts.ps1 [-Index N] [-Name n]` | boots FM3 to Free Play environment N (`REGPU_NO_PACKED_CONSTANTS=1`), freezes in the countdown and saves a debug-server capture (every draw with its constants) |
| `expo.ps1` | as capconsts, with `REGPU_TRACE_VC=1` (vertex constants) and `hlsl` dumps of the post-process shaders (exposure / bloom) into the recomp's `out/run/out/hlsl` |
| `cubecmp.ps1 [-Index N] -Gltf <abs>` | the game's car reflection cube against the viewer's live cube: a capture (resolve dumps) plus the viewer's six faces (`FM3_DUMP_LIVE_CUBE=1`), same frozen moment |
| `paintdbg.ps1 [-Index N] -Gltf <abs> [-Modes 0,1,2,3]` | the paint's reflection terms one at a time: the game's paint ps edited live, the viewer with `FM3_PAINT_DEBUG` |
| `lumpeek.ps1` | tries to read the adapted-luminance 32x32 texture from guest memory (gave zeros: it stays on the GPU) |
| `gamshots.ps1` | game shots with and without the display gamma (`REGPU_NO_GAMMA`, `REGPU_NO_GAMMA_PWL`): the gamma table is a fixed toe curve |
| `roadprobe.py`, `roadfit.py` | road_3clr_blnd_2's shadowed variant run in `tools/fir_vs.py`: the road sun specular, probed input by input |
| `specgen.py` | the same probe for any road shader: which sampler's alpha masks the specular |
| `matscan.py <track dir> <names>` | material name -> shader, stride, parameters, slots |
| `norecipe.py` | multi-texture track shaders without a recipe in `fm3_families.py`, by mesh count |

Post-process shader code: pixel shaders are in the recomp's `out/user/static_shaders.bin` (records: u32 pixel, u32 dword
count, big-endian code), named by ReGPU's hash `FNV-1a-64(code bytes) ^ pixel`; vertex shaders via the debug server's
`hlsl <hash> <path>`. Disassemble with `tools/fir_disasm.disasm(struct.unpack('<%dI' % n, code))`.
