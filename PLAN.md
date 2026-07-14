# FNAF Agent — Autonomous Development Plan

**MVP (non-negotiable): an agent that plays a live FNAF 1 session — survives Night 1 unassisted — by any means necessary.** Every crutch is allowed: reading game memory for state, forcing windowed mode via a wrapper, scripted heuristics.

**Post-MVP: the purity ladder.** Each tier removes a crutch so the agent plays more like a human. Tiers are strictly ordered; never start a tier before the previous one passes its exit test.

## Scoping principle

When choosing between two designs, pick whichever ships a live-playing agent sooner. Elegance, vision-only purity, and RL are ladder work, not MVP work.

## Why this is autonomously buildable by Claude Code

Claude can't watch the game live, so every layer must be verifiable from artifacts it can read (PNGs via Read, JSON, pytest output). Enablers:

1. **Memory oracle**: Clickteam Fusion keeps game globals (power, hour, night, AI levels, door states) in easily-located process memory. One human-assisted Cheat Engine session yields addresses; after that, `pymem` gives perfect ground-truth GameState at any moment — both the MVP's state source and the automated labeler that later validates the vision pipeline.
2. **Extracted assets**: ~18k sprites in `Five Nights at Freddy's/FiveNightsatFreddys/images/` — every camera view, animatronic pose, UI element, HUD digit. The vision tier is built and unit-tested offline against these.
3. **Documented mechanics**: FNAF 1 AI levels/movement/power rules are public — an offline simulator for RL training is verifiable against the wiki.

## The live loop

```
capture thread ──► latest-frame slot (never queue; always freshest)
                        │ 5–10 Hz agent tick (FNAF decisions are seconds-scale;
                        ▼  optimize per-frame latency, not FPS)
                   state reader ──► GameState (typed dataclass, JSON-serializable)
                     MVP: pymem memory reads (+ phash screen classifier)
                     Tier 1: vision (templates)          Tier 2: + audio
                        ▼
                   policy (MVP: scripted heuristic → Tier 3: learned)
                        ▼
                   action executor ── act ► verify GameState delta ► retry once ► abort loudly
```

Design decisions from the live-loop brainstorm:

- **Windowing/capture**: FNAF 1 is DirectDraw exclusive-fullscreen; that can defeat capture and skew coordinates. Preferred fix: **dgVoodoo2** (DirectDraw→D3D11 wrapper, borderless windowed at chosen scale — fixes capture and coordinate mapping at once). Fallbacks: DxWnd, then full-desktop capture + calibrated stretch transform. Backends: `mss` (simple) vs `bettercam` (Desktop Duplication, 60+ fps, frames only on change). Phase 0 probe decides.
- **Canonical frame**: all coordinates in 1280x720 logical space; a single calibrated transform at the capture/input boundary.
- **Input is not click-only**: office panning = hover at screen edges; monitor raise = hover over bottom strip. Executor needs move-and-dwell primitives plus clicks (`pydirectinput`/SendInput; Clickteam polls real cursor position).
- **Act-then-verify**: every action confirms its expected GameState delta on the next read, retries once, then aborts loudly. This is what makes a screen-bot reliable, and it's nearly free.
- **Vision cost control** (Tier 1): perceptual-hash the frame to classify screen type in microseconds; run only that screen's detectors. Office pan offset estimated from one landmark match, then all buttons are at known offsets. Camera static defeats naïve matching — grayscale, relaxed thresholds, median-stack 2–3 frames.
- **Audio** (Tier 2): Kitchen (CAM 6) is audio-only; Foxy's sprint and door knocks are sound events. WASAPI loopback (`soundcard`) + spectral fingerprints.

## MVP phases

### Phase 0 — Bootstrap + windowing probe
Human runs `scripts/bootstrap.ps1`, installs dgVoodoo2 into the game folder, launches once. Probe script decides capture backend, records window geometry/DPI, saves a real screenshot to fixtures. Exit: pytest green + committed live screenshot + capture decision in CLAUDE.md Gotchas.

