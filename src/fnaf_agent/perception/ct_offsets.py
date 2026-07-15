"""
Clickteam Fusion 2.5 Runtime Offsets.
Extracted from CTFPV source.
All offsets assume a 32-bit (4-byte pointer) process.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CRunApp:
    """Offsets from the CRunApp block (starts with 'PAMU' magic)."""

    PRODUCT_BUILD = 0xC  # int — determines struct variant
    FRAME_COUNT = 0xC4  # int (verified from CRunApp.cs)
    OBJECT_INFO_MAX_INDEX = 0x190
    OBJECT_INFO_MAX_HANDLE = 0x194
    OBJECT_INFO_HANDLE_TO_INDEX = 0x198  # ptr → ushort[]
    OBJECT_INFOS = 0x19C  # ptr → ptr[] → CRunObjectInfo


@dataclass(frozen=True)
class CRunFrame:
    """Offsets from the CRunFrame block."""

    LEVEL_QUIT = 0x74
    OBJECTS = 0x8D0  # ptr → 8-byte-slot array
    MAX_OBJECTS = 0x8F0  # ushort


@dataclass(frozen=True)
class CRunObjectInfo:
    """Offsets from a CRunObjectInfo block."""

    HANDLE = 0x0  # ushort
    TYPE = 0x2  # ushort
    NAME = 0x10  # ptr → UTF-16LE string


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
    IDENTIFIER = 0xB4  # 4 bytes ascii ("SPRI", "CNTR", etc.)

    # Animation/Movement
    CURRENT_ANIMATION = 0xD8  # int
    CURRENT_FRAME = 0xDC  # int
    CURRENT_DIRECTION = 0xEC  # int


@dataclass(frozen=True)
class CRunActiveObject:
    """Offsets for Active Objects (Identifier "SPRI").
    Relative to the CRunObject base address."""

    ALTERABLE_VALUES_ARRAY = 0x242  # ptr → CRunValue[16 each]
    ALTERABLE_VALUES_COUNT = 0x246  # int
    ALTERABLE_STRINGS_ARRAY = 0x2C8  # ptr → ptr[]
    ALTERABLE_STRINGS_COUNT = 0x2CC  # int


@dataclass(frozen=True)
class CRunSystemObject:
    """Offsets for Counter/Lives/String objects.

    These use a version-dependent "OddOffset" base:
      build >= 292  →  OddOffset = 680 (0x2A8)
      build <  292  →  OddOffset = 506 (0x1FA)

    Value struct sits at obj_ptr + OddOffset + 8.
    For int counters the raw value is stored inverted:
      display_value = (-raw - 1)
    """

    # OddOffset values
    ODD_OFFSET_NEW = 0x2A8  # build >= 292
    ODD_OFFSET_OLD = 0x1FA  # build <  292

    # Offsets relative to (obj_ptr + OddOffset)
    OLD_LEVEL = 0x0  # int
    LEVEL = 0x4  # int
    VALUE_TYPE = 0x8  # int (CRunValue.Type)
    VALUE_DATA = 0x10  # int/double (CRunValue + 8)


@dataclass(frozen=True)
class CRunValue:
    """Offsets within a CRunValue block (16 bytes)."""

    TYPE = 0x0  # int: 0=int, 1=string, 2=double
    VALUE = 0x8  # int or float (4 bytes for alt-vals)

