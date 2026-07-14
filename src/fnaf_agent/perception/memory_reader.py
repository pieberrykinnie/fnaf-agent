"""MemoryStateReader: GameState from game-process memory (the MVP state source).

The reader is built on two pieces:

- MemoryAccess: a tiny protocol (module base lookup + typed reads). The live
  implementation wraps pymem; tests inject a dict-backed fake, so the whole
  pointer-chain and field-decoding path is unit-tested offline.
- MemoryMap: parsed from assets/memory_map.yaml, which the human-assisted
  Cheat Engine session fills in. Fields whose chain is still the TBD
  placeholder are skipped (reported via MemoryMap.unmapped), so the reader
  degrades gracefully while the map is incomplete.

Pointer chain semantics (standard Cheat Engine convention):
    base = module_base(module) + module_offset
    for each offset in offsets: base = read_ptr(base) + offset
    value = read_<type>(base)
An empty offsets list means a static address at module_base + module_offset.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import yaml

from fnaf_agent.state import Camera, GameState

VALUE_TYPES = ("i32", "u8", "f64", "bool")


class MemoryAccess(Protocol):
    """The minimal surface MemoryStateReader needs from a process."""

    def module_base(self, module: str) -> int: ...

    def read_ptr(self, address: int) -> int: ...

    def read_i32(self, address: int) -> int: ...

    def read_u8(self, address: int) -> int: ...

    def read_f64(self, address: int) -> float: ...


@dataclass(frozen=True)
class PointerChain:
    module: str
    module_offset: int
    offsets: tuple[int, ...] = ()

    def resolve(self, mem: MemoryAccess) -> int:
        addr = mem.module_base(self.module) + self.module_offset
        for off in self.offsets:
            addr = mem.read_ptr(addr) + off
        return addr


@dataclass(frozen=True)
class FieldSpec:
    name: str
    type: str  # one of VALUE_TYPES
    chain: PointerChain
    enum_map: dict[int, str] = field(default_factory=dict)  # raw value -> label

    def read(self, mem: MemoryAccess) -> Any:
        addr = self.chain.resolve(mem)
        if self.type == "i32":
            raw: Any = mem.read_i32(addr)
        elif self.type == "u8":
            raw = mem.read_u8(addr)
        elif self.type == "f64":
            raw = mem.read_f64(addr)
        elif self.type == "bool":
            raw = mem.read_i32(addr) != 0
        else:  # pragma: no cover - blocked by MemoryMap validation
            raise ValueError(f"unknown field type {self.type!r}")
        if self.enum_map:
            return self.enum_map.get(int(raw))
        return raw


@dataclass
class MemoryMap:
    process: str
    fields: dict[str, FieldSpec]
    unmapped: list[str]  # field names still waiting on the Cheat Engine session

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> MemoryMap:
        fields: dict[str, FieldSpec] = {}
        unmapped: list[str] = []
        for name, spec in (d.get("fields") or {}).items():
            if spec is None or spec.get("chain") is None:
                unmapped.append(name)
                continue
            vtype = spec.get("type", "i32")
            if vtype not in VALUE_TYPES:
                raise ValueError(f"field {name!r}: unknown type {vtype!r} (use {VALUE_TYPES})")
            chain = spec["chain"]
            fields[name] = FieldSpec(
                name=name,
                type=vtype,
                chain=PointerChain(
                    module=chain.get("module", d["process"]),
                    module_offset=int(chain["module_offset"]),
                    offsets=tuple(int(o) for o in chain.get("offsets", [])),
                ),
                enum_map={int(k): str(v) for k, v in (spec.get("enum_map") or {}).items()},
            )
        return cls(process=d["process"], fields=fields, unmapped=sorted(unmapped))

    @classmethod
    def from_yaml(cls, path: Path) -> MemoryMap:
        return cls.from_dict(yaml.safe_load(path.read_text(encoding="utf-8")))


# GameState attributes the map may provide, and how to coerce the raw value.
_INT_FIELDS = ("night", "hour", "power", "usage_bars")
_BOOL_FIELDS = (
    "door_left_closed",
    "door_right_closed",
    "light_left_on",
    "light_right_on",
    "monitor_up",
)


class MemoryStateReader:
    """Reads every mapped field and assembles a GameState.

    Unmapped fields stay None on the GameState — the phash screen classifier
    and later tiers fill in what memory can't (screen type, jumpscares).
    """

    def __init__(self, mem: MemoryAccess, memory_map: MemoryMap) -> None:
        self.mem = mem
        self.map = memory_map

    def read(self) -> GameState:
        state = GameState()
        for name, spec in self.map.fields.items():
            value = spec.read(self.mem)
            if name in _INT_FIELDS:
                setattr(state, name, int(value) if value is not None else None)
            elif name in _BOOL_FIELDS:
                setattr(state, name, bool(value))
            elif name == "active_camera":
                state.active_camera = Camera(value) if value is not None else None
            # unknown extra fields are read (validates the chain) but not mapped
        return state


class PymemAccess:
    """Live MemoryAccess over pymem. Import-light so pytest stays offline."""

    def __init__(self, process_name: str) -> None:
        import pymem

        self._pm = pymem.Pymem(process_name)
        self._modules = {m.name.lower(): m.lpBaseOfDll for m in self._pm.list_modules()}

    def module_base(self, module: str) -> int:
        try:
            return self._modules[module.lower()]
        except KeyError:
            raise KeyError(f"module {module!r} not loaded; have {sorted(self._modules)}") from None

    def read_ptr(self, address: int) -> int:
        # FNAF 1 is a 32-bit Clickteam executable: pointers are 4 bytes.
        return self._pm.read_uint(address)

    def read_i32(self, address: int) -> int:
        return self._pm.read_int(address)

    def read_u8(self, address: int) -> int:
        return self._pm.read_uchar(address)

    def read_f64(self, address: int) -> float:
        return self._pm.read_double(address)
