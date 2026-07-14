"""Offline-testable core of the in-repo memory scanner — the open-source
replacement for Cheat Engine (closed source, banned from this project).

A Snapshot is an immutable copy of a process's writable memory regions.
Scanning = find addresses whose bytes decode to a target value; narrowing =
re-snapshot and keep only candidates that satisfy a predicate against their
previous value (equal / changed / increased / ...). Pointer search = find
4-byte values that point at (or just below) a target address, which is how
static pointer chains into the Clickteam heap are discovered.

The live side (region enumeration via VirtualQueryEx + pymem reads) lives in
scripts/memory_scan.py; everything here runs against synthetic regions in
pytest.
"""

from __future__ import annotations

import struct
from bisect import bisect_right
from dataclasses import dataclass

import numpy as np

SCAN_TYPES = ("i32", "u8", "f64")
_DTYPE = {"i32": np.int32, "u8": np.uint8, "f64": np.float64}
_STRUCT = {"i32": "<i", "u8": "<B", "f64": "<d"}
SIZE = {"i32": 4, "u8": 1, "f64": 8}


@dataclass(frozen=True)
class Region:
    base: int
    data: bytes

    @property
    def end(self) -> int:
        return self.base + len(self.data)


class Snapshot:
    """Sorted, immutable set of memory regions supporting scan and lookup."""

    def __init__(self, regions: list[Region]) -> None:
        self.regions = sorted(regions, key=lambda r: r.base)
        self._bases = [r.base for r in self.regions]

    def scan_equal(self, value: int | float, vtype: str) -> dict[int, int | float]:
        """All type-aligned addresses whose bytes decode to `value`."""
        size = SIZE[vtype]
        out: dict[int, int | float] = {}
        for r in self.regions:
            n = len(r.data) // size
            if n == 0:
                continue
            arr = np.frombuffer(r.data[: n * size], dtype=_DTYPE[vtype])
            for i in np.nonzero(arr == value)[0]:
                out[r.base + int(i) * size] = value
        return out

    def value_at(self, addr: int, vtype: str) -> int | float | None:
        """Decode one value at addr, or None if addr isn't in the snapshot."""
        i = bisect_right(self._bases, addr) - 1
        if i < 0:
            return None
        r = self.regions[i]
        if addr + SIZE[vtype] > r.end:
            return None
        return struct.unpack_from(_STRUCT[vtype], r.data, addr - r.base)[0]

    def find_pointers_to(self, target: int, max_offset: int = 0x400) -> list[tuple[int, int]]:
        """(holder_address, offset) pairs where [holder] + offset == target.

        Scans for 4-byte little-endian values in [target - max_offset, target]
        — i.e. pointers to a structure that contains the target at a small
        positive offset. FNAF 1 is 32-bit, so all pointers are 4 bytes.
        """
        lo = max(target - max_offset, 0)
        hits: list[tuple[int, int]] = []
        for r in self.regions:
            n = len(r.data) // 4
            if n == 0:
                continue
            arr = np.frombuffer(r.data[: n * 4], dtype=np.uint32)
            for i in np.nonzero((arr >= lo) & (arr <= target))[0]:
                hits.append((r.base + int(i) * 4, target - int(arr[i])))
        return hits


def narrow(
    candidates: dict[int, int | float],
    snap: Snapshot,
    vtype: str,
    mode: str,
    target: int | float | None = None,
) -> dict[int, int | float]:
    """Keep candidates whose current value satisfies the predicate.

    mode: "eq" (== target), "changed", "unchanged", "inc", "dec" —
    the last four compare against the candidate's previous value.
    Returns surviving addresses mapped to their *current* values.
    """
    out: dict[int, int | float] = {}
    for addr, old in candidates.items():
        new = snap.value_at(addr, vtype)
        if new is None:
            continue
        keep = (
            (mode == "eq" and new == target)
            or (mode == "changed" and new != old)
            or (mode == "unchanged" and new == old)
            or (mode == "inc" and new > old)
            or (mode == "dec" and new < old)
        )
        if keep:
            out[addr] = new
    return out


def annotate_module(addr: int, modules: dict[str, tuple[int, int]]) -> str | None:
    """'module.exe+0x1234' if addr falls inside a module (=> static address)."""
    for name, (base, size) in modules.items():
        if base <= addr < base + size:
            return f"{name}+{addr - base:#x}"
    return None
