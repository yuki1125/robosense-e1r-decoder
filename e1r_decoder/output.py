from dataclasses import asdict
import json
from pathlib import Path
import numpy as np

def save_frame(frame, directory, formats=("npz",)):
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    base = path / f"frame_{frame.frame_index:06d}"
    p = frame.points
    if "npz" in formats:
        np.savez(base.with_suffix(".npz"), **{k:p[k] for k in p.dtype.names})
    if "pcd" in formats:
        header = ("# .PCD v0.7\nVERSION 0.7\nFIELDS x y z intensity\nSIZE 4 4 4 4\n"
                  "TYPE F F F F\nCOUNT 1 1 1 1\n" + f"WIDTH {len(p)}\nHEIGHT 1\n"
                  "VIEWPOINT 0 0 0 1 0 0 0\n" + f"POINTS {len(p)}\nDATA binary\n")
        values = np.column_stack([p[k] for k in ("x", "y", "z", "intensity")]).astype("<f4")
        base.with_suffix(".pcd").write_bytes(header.encode("ascii") + values.tobytes())
    metadata = {k:v for k,v in vars(frame).items() if k != "points"}
    metadata["point_count"] = len(p)
    base.with_suffix(".json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

def save_imu(imu, directory):
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    with (path / "imu.jsonl").open("a", encoding="utf-8") as f:
        import math
        values = asdict(imu)
        # JSON has no NaN/Inf literals. Preserve their identity as strings.
        values = {k: str(v) if isinstance(v, float) and not math.isfinite(v) else v
                  for k,v in values.items()}
        f.write(json.dumps(values, allow_nan=False) + "\n")
