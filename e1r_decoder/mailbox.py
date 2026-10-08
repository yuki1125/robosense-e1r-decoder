"""A bounded latest-frame handoff for threads."""
import threading


class LatestFrame:
    """One-slot mailbox: slow rendering never queues old frames."""
    def __init__(self):
        self.lock = threading.Lock()
        self.frame = None
        self.skipped = 0

    def put(self, frame):
        with self.lock:
            if self.frame is not None:
                self.skipped += 1
            self.frame = frame

    def take(self):
        with self.lock:
            frame, self.frame = self.frame, None
            return frame
