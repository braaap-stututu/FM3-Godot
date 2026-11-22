# ReGPU changes

- `regpu-m0-switches.patch`: the M0 measuring switches (below). **Committed and pushed** on `vulkan` as 478adb8.
- `regpu-fir-tap-stage1.patch`: the M1 capture tap, stage 1 (`REGPU_FIR_CAPTURE`, `REGPU_FIR_ARM`, `REGPU_FIR_AT`,
  `REGPU_FIR_FRAMES`). Against `vulkan` 478adb8 (applies cleanly; compiles with FM3's flags). Also applied, uncommitted,
  in the FM3 checkout on 604dd2b. Design, records and results: [`../M1.md`](../M1.md). **Committed on `vulkan` as
  d828ed8 + d540cb0** (2026-11-22, not pushed); the patch file is both, against 478adb8.

# M0 switches

`regpu-m0-switches.patch`: the measuring switches the FM3 M0 plan needs, against
[braaap-stututu/ReGPU](https://github.com/braaap-stututu/ReGPU) branch `vulkan` at **604dd2b** (the commit FM3 main
pins). 72 lines added in `src/gpu/gpu.cpp` and `src/gpu/renderer.cpp`, LF line endings, nothing changes unless a switch
is set.

## What it adds

| M0 run | Switch | What it does |
|---|---|---|
| R6 No GPU work | `REGPU_NO_GPU_WORK=1` (**new**, start-time) | Every frame is recorded as usual, but nothing recorded reaches the GPU and nothing is presented. Queued command lists are submitted empty, so the queue's timeline and the frame fences still advance in order and nothing waits forever. The frame's end acquires no swap chain image. The light perf log's frame rate (counted at the swap, not the present) is then what the command processor, draw thread and replay thread reach without the GPU. |
| R7 No draw-thread work | `REGPU_NO_RENDER=1` (**already exists**, live) | `DrawImpl` returns at once for every draw, including the triple-screen replays: what remains is FM3, the command processor and the frame bookkeeping. |
| Per-screen draws | `REGPU_PERF_LITE=1` in triple mode (**new log line**) | Once a second: `triple: draws/frame: N centre and shared passes, N left, N right (N in all, N frames)`. Guest draws counted where they reach the draw thread (before any draw workers), so these are the game's draws, not host draw calls. "Centre and shared" includes the shadow, reflection and mirror passes drawn once before the main view. |

`REGPU_NO_GPU_WORK` also turns Hyper culling off (its sample counts would be stale, and it would cull everything).
Occlusion answers (the sun flare) and read-back pixels are stale, and the boot and loading screens' own presents may show
garbage. It is for measuring only.

## Applying it

In the ReGPU checkout FM3 builds against (`thirdparty/ReGPU`, or the ReGPU-V workspace):

```powershell
git -C thirdparty\ReGPU apply --check "G:\claude code projects\Godot\frame-ir\regpu\regpu-m0-switches.patch"
git -C thirdparty\ReGPU apply "G:\claude code projects\Godot\frame-ir\regpu\regpu-m0-switches.patch"
```

then rebuild FM3 as usual. To keep it, commit it on a branch of the ReGPU fork. It follows ReGPU's rules (a named
`REGPU_*` switch, off by default, explained in comments) and could stay as a permanent measuring switch.

## Running the M0 runs with it

All with `REGPU_PERF_LITE=1`, the grid method from NOTES (2026-11-21), and `FM3_TRIPLE=1` for the triple runs:

- R6: add `REGPU_NO_GPU_WORK=1`. The window freezes on its last picture; read the frame rate from the perf log.
- R7: add `REGPU_NO_RENDER=1`, or switch it live (`py -3 tools/regpuctl.py switch REGPU_NO_RENDER 1`).
- Draw split: read the `triple: draws/frame` lines in any triple run.

**The 360 fps engine cap still applies** in R6 and R7. If a run sits at the cap, it says only "at least 360"; use the
2-core contention setup from the existing tests to get under it, as for the single-screen numbers.

## What was checked

- The patch applies cleanly to 604dd2b (`git apply --check`).
- **Syntax check with clang-cl 23**, the compiler ReGPU requires: a full build needs FM3's generated `ppc_config.h`, the
  FidelityFX SDK and the generated shader headers, which aren't on this machine. So `gpu.cpp` and `renderer.cpp` were
  checked with `/Zs` (syntax only) against stand-ins for those, with and without the patch. `gpu.cpp`: no errors.
  `renderer.cpp`: the same 23 errors with and without the patch, all from the stand-in shader headers. The patch adds no
  errors.
- **Not checked:** an actual build, linking, and a run. The first real check is a triple grid boot with
  `REGPU_NO_GPU_WORK=1`: it should keep advancing frames in the perf log with the window frozen.

## Limits

- The per-screen counts need the draw thread (the default). With it turned off, draws don't pass the counting point and
  the centre count reads 0.
- In VR stereo mode the second eye's replay is counted under "centre and shared"; the log line only appears in triple
  mode.
