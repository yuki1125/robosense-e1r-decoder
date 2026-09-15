import struct
import numpy as np
from .constants import *
from .models import E1RPacket, validate, timestamp

def decode_msop(payload: bytes, capture_timestamp=None, *, reference=False):
    validate(payload, MSOP_SIZE, MSOP_MAGIC)
    seq, version = struct.unpack_from(">HH", payload, 4)
    ts = timestamp(payload, MSOP_TIMESTAMP_OFFSET)
    points = np.zeros(POINT_COUNT, dtype=POINT_DTYPE)
    if reference:
        for i in range(POINT_COUNT):
            off, dist, dx, dy, dz, intensity, attr = struct.unpack_from(">HHhhhBB", payload, HEADER_SIZE + i * BLOCK_SIZE)
            r = np.float32(dist) * np.float32(DISTANCE_SCALE)
            points[i] = (np.float32(dx)*r/VECTOR_SCALE, np.float32(dy)*r/VECTOR_SCALE,
                         np.float32(dz)*r/VECTOR_SCALE, intensity, ts+off*OFFSET_SCALE,
                         off*OFFSET_SCALE, seq, i, attr, dist, dx, dy, dz)
    else:
        blocks = np.frombuffer(payload, BLOCK_DTYPE, POINT_COUNT, HEADER_SIZE)
        r = blocks["distance"].astype(np.float32) * np.float32(DISTANCE_SCALE)
        for axis in "xyz":
            points[axis] = blocks["d"+axis].astype(np.float32) * r / VECTOR_SCALE
            points["d"+axis+"_raw"] = blocks["d"+axis]
        points["time_offset"] = blocks["offset"].astype(np.float64) * OFFSET_SCALE
        points["timestamp"] = ts + points["time_offset"]
        points["intensity"], points["attribute"] = blocks["intensity"], blocks["attribute"]
        points["distance_raw"] = blocks["distance"]
        points["packet_sequence"], points["point_index"] = seq, np.arange(POINT_COUNT)
    return E1RPacket(seq, ts, points, capture_timestamp, version, payload[8], payload[9], bytes(payload))
