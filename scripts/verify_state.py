"""Phase M1 exit check: same-tick screenshot + GameState JSON to runs/.

Captures a canonical 1280x720 frame and reads GameState from process memory
back-to-back (the gap is measured and recorded), so a human — or Claude, via
Read — can confirm the two agree.

Runs meaningfully once assets/memory_map.yaml has chains filled in; before
that it still exercises the whole path but the GameState is mostly null
(unmapped fields are listed in the JSON).

Usage: uv run python scripts/verify_state.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import cv2

from fnaf_agent.perception.capture import (
    FrameSource,
    GameWindow,
    WindowNotFoundError,
    set_dpi_awareness,
)
from fnaf_agent.perception.memory_reader import MemoryMap, MemoryStateReader, PymemAccess

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    RUNS.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    set_dpi_awareness()

    try:
        window = GameWindow.find()
    except WindowNotFoundError as e:
        print(f"FAIL: {e}")
        return 1

    memory_map = MemoryMap.from_yaml(ROOT / "assets" / "memory_map.yaml")
    if not memory_map.fields:
        print("WARN: memory_map.yaml has no mapped fields yet — GameState will be empty.")

    try:
        reader = MemoryStateReader(PymemAccess(memory_map.process), memory_map)
    except Exception as e:  # noqa: BLE001 - report and abort loudly
        print(f"FAIL: cannot attach to {memory_map.process}: {type(e).__name__}: {e}")
        return 1

    source = FrameSource(window.transform)
    try:
        t0 = time.perf_counter()
        frame = source.grab()
        state = reader.read()
        gap_ms = (time.perf_counter() - t0) * 1000
    finally:
        source.close()

    png = RUNS / f"verify_state-{stamp}.png"
    cv2.imwrite(str(png), frame)
    payload = {
        "timestamp": stamp,
        "capture_backend": source.backend,
        "frame_to_state_gap_ms": round(gap_ms, 2),
        "window_focused": window.is_focused,
        "unmapped_fields": memory_map.unmapped,
        "state": json.loads(state.to_json()),
    }
    out = RUNS / f"verify_state-{stamp}.json"
    out.write_text(json.dumps(payload, indent=2))
    print(json.dumps(payload, indent=2))
    print(f"\nOK: {png}\n    {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
