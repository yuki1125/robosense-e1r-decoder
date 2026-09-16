"""Blocking frame API backed by a UDP receiver thread."""
from collections import deque
import threading

from .constants import MSOP_PORT, DIFOP_PORT
from .pipeline import Pipeline


class E1RSensor:
    """Read frames with the latest IMU observed at frame delivery (not synchronized).

    Start with a context manager. A bounded queue drops its oldest frame when
    full. IMU is a latest-value snapshot, not a lossless IMU stream. Instances
    are single-use. read() returns (E1RFrame, E1RImu | None).
    """

    def __init__(self, *, bind_ip="0.0.0.0", msop_port=MSOP_PORT,
                 difop_port=DIFOP_PORT, source_ip=None, queue_size=1,
                 complete_only=True):
        if not isinstance(queue_size, int) or queue_size < 1:
            raise ValueError("queue_size must be a positive integer")
        self._options = dict(bind_ip=bind_ip, msop_port=msop_port,
                             difop_port=difop_port, source_ip=source_ip)
        self._frames = deque(maxlen=queue_size)
        self._condition = threading.Condition()
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread = None
        self._closed = False
        self._done = False
        self._error = None
        self._imu = None
        self._complete_only = complete_only
        self.dropped_frames = 0
        self._pipeline = Pipeline(on_frame=self._on_frame, on_imu=self._on_imu)

    def _on_imu(self, imu):
        self._imu = imu  # Only accessed by the receiver thread.

    def _on_frame(self, frame):
        if self._complete_only and not frame.complete:
            return
        with self._condition:
            if len(self._frames) == self._frames.maxlen:
                self.dropped_frames += 1
            self._frames.append((frame, self._imu))
            self._condition.notify_all()

    def _run(self):
        from .live import receive
        try:
            receive(self._pipeline, **self._options, stop_event=self._stop,
                    on_ready=self._ready.set)
        except Exception as error:
            self._error = error
        finally:
            try:
                self._pipeline.finish()
            finally:
                with self._condition:
                    self._done = True
                    self._condition.notify_all()
                self._ready.set()

    def start(self):
        if self._closed or self._thread is not None:
            raise RuntimeError("E1RSensor instances can only be started once")
        self._thread = threading.Thread(target=self._run, name="e1r-receiver", daemon=True)
        self._thread.start()
        try:
            self._ready.wait()
            if self._error is not None:
                raise RuntimeError("E1R receiver failed to start") from self._error
        except BaseException:
            self.close()
            raise
        return self

    def read(self, timeout=None):
        """Wait for a new frame; raise TimeoutError when no frame arrives in time.

        IMU can be None or stale. Check its timestamp/receive_timestamp as needed.
        After close(), read() raises RuntimeError rather than draining the queue.
        """
        if timeout is not None and timeout < 0:
            raise ValueError("timeout must be nonnegative or None")
        with self._condition:
            if self._thread is None:
                raise RuntimeError("Start the sensor before calling read()")
            available = self._condition.wait_for(
                lambda: self._frames or self._done or self._closed, timeout)
            if self._error is not None:
                raise RuntimeError("E1R receiver failed") from self._error
            if self._closed:
                raise RuntimeError("E1R receiver is closed")
            if self._frames:
                return self._frames.popleft()
            if self._done:
                raise RuntimeError("E1R receiver stopped")
            if not available:
                raise TimeoutError("No E1R frame received")

    def close(self):
        """Stop reception and release sockets; safe to call repeatedly."""
        with self._condition:
            self._closed = True
            self._stop.set()
            self._condition.notify_all()
        if self._thread is not None:
            self._thread.join()

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.close()
