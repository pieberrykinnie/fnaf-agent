"""Offline tests for MemoryStateReader: pointer chains, field decoding, and
the memory_map.yaml schema — all against a dict-backed fake process."""

from pathlib import Path

import pytest

from fnaf_agent.perception.memory_reader import (
    FieldSpec,
    MemoryMap,
    MemoryStateReader,
    PointerChain,
)
from fnaf_agent.state import Camera

REPO = Path(__file__).resolve().parent.parent.parent


class FakeMemory:
    """MemoryAccess backed by dicts: {address: value} per type."""

    def __init__(
        self,
        modules: dict[str, int],
        pointers: dict[int, int] | None = None,
        i32: dict[int, int] | None = None,
        u8: dict[int, int] | None = None,
        f64: dict[int, float] | None = None,
    ) -> None:
        self.modules = {k.lower(): v for k, v in modules.items()}
        self.pointers = pointers or {}
        self.i32 = i32 or {}
        self.u8 = u8 or {}
        self.f64 = f64 or {}

    def module_base(self, module: str) -> int:
        return self.modules[module.lower()]

    def read_ptr(self, address: int) -> int:
        return self.pointers[address]

    def read_i32(self, address: int) -> int:
        return self.i32[address]

    def read_u8(self, address: int) -> int:
        return self.u8[address]

    def read_f64(self, address: int) -> float:
        return self.f64[address]


GAME = "FiveNightsatFreddys.exe"
BASE = 0x400000


def test_static_address_resolution() -> None:
    chain = PointerChain(module=GAME, module_offset=0x1234)
    mem = FakeMemory(modules={GAME: BASE})
    assert chain.resolve(mem) == BASE + 0x1234


def test_pointer_chain_resolution() -> None:
    # base+0x4B2E8 -> [.]+0x654 -> [.]+0x30
    chain = PointerChain(module=GAME, module_offset=0x4B2E8, offsets=(0x654, 0x30))
    mem = FakeMemory(
        modules={GAME: BASE},
        pointers={BASE + 0x4B2E8: 0x0A000000, 0x0A000654: 0x0B000000},
        i32={0x0B000030: 87},
    )
    assert chain.resolve(mem) == 0x0B000030
    spec = FieldSpec(name="power", type="i32", chain=chain)
    assert spec.read(mem) == 87


def test_field_types_and_enum_map() -> None:
    mem = FakeMemory(
        modules={GAME: BASE},
        i32={BASE + 0x10: 3, BASE + 0x20: 1},
        u8={BASE + 0x30: 5},
        f64={BASE + 0x40: 42.5},
    )
    cam = FieldSpec(
        name="active_camera",
        type="i32",
        chain=PointerChain(GAME, 0x10),
        enum_map={3: "1C", 4: "2A"},
    )
    assert cam.read(mem) == "1C"
    assert FieldSpec("monitor_up", "bool", PointerChain(GAME, 0x20)).read(mem) is True
    assert FieldSpec("usage", "u8", PointerChain(GAME, 0x30)).read(mem) == 5
    assert FieldSpec("timer", "f64", PointerChain(GAME, 0x40)).read(mem) == 42.5


def test_enum_map_unknown_raw_value_is_none() -> None:
    mem = FakeMemory(modules={GAME: BASE}, i32={BASE + 0x10: 99})
    spec = FieldSpec("active_camera", "i32", PointerChain(GAME, 0x10), enum_map={0: "1A"})
    assert spec.read(mem) is None


def test_memory_map_from_dict_skips_unmapped_and_validates() -> None:
    d = {
        "process": GAME,
        "fields": {
            "power": {"type": "i32", "chain": {"module_offset": 0x10}},
            "hour": {"type": "i32", "chain": None},
            "night": None,
        },
    }
    m = MemoryMap.from_dict(d)
    assert set(m.fields) == {"power"}
    assert m.unmapped == ["hour", "night"]
    assert m.fields["power"].chain.module == GAME  # module defaults to process

    with pytest.raises(ValueError, match="unknown type"):
        MemoryMap.from_dict(
            {"process": GAME, "fields": {"x": {"type": "i64", "chain": {"module_offset": 0}}}}
        )


def test_reader_assembles_gamestate() -> None:
    mem = FakeMemory(
        modules={GAME: BASE},
        i32={
            BASE + 0x10: 76,  # power
            BASE + 0x14: 3,  # hour
            BASE + 0x18: 1,  # night
            BASE + 0x1C: 1,  # monitor_up
            BASE + 0x20: 0,  # door_left_closed
            BASE + 0x24: 7,  # active_camera raw
        },
    )
    m = MemoryMap.from_dict(
        {
            "process": GAME,
            "fields": {
                "power": {"chain": {"module_offset": 0x10}},
                "hour": {"chain": {"module_offset": 0x14}},
                "night": {"chain": {"module_offset": 0x18}},
                "monitor_up": {"type": "bool", "chain": {"module_offset": 0x1C}},
                "door_left_closed": {"type": "bool", "chain": {"module_offset": 0x20}},
                "active_camera": {"chain": {"module_offset": 0x24}, "enum_map": {7: "4B"}},
                "hour_still_unmapped": {"chain": None},
            },
        }
    )
    state = MemoryStateReader(mem, m).read()
    assert state.power == 76
    assert state.hour == 3
    assert state.night == 1
    assert state.monitor_up is True
    assert state.door_left_closed is False
    assert state.active_camera is Camera.CAM_4B
    assert state.door_right_closed is None  # unmapped -> stays None


def test_shipped_memory_map_template_parses() -> None:
    m = MemoryMap.from_yaml(REPO / "assets" / "memory_map.yaml")
    assert m.process == GAME
    # Template ships fully unmapped; the memory-scan session fills it in.
    # This asserts schema validity either way, without pinning progress.
    for name in ("power", "hour", "night", "active_camera", "monitor_up"):
        assert name in m.fields or name in m.unmapped
