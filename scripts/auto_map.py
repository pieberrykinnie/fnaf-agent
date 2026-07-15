"""Enumerate all Clickteam Fusion objects in a live FNAF 1 session.

Prints:
  1. Active Objects with non-trivial alterable values.
  2. Counter/Lives objects with their numeric values.
  3. Full object name list with positions.
"""

import contextlib
import sys

from fnaf_agent.perception.ct_runtime import CTFRuntime


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print(
        "Initializing CTF Runtime "
        "(Make sure Five Nights at Freddy's is running)..."
    )
    try:
        runtime = CTFRuntime("FiveNightsatFreddys.exe")
    except Exception as e:
        print(f"Failed to attach to process: {e}")
        return

    print("Attached successfully!")
    print(f"Global Pointer Table : {hex(runtime._global_ptr_addr)}")
    print(f"  CRunApp  struct    @ {hex(runtime.crunapp_addr)}")
    print(f"  CRunFrame struct   @ {hex(runtime.crunframe_addr)}")
    print(f"  ProductBuild       = {runtime.product_build}")
    print(f"  OddOffset          = {hex(runtime.odd_offset)}")

    try:
        objects = runtime.enumerate_objects()
    except Exception as e:
        print(f"Failed to enumerate objects: {e}")
        import traceback

        traceback.print_exc()
        return

    print(f"\nFound {len(objects)} active objects.")

    # --- Active Objects with alterable values ---
    print("\n=== Active Objects with Alterable Values ===")
    for obj in objects:
        try:
            vals = obj.read_alterable_values()
            if not vals:
                continue
            # Only print if at least one value is non-zero
            if not any(v.value != 0 for v in vals):
                continue
            parts = [f"[{i}]={v.value}" for i, v in enumerate(vals)]
            print(
                f"  H:{obj.handle:4} | "
                f"{obj.name:<30} | {', '.join(parts)}"
            )
        except Exception:
            pass

    # --- Counter / Lives objects ---
    print("\n=== Counter / Lives Objects ===")
    for obj in objects:
        try:
            cv = obj.read_counter_value()
            if cv is not None:
                print(
                    f"  H:{obj.handle:4} | "
                    f"{obj.name:<30} | value = {cv}"
                )
        except Exception:
            pass

    # --- Full object list ---
    print("\n=== All Objects ===")
    for obj in objects:
        ident = ""
        with contextlib.suppress(Exception):
            ident = obj.identifier
        print(
            f"  H:{obj.handle:4}  "
            f"[{ident:<4}]  "
            f"{obj.name:<30}  "
            f"({obj.x}, {obj.y})"
        )


if __name__ == "__main__":
    main()
