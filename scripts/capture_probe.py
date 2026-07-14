"""Phase 0 probe: find the game window, capture it via mss AND bettercam,
save PNGs + a metadata JSON (geometry, DPI, backend timings) to runs/.

Decides the capture backend for the live loop. Fails loudly (non-zero exit,
window inventory printed) if the game window is not found, so a windowing
problem is caught here and not three layers up.

Usage: uv run python scripts/capture_probe.py [window-title-substring]
"""

from __future__ import annotations

import ctypes
import json
import statistics
import sys
import time
from ctypes import wintypes
from pathlib import Path
from typing import Any

GAME_TITLE = "Five Nights at Freddy's"
RUNS = Path(__file__).resolve().parent.parent / "runs"
TIMING_FRAMES = 10

# Windows console defaults to cp1252; window titles are arbitrary unicode.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def set_dpi_awareness() -> str:
    """Make this process DPI-aware so window coords are physical pixels."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE
        return "per-monitor"
    except OSError:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
            return "system"
        except OSError:
            return "unaware"


def client_rect_on_screen(hwnd: int) -> tuple[int, int, int, int]:
    """(left, top, width, height) of the window's client area in screen pixels."""
    rect = wintypes.RECT()
    if not ctypes.windll.user32.GetClientRect(hwnd, ctypes.byref(rect)):
        raise OSError(f"GetClientRect failed for hwnd {hwnd}")
    origin = wintypes.POINT(rect.left, rect.top)
    if not ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(origin)):
        raise OSError(f"ClientToScreen failed for hwnd {hwnd}")
    return (origin.x, origin.y, rect.right - rect.left, rect.bottom - rect.top)


def window_dpi(hwnd: int) -> int | None:
    try:
        return ctypes.windll.user32.GetDpiForWindow(hwnd)
    except OSError:
        return None


def find_game_window(title_substring: str):
    import pygetwindow as gw

    matches = [w for w in gw.getAllWindows() if title_substring.lower() in w.title.lower()]
    if not matches:
        print(f"FAIL: no window matching {title_substring!r}. Open windows:")
        for w in gw.getAllWindows():
            if w.title.strip():
                print(f"  {w.title!r} at {w.box}")
        return None
    w = matches[0]
    if w.isMinimized:
        print(f"FAIL: window {w.title!r} is minimized; restore it first.")
        return None
    return w


def probe_mss(region: dict[str, int], out_png: Path) -> dict[str, Any]:
    import mss
    import mss.tools

    result: dict[str, Any] = {"backend": "mss"}
    with mss.MSS() as sct:
        img = sct.grab(region)  # warm-up + saved frame
        mss.tools.to_png(img.rgb, img.size, output=str(out_png))
        result["captured_size"] = list(img.size)

        times = []
        for _ in range(TIMING_FRAMES):
            t0 = time.perf_counter()
            sct.grab(region)
            times.append((time.perf_counter() - t0) * 1000)
        result["frame_ms_median"] = round(statistics.median(times), 2)
        result["frame_ms_max"] = round(max(times), 2)
        result["png"] = out_png.name
    return result


def probe_bettercam(region: dict[str, int], out_png: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"backend": "bettercam"}
    cam = None
    try:
        import bettercam
        import cv2

        cam = bettercam.create(output_color="BGR")
        box = (
            region["left"],
            region["top"],
            region["left"] + region["width"],
            region["top"] + region["height"],
        )
        frame = cam.grab(region=box)
        if frame is None:
            # Desktop Duplication yields None when nothing changed since the
            # last grab; one retry after a repaint window is fair.
            time.sleep(0.1)
            frame = cam.grab(region=box)
        if frame is None:
            result["error"] = "grab returned None twice (no desktop change or duplication blocked)"
            if cam is not None:
                cam.release()
            return result

        cv2.imwrite(str(out_png), frame)
        result["captured_size"] = [frame.shape[1], frame.shape[0]]
        result["png"] = out_png.name

        times = []
        got = 0
        for _ in range(TIMING_FRAMES * 3):  # None-grabs don't count toward timing
            t0 = time.perf_counter()
            f = cam.grab(region=box)
            if f is not None:
                times.append((time.perf_counter() - t0) * 1000)
                got += 1
                if got >= TIMING_FRAMES:
                    break
        if times:
            result["frame_ms_median"] = round(statistics.median(times), 2)
            result["frame_ms_max"] = round(max(times), 2)
        result["none_grab_note"] = (
            "bettercam returns None on unchanged frames; live loop must keep last frame"
        )
        if cam is not None:
            cam.release()
    except Exception as e:  # noqa: BLE001 - probe records, never crashes on a backend
        if cam is not None:
            cam.release()
        result["error"] = f"{type(e).__name__}: {e}"
    return result


def main() -> int:
    title = sys.argv[1] if len(sys.argv) > 1 else GAME_TITLE
    RUNS.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")

    dpi_mode = set_dpi_awareness()
    win = find_game_window(title)
    if win is None:
        return 1

    hwnd = win._hWnd
    client = client_rect_on_screen(hwnd)
    region = {"left": client[0], "top": client[1], "width": client[2], "height": client[3]}
    if region["width"] <= 0 or region["height"] <= 0:
        print(f"FAIL: degenerate client rect {client} — window not rendered?")
        return 1

    meta: dict[str, Any] = {
        "timestamp": stamp,
        "title": win.title,
        "dpi_awareness": dpi_mode,
        "window_box": list(win.box),
        "client_rect_screen": list(client),
        "window_dpi": window_dpi(hwnd),
        "is_active": win.isActive,
        "backends": {},
    }

    meta["backends"]["mss"] = probe_mss(region, RUNS / f"probe-{stamp}-mss.png")
    meta["backends"]["bettercam"] = probe_bettercam(region, RUNS / f"probe-{stamp}-bettercam.png")

    ok = {
        name: b["frame_ms_median"] for name, b in meta["backends"].items() if "frame_ms_median" in b
    }
    if not ok:
        meta["recommendation"] = None
        print("FAIL: no backend captured successfully.")
    else:
        meta["recommendation"] = min(ok, key=lambda k: ok[k])

    out_json = RUNS / f"probe-{stamp}.json"
    out_json.write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))
    print(f"\n{'OK' if ok else 'FAIL'}: metadata at {out_json}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
