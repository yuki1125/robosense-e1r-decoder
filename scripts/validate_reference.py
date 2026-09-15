"""Run official C++ decoder and compare every PCAP point and boundary."""
import argparse
import json
from pathlib import Path
import struct
import subprocess
import numpy as np
from e1r_decoder.pcap import read_pcap
from e1r_decoder.msop import decode_msop
from e1r_decoder.frame import SplitStrategyBySeq

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pcap", default="testdata/e1r_frames.pcap")
    parser.add_argument("--executable", default="build/rs_reference.exe")
    args = parser.parse_args()
    path = Path("build")
    path.mkdir(exist_ok=True)
    records = [r for r in read_pcap(args.pcap) if r.destination_port == 6699]
    source, result = path / "payloads.bin", path / "reference.bin"
    with source.open("wb") as f:
        for r in records:
            f.write(r.payload)
    subprocess.run([args.executable, str(source), str(result)], check=True)
    dtype = np.dtype([("x","<f4"),("y","<f4"),("z","<f4"),("intensity","u1"),("timestamp","<f8")])
    split = SplitStrategyBySeq()
    frame = 0
    max_xyz = max_ts = 0.0
    excluded = total = 0
    with result.open("rb") as f:
        for rec in records:
            packet = decode_msop(rec.payload)
            frame += split.push(packet.sequence)
            ref_frame, count = struct.unpack("<II", f.read(8))
            assert ref_frame == frame, (ref_frame, frame)
            assert count == len(packet.points) == 96
            reference = np.frombuffer(f.read(count*dtype.itemsize), dtype)
            actual = packet.points
            finite = np.isfinite(reference["x"])
            expected_valid = actual["distance_raw"].astype(np.float32)*np.float32(.005) <= 200
            np.testing.assert_array_equal(finite, expected_valid)
            excluded += int((~finite).sum())
            for key in "xyz":
                delta = np.abs(reference[key][finite]-actual[key][finite])
                max_xyz = max(max_xyz, float(delta.max(initial=0)))
                np.testing.assert_allclose(actual[key][finite], reference[key][finite], rtol=2e-7, atol=1e-6)
            np.testing.assert_array_equal(actual["intensity"][finite], reference["intensity"][finite])
            max_ts = max(max_ts, float(np.abs(reference["timestamp"]-actual["timestamp"]).max()))
            np.testing.assert_allclose(actual["timestamp"], reference["timestamp"], rtol=0, atol=1e-9)
            total += count
        assert not f.read(1)
    report = dict(status="PASS", packets=len(records), points=total, frames=frame+1,
                  excluded_by_official_distance=excluded, max_xyz_error_m=max_xyz,
                  max_timestamp_error_s=max_ts, intensity="exact", boundaries="exact")
    Path("validation_reference.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
