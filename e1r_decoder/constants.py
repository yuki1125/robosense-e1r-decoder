"""Wire layout from rs_driver 897b14d3, decoder_RSE1.hpp (BSD-3-Clause)."""
import numpy as np

MSOP_PORT, DIFOP_PORT = 6699, 7788
MSOP_SIZE, DIFOP_SIZE = 1200, 256
MSOP_MAGIC = bytes.fromhex("55 aa 5a a5")
DIFOP_MAGIC = bytes.fromhex("a5 ff 00 5a 11 11 55 55")
HEADER_SIZE, BLOCK_SIZE, POINT_COUNT = 32, 12, 96
MSOP_TIMESTAMP_OFFSET, DIFOP_TIMESTAMP_OFFSET, IMU_OFFSET = 10, 103, 208
DISTANCE_SCALE, VECTOR_SCALE, OFFSET_SCALE = 0.005, 32768, 1e-6
BLOCK_DTYPE = np.dtype([("offset", ">u2"), ("distance", ">u2"),
                        ("dx", ">i2"), ("dy", ">i2"), ("dz", ">i2"),
                        ("intensity", "u1"), ("attribute", "u1")])
POINT_DTYPE = np.dtype([(k, "<f4") for k in ("x", "y", "z")] +
    [("intensity", "u1"), ("timestamp", "<f8"), ("time_offset", "<f8"),
     ("packet_sequence", "<u2"), ("point_index", "<u2"),
     ("attribute", "u1"), ("distance_raw", "<u2"),
     ("dx_raw", "<i2"), ("dy_raw", "<i2"), ("dz_raw", "<i2")])
