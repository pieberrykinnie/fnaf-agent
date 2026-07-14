import struct
from typing import Any

import pymem
import pymem.process

from fnaf_agent.perception.ct_offsets import (
    CRunActiveObject,
    CRunApp,
    CRunFrame,
    CRunObject,
    CRunObjectInfo,
    CRunValue,
)


class CTFMemoryError(Exception):
    pass


class CTFValue:
    """Represents an alterable value (int or float)."""

    def __init__(self, val_type: int, raw_bytes: bytes):
        self.val_type = val_type
        # In CF 2.5: Type 0 = int, 1 = string?, 2 = float
        # Actually in CTFPV:
        # if val.Type == 1 -> ActionType = 5 (string?)
        # if val.Type == 2 -> ActionType = 4 (float?)
        # Let's handle 0 as int and 2 as float, or just return raw.
        # Wait, usually values are int or float.
        self.raw_bytes = raw_bytes

    @property
    def value(self) -> Any:
        if self.val_type == 2:
            return struct.unpack("<f", self.raw_bytes)[0]
        else:
            return struct.unpack("<i", self.raw_bytes)[0]

    def __repr__(self):
        return f"CTFValue(type={self.val_type}, val={self.value})"


class CTFObject:
    def __init__(self, pm: pymem.Pymem, addr: int, info_name: str, handle: int):
        self.pm = pm
        self.addr = addr
        self.name = info_name
        self.handle = handle

    @property
    def x(self) -> int:
        return self.pm.read_int(self.addr + CRunObject.X)

    @property
    def y(self) -> int:
        return self.pm.read_int(self.addr + CRunObject.Y)

    def read_alterable_values(self) -> list[CTFValue]:
        """Read alterable values (applicable mostly to Active Objects)."""
        try:
            # deref(obj_ptr + 0x242) -> array of CRunValue
            array_ptr = self.pm.read_int(self.addr + CRunActiveObject.ALTERABLE_VALUES_ARRAY)
            if array_ptr == 0:
                return []

            count = self.pm.read_int(self.addr + CRunActiveObject.ALTERABLE_VALUES_COUNT)
            if count <= 0 or count > 1000:
                return []

            # Each CRunValue is 16 bytes:
            # +0x0: Type (int)
            # +0x8: Value (int or float)
            values = []
            for i in range(count):
                element_addr = array_ptr + (i * 16)
                val_type = self.pm.read_int(element_addr + CRunValue.TYPE)
                raw_val = self.pm.read_bytes(element_addr + CRunValue.VALUE, 4)
                values.append(CTFValue(val_type, raw_val))
            return values
        except Exception:
            return []

    def read_alterable_strings(self) -> list[str]:
        """Read alterable strings."""
        try:
            array_ptr = self.pm.read_int(self.addr + CRunActiveObject.ALTERABLE_STRINGS_ARRAY)
            if array_ptr == 0:
                return []

            count = self.pm.read_int(self.addr + CRunActiveObject.ALTERABLE_STRINGS_COUNT)
            if count <= 0 or count > 1000:
                return []

            strings = []
            for i in range(count):
                # array_ptr points to array of pointers to wide strings
                str_ptr = self.pm.read_int(array_ptr + (i * 4))
                if str_ptr == 0:
                    strings.append("")
                else:
                    # Read wide string
                    # Read until null terminator (2 null bytes)
                    raw = []
                    while True:
                        c = self.pm.read_bytes(str_ptr + len(raw), 2)
                        if c == b"\x00\x00":
                            break
                        raw.append(c)
                        if len(raw) > 256:  # sanity limit
                            break
                    strings.append(b"".join(raw).decode("utf-16le", errors="replace"))
            return strings
        except Exception:
            return []

    def __repr__(self):
        return f"<CTFObject '{self.name}' @ {hex(self.addr)} (H:{self.handle})>"


