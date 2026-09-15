import json
import socket
import subprocess
import sys
import time
from pathlib import Path
import numpy as np
import pytest
from e1r_decoder.pcap import read_pcap
from e1r_decoder.pipeline import Pipeline

def free_ports():
    sockets = [socket.socket(socket.AF_INET, socket.SOCK_DGRAM) for _ in range(2)]
    try:
        for s in sockets:
            s.bind(("127.0.0.1", 0))
        return [s.getsockname()[1] for s in sockets]
    finally:
        for s in sockets:
            s.close()

@pytest.mark.parametrize("rate", [1, 0])
def test_cli_udp_loopback(tmp_path, rate):
    port, difop_port = free_ports()
    stats_path = tmp_path/"stats.json"
    log_path = tmp_path/"live.log"
    output = tmp_path/"frames"
    with log_path.open("w") as log:
        process = subprocess.Popen([sys.executable,"-m","e1r_decoder.live",
            "--bind-ip","127.0.0.1","--msop-port",str(port),"--difop-port",str(difop_port),
            "--max-packets","14184","--duration","15","--stats-json",str(stats_path),
            "--output",str(output)], stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic()+10
            while "READY" not in log_path.read_text():
                assert process.poll() is None, log_path.read_text()
                assert time.monotonic() < deadline, "receiver readiness timeout"
                time.sleep(.02)
            sent = subprocess.run([sys.executable,"-m","e1r_decoder.replay","--pcap",
                "testdata/e1r_frames.pcap","--dst-port",str(port),"--rate",str(rate)],
                capture_output=True, text=True, timeout=15, check=True)
            assert "14184" in sent.stdout
            process.wait(timeout=20)
            assert process.returncode == 0, log_path.read_text()
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
    stats = json.loads(stats_path.read_text())
    evidence = dict(rate=rate, sent=14184, received=stats["received"],
                    loss=14184-stats["received"], stats=stats)
    Path(f"validation_udp_rate_{rate}.json").write_text(json.dumps(evidence, indent=2))
    # Equal-rate replay must be lossless; max-speed replay may exceed OS buffers.
    if rate == 1:
        assert stats["valid_msop"] == 14184
        assert stats["frames"] == 50 and stats["partial_frames"] == 2
    assert stats["valid_msop"] > 0
    if stats["received"] == 14184:
        frames = []
        pipe = Pipeline(frames.append)
        for r in read_pcap("testdata/e1r_frames.pcap"):
            pipe.feed(r.payload, r.destination_port, r.capture_timestamp)
        pipe.finish()
        for frame in frames:
            with np.load(output/f"frame_{frame.frame_index:06d}.npz") as saved:
                for key in frame.points.dtype.names:
                    np.testing.assert_array_equal(saved[key], frame.points[key])
