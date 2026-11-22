# Game logic: tracing it, and when offloading it would pay

Rendering comes first (M0-M6). This note records what FM3's game logic costs today, how to trace it with the tools
already in the FM3 checkout, what Pinyon Shift (the Forza Horizon 1 recomp) found, and the route if we replace parts of
it natively later. First measurements 2026-11-22.

## What it costs today (FM3, this PC)

AI race on the frozen grid's track, 20 s with the throttle held, single 2560×1440, **ReGPU drawing removed**
(`REGPU_NO_RENDER=1`) so only game work and ReGPU's command handling remain. Per-thread CPU with
`tools\perf\threads.ps1`:

| Thread | Full CPU (360 fps cap) | 2 cores (358 fps) | What it is |
|---|---|---|---|
| guest 9, ReGPU command processor | 99.8 % | 95.3 % | Parses the game's GPU commands; includes waiting at the cap |
| ReGPU draw thread | 49.3 % | 58.1 % | Bookkeeping only (draws are dropped) |
| guest 7 | 39.4 % | 47.3 % | FM3's render thread (FM3 notes: t7): scene walk, command list building |
| guest 3 | 30.1 % | 37.5 % | Main / simulation thread (to confirm) |
| guest 14 | 8.6 % | 10.4 % | Unknown |
| xma decoder | 6.8 % | 7.1 % | Audio |
| guest 20 | 4.5 % | 5.4 % | Unknown |

At 358 fps on 2 cores that is about **1.3 ms a frame for thread 7, 1.05 ms for thread 3, 0.3 ms for thread 14**:
roughly 2.7 ms of game logic a frame in all. With rendering in, the frame is bound by ReGPU's draw thread (M0), not by
any of these.

Function samples (`FM3_SAMPLE_THREAD=3` / `7` with `FM3_SAMPLE_CALLERS=1`, 1 ms sampling) at the cap:

- **Thread 3** waits 83 % of the time; of the rest no function exceeds 1.1 %. The busiest subtree is
  `sub_8220CA10` (called from `sub_8220D648` / `sub_8220C540`), a candidate for the per-tick simulation. Not confirmed.
- **Thread 7** sleeps ~70 % in frame pacing; the rest is spread over `sub_82886xxx`, `sub_828342D8`/`sub_82AF4AA8`,
  `sub_8280xxxx` and `sub_824AF280` (which calls `VdSwap`), none above 0.6 %.

**Conclusion for this PC:** game logic is cheap and flat. Offloading it would not raise FM3's frame rate here; the
render path is the limit. It matters for weak CPUs (Steam Deck, low-end laptops) and for control (fixed-timestep
physics at any rate, new features), not for the desktop frame rate.

## What Pinyon Shift found (FH1 recomp, read from its public docs, 2026-11-22)

From `docs/NATIVE_REPLACEMENT_RESEARCH.md` and `docs/BEYOND_RECOMP_RESEARCH.md` in arcanite24/pinyon-shift:

- Guest threads use about 23 ms of CPU a frame on the Steam Deck: render 8, simulation outside physics 5.3, FMOD
  mixer 3.0, audio logic 2.1, **physics 1.8** (1.4 on the Odin). Profiles are flat: no function above ~3 %; inside
  physics no leaf above 13 % of physics itself.
- Rewriting game logic natively has a ceiling of **about a third of the game threads' time**; translated guest code is
  already close to native (a native scene-submission rewrite ran only 1.2-1.5x faster).
- Done natively so far: **audio logic** gated to the console's rate (their NR-1, on by default).
- Planned: a **native whole-car physics step** (NR-10), verified against the translation by behaviour gates
  (handling, AI lap times). They call the route "the OpenRCT2 one": every guest function can be overridden
  (`guest_native`), and subsystems are replaced one at a time, each checked against the original.
- Their ladder puts "an owned renderer for the whole frame" (B5) as the only step whose payoff scales; full
  reimplementation (B6) buys control, not much speed. That matches this project's priority on rendering.
- I found no statement that physics and AI are already replicated from constants; that may be newer or not public.

## How to trace FM3's game logic (tools that exist)

| Question | Tool | Notes |
|---|---|---|
| Which threads cost what | `tools\perf\threads.ps1 -Seconds N` | OS thread times; free |
| Which functions on a thread | `FM3_SAMPLE_THREAD=<guest id>` (+ `FM3_SAMPLE_CALLERS=1..16`, `FM3_SAMPLE_LINES=1`, `FM3_SAMPLE_RVA=1`) | 1 ms sampling, table every 5 s in `fm3.log`; never with `REGPU_PERF` on |
| Game work without rendering | `REGPU_NO_RENDER=1` | Live switch |
| Contention like a weak CPU | Affinity mask `0x0F` (2 cores / 4 threads) | As in the existing 2-core tests |
| A repeatable scene | Frozen grid (`FM3_GRID_TEST=1`) + `Test-Drive` (AI race, throttle held) | `tools\perf_suite.ps1` |

The script used above is [`gamelogic/gamecpu.ps1`](gamelogic/gamecpu.ps1) (`-Sample <thread>`, `-Mask 0x0F`); logs in
`gamelogic/`.

## What is missing for real offloading work (proposed, not built)

1. **Name the threads and the per-tick functions.** Find the simulation step by call rate: a function called 360
   times a second during a race is the physics tick, one called at the frame rate is the frame update. Needs a call
   counter for chosen guest functions: a compile-time hook list in FM3's `src/hooks` (the mechanism `TripleHandOff`
   uses), each hook counting calls and time, logged once a second.
2. **A state recorder for one subsystem.** For a candidate (say the car physics step): record its inputs and outputs
   every call (the car state struct before and after, the controls) to a file during a race. That is the reference a
   native reimplementation must reproduce, and the data a "remade from constants" physics would be validated against.
3. **Behaviour gates.** Lap time of an AI car over a fixed race, a car's position after N seconds of a recorded input,
   tyre temperatures: compared between the original and a replacement, as Pinyon Shift plans.
4. **Then, one subsystem at a time**, overriding the guest function natively, each gated. Physics and AI first only if
   a weak target needs the time; otherwise this stays a control feature.

None of this is needed for M1-M6.
