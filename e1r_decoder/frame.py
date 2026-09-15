"""Official boundary algorithm; conservative, additional integrity metadata."""
from collections import Counter
import numpy as np
from .models import E1RFrame

class SplitStrategyBySeq:
    def __init__(self):
        self.prev = self.maximum = 0
        self.looped = False

    def push(self, seq):
        self.maximum = max(self.maximum, seq)
        low, high = max(0, self.prev - 10), (self.prev + 10) & 65535
        split = seq < low
        if split:
            self.prev, self.looped = seq, True
        elif seq < self.prev:
            pass
        elif seq <= high or self.prev == 0:
            self.prev = seq
        return split

class FrameAssembler:
    def __init__(self):
        self.strategy = SplitStrategyBySeq()
        self.packets = []
        self.index = 0
        self.started = False
        self.stats = Counter()

    def push(self, packet):
        frame = None
        if self.strategy.push(packet.sequence):
            frame = self._finish(True, packet.sequence)
            self.started = True
        self.packets.append(packet)
        return frame

    def _finish(self, ended, next_seq=None):
        if not self.packets:
            return None
        seqs = [p.sequence for p in self.packets]
        reasons = []
        if not self.started:
            reasons.append("capture_start_unverified")
        if not ended:
            reasons.append("end_unverified")
        counts = Counter(seqs)
        duplicates = sum(n-1 for n in counts.values())
        gaps = sum(max(0, b-a-1) for a,b in zip(seqs, seqs[1:]))
        disorder = sum(b<a for a,b in zip(seqs, seqs[1:]))
        for name, n in [("duplicates", duplicates), ("sequence_gaps", gaps), ("order_anomalies", disorder)]:
            self.stats[name] += n
            if n:
                reasons.append(name)
        # Only a restart at 0 or 1 followed by the same restart is evidence
        # of both ends. No inference of a fixed 288-packet frame length.
        if ended and (seqs[0] not in (0, 1) or next_seq != seqs[0]):
            reasons.append("sequence_extent_unverified")
        if ended and seqs[-1] != self.strategy.maximum:
            reasons.append("end_sequence_shorter_than_observed")
        points = np.concatenate([p.points for p in self.packets])
        result = E1RFrame(self.index, points, len(self.packets),
            float(points["timestamp"].min()), float(points["timestamp"].max()),
            not reasons, reasons, seqs)
        self.index += 1
        self.packets = []
        return result

    def flush(self):
        result = self._finish(False)
        self.started = False
        return result
