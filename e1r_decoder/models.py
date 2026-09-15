from dataclasses import dataclass, field
import numpy as np

class PacketError(ValueError):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)

@dataclass
class E1RPoint:
    x: float
    y: float
    z: float
    intensity: int
    timestamp: float
    time_offset: float
    packet_sequence: int
    point_index: int
    attribute: int = 0

@dataclass
class E1RPacket:
    sequence: int
    timestamp: float
    points: np.ndarray
    capture_timestamp: float | None
    protocol_version: int
    return_mode: int
    time_mode: int
    raw_payload: bytes
    receive_timestamp: float | None = None

@dataclass
class E1RFrame:
    frame_index: int
    points: np.ndarray
    packet_count: int
    start_timestamp: float
    end_timestamp: float
    complete: bool
    reasons: list[str] = field(default_factory=list)
    sequences: list[int] = field(default_factory=list)

@dataclass
class E1RImu:
    timestamp: float
    accel_x_raw: float
    accel_y_raw: float
    accel_z_raw: float
    gyro_x_raw: float
    gyro_y_raw: float
    gyro_z_raw: float
    capture_timestamp: float | None = None
    receive_timestamp: float | None = None

def validate(payload, size, magic):
    if len(payload) != size:
        raise PacketError("invalid_length")
    if not payload.startswith(magic):
        raise PacketError("invalid_magic")

def timestamp(payload, offset):
    seconds = int.from_bytes(payload[offset:offset+6], "big")
    micros = int.from_bytes(payload[offset+6:offset+10], "big")
    # Same arithmetic as parseTimeUTCWithUs; do not invent field constraints.
    return (seconds * 1000000 + micros) * 1e-6
