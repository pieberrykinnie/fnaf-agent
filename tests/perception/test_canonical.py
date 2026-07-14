"""Unit tests for the screen <-> canonical 1280x720 transform."""

import pytest

from fnaf_agent.perception.canonical import (
    CANONICAL_HEIGHT,
    CANONICAL_WIDTH,
    CanonicalTransform,
)


def test_identity_at_native_size() -> None:
    t = CanonicalTransform(left=0, top=0, width=1280, height=720)
    assert t.scale == 1.0
    assert t.content_offset == (0.0, 0.0)
    assert t.to_screen(0, 0) == (0, 0)
    assert t.to_screen(1280, 720) == (1280, 720)
    assert t.to_canonical(640, 360) == (640.0, 360.0)


def test_window_at_offset() -> None:
    t = CanonicalTransform(left=100, top=50, width=1280, height=720)
    assert t.to_screen(0, 0) == (100, 50)
    assert t.to_screen(640, 360) == (740, 410)
    assert t.to_canonical(740, 410) == (640.0, 360.0)


def test_uniform_2x_scale() -> None:
    t = CanonicalTransform(left=0, top=0, width=2560, height=1440)
    assert t.scale == 2.0
    assert t.content_offset == (0.0, 0.0)
    assert t.to_screen(640, 360) == (1280, 720)


def test_pillarbox_wider_than_16_9() -> None:
    # 1600x720 client: content is 1280x720 centered, 160 px bands left/right.
    t = CanonicalTransform(left=0, top=0, width=1600, height=720)
    assert t.scale == 1.0
    assert t.content_offset == (160.0, 0.0)
    assert t.to_screen(0, 0) == (160, 0)
    assert t.content_rect() == (160, 0, 1280, 720)
    assert not t.contains_screen_point(80, 360)  # in the left band
    assert t.contains_screen_point(800, 360)


def test_letterbox_taller_than_16_9() -> None:
    # 1280x800 client: content is 1280x720 centered, 40 px bands top/bottom.
    t = CanonicalTransform(left=0, top=0, width=1280, height=800)
    assert t.scale == 1.0
    assert t.content_offset == (0.0, 40.0)
    assert t.to_screen(0, 0) == (0, 40)
    assert not t.contains_screen_point(640, 20)  # in the top band
    assert t.contains_screen_point(640, 400)


def test_roundtrip_arbitrary_geometry() -> None:
    t = CanonicalTransform(left=37, top=113, width=1000, height=700)
    for cx, cy in [(0, 0), (1280, 720), (640, 360), (13.5, 700.25)]:
        rx, ry = t.to_canonical(*t.to_screen(cx, cy))
        # to_screen rounds to a whole pixel, so round-trip error is bounded
        # by half a pixel divided by the scale.
        tol = 0.5 / t.scale + 1e-9
        assert abs(rx - cx) <= tol
        assert abs(ry - cy) <= tol


def test_canonical_constants() -> None:
    assert (CANONICAL_WIDTH, CANONICAL_HEIGHT) == (1280, 720)


def test_degenerate_rect_rejected() -> None:
    with pytest.raises(ValueError):
        CanonicalTransform(left=0, top=0, width=0, height=720)
    with pytest.raises(ValueError):
        CanonicalTransform(left=0, top=0, width=1280, height=-1)
