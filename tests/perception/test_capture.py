"""Offline tests for the pure part of capture: canonical frame conversion."""

import numpy as np

from fnaf_agent.perception.capture import to_canonical_frame


def test_exact_size_is_passthrough() -> None:
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    assert to_canonical_frame(frame) is frame


def test_scaled_capture_is_resized() -> None:
    frame = np.full((1440, 2560, 3), 200, dtype=np.uint8)
    out = to_canonical_frame(frame)
    assert out.shape == (720, 1280, 3)
    assert out[0, 0, 0] == 200
