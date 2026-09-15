import struct
import pytest
from e1r_decoder.constants import DIFOP_MAGIC
from e1r_decoder.difop import decode_difop
from e1r_decoder.models import PacketError

def test_synthetic_imu():
    p = bytearray(256)
    p[:8] = DIFOP_MAGIC
    p[103:109] = (100).to_bytes(6, "big")
    p[109:113] = (500000).to_bytes(4, "big")
    struct.pack_into(">6f", p, 208, 1, 2, 3, 4, 5, 6)
    imu = decode_difop(bytes(p))
    assert imu.timestamp == 100.5
    assert tuple(vars(imu).values())[1:7] == (1., 2., 3., 4., 5., 6.)
    struct.pack_into("<6f", p, 208, 1, 2, 3, 4, 5, 6)
    assert decode_difop(bytes(p)).accel_x_raw != 1

@pytest.mark.parametrize("size", [0, 255, 257])
def test_length(size):
    with pytest.raises(PacketError, match="invalid_length"):
        decode_difop(bytes(size))

def test_magic():
    with pytest.raises(PacketError, match="invalid_magic"):
        decode_difop(bytes(256))
