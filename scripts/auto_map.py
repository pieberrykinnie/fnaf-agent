import sys

from fnaf_agent.perception.ct_runtime import CTFRuntime


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("Initializing CTF Runtime (Make sure Five Nights at Freddy's is running)...")
    try:
        runtime = CTFRuntime("FiveNightsatFreddys.exe")
    except Exception as e:
        print(f"Failed to attach to process: {e}")
        return

    print("Attached successfully!")
    print(f"CRunApp Pointer: {hex(runtime.crunapp_addr)}")
    print(f"CRunFrame Pointer: {hex(runtime.crunframe_addr)}")

    try:
        objects = runtime.enumerate_objects()
    except Exception as e:
        print(f"Failed to enumerate objects: {e}")
        return

    print(f"\nFound {len(objects)} active objects.")

    # We want to find specific FNAF state objects like doors, lights, monitor.
    # We'll print all objects that have alterable values.
    # FNAF 1 objects of interest usually have Alterable Values for state.

    # Optional: we can filter out common background objects to reduce noise
    print("\n--- Objects with Alterable Values ---")
    for obj in objects:
        try:
            # Only print objects that might be interesting
            # Often, active objects with names like 'DoorLeft', 'Monitor', etc.
            vals = obj.read_alterable_values()
            if vals:
                # Format values
                val_str = ", ".join(
                    [f"[{i}]={v.value}" for i, v in enumerate(vals) if v.value != 0]
                )
                if not val_str:
                    val_str = "All Zeros"
                print(f"Handle: {obj.handle:4} | Name: {obj.name:<30} | Vals: {val_str}")

        except Exception:
            pass


if __name__ == "__main__":
    main()
