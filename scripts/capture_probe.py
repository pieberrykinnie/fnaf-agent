"""Phase 0 probe: capture the game window, save PNG + metadata JSON to runs/.

Stub — see BACKLOG.md Phase 0 for acceptance criteria. Must decide capture
backend (mss vs bettercam), record window geometry/DPI, and fail loudly if the
game window is not found.
"""

import json
import sys
import time
from pathlib import Path

GAME_TITLE = "Five Nights at Freddy's"
RUNS = Path(__file__).resolve().parent.parent / "runs"


def main() -> int:
    RUNS.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")

    import mss
    import mss.tools
    import pygetwindow as gw

    wins = [w for w in gw.getAllWindows() if GAME_TITLE.lower() in w.title.lower()]
    if not wins:
        print(f"FAIL: no window matching {GAME_TITLE!r}. Open windows:")
        for w in gw.getAllWindows():
            if w.title.strip():
                print(f"  {w.title!r} at {w.box}")
        return 1

    w = wins[0]
    meta = {"title": w.title, "box": list(w.box), "timestamp": stamp}
    with mss.mss() as sct:
        region = {"left": w.left, "top": w.top, "width": w.width, "height": w.height}
        img = sct.grab(region)
        out_png = RUNS / f"probe-{stamp}.png"
        mss.tools.to_png(img.rgb, img.size, output=str(out_png))
        meta["captured_size"] = list(img.size)

    (RUNS / f"probe-{stamp}.json").write_text(json.dumps(meta, indent=2))
    print(f"OK: {out_png}\n{json.dumps(meta, indent=2)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
