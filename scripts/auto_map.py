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
    print(
        f"Global Pointer Table: "
        f"{hex(runtime._global_ptr_addr)}"
    )
    print(f"  CRunApp  struct @ {hex(runtime.crunapp_addr)}")
    print(f"  CRunFrame struct @ {hex(runtime.crunframe_addr)}")

    try:
        objects = runtime.enumerate_objects()
    except Exception as e:
        print(f"Failed to enumerate objects: {e}")
        import traceback

        traceback.print_exc()
        return

    print(f"\nFound {len(objects)} active objects.")

    print("\n--- Objects with Alterable Values ---")
    for obj in objects:
        try:
            vals = obj.read_alterable_values()
            if vals:
                parts = [
                    f"[{i}]={v.value}" for i, v in enumerate(vals)
                ]
                val_str = ", ".join(parts)
                print(
                    f"H:{obj.handle:4} | "
                    f"{obj.name:<30} | {val_str}"
                )
        except Exception:
            pass

    print("\n--- All Objects (name list) ---")
    for obj in objects:
        print(
            f"  H:{obj.handle:4}  "
            f"Name={obj.name:<30}  "
            f"Pos=({obj.x}, {obj.y})"
        )


if __name__ == "__main__":
    main()
