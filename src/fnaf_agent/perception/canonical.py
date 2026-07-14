"""Screen <-> canonical 1280x720 coordinate transform.

The game renders a 1280x720 logical frame. Under dgVoodoo2 (or any windowed
wrapper) the client area on screen may be scaled and, if its aspect ratio is
not 16:9, letterboxed/pillarboxed. This module is the single place where
screen pixels and canonical coordinates meet: perception and control code
only ever speak canonical, and convert at the capture/input boundary.

The mapping is aspect-preserving (fit): the canonical frame is scaled by
min(w/1280, h/720) and centered in the client rect.
"""

from __future__ import annotations

from dataclasses import dataclass

CANONICAL_WIDTH = 1280
CANONICAL_HEIGHT = 720


@dataclass(frozen=True)
class CanonicalTransform:
    """Affine map between a screen-space client rect and the canonical frame.

    left/top are the client rect's origin in screen coordinates (physical
    pixels, DPI-aware); width/height its size. scale and the content offsets
    are derived in __post_init__.
    """

    left: int
    top: int
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError(f"client rect must be positive, got {self.width}x{self.height}")

    @property
    def scale(self) -> float:
        return min(self.width / CANONICAL_WIDTH, self.height / CANONICAL_HEIGHT)

    @property
    def content_offset(self) -> tuple[float, float]:
        """Screen-space offset of the game content's top-left inside the client rect."""
        ox = (self.width - CANONICAL_WIDTH * self.scale) / 2
        oy = (self.height - CANONICAL_HEIGHT * self.scale) / 2
        return (ox, oy)

    def to_screen(self, cx: float, cy: float) -> tuple[int, int]:
        """Canonical point -> absolute screen pixel (for SendInput)."""
        ox, oy = self.content_offset
        sx = self.left + ox + cx * self.scale
        sy = self.top + oy + cy * self.scale
        return (round(sx), round(sy))

    def to_canonical(self, sx: float, sy: float) -> tuple[float, float]:
        """Absolute screen pixel -> canonical point (unclamped)."""
        ox, oy = self.content_offset
        cx = (sx - self.left - ox) / self.scale
        cy = (sy - self.top - oy) / self.scale
        return (cx, cy)

    def contains_screen_point(self, sx: float, sy: float) -> bool:
        """True if the screen point lands inside the game content (not letterbox bands)."""
        cx, cy = self.to_canonical(sx, sy)
        return 0 <= cx < CANONICAL_WIDTH and 0 <= cy < CANONICAL_HEIGHT

    def content_rect(self) -> tuple[int, int, int, int]:
        """Screen-space (left, top, width, height) of the game content itself.

        This is the region a capture backend should grab so the frame can be
        resized straight to 1280x720 with no letterbox bands in it.
        """
        ox, oy = self.content_offset
        return (
            round(self.left + ox),
            round(self.top + oy),
            round(CANONICAL_WIDTH * self.scale),
            round(CANONICAL_HEIGHT * self.scale),
        )
