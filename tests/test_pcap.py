import hashlib
from pathlib import Path
import numpy as np
import pytest
from e1r_decoder.pcap import read_pcap
from e1r_decoder.pipeline import Pipeline
from e1r_decoder.output import save_frame
from scripts.inspect_pcap import EXPECTED_SHA, EXPECTED_SIZE

PCAP = Path("testdata/e1r_frames.pcap")

def test_real_pcap(tmp_path):
    assert PCAP.exists(), "Obtain the public LFS PCAP before running integration tests"
    assert PCAP.stat().st_size == EXPECTED_SIZE
    assert hashlib.sha256(PCAP.read_bytes()).hexdigest() == EXPECTED_SHA
    frames = []
    p = Pipeline(frames.append)
    for r in read_pcap(PCAP, p.stats):
        p.feed(r.payload, r.destination_port, r.capture_timestamp)
    stats = p.finish()
    assert stats["valid_msop"] == 14184
    assert stats.get("valid_difop", 0) == 0
    assert len(frames) == 50 and sum(f.complete for f in frames) == 48
    points = np.concatenate([f.points for f in frames])
    assert len(points) == 1361664
    assert all(np.isfinite(points[k]).all() for k in "xyz")
    assert np.count_nonzero(points["distance_raw"]) > 1000000
    # Dataset regression bounds, never used to filter decoder output.
    assert 29 < points["distance_raw"].max()*.005 < 30
    save_frame(frames[1], tmp_path, ("npz", "pcd"))
    with np.load(tmp_path/"frame_000001.npz") as saved:
        for name in points.dtype.names:
            np.testing.assert_array_equal(saved[name], frames[1].points[name])
    raw = (tmp_path/"frame_000001.pcd").read_bytes()
    data = raw.split(b"DATA binary\n",1)[1]
    xyz = np.frombuffer(data, "<f4").reshape(-1,4)
    np.testing.assert_array_equal(xyz[:,0], frames[1].points["x"])

def test_lfs_pointer(tmp_path):
    p = tmp_path/"bad.pcap"
    p.write_text("version https://git-lfs.github.com/spec/v1\noid sha256:abc")
    with pytest.raises(ValueError, match="LFS"):
        list(read_pcap(p))

def test_pipeline_invalid_continues(packet_factory):
    p = Pipeline()
    p.feed(b"bad")
    p.feed(bytes(1200))
    p.feed(packet_factory())
    stats = p.finish()
    assert stats["invalid_packets"] == 2 and stats["valid_msop"] == 1
