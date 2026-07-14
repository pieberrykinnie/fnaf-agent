# FNAF Agent

AI agent that plays Five Nights at Freddy's 1 live. See PLAN.md for phases; BACKLOG.md for the current task queue.

## Scoping (read first)

- **MVP is non-negotiable: a live agent that survives Night 1, by any means necessary.** Memory reads for state, dgVoodoo2 windowing, scripted heuristics — all allowed.
- Post-MVP work follows the purity ladder in PLAN.md (vision → audio → learned policy → human-like motor model), strictly in order. Never start a tier before the previous one's exit test passes.
- When two designs compete, pick the one that ships a live-playing agent sooner.

## Hard constraints

- Windows host. i7-1360P, Iris Xe (no CUDA) — CPU-only; no pixel-based RL, no heavy models.
- Python 3.14, OpenCV 5.0, Stable-Baselines3 2.9.0, managed with `uv`. Never pip-install directly; use `uv add`.
- Game: `Five Nights at Freddy's/FiveNightsatFreddys.exe` (Clickteam Fusion, 1280x720 logical resolution). Extracted sprites live in `Five Nights at Freddy's/FiveNightsatFreddys/images/` — treat as read-only source data.
- All perception/control coordinates use the canonical 1280x720 frame; convert at the capture/input boundary only.

## Commands

- `uv sync` — install deps
- `uv run pytest` — full test suite (offline; never launches the game)
- `uv run ruff check --fix . && uv run ruff format .` — lint/format
- `uv run python scripts/capture_probe.py` — capture one screenshot to runs/
- `uv run python scripts/verify_state.py` — same-tick screenshot + GameState JSON to runs/ (M1+)
- `uv run python scripts/verify_control.py <action-script>` — execute actions, save before/after screenshots + state deltas (M2+)
- `uv run python scripts/verify_perception.py [image.png]` — annotated overlay PNG + GameState JSON to runs/ (Tier 1+)
- `uv run python scripts/verify_vision_vs_oracle.py` — vision vs memory-oracle divergence report (Tier 1+)

## Workflow (every session)

1. Read BACKLOG.md; take the top unchecked task. Work in small, verifiable increments.
2. Offline-first: build against `tests/fixtures/` and extracted assets. Only run the live game when the backlog item explicitly says integration.
3. Definition of done: pytest green + the relevant verify script's output PNG/JSON generated and **inspected with Read** + BACKLOG.md checked off + commit.
4. Discovered a gotcha? Append it to the Gotchas section below in the same commit.

## Verification protocol

- Never claim a perception or control change works without reading its verify-script artifact (annotated PNG or before/after screenshots in `runs/`).
- Perception changes must keep the fixture suite at 100% and parse < 30 ms/frame.
- Live-game runs write `runs/<timestamp>/` (JSONL events + screenshots). Debug from artifacts, not speculation.

## Live-game rules

- Check the game window exists and is focused before sending input; abort loudly otherwise.
- Respect the kill switch: mouse to screen corner aborts (FAILSAFE). Watchdog caps any live session at 15 min.
- Never leave the game running at session end.

## Live-loop rules

- Latest-frame slot, never a frame queue; agent ticks at 5–10 Hz — optimize per-frame latency, not FPS.
- Input is not click-only: office pan = hover at screen edge; monitor raise = hover over the bottom strip. Use move-and-dwell primitives.
- Every action is act-then-verify: send input → confirm expected GameState delta → retry once → abort loudly.
- Memory reads (pymem) are the MVP state source; from Tier 1 on they are a test oracle only, and in Tier 4 they leave the live path entirely.
- Human touchpoints (flag in output, don't attempt): bootstrap, dgVoodoo2 install, Cheat Engine address hunt.

## Gotchas

- (Phase 0 to confirm) FNAF 1 is DirectDraw exclusive-fullscreen; may defeat capture and offset clicks. Preferred fix: dgVoodoo2 borderless-windowed; fallbacks DxWnd, then desktop capture + calibrated transform. Set DPI-awareness (`SetProcessDpiAwareness`) either way.
- Clickteam polls the real cursor, so absolute SendInput moves work — but pace inputs; animation locks (monitor flip) can eat clicks. Act-then-verify catches this.
- Camera static overlay defeats naïve template matching — grayscale, relaxed thresholds, median-stack 2–3 frames.
- Extracted asset PNGs may have palette/alpha differences vs live captures — validate thresholds against real screenshots, not just composited fixtures.
- Memory addresses may shift per launch — use pointer chains from static bases; run a sanity check at session start (`verify_state.py`).

## Style

- Typed Python, dataclasses for GameState/Action. Ruff enforced.
- Modules: `src/fnaf_agent/{perception,control,env,agent,sim}`. Tests mirror the tree.
- No new top-level deps without noting the reason in the commit message.
