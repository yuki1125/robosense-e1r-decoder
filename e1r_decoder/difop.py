import struct
from .constants import DIFOP_SIZE, DIFOP_MAGIC, DIFOP_TIMESTAMP_OFFSET, IMU_OFFSET
from .models import E1RImu, validate, timestamp

def decode_difop(payload: bytes, capture_timestamp=None):
    validate(payload, DIFOP_SIZE, DIFOP_MAGIC)
    return E1RImu(timestamp(payload, DIFOP_TIMESTAMP_OFFSET),
                  *struct.unpack_from(">6f", payload, IMU_OFFSET), capture_timestamp)
