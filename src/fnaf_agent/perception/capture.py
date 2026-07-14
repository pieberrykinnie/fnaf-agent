"""Live frame capture: find the game window, derive its canonical transform,
and grab 1280x720 BGR frames of the client area.

Backend policy (decided by the Phase 0 probe, 2026-07-14): bettercam
(Desktop Duplication, ~3.6 ms) preferred, mss (~11 ms) fallback. bettercam
returns None when the screen hasn't changed since the last grab, so the
grabber retains and re-serves the last frame — callers always get a frame.

Everything here except to_canonical_frame touches Win32 and is exercised by
the verify scripts against the live game, not by pytest.
"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from dataclasses import dataclass

import cv2
import numpy as np

from fnaf_agent.perception.canonical import (
    CANONICAL_HEIGHT,
    CANONICAL_WIDTH,
    CanonicalTransform,
)

GAME_TITLE = "Five Nights at Freddy's"


class WindowNotFoundError(RuntimeError):
    """The game window is missing or unusable — abort loudly, per live-game rules."""


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


@dataclass(frozen=True)
class GameWindow:
    hwnd: int
    title: str
    transform: CanonicalTransform

    @classmethod
    def find(cls, title_substring: str = GAME_TITLE) -> GameWindow:
        """Locate the game window or raise WindowNotFoundError listing what's open."""
        import pygetwindow as gw

        matches = [w for w in gw.getAllWindows() if title_substring.lower() in w.title.lower()]
        if not matches:
            titles = [w.title for w in gw.getAllWindows() if w.title.strip()]
            raise WindowNotFoundError(f"no window matching {title_substring!r}; open: {titles}")
        win = matches[0]
        if win.isMinimized:
            raise WindowNotFoundError(f"window {win.title!r} is minimized; restore it first")
        left, top, width, height = client_rect_on_screen(win._hWnd)
        return cls(
            hwnd=win._hWnd,
            title=win.title,
            transform=CanonicalTransform(left, top, width, height),
        )

    @property
    def is_focused(self) -> bool:
        return ctypes.windll.user32.GetForegroundWindow() == self.hwnd


def to_canonical_frame(frame_bgr: np.ndarray) -> np.ndarray:
    """Resize a content-rect capture to 1280x720 (no-op when already exact)."""
    h, w = frame_bgr.shape[:2]
    if (w, h) == (CANONICAL_WIDTH, CANONICAL_HEIGHT):
        return frame_bgr
    return cv2.resize(frame_bgr, (CANONICAL_WIDTH, CANONICAL_HEIGHT), interpolation=cv2.INTER_AREA)


class FrameSource:
    """Grabs canonical 1280x720 BGR frames of the game content rect.

    backend: "auto" (bettercam, fall back to mss), "bettercam", or "mss".
    """

    def __init__(self, transform: CanonicalTransform, backend: str = "auto") -> None:
        self.transform = transform
        self._region = transform.content_rect()
        self._last: np.ndarray | None = None
        self._sct = None
        self._cam = None

        if backend in ("auto", "bettercam"):
            try:
                import bettercam

                self._cam = bettercam.create(output_color="BGR")
                self.backend = "bettercam"
                return
            except Exception:
                if backend == "bettercam":
                    raise
        import mss

        self._sct = mss.MSS()
        self.backend = "mss"

    def grab(self, timeout_s: float = 1.0) -> np.ndarray:
        """Latest frame; blocks up to timeout_s for the first frame ever."""
        left, top, w, h = self._region
        if self.backend == "bettercam":
            box = (left, top, left + w, top + h)
            deadline = time.perf_counter() + timeout_s
            frame = self._cam.grab(region=box)
            # None = unchanged since last grab; only a problem if we have no
            # previous frame yet (first grab after a fresh Duplication session).
            while frame is None and self._last is None and time.perf_counter() < deadline:
                time.sleep(0.005)
                frame = self._cam.grab(region=box)
            if frame is not None:
                self._last = to_canonical_frame(np.asarray(frame))
        else:
            img = self._sct.grab({"left": left, "top": top, "width": w, "height": h})
            self._last = to_canonical_frame(np.asarray(img)[:, :, :3])  # BGRA -> BGR

        if self._last is None:
            raise RuntimeError(f"no frame within {timeout_s}s ({self.backend})")
        return self._last

    def close(self) -> None:
        if self._cam is not None:
            self._cam.release()
        if self._sct is not None:
            self._sct.close()