### Phase M1 — State by any means (memory-first)
Human-assisted Cheat Engine session finds addresses/pointer chains for power, hour, night, camera, doors, lights, monitor, and (if findable) animatronic positions; recorded in `assets/memory_map.yaml`. `MemoryStateReader` produces GameState via pymem. Thin vision assist only where memory is awkward: phash screen classifier for menu/jumpscare/6AM. Exit: `scripts/verify_state.py` dumps live GameState JSON matching a screenshot taken in the same tick (Claude inspects both).

### Phase M2 — Control
Window find/focus/launch, kill switch (mouse-to-corner FAILSAFE) + 15-min watchdog. Primitives: click, move, dwell-hover. All Actions implemented with act-then-verify against memory state. Exit: `scripts/verify_control.py` runs an action script; before/after screenshots + state deltas prove every action.

### Phase M3 — Live agent (MVP done)
`GameInterface` (observe/act + menu-nav reset), run recorder (`runs/<ts>/` JSONL + screenshots on state change/death), heuristic policy: door-light checks, Foxy cam discipline, power budgeting. **Exit: Night 1 survived unassisted, 6AM screen in the run log. This is the MVP.** Then push through Night 3 and harvest screenshots as vision fixtures.

## Purity ladder (post-MVP, in order)

### Tier 1 — Eyes instead of memory taps
Full vision GameState: template library curated from extracted assets (digits, buttons, camera signatures, animatronic sprites), screen classifier, digit readers, office/camera parsers. Built offline against fixtures; validated live by **auto-comparing vision output to the memory oracle every frame** (`scripts/verify_vision_vs_oracle.py` reports divergence rates — memory is demoted from agent input to test oracle). Budget: parse < 30 ms/frame. Exit: agent survives Night 1 on vision alone; oracle divergence < 1% of frames.

### Tier 2 — Ears
Audio perception for Kitchen tracking, Foxy sprint, door knocks; fuse into GameState. Exit: policy uses audio (e.g., reacts to Kitchen noise) in a logged live run.

### Tier 3 — Learned policy instead of scripted
Offline simulator of documented mechanics (same GameState/Action interface; property tests vs wiki; calibrated against Phase M3 run logs). Gymnasium env with **state-vector observations** (CPU-only rules out pixel RL; real time rules out on-game training — 1 night ≈ 8.6 min). Train SB3 PPO/DQN on sim, evaluate on sim, transfer to live via GameInterface. Exit: sim-trained policy survives live Night 1+; stretch: 4/20 mode in sim.

### Tier 4 — Plays like a human
No memory access at runtime at all (delete the oracle from the live path). Human-ish motor model: ~150–250 ms reaction latency, curved mouse trajectories with noise, capped APM. Native fullscreen (drop dgVoodoo2) if capture allows. Exit: side-by-side run log indistinguishable-in-kind from a human playthrough (reaction-time histogram, input traces).

## Autonomy infrastructure

- **CLAUDE.md**: constraints, commands, verification protocol, gotchas — updated in the same commit as any discovery.
- **BACKLOG.md**: ordered queue with acceptance criteria; one item per session increment.
- **.claude/settings.json**: pre-approved permissions so sessions don't stall.
- **Verification protocol**: no live-loop change is done until its verify-script artifact is generated and inspected with Read, and pytest is green.
- **Human touchpoints are explicit and front-loaded**: bootstrap, dgVoodoo2 install, one Cheat Engine session. Everything else is Claude solo.

## Risks

- **Memory addresses unstable across launches** → prefer pointer chains from static base; re-scan script + `verify_state.py` sanity check at session start; if hopeless, fall back to accelerating Tier 1 vision (MVP tolerates either means).
- **dgVoodoo2 breaks the game or timing** → DxWnd, then desktop capture + transform; probe decides in Phase 0, before anything is built on top.
- **Input rejected/dropped** → SendInput via pydirectinput, paced; act-then-verify catches drops; focus assertion before every send.
- **Sim-to-real gap (Tier 3)** → state-vector policy + sim calibrated against real run logs from M3.
