import struct
import pytest
from e1r_decoder.constants import MSOP_MAGIC

def msop(seq=1, distance=1000, direction=(16384, -16384, -32768), intensity=42, offset=250):
    p = bytearray(1200)
    p[:4] = MSOP_MAGIC
    struct.pack_into(">H", p, 4, seq)
    p[10:16] = (1700000000).to_bytes(6, "big")
    p[16:20] = (123456).to_bytes(4, "big")
    for i in range(96):
        struct.pack_into(">HHhhhBB", p, 32+i*12, offset, distance, *direction, intensity, 7)
    return bytes(p)

@pytest.fixture
def packet_factory():
    return msop
