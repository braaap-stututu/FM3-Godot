# Godot backend pieces

This folder is a Godot 4.7 project (`project.godot`) holding the parts of the Godot renderer
backend (SCENE_API.md §11) that exist so far, and the M0 benchmark. Open it in the editor or run
it from the command line; its main scene is the G1 benchmark.

| File | What |
|---|---|
| `triple_camera.h` | Turns the core's triple-screen views (`core/triple_view.h`) into Godot frustum-camera settings: yaw, size, offset, near, far |
| `triple_cameras.gd` | Applies those settings to a `Camera3D` or a RenderingServer camera RID; builds the three SubViewports |
| `tools/triple_layout_json.c` | Prints those settings for a layout (the launcher's `FM3_TRIPLE_*` values) as JSON |
| `bench/g1/` | **G1**, the M0 Godot benchmark (below) |
| `tests/triple_camera_test.c` | Checks the camera conversion against ReGPU's projection in C; writes cases as JSON |
| `tests/triple_camera_godot_test.gd` | The same check inside Godot with real `Camera3D` nodes |

## G1 benchmark (M0)

Measures what Godot costs per mesh instance when it draws three triple-screen views, so M0 can
predict the new renderer's frame rate (M0 plan, "Decision rules").

**Scene:** three 16:9 SubViewports side by side with the triple cameras, one shared world: a
ground plane, a procedural sky, a directional sun with shadows, and N RenderingServer mesh
instances (the way the Scene API backend will create them) drawn from a few hundred unique meshes
and materials, placed along both sides of a 300 m loop. The camera drives the loop at 40 m/s.
For each N: warm up, then measure fps, p99 frame time, Godot's render CPU and GPU time (summed
over the three views), draw calls and objects drawn.

**Run on the triple rig** (a borderless window at 0,0 spanning 7680×1440; add `--fullscreen` for
exclusive fullscreen on the Eyefinity display):

```powershell
& "G:\claude code projects\Godot\Godot_v4.7.2-stable_win64.exe" --path "G:\claude code projects\Godot\frame-ir\godot" -- --out=g1_results.json
```

Options after `--` (all optional):

| Option | Default | Meaning |
|---|---|---|
| `--screen=WxH` | `2560x1440` | One screen's size; the window is three of them |
| `--msaa=N` | `4` | 0, 2, 4 or 8, like FM3's 4x |
| `--counts=a,b,c` | `1000,2000,4000,7000,10000` | Instance counts to measure, in order |
| `--unique=N` | `300` | Unique meshes and materials |
| `--warmup=S` / `--measure=S` | `3` / `8` | Seconds per phase |
| `--layout=path` | `res://bench/g1/layout_auto.json` | Triple layout from `tools/triple_layout_json.c` |
| `--out=path` | `user://g1_results.json` | Results file (the console prints the full path) |
| `--fullscreen` | off | Exclusive fullscreen instead of a borderless window |
| `--no-shadows` | shadows on | Turn off the sun's shadows |
| `--quick` | | Tiny counts and short phases, a smoke test |

**Your own layout:** build the tool and pass the launcher's triple settings:

```powershell
cl /nologo /std:c11 tools\triple_layout_json.c /Fe:triple_layout_json.exe
.\triple_layout_json.exe mode=physical diag=27 dist=60 bezel_mm=10 gap_mm=5 > bench\g1\layout_mine.json
```

then add `--layout=res://bench/g1/layout_mine.json`. `layout_auto.json` is the auto layout for a
game camera with a 50° vertical FOV.

If the desktop is smaller than three screens (no Eyefinity/Surround span), the three views still
render at full size; only the on-screen preview is scaled down. `--shots=<dir>` saves each view as
a PNG at the end.

**First results (2026-11-22, RX 7900 XTX, one 2560×1440 display):** in
`bench/g1/results/2026-11-22/`. 10,000 instances in three 2560×1440 views with 4x MSAA and shadows:
~427 fps on Vulkan, ~337 fps on D3D12.

**Known issue on the 2026-11-22 PC: GPU driver timeouts.** Some runs ended in "Vulkan device was
lost" (or a hang on D3D12). Windows logged these as GPU timeouts (LiveKernelEvent 141/117), and the
user confirmed the driver has timeouts on that PC in general, so it is not a Godot or G1 problem.
Rerun a failed run; completed runs are valid. Details: `bench/g1/results/2026-11-22/DEVICE-LOST.md`.

## Running the camera tests

```powershell
cl /nologo /std:c11 /W4 tests\triple_camera_test.c /Fe:triple_camera_test.exe
.\triple_camera_test.exe cases.json
$env:FIR_TRIPLE_CASES = "<full path>\cases.json"
& "<Godot dir>\Godot_v4.7.2-stable_win64.exe" --headless --path . --script res://tests/triple_camera_godot_test.gd
```

Exit code 0 means every point matched ReGPU's triple view within 1e-3 NDC (measured: under 5e-7).
`apply_rid` (the RenderingServer path) is not covered yet: RenderingServer cameras don't expose
their projection for reading back.
