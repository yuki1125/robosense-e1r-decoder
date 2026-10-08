"""Stream captured UDP into the common decoder without opening UDP sockets."""
from collections import Counter
import ipaddress
import math
import threading
import time

from .constants import MSOP_PORT, DIFOP_PORT
from .pcap import read_pcap
from .pipeline import Pipeline


def play_capture(path, on_frame, *, stop_event=None, rate=1.0, loop=False,
                 duration=0, msop_port=MSOP_PORT, difop_port=DIFOP_PORT,
                 source_ip=None, on_imu=lambda imu: None):
    """Replay by capture time; rate=0 decodes without waiting.

    Each pass has its own assembler, including an EOF partial frame. Memory is
    bounded by the current frame. Returns cumulative statistics over all passes.
    """
    if not math.isfinite(rate) or rate < 0:
        raise ValueError("rate must be finite and nonnegative")
    if not math.isfinite(duration) or duration < 0:
        raise ValueError("duration must be finite and nonnegative")
    if msop_port == difop_port:
        raise ValueError("MSOP and DIFOP ports must differ")
    source = ipaddress.ip_address(source_ip).packed if source_ip else None
    stop = stop_event if stop_event is not None else threading.Event()
    deadline = time.monotonic() + duration if duration else math.inf
    totals = Counter()
    while not stop.is_set() and time.monotonic() < deadline:
        pipeline = Pipeline(on_frame=on_frame, on_imu=on_imu)
        first_timestamp = None
        start = time.monotonic()
        interrupted = False
        try:
            for record in read_pcap(path, pipeline.stats):
                if stop.is_set() or time.monotonic() >= deadline:
                    interrupted = True
                    break
                if source is not None and record.source_ip != source:
                    pipeline.stats["source_filtered"] += 1
                    continue
                if record.destination_port not in (msop_port, difop_port):
                    continue
                if first_timestamp is None:
                    first_timestamp = record.capture_timestamp
                    start = time.monotonic()
                if rate:
                    target = start + max(0, record.capture_timestamp-first_timestamp) / rate
                    delay = max(0, min(target, deadline) - time.monotonic())
                    if stop.wait(delay) or time.monotonic() >= deadline:
                        interrupted = True
                        break
                port = MSOP_PORT if record.destination_port == msop_port else DIFOP_PORT
                pipeline.feed(record.payload, port, record.capture_timestamp)
        finally:
            totals.update(pipeline.finish())
        if interrupted or stop.is_set():
            break
        if not pipeline.stats["valid_msop"]:
            raise ValueError("No valid E1R MSOP packets found; check capture, ports and source IP")
        totals["playback_passes"] += 1
        if not loop:
            break
        # Avoid a busy loop for empty-duration captures at rate=0.
        if stop.wait(0.01):
            break
    return dict(totals)
