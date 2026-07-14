# FNAF Agent

AI agent that plays Five Nights at Freddy's 1 live. See PLAN.md for phases; BACKLOG.md for the current task queue.

## Scoping (read first)

- **MVP is non-negotiable: a live agent that survives Night 1, by any means necessary.** Memory reads for state, scripted heuristics — all allowed. One boundary: **open-source tooling only** (Cheat Engine is banned — closed source; use `scripts/memory_scan.py`).
- Post-MVP work follows the purity ladder in PLAN.md (vision → audio → learned policy → human-like motor model), strictly in order. Never start a tier before the previous one's exit test passes.
- When two designs compete, pick the one that ships a live-playing agent sooner.

## Hard constraints

- Windows host. i7-1360P, Iris Xe (no CUDA) — CPU-only; no pixel-based RL, no heavy models.
- Python 3.14, OpenCV 5.0, Stable-Baselines3 2.9.0, managed with `uv`. Never pip-install directly; use `uv add`.
- Game: `Five Nights at Freddy's/FiveNightsatFreddys.exe` (Clickteam Fusion, 1280×720 logical resolution). Extracted sprites live in `Five Nights at Freddy's/FiveNightsatFreddys/images/` — treat as read-only source data.
- All perception/control coordinates use the canonical 1280×720 frame; convert at the capture/input boundary only.

## Permitted commands

The following commands may be run freely (request permission proactively if prompted):

- `uv sync` — install deps
- `uv add <pkg>` — add a dependency
- `uv run pytest` (and variants) — full test suite (offline; never launches the game)
- `uv run ruff check --fix . && uv run ruff format .` — lint/format
- `uv run python scripts/<script>` — any script in the scripts directory
- `uv run python -m fnaf_agent` — run the agent module
- `git add`, `git commit`, `git status`, `git diff`, `git log` — standard version control

## Denied operations

> [!CAUTION]
> **Never write to or edit any file under the `Five Nights at Freddy's/` directory.**
> This directory contains the game installation and extracted assets. It is read-only source data.
> This restriction applies to all tools: file creation, file editing, and shell commands that would modify contents under that path.

## Workflow (every session)

1. Read BACKLOG.md; take the top unchecked task. Work in small, verifiable increments.
2. Offline-first: build against `tests/fixtures/` and extracted assets. Only run the live game when the backlog item explicitly says integration.
3. Definition of done: pytest green + the relevant verify script's output PNG/JSON generated and **inspected with `view_file`** + BACKLOG.md checked off + commit.
4. Discovered a gotcha? Append it to the Gotchas section in CLAUDE.md in the same commit.

## Verification protocol

- Never claim a perception or control change works without viewing its verify-script artifact (annotated PNG or before/after screenshots in `runs/`) via `view_file`.
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
- Human touchpoints (flag in output, don't attempt): bootstrap, game launches, guided memory-scan session (`scripts/memory_scan.py`).

## Gotchas

- RESOLVED (2026-07-14): FNAF 1 v1.132 is NOT exclusive-fullscreen — it runs in a plain titled window (~1280×720 physical client at 200% DPI) and mss captures it cleanly. No dgVoodoo2/DxWnd wrapper needed. Capture the CLIENT rect, not the window box: the box includes title bar + a desktop-bleed border sliver.
- Clickteam polls the real cursor, so absolute SendInput moves work — but pace inputs; animation locks (monitor flip) can eat clicks. Act-then-verify catches this.
- Camera static overlay defeats naïve template matching — grayscale, relaxed thresholds, median-stack 2–3 frames.
- Extracted asset PNGs may have palette/alpha differences vs live captures — validate thresholds against real screenshots, not just composited fixtures.
- Memory addresses may shift per launch — use pointer chains from static bases; run a sanity check at session start (`verify_state.py`).
- Host display runs 200% scaling (window DPI 192). With per-monitor DPI awareness set (capture_probe does this), all window/screen coords are physical pixels. pygetwindow's `box` includes invisible borders/shadow — use `GetClientRect`+`ClientToScreen` for the capture region.
- Windows console is cp1252; printing arbitrary window titles crashes with UnicodeEncodeError. Scripts must `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`.
- DECIDED (live-game probe 2026-07-14): capture backend is **bettercam** (3.6 ms median vs mss 11.4 ms on the 1280×720 game client; both verified pixel-perfect). mss is the fallback. bettercam returns None when the frame is unchanged since last grab — the latest-frame slot must retain the previous frame.
- The game window's client rect is exactly 1280×720 physical pixels (probe: client at (800,562)) — the canonical transform degenerates to a pure offset, scale 1.0. Don't hardcode that offset; the window moves between launches, so read the client rect each session.
- Capture works with the game window unfocused (`is_active: false` in probe) — focus is only an input-sending requirement.

## Style

- Typed Python, dataclasses for GameState/Action. Ruff enforced.
- Modules: `src/fnaf_agent/{perception,control,env,agent,sim}`. Tests mirror the tree.
- No new top-level deps without noting the reason in the commit message.
