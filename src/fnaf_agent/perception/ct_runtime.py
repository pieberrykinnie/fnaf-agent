"""Clickteam Fusion 2.5 runtime memory traversal.

Ported from CTFPV (C#) to Python/pymem.  The entry point is CTFRuntime,
which attaches to a running CF 2.5 process, locates the global pointer
table via the "PAMU" magic-byte signature, and exposes the runtime's
object tree (names, alterable values, positions).
"""

import struct
from typing import Any

import pymem
import pymem.pattern
import pymem.process

from fnaf_agent.perception.ct_offsets import (
    CRunActiveObject,
    CRunApp,
    CRunFrame,
    CRunObject,
    CRunObjectInfo,
    CRunSystemObject,
    CRunValue,
)


class CTFMemoryError(Exception):
    pass


def _read_wide_string(
    pm: pymem.Pymem, ptr: int, max_chars: int = 256
) -> str:
    """Read a null-terminated UTF-16LE string from *ptr*."""
    raw = bytearray()
    for i in range(max_chars):
        c = pm.read_bytes(ptr + i * 2, 2)
        if c == b"\x00\x00":
            break
        raw.extend(c)
    return raw.decode("utf-16le", errors="replace")


class CTFValue:
    """Represents an alterable value (int or float)."""

    def __init__(self, val_type: int, raw_bytes: bytes):
        self.val_type = val_type
        self.raw_bytes = raw_bytes

    @property
    def value(self) -> Any:
        # CF 2.5 type codes: 0 = int, 2 = float
        if self.val_type == 2:
            return struct.unpack("<f", self.raw_bytes)[0]
        return struct.unpack("<i", self.raw_bytes)[0]

    def __repr__(self):
        return f"CTFValue(type={self.val_type}, val={self.value})"


class CTFObject:
    """A live CRunObject handle with lazy field reads."""

    def __init__(
        self,
        pm: pymem.Pymem,
        addr: int,
        info_name: str,
        handle: int,
        odd_offset: int = CRunSystemObject.ODD_OFFSET_NEW,
    ):
        self.pm = pm
        self._odd_offset = odd_offset
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
        """Read alterable values (Active Objects only)."""
        try:
            array_ptr = self.pm.read_int(
                self.addr + CRunActiveObject.ALTERABLE_VALUES_ARRAY
            )
            if array_ptr == 0:
                return []

            count = self.pm.read_int(
                self.addr + CRunActiveObject.ALTERABLE_VALUES_COUNT
            )
            if count <= 0 or count > 1000:
                return []

            # Each CRunValue is 16 bytes: +0 Type(int), +8 Value
            values = []
            for i in range(count):
                base = array_ptr + i * 16
                val_type = self.pm.read_int(base + CRunValue.TYPE)
                raw_val = self.pm.read_bytes(base + CRunValue.VALUE, 4)
                values.append(CTFValue(val_type, raw_val))
            return values
        except Exception:
            return []

    def read_alterable_strings(self) -> list[str]:
        """Read alterable strings (Active Objects only)."""
        try:
            array_ptr = self.pm.read_int(
                self.addr + CRunActiveObject.ALTERABLE_STRINGS_ARRAY
            )
            if array_ptr == 0:
                return []

            count = self.pm.read_int(
                self.addr + CRunActiveObject.ALTERABLE_STRINGS_COUNT
            )
            if count <= 0 or count > 1000:
                return []

            strings = []
            for i in range(count):
                str_ptr = self.pm.read_int(array_ptr + i * 4)
                if str_ptr == 0:
                    strings.append("")
                else:
                    strings.append(_read_wide_string(self.pm, str_ptr))
            return strings
        except Exception:
            return []

    @property
    def identifier(self) -> str:
        """4-byte ASCII tag: SPRI, CNTR, LIVE, TEXT, etc."""
        raw = self.pm.read_bytes(
            self.addr + CRunObject.IDENTIFIER, 4
        )
        return raw.decode("ascii", errors="replace").rstrip("\x00")

    def read_counter_value(self) -> int | float | None:
        """Read the value of a Counter/Lives object.

        Returns the display value (int counters are stored
        inverted: display = -raw - 1).
        Returns None if this is not a counter object.
        """
        try:
            ident = self.identifier
            if ident not in (
                "CNTR", "LIVE", "CN",
                # some builds use 2-char tags
            ):
                return None

            base = self.addr + self._odd_offset
            val_type = self.pm.read_int(
                base + CRunSystemObject.VALUE_TYPE
            )

            if val_type == 0:  # int
                raw = self.pm.read_int(
                    base + CRunSystemObject.VALUE_DATA
                )
                return (-raw) - 1
            elif val_type == 2:  # double
                raw_bytes = self.pm.read_bytes(
                    base + CRunSystemObject.VALUE_DATA, 8
                )
                return struct.unpack("<d", raw_bytes)[0]
            else:
                return None
        except Exception:
            return None

    def __repr__(self):
        return (
            f"<CTFObject '{self.name}' "
            f"@ {hex(self.addr)} (H:{self.handle})>"
        )


