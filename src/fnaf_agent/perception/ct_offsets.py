"""
Clickteam Fusion 2.5 Runtime Offsets.
Extracted from CTFPV source.
All offsets assume a 32-bit (4-byte pointer) process.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CRunApp:
    """Offsets from the CRunApp block (which starts with 'PAMU' magic)."""

    FRAME_COUNT = 0x14  # Unverified but likely standard.
    OBJECT_INFO_MAX_INDEX = 0x190
    OBJECT_INFO_MAX_HANDLE = 0x194
    OBJECT_INFO_HANDLE_TO_INDEX = 0x198  # pointer to array of ushort
    OBJECT_INFOS = 0x19C  # pointer to array of ptr to CRunObjectInfo


@dataclass(frozen=True)
class CRunFrame:
    """Offsets from the CRunFrame block."""

    LEVEL_QUIT = 0x74
    OBJECTS = (
        0x8D0  # pointer to array of elements (size 8, where first 4 bytes is pointer to CRunObject)
    )
    MAX_OBJECTS = 0x8F0


@dataclass(frozen=True)
class CRunObjectInfo:
    """Offsets from a CRunObjectInfo block."""

    HANDLE = 0x0  # ushort
    TYPE = 0x2  # ushort
    NAME = 0x10  # pointer to wide string (utf-16le)


@dataclass(frozen=True)
class CRunObject:
    """Offsets from a CRunObject block."""

    # Header
    NUMBER = 0x0  # short (Handle)
    NEXT = 0x2  # short
    SIZE = 0x4  # int
    OBJ_INFO_NUMBER = 0x12  # short (Object Info Handle)
    TYPE = 0x18  # short

    # Object
    X = 0x4C  # int
    Y = 0x54  # int
    WIDTH = 0x60  # int
    HEIGHT = 0x64  # int
    IDENTIFIER = 0xB4  # 4 bytes ascii (e.g., "SPRI", "TEXT")

    # Animation/Movement
    CURRENT_ANIMATION = 0xD8  # int
    CURRENT_FRAME = 0xDC  # int
    CURRENT_DIRECTION = 0xEC  # int


@dataclass(frozen=True)
class CRunActiveObject:
    """Offsets from a CRunActiveObject block (which is an extension of CRunObject).
    These offsets are relative to the SAME object pointer as CRunObject."""

    # Alterable Values array pointer
    # Memory structure: deref(obj_ptr + 0x242) gives pointer to array of CRunValue (size 16 each)
    ALTERABLE_VALUES_ARRAY = 0x242
    ALTERABLE_VALUES_COUNT = 0x246  # int count

    # Alterable Strings array pointer
    ALTERABLE_STRINGS_ARRAY = 0x2C8
    ALTERABLE_STRINGS_COUNT = 0x2CC  # int count


@dataclass(frozen=True)
class CRunValue:
    """Offsets from a CRunValue block (Size = 16 bytes)."""

    TYPE = 0x0  # int
    VALUE = 0x8  # int (or float depending on TYPE)
