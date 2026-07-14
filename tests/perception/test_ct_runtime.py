import struct

from fnaf_agent.perception.ct_offsets import CRunActiveObject, CRunObject, CRunValue
from fnaf_agent.perception.ct_runtime import CTFObject, CTFValue


class MockPymem:
    """A minimal mock for pymem to test CTFObject reading logic."""

    def __init__(self, memory_map: dict):
        # memory_map is a dict of address -> bytes
        self.memory_map = memory_map

    def read_int(self, address: int) -> int:
        data = self.read_bytes(address, 4)
        return struct.unpack("<i", data)[0]

    def read_bytes(self, address: int, size: int) -> bytes:
        for base_addr, mem_bytes in self.memory_map.items():
            if base_addr <= address < base_addr + len(mem_bytes):
                offset = address - base_addr
                if offset + size <= len(mem_bytes):
                    return mem_bytes[offset : offset + size]
        # Return zeros if unmapped
        return b"\x00" * size


def test_ctf_value_parsing():
    # Int value
    v_int = CTFValue(val_type=0, raw_bytes=struct.pack("<i", 42))
    assert v_int.value == 42

    # Float value
    v_float = CTFValue(val_type=2, raw_bytes=struct.pack("<f", 3.14))
    assert abs(v_float.value - 3.14) < 0.001


def test_ctf_object_read_position():
    # Create fake object memory
    obj_mem = bytearray(256)
    struct.pack_into("<i", obj_mem, CRunObject.X, 100)
    struct.pack_into("<i", obj_mem, CRunObject.Y, 200)

    pm = MockPymem({0x1000: bytes(obj_mem)})
    obj = CTFObject(pm, 0x1000, "TestObject", 1)

    assert obj.x == 100
    assert obj.y == 200


def test_ctf_object_read_alterable_values():
    obj_mem = bytearray(1024)
    # Set ALTERABLE_VALUES_ARRAY to 0x2000
    struct.pack_into("<i", obj_mem, CRunActiveObject.ALTERABLE_VALUES_ARRAY, 0x2000)
    # Set count to 2
    struct.pack_into("<i", obj_mem, CRunActiveObject.ALTERABLE_VALUES_COUNT, 2)

    # Values array at 0x2000
    # Each value is 16 bytes: [0x0: type(int), 0x4: pad, 0x8: val(int/float), 0xC: pad]
    val_mem = bytearray(32)
    # Value 1: int(42)
    struct.pack_into("<i", val_mem, 0 + CRunValue.TYPE, 0)
    struct.pack_into("<i", val_mem, 0 + CRunValue.VALUE, 42)
    # Value 2: float(1.5)
    struct.pack_into("<i", val_mem, 16 + CRunValue.TYPE, 2)
    struct.pack_into("<f", val_mem, 16 + CRunValue.VALUE, 1.5)

    pm = MockPymem({0x1000: bytes(obj_mem), 0x2000: bytes(val_mem)})

    obj = CTFObject(pm, 0x1000, "TestObject", 1)
    values = obj.read_alterable_values()

    assert len(values) == 2
    assert values[0].value == 42
    assert values[1].value == 1.5
