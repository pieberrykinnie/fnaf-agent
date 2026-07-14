# Backlog

Work top-down. One item = one session increment. Done means: pytest green, verify artifact inspected with Read, checked off here, committed. See CLAUDE.md. MVP = live agent survives Night 1 (end of Phase M3); everything after is the purity ladder.

## Phase 0 — Bootstrap + windowing probe
- [x] HUMAN: run `scripts/bootstrap.ps1`; launch game once and confirm it runs. (Done 2026-07-14. dgVoodoo2 turned out unnecessary — v1.132 runs windowed natively; stub-probe screenshot confirmed clean mss capture of the title menu.)
- [x] Implement `scripts/capture_probe.py` for real: enumerate windows, capture via mss AND bettercam, save PNGs + metadata JSON (geometry, DPI, backend timings) to `runs/`. (Verified end-to-end against a non-game window 2026-07-14; bettercam ~8 ms vs mss ~34 ms.)
- [x] INTEGRATION: capture_probe run against the live game (2026-07-14): client rect exactly 1280x720 physical; bettercam 3.6 ms vs mss 11.4 ms → **bettercam decided**, mss fallback; both PNGs inspected pixel-perfect. `tests/fixtures/live/title_menu.png` committed; decision in CLAUDE.md Gotchas
- [x] Canonical transform (screen ↔ 1280x720) from probe geometry; implement + unit test `perception/canonical.py`

## Phase M1 — State by any means (memory-first)
- [x] Attach to game process with pymem (`uv add pymem`): `scripts/attach_probe.py` dumps module list, confirms read access (PE magic), reads any mapped fields. (Fail path verified offline 2026-07-14.) INTEGRATION half pending: run against the live game, confirm module base addresses print
- [x] SUPERSEDED: HUMAN-assisted: guided scan session. Instead of manual static pointers, we implemented `CTFRuntime` and `scripts/auto_map.py` to auto-discover state dynamically from Clickteam's runtime structures.
- [ ] `CTFMemoryStateReader` → GameState from dynamically scanned active objects. Acceptance: `auto_map.py` successfully reads FNAF state objects (power, doors, lights, etc.) live, and values are stable across two game launches. (CTF runtime traversal unit-tested offline; remaining: run `auto_map.py` live to map names/indices).
- [ ] Phash screen classifier (menu/office+camera/jumpscare/6AM) from a handful of live screenshots — covers what memory reads awkwardly. Acceptance: fixture test on live captures
- [ ] `scripts/verify_state.py`: same-tick screenshot + GameState JSON to `runs/`. INTEGRATION acceptance: Claude inspects pair and confirms they agree. (Script + `perception/capture.py` FrameSource — bettercam→mss, keep-last-frame — implemented offline 2026-07-14; remaining: live run once memory_map has chains)

## Phase M2 — Control
- [ ] Window manager: find/launch/focus, fail-loud focus assertion, kill switch (mouse-to-corner) + 15-min watchdog
- [ ] Input primitives: click, absolute move, dwell-hover (pan = hover screen edge; monitor = hover bottom strip). All Actions in `state.py` implemented via pydirectinput in canonical coords
- [ ] Act-then-verify wrapper: send input → confirm expected GameState delta → retry once → abort loudly
- [ ] `scripts/verify_control.py`: run action list live; save before/after screenshots + state deltas. INTEGRATION acceptance: every action proven from artifacts

## Phase M3 — Live agent (MVP)
- [ ] `GameInterface`: observe/act loop on latest-frame slot at 5–10 Hz + menu-nav reset (new game / continue)
- [ ] Run recorder: `runs/<ts>/` JSONL events + screenshots on state change and death
- [ ] Heuristic policy: door-light checks, Foxy (1C) cam discipline, power budget. INTEGRATION acceptance: **Night 1 survived unassisted; 6AM screen in run log — MVP done**
- [ ] Push through Night 3; harvest run screenshots into `tests/fixtures/live/` (labeled by memory oracle) for Tier 1

## Tier 1 — Vision replaces memory taps
- [ ] `scripts/index_assets.py`: inventory the extracted `images/` tree (~18k files) → JSON
- [ ] Curate templates + `manifest.yaml`: HUD digits, door/light buttons (both states), monitor flip, power bars, camera map, menu items, per-camera signatures, animatronic sprites per camera
- [ ] Screen classifier + digit readers (power/hour/night) on fixtures. Acceptance: 100% fixture pass, <5 ms/read
- [ ] Office parser: pan offset via landmark match, then door/light/monitor at known offsets
- [ ] Camera parser: active cam + animatronic presence; median-stack 2–3 frames against static noise
- [ ] `parse_frame` composed + benchmarked <30 ms (pytest-benchmark); `scripts/verify_perception.py` overlay PNG + JSON
- [ ] `scripts/verify_vision_vs_oracle.py`: live run comparing vision GameState vs memory oracle per frame → divergence report. Acceptance: <1% divergence
- [ ] Swap GameInterface state source to vision. INTEGRATION acceptance: Night 1 survived on vision alone

## Tier 2 — Audio
- [ ] WASAPI loopback capture (`uv add soundcard`) + spectral fingerprints for Kitchen activity, Foxy sprint, door knock; fuse into GameState
- [ ] INTEGRATION acceptance: logged live run shows policy reacting to an audio-only event

## Tier 3 — Learned policy
- [ ] Offline sim of documented mechanics (AI levels, movement opportunities, power model, hour timing) on the same GameState/Action interface; property tests vs wiki
- [ ] Calibrate sim against M3/Tier-1 run logs
- [ ] Gymnasium env (state-vector obs, discrete actions, survival+power reward); SB3 PPO baseline beats sim Night 1, then harder configs
- [ ] Transfer to live via GameInterface. INTEGRATION acceptance: real Night 1 survived by learned policy

## Tier 4 — Human-like play
- [ ] Remove memory access from live path entirely (oracle stays test-only)
- [ ] Motor model: 150–250 ms reaction latency, curved noisy mouse paths, capped action rate
- [ ] Optional fullscreen probe (game already runs windowed natively; only relevant if a fullscreen mode is ever wanted)
- [ ] Acceptance: run-log analysis (reaction histogram, input traces) plausibly human
