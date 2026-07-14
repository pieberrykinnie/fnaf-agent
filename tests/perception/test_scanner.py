"""Offline tests for the scanner core: scan, narrow, pointer search — all
against synthetic memory regions."""

import struct

from fnaf_agent.perception.scanner import Region, Snapshot, annotate_module, narrow


def i32s(*values: int) -> bytes:
    return struct.pack(f"<{len(values)}i", *values)


def test_scan_equal_i32_across_regions() -> None:
    snap = Snapshot(
        [
            Region(0x1000, i32s(5, 99, 7, 99)),
            Region(0x9000, i32s(99, 0)),
        ]
    )
    assert snap.scan_equal(99, "i32") == {0x1004: 99, 0x100C: 99, 0x9000: 99}


def test_scan_equal_f64_and_u8() -> None:
    snap = Snapshot([Region(0x2000, struct.pack("<dd", 99.0, 42.5) + bytes([7, 99]))])
    assert set(snap.scan_equal(42.5, "f64")) == {0x2008}
    # u8 scan finds the 99 byte and any 99 bytes inside wider values
    assert 0x2011 in snap.scan_equal(99, "u8")


def test_value_at_bounds() -> None:
    snap = Snapshot([Region(0x1000, i32s(11, 22))])
    assert snap.value_at(0x1000, "i32") == 11
    assert snap.value_at(0x1004, "i32") == 22
    assert snap.value_at(0x1005, "i32") is None  # would read past the region
    assert snap.value_at(0x0500, "i32") is None  # before any region
    assert snap.value_at(0x9999, "i32") is None  # after all regions


def test_narrow_modes() -> None:
    before = Snapshot([Region(0x1000, i32s(99, 99, 99))])
    candidates = before.scan_equal(99, "i32")
    assert len(candidates) == 3

    # power ticked 99 -> 98 at 0x1000; 0x1004 unchanged; 0x1008 rose to 150
    after = Snapshot([Region(0x1000, i32s(98, 99, 150))])
    assert narrow(candidates, after, "i32", "eq", 98) == {0x1000: 98}
    assert narrow(candidates, after, "i32", "dec") == {0x1000: 98}
    assert narrow(candidates, after, "i32", "inc") == {0x1008: 150}
    assert narrow(candidates, after, "i32", "unchanged") == {0x1004: 99}
    assert set(narrow(candidates, after, "i32", "changed")) == {0x1000, 0x1008}


def test_narrow_drops_vanished_addresses() -> None:
    candidates = {0x1000: 99, 0x5000: 99}  # 0x5000's region freed since
    after = Snapshot([Region(0x1000, i32s(99))])
    assert narrow(candidates, after, "i32", "unchanged") == {0x1000: 99}


def test_find_pointers_to() -> None:
    target = 0x0A000654
    snap = Snapshot(
        [
            # one pointer to the exact target, one to the struct 0x54 below,
            # one unrelated value
            Region(0x400000, struct.pack("<III", target, 0x0A000600, 0xDEAD)),
        ]
    )
    hits = snap.find_pointers_to(target, max_offset=0x100)
    assert (0x400000, 0x0) in hits
    assert (0x400004, 0x54) in hits
    assert all(holder != 0x400008 for holder, _ in hits)


def test_annotate_module() -> None:
    modules = {"FiveNightsatFreddys.exe": (0x400000, 0x100000)}
    assert annotate_module(0x44B2E8, modules) == "FiveNightsatFreddys.exe+0x4b2e8"
    assert annotate_module(0x0A000000, modules) is None
