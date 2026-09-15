import hashlib
import json
from collections import Counter
from pathlib import Path
import numpy as np
from e1r_decoder.pcap import read_pcap
from e1r_decoder.pipeline import Pipeline

EXPECTED_SHA = "e5e3529e4ddf883376448d4e20fe1dd21a979ed8b37a96b8c7a8d7d3f43028eb"
EXPECTED_SIZE = 17843496

def main():
    p = Path("testdata/e1r_frames.pcap")
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    assert sha == EXPECTED_SHA and p.stat().st_size == EXPECTED_SIZE
    frames = []
    pipe = Pipeline(frames.append)
    lengths = Counter()
    capture = []
    for rec in read_pcap(p, pipe.stats):
        lengths[len(rec.payload)] += 1
        capture.append(rec.capture_timestamp)
        pipe.feed(rec.payload, rec.destination_port, rec.capture_timestamp)
    stats = pipe.finish()
    pts = np.concatenate([f.points for f in frames])
    distances = pts["distance_raw"]*.005
    report = dict(sha256=sha, size=p.stat().st_size, stats=stats, payload_lengths=dict(lengths),
                  capture_start=capture[0], capture_end=capture[-1],
                  lidar_start=frames[0].start_timestamp, lidar_end=frames[-1].end_timestamp,
                  distance_min=float(distances.min()), distance_max=float(distances.max()),
                  nonzero_points=int(np.count_nonzero(distances)),
                  finite_xyz=bool(all(np.isfinite(pts[k]).all() for k in "xyz")),
                  frames=[{k:v for k,v in vars(f).items() if k not in ("points", "sequences")} for f in frames])
    Path("validation_pcap.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k != "frames"}, indent=2))

if __name__ == "__main__":
    main()