class CTFRuntime:
    """Clickteam Fusion 2.5 Runtime Memory Interface.

    Memory layout at the global pointer table (3 consecutive 4-byte ptrs):
        [_global_ptr_addr + 0]  →  CRunApp struct
        [_global_ptr_addr + 4]  →  CRunFrame struct
        [_global_ptr_addr + 8]  →  CRunHeader struct
    """

    def __init__(
        self, process_name: str = "FiveNightsatFreddys.exe"
    ):
        self.pm = pymem.Pymem(process_name)
        mod = pymem.process.module_from_name(
            self.pm.process_handle, process_name
        )
        self.base_address = mod.lpBaseOfDll
        self._global_ptr_addr = self._find_global_pointer()
        if not self._global_ptr_addr:
            raise CTFMemoryError(
                "Could not locate CRunApp (PAMU header) in memory."
            )

    # -- properties that dereference the global pointer table -----------

    @property
    def crunapp_addr(self) -> int:
        """Address of the CRunApp struct (deref'd from global ptr)."""
        return self.pm.read_int(self._global_ptr_addr)

    @property
    def product_build(self) -> int:
        """CF2.5 ProductBuild — determines struct variant."""
        return self.pm.read_int(
            self.crunapp_addr + CRunApp.PRODUCT_BUILD
        )

    @property
    def odd_offset(self) -> int:
        """Version-dependent offset for counter objects."""
        if self.product_build >= 292:
            return CRunSystemObject.ODD_OFFSET_NEW
        return CRunSystemObject.ODD_OFFSET_OLD

    @property
    def crunframe_addr(self) -> int:
        """Address of the CRunFrame struct (deref'd from global ptr+4)."""
        return self.pm.read_int(self._global_ptr_addr + 4)

    # -- bootstrap: find the global pointer table ----------------------

    def _robust_pattern_scan(self, pattern: bytes) -> list[int]:
        """Safely scan process memory, ignoring partial copy errors (299)."""
        import sys

        matches = []
        user_space_limit = 0x7FFFFFFF0000 if sys.maxsize > 2**32 else 0x7fff0000
        next_region = 0

        while next_region < user_space_limit:
            try:
                mbi = pymem.memory.virtual_query(
                    self.pm.process_handle, next_region
                )
            except Exception:
                break

            next_region = mbi.BaseAddress + mbi.RegionSize

            allowed_protections = [
                pymem.ressources.structure.MEMORY_PROTECTION.PAGE_EXECUTE,
                pymem.ressources.structure.MEMORY_PROTECTION.PAGE_EXECUTE_READ,
                pymem.ressources.structure.MEMORY_PROTECTION.PAGE_EXECUTE_READWRITE,
                pymem.ressources.structure.MEMORY_PROTECTION.PAGE_READWRITE,
                pymem.ressources.structure.MEMORY_PROTECTION.PAGE_READONLY,
            ]
            if (
                mbi.state != pymem.ressources.structure.MEMORY_STATE.MEM_COMMIT
                or mbi.protect not in allowed_protections
            ):
                continue

            try:
                page_bytes = self.pm.read_bytes(
                    mbi.BaseAddress, mbi.RegionSize
                )
            except Exception:
                continue

            idx = -1
            while True:
                idx = page_bytes.find(pattern, idx + 1)
                if idx == -1:
                    break
                matches.append(mbi.BaseAddress + idx)

        return matches

    def _find_global_pointer(self) -> int:
        """Locate the global pointer table by scanning for PAMU magic.

        Algorithm (mirroring CTFPV):
        1. AoB-scan for "PAMU" + version 0x0302  →  PAMU header address.
        2. AoB-scan for the 4-byte LE representation of that address →
           candidate global pointers.
        3. Filter to pointers within the first 1 MB of the module, and
           validate that dereferencing them yields the PAMU header.
        """
        magic_pattern = b"PAMU\x02\x03\x00\x00"
        matches = self._robust_pattern_scan(magic_pattern)
        if not matches:
            return 0

        for magic_addr in matches:
            addr_bytes = struct.pack("<I", magic_addr)
            ptr_matches = self._robust_pattern_scan(addr_bytes)
            for ptr in ptr_matches:
                offset = ptr - self.base_address
                if not (0 <= offset <= 1_048_576):
                    continue
                # Validate: deref should point back to PAMU
                try:
                    check = self.pm.read_bytes(
                        self.pm.read_int(ptr), 4
                    )
                    if check == b"PAMU":
                        return ptr
                except Exception:
                    continue
        return 0

    # -- object enumeration -------------------------------------------

    def get_object_infos(self) -> dict[int, str]:
        """Read the ObjectInfo table.  Returns {handle: name}."""
        app = self.crunapp_addr

        max_handle = self.pm.read_int(
            app + CRunApp.OBJECT_INFO_MAX_HANDLE
        )
        h2i_ptr = self.pm.read_int(
            app + CRunApp.OBJECT_INFO_HANDLE_TO_INDEX
        )
        infos_ptr = self.pm.read_int(app + CRunApp.OBJECT_INFOS)

        result: dict[int, str] = {}
        for i in range(max_handle):
            idx = struct.unpack(
                "<H", self.pm.read_bytes(h2i_ptr + i * 2, 2)
            )[0]

            info_ptr = self.pm.read_int(infos_ptr + idx * 4)
            if info_ptr == 0:
                continue

            name_ptr = self.pm.read_int(
                info_ptr + CRunObjectInfo.NAME
            )
            if name_ptr == 0:
                continue

            result[i] = _read_wide_string(self.pm, name_ptr)

        return result

    def enumerate_objects(self) -> list[CTFObject]:
        """Enumerate all active CRunObjects in the current frame."""
        frame = self.crunframe_addr
        if frame == 0:
            return []

        max_objects = struct.unpack(
            "<H", self.pm.read_bytes(frame + CRunFrame.MAX_OBJECTS, 2)
        )[0]
        obj_array = self.pm.read_int(frame + CRunFrame.OBJECTS)
        if obj_array == 0:
            return []

        try:
            infos = self.get_object_infos()
        except Exception:
            infos = {}

        objects: list[CTFObject] = []
        for i in range(max_objects):
            # 8-byte slots: [ptr_to_CRunObject | 4-byte pad]
            obj_ptr = self.pm.read_int(obj_array + i * 8)
            if obj_ptr == 0:
                continue

            handle = struct.unpack(
                "<h",
                self.pm.read_bytes(obj_ptr + CRunObject.NUMBER, 2),
            )[0]
            oi_handle = struct.unpack(
                "<h",
                self.pm.read_bytes(
                    obj_ptr + CRunObject.OBJ_INFO_NUMBER, 2
                ),
            )[0]

            name = infos.get(
                oi_handle, f"Unknown_{oi_handle}"
            )
            objects.append(
                CTFObject(
                    self.pm,
                    obj_ptr,
                    name,
                    handle,
                    odd_offset=self.odd_offset,
                )
            )

        return objects
