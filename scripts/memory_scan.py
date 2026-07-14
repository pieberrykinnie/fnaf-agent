"""Interactive memory scanner — the open-source Cheat Engine replacement.

Human-guided M1 session: run this in a terminal next to the running game,
narrow candidates by telling the scanner what a value is right now, verify
causality with `write`, then find static holders with `ptr` and transcribe
the result into assets/memory_map.yaml.

Usage: uv run python scripts/memory_scan.py [process-name]

Commands (value type defaults to i32; Clickteam also stores doubles — if a
value never matches as i32, retry with `type f64`):
  type i32|u8|f64     set scan type (clears candidates)
  = <v>               first use: scan all writable memory for v;
                      after: narrow candidates to those now equal to v
  changed / same      narrow: value changed / stayed the same since last scan
  inc / dec           narrow: value increased / decreased
  list [n]            show up to n candidates (default 30), values, module+off
  watch <addr>        print the value at addr every 0.5 s for 5 s
  write <addr> <v>    write v to addr (causality check: watch the game react)
  ptr <addr> [max]    find pointers to addr (offset <= max, default 0x400);
                      static holders are printed as module+offset
  save <name>         dump candidates to runs/scan-<name>.json
  reset               clear candidates
  quit
"""

from __future__ import annotations

import contextlib
import ctypes
import json
import sys
import time
from ctypes import wintypes
from pathlib import Path

from fnaf_agent.perception.scanner import (
    SCAN_TYPES,
    Region,
    Snapshot,
    annotate_module,
    narrow,
)

ROOT = Path(__file__).resolve().parent.parent

PROCESS = "FiveNightsatFreddys.exe"
RUNS = ROOT / "runs"

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MEM_COMMIT = 0x1000
PAGE_GUARD = 0x100
WRITABLE = {0x04, 0x08, 0x40, 0x80}  # RW, WRITECOPY, EXEC_RW, EXEC_WRITECOPY


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wintypes.DWORD),
        ("PartitionId", wintypes.WORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
    ]


def take_snapshot(pm) -> Snapshot:
    """Copy every committed writable region of the target process."""
    regions: list[Region] = []
    mbi = MEMORY_BASIC_INFORMATION()
    addr = 0
    while ctypes.windll.kernel32.VirtualQueryEx(
        pm.process_handle, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)
    ):
        base = mbi.BaseAddress or 0
        if (
            mbi.State == MEM_COMMIT
            and (mbi.Protect & 0xFF) in WRITABLE
            and not (mbi.Protect & PAGE_GUARD)
        ):
            # regions can vanish mid-walk; skip unreadable ones
            with contextlib.suppress(Exception):
                regions.append(Region(base, pm.read_bytes(base, mbi.RegionSize)))
        addr = base + mbi.RegionSize
    return Snapshot(regions)


def parse_num(s: str, vtype: str) -> int | float:
    if vtype == "f64":
        return float(s)
    return int(s, 0)  # accepts decimal and 0x-hex


def main() -> int:  # noqa: PLR0912, PLR0915 - interactive command dispatch
    process_name = sys.argv[1] if len(sys.argv) > 1 else PROCESS
    RUNS.mkdir(exist_ok=True)

    import pymem

    try:
        pm = pymem.Pymem(process_name)
    except pymem.exception.ProcessNotFound:
        print(f"FAIL: process {process_name!r} not running. Start the game first.")
        return 1

    modules = {m.name: (m.lpBaseOfDll, m.SizeOfImage) for m in pm.list_modules()}
    print(f"Attached to {process_name} (pid {pm.process_id}), {len(modules)} modules.")
    print("Type a command (see module docstring); e.g.  = 99   after a fresh night starts.")

    vtype = "i32"
    candidates: dict[int, int | float] = {}

    def show(n: int = 30) -> None:
        print(f"{len(candidates)} candidate(s) [{vtype}]")
        for addr, val in list(candidates.items())[:n]:
            mod = annotate_module(addr, modules)
            print(f"  {addr:#010x} = {val}" + (f"   [{mod}]" if mod else ""))

    while True:
        try:
            line = input(f"scan[{vtype}:{len(candidates)}]> ").strip()
        except EOFError, KeyboardInterrupt:
            print()
            return 0
        if not line:
            continue
        cmd, *args = line.split()
        try:
            if cmd == "quit":
                return 0
            elif cmd == "reset":
                candidates = {}
            elif cmd == "type":
                if args[0] not in SCAN_TYPES:
                    print(f"types: {SCAN_TYPES}")
                    continue
                vtype, candidates = args[0], {}
            elif cmd == "=":
                target = parse_num(args[0], vtype)
                t0 = time.perf_counter()
                snap = take_snapshot(pm)
                if candidates:
                    candidates = narrow(candidates, snap, vtype, "eq", target)
                else:
                    candidates = snap.scan_equal(target, vtype)
                print(f"({time.perf_counter() - t0:.1f}s)")
                show()
            elif cmd in ("changed", "same", "inc", "dec"):
                mode = {"same": "unchanged"}.get(cmd, cmd)
                candidates = narrow(candidates, take_snapshot(pm), vtype, mode)
                show()
            elif cmd == "list":
                show(int(args[0]) if args else 30)
            elif cmd == "watch":
                addr = int(args[0], 0)
                read = {"i32": pm.read_int, "u8": pm.read_uchar, "f64": pm.read_double}[vtype]
                for _ in range(10):
                    print(f"  {addr:#010x} = {read(addr)}")
                    time.sleep(0.5)
            elif cmd == "write":
                addr, val = int(args[0], 0), parse_num(args[1], vtype)
                if vtype == "i32":
                    pm.write_int(addr, int(val))
                elif vtype == "u8":
                    pm.write_uchar(addr, int(val))
                else:
                    pm.write_double(addr, float(val))
                print(f"wrote {val} to {addr:#010x} — check the game reacted")
            elif cmd == "ptr":
                addr = int(args[0], 0)
                max_off = int(args[1], 0) if len(args) > 1 else 0x400
                hits = take_snapshot(pm).find_pointers_to(addr, max_off)
                statics = [(h, o) for h, o in hits if annotate_module(h, modules)]
                print(f"{len(hits)} holder(s), {len(statics)} static:")
                for holder, off in (statics or hits)[:30]:
                    mod = annotate_module(holder, modules)
                    label = f"[{mod}]" if mod else "(heap — run ptr on this holder)"
                    print(f"  holder {holder:#010x} offset {off:#x}   {label}")
            elif cmd == "save":
                out = RUNS / f"scan-{args[0]}.json"
                out.write_text(
                    json.dumps(
                        {
                            "process": process_name,
                            "type": vtype,
                            "candidates": {hex(a): v for a, v in candidates.items()},
                            "modules": {n: hex(b) for n, (b, _) in modules.items()},
                        },
                        indent=2,
                    )
                )
                print(f"saved {out}")
            else:
                print("unknown command — see the module docstring")
        except (IndexError, ValueError) as e:
            print(f"bad arguments: {e}")
        except Exception as e:  # noqa: BLE001 - keep the session alive
            print(f"ERROR {type(e).__name__}: {e}")


if __name__ == "__main__":
    sys.exit(main())
