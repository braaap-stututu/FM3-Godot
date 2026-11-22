# G1 device lost / GPU hang — investigation, 2026-11-22

**Update (same day): the user confirmed their GPU driver is having timeouts on this PC in general.**
So the G1 failures are this system's driver timeouts, not a Godot or G1 problem, and they are not a
blocker for Godot as the backend. G1 numbers from completed runs stand; a failed run is simply rerun.

**Conclusion of the investigation: the GPU hangs and Windows resets it (TDR).** Godot's "Vulkan device was lost"
is the after-effect, not the cause. It happens on Vulkan and on D3D12, so it is not specific to
Godot's Vulkan code, and it is not caused by overlay layers, the frame queue depth or adding
instances mid-run. The open question is driver vs. GPU stability (tuning, power, temperature).

## Setup

- AMD Radeon RX 7900 XTX, driver 32.0.32029.2010 (dated 2026-11-18); Ryzen 9800X3D (its iGPU is
  also present); Windows 11 build 26200.
- Also installed: Virtual Desktop Monitor and SudoMaker virtual display adapters.
- One 2560×1440 display attached; G1 renders three 2560×1440 views offscreen (4x MSAA, sun shadows)
  and presents a scaled preview. Godot 4.7.2 stable.

## Evidence

| Condition | Runs | Failed | How it failed |
|---|---|---|---|
| Vulkan, full sweep (1k–20k instances, ~70 s) | 4 | 3 | Device lost at present (`command_queue_execute_and_present`), from the first seconds to ~25 s in |
| Vulkan, shorter sweeps and a 40 s soak at 4k | 3 | 0 | |
| Vulkan, implicit layers disabled (`VK_LOADER_LAYERS_DISABLE=~implicit~`) | 2 | 2 | Same |
| Vulkan, frame queue 3 (`rendering_device/vsync/frame_queue_size=3`) | 3 | 1 | Same, at startup |
| Vulkan, short runs (1k–2k, ~12 s) | 8 | 1 | Same |
| Vulkan, capped at 300 fps | 8 short + 1 full | 0 | Not conclusive: fewer frames alone lowers the odds |
| Vulkan, `--accurate-breadcrumbs` | 3 | 0 | |
| Vulkan, growing instances vs precreated hidden (`--precreate`) | 2 + 2 | 0 | Growth is not the trigger |
| D3D12 | 3 full | 1 | **Hang**: Godot stopped responding a second after startup, no error |

Windows Error Reporting logged **8 LiveKernelEvent reports (6 × code 141, 2 × code 117)**, matching
the number of failed runs. 141 and 117 are the codes for a GPU that stopped responding and was reset
by the driver (TDR). They do not appear in the System log as Display event 4101, which is why the
first check missed them.

Loaded implicit Vulkan layers by default: Overwolf OBS hook, Overwolf overlay, RivaTuner (their
apps were not running). Disabling all implicit layers did not help.

## What this rules out

- Overlay layers (crashes with all implicit layers off).
- Godot's Vulkan driver code specifically (D3D12 hangs too).
- The 7680×1440 window (crashes with a 2560-wide window too).
- Adding instances while rendering.
- Frame queue depth 2 vs 3.

## Next steps

1. **GPU tuning back to stock** (Adrenalin → Performance → Tuning → reset), then rerun the full sweep
   3 times on Vulkan. GPU hangs only under some loads are typical of an undervolt or overclock that
   is stable in games but not in an uncapped high-frame-rate load. This is the quickest discriminator.
   It needs the user: it changes a system setting.
2. If it still hangs at stock: **try the previous AMD driver** (also the user's call).
3. **AMD Radeon GPU Detective (RGD)** captures a crash dump at the TDR and names the hung pass and
   shader, for Vulkan and D3D12. Use it if 1 and 2 don't settle it (it's a download; ask first).
4. Only if it reproduces on stock settings and two drivers: report to AMD with RGD output, and to
   Godot if RGD points at an engine pass.

Until then, G1 numbers should be taken from completed runs only; they are unaffected by the hangs.