class CTFRuntime:
    """Clickteam Fusion 2.5 Runtime Memory Interface."""

    def __init__(self, process_name: str = "FiveNightsatFreddys.exe"):
        self.pm = pymem.Pymem(process_name)
        self.base_address = pymem.process.module_from_name(
            self.pm.process_handle, process_name
        ).lpBaseOfDll
        self.crunapp_addr = self._find_crunapp()
        if not self.crunapp_addr:
            raise CTFMemoryError("Could not locate CRunApp (PAMU header) in memory.")

    def _find_crunapp(self) -> int:
        """Finds the main CRunApp struct pointer by pattern scanning."""
        # 1. Find "PAMU" magic byte
        # CTFPV uses PAMU exactly. Let's scan for PAMU.
        magic_pattern = b"PAMU\x02\x03\x00\x00"
        # We can also just search for PAMU, but PAMU\x02\x03\x00\x00 is safer.
        matches = pymem.pattern.pattern_scan_all(
            self.pm.process_handle, magic_pattern, return_multiple=True
        )
        if not matches:
            # Fallback: try just PAMU if we need to. But usually it's this.
            return 0

        # For each match, CTFPV checks if (match + 4) == 770 (0x0302).
        # We already included \x02\x03 in the pattern! So `matches` are valid PAMU headers.

        # 2. Find pointers to the PAMU header
        # CF 2.5 stores a global pointer to CRunApp in the heap/BSS.
        # CTFPV scans for pointers that point to the PAMU header.
        for magic_addr in matches:
            addr_bytes = struct.pack("<I", magic_addr)
            ptr_matches = pymem.pattern.pattern_scan_all(
                self.pm.process_handle, addr_bytes, return_multiple=True
            )
            for ptr in ptr_matches:
                # Calculate relative offset
                offset = ptr - self.base_address
                if 0 <= offset <= 1048576:  # CTFPV constraint
                    # Found the global main pointer!
                    # The pointer points to CRunApp.
                    return ptr
        return 0

    @property
    def crunframe_addr(self) -> int:
        # MainPointer + 4 points to CRunFrame
        return self.pm.read_int(self.crunapp_addr + 4)

    def get_object_infos(self) -> dict:
        """Reads the ObjectInfo array. Returns dict of handle -> name."""
        app_ptr = self.pm.read_int(self.crunapp_addr)

        max_handle = self.pm.read_int(app_ptr + CRunApp.OBJECT_INFO_MAX_HANDLE)
        handle_to_index_ptr = self.pm.read_int(app_ptr + CRunApp.OBJECT_INFO_HANDLE_TO_INDEX)
        infos_ptr = self.pm.read_int(app_ptr + CRunApp.OBJECT_INFOS)

        handle_to_name = {}

        for i in range(max_handle):
            # Read index from short array
            index = struct.unpack("<H", self.pm.read_bytes(handle_to_index_ptr + (i * 2), 2))[0]

            # Read info pointer
            info_ptr = self.pm.read_int(infos_ptr + (index * 4))
            if info_ptr == 0:
                continue

            # Read name
            name_ptr = self.pm.read_int(info_ptr + CRunObjectInfo.NAME)
            if name_ptr == 0:
                continue

            # Read wide string
            raw = []
            while True:
                c = self.pm.read_bytes(name_ptr + len(raw), 2)
                if c == b"\x00\x00":
                    break
                raw.append(c)
                if len(raw) > 256:  # sanity limit
                    break
            name = b"".join(raw).decode("utf-16le", errors="replace")

            # Note: CRunObjectInfo also has HANDLE at +0. We can verify it matches i.
            handle_to_name[i] = name

        return handle_to_name

    def enumerate_objects(self) -> list[CTFObject]:
        """Enumerates all active objects in the current frame."""
        frame_ptr = self.pm.read_int(self.crunframe_addr)
        if frame_ptr == 0:
            return []

        max_objects = struct.unpack("<H", self.pm.read_bytes(frame_ptr + CRunFrame.MAX_OBJECTS, 2))[
            0
        ]
        objects_array_ptr = self.pm.read_int(frame_ptr + CRunFrame.OBJECTS)
        if objects_array_ptr == 0:
            return []

        # We need ObjectInfos to map handles to names
        try:
            infos = self.get_object_infos()
        except Exception:
            infos = {}

        objects = []
        for i in range(max_objects):
            # Array of 8-byte elements. First 4 bytes is pointer.
            obj_ptr = self.pm.read_int(objects_array_ptr + (i * 8))
            if obj_ptr == 0:
                continue

            # Read object header
            handle = struct.unpack("<h", self.pm.read_bytes(obj_ptr + CRunObject.NUMBER, 2))[0]
            obj_info_handle = struct.unpack(
                "<h", self.pm.read_bytes(obj_ptr + CRunObject.OBJ_INFO_NUMBER, 2)
            )[0]

            name = infos.get(obj_info_handle, f"Unknown_{obj_info_handle}")

            objects.append(CTFObject(self.pm, obj_ptr, name, handle))

        return objects
