"""Phase M1 probe: attach to the running game with pymem, dump the module
list with base addresses, and confirm read access.

Also resolves and reads every mapped field in assets/memory_map.yaml (if any
are filled in yet), so this doubles as the post-Cheat-Engine sanity check.

Usage: uv run python scripts/attach_probe.py [process-name]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROCESS = "FiveNightsatFreddys.exe"
RUNS = ROOT / "runs"

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    process_name = sys.argv[1] if len(sys.argv) > 1 else PROCESS
    RUNS.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")

    import pymem

    from fnaf_agent.perception.memory_reader import MemoryMap, PymemAccess

    try:
        pm = pymem.Pymem(process_name)
    except pymem.exception.ProcessNotFound:
        print(f"FAIL: process {process_name!r} not running. Start the game first.")
        return 1

    meta: dict = {"timestamp": stamp, "process": process_name, "pid": pm.process_id, "modules": []}
    for m in pm.list_modules():
        meta["modules"].append({"name": m.name, "base": hex(m.lpBaseOfDll), "size": m.SizeOfImage})

    # Confirm read access: read the PE signature at the main module base.
    main_base = meta["modules"][0]
    raw = pm.read_bytes(int(main_base["base"], 16), 2)
    meta["read_access"] = raw == b"MZ"
    if not meta["read_access"]:
        print(f"FAIL: read at {main_base['base']} returned {raw!r}, expected b'MZ'")

    # If the memory map has any chains filled in, resolve and read them all.
    map_path = ROOT / "assets" / "memory_map.yaml"
    memory_map = MemoryMap.from_yaml(map_path)
    meta["unmapped_fields"] = memory_map.unmapped
    meta["mapped_values"] = {}
    if memory_map.fields:
        access = PymemAccess(process_name)
        for name, spec in memory_map.fields.items():
            try:
                meta["mapped_values"][name] = spec.read(access)
            except Exception as e:  # noqa: BLE001 - report per-field, keep probing
                meta["mapped_values"][name] = f"ERROR {type(e).__name__}: {e}"

    out = RUNS / f"attach-{stamp}.json"
    out.write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))
    ok = meta["read_access"]
    print(f"\n{'OK' if ok else 'FAIL'}: metadata at {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
