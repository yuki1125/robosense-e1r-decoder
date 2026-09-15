from collections import Counter
from .msop import decode_msop
from .difop import decode_difop
from .models import PacketError
from .frame import FrameAssembler
from .constants import MSOP_PORT, DIFOP_PORT

class Pipeline:
    def __init__(self, on_frame=lambda f: None, on_imu=lambda i: None, debug=0):
        self.assembler = FrameAssembler()
        self.stats = Counter()
        self.on_frame, self.on_imu, self.debug = on_frame, on_imu, debug

    def emit(self, frame):
        if frame is not None:
            self.stats["frames"] += 1
            self.stats["partial_frames"] += not frame.complete
            self.stats["points"] += len(frame.points)
            self.on_frame(frame)

    def feed(self, payload, port=MSOP_PORT, capture_timestamp=None, *, receive_timestamp=None):
        self.stats["received"] += 1
        try:
            if port == MSOP_PORT:
                self.stats["msop_packets"] += 1
                packet = decode_msop(payload, capture_timestamp)
                packet.receive_timestamp = receive_timestamp
                self.stats["valid_msop"] += 1
                if self.debug > 0:
                    print(f"length={len(payload)} magic={payload[:4].hex()} sequence={packet.sequence} "
                          f"packet_timestamp={packet.timestamp:.9f} points={len(packet.points)} "
                          f"first_point={packet.points[0]}")
                    self.debug -= 1
                self.emit(self.assembler.push(packet))
            elif port == DIFOP_PORT:
                imu = decode_difop(payload, capture_timestamp)
                imu.receive_timestamp = receive_timestamp
                self.on_imu(imu)
                self.stats["valid_difop"] += 1
        except PacketError as error:
            self.stats[error.reason] += 1
            self.stats["invalid_packets"] += 1

    def finish(self):
        self.emit(self.assembler.flush())
        for key, value in self.assembler.stats.items():
            self.stats[key] = value
        for key in ("invalid_packets", "invalid_length", "invalid_magic", "malformed_packet",
                    "valid_msop", "valid_difop", "frames", "partial_frames"):
            self.stats.setdefault(key, 0)
        return dict(self.stats)
