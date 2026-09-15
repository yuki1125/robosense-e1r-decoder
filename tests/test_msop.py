import numpy as np
import pytest
from e1r_decoder.msop import decode_msop
from e1r_decoder.models import PacketError

def test_fields(packet_factory):
    packet = decode_msop(packet_factory(), 12.0)
    p = packet.points[0]
    assert len(packet.points) == 96
    assert (p["x"], p["y"], p["z"]) == (2.5, -2.5, -5)
    assert p["intensity"] == 42 and p["attribute"] == 7
    assert p["time_offset"] == .00025
    assert packet.timestamp == (1700000000*1000000+123456)*1e-6
    assert p["timestamp"] == packet.timestamp+.00025
    assert packet.capture_timestamp == 12.0

@pytest.mark.parametrize("size", [0, 1199, 1201])
def test_length(size):
    with pytest.raises(PacketError, match="invalid_length"):
        decode_msop(bytes(size))

def test_magic():
    with pytest.raises(PacketError, match="invalid_magic"):
        decode_msop(bytes(1200))

@pytest.mark.parametrize("distance", [0, 1, 7001, 40001, 65535])
def test_raw_retention_and_reference(packet_factory, distance):
    raw = packet_factory(distance=distance, intensity=0)
    a, b = decode_msop(raw), decode_msop(raw, reference=True)
    np.testing.assert_array_equal(a.points, b.points)
    assert len(a.points) == 96
    assert a.points["distance_raw"][0] == distance

def test_random_reference(packet_factory):
    rng = np.random.default_rng(12)
    for _ in range(100):
        p = bytearray(packet_factory())
        p[32:1184] = rng.bytes(1152)
        np.testing.assert_array_equal(decode_msop(bytes(p)).points,
                                      decode_msop(bytes(p), reference=True).points)
