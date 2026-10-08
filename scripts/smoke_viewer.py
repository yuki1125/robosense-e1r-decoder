"""Real Open3D + independent 1x UDP replay, with strict decode assertions.

Run: python -m scripts.smoke_viewer
The 30 s duration is a watchdog; reception completes at the exact packet count.
Output includes sender timing, actual receive buffers, Linux socket drops,
decoder statistics, and a screenshot. No global OS settings are changed.
"""
import argparse
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
from types import SimpleNamespace

EXPECTED = dict(received=14184, valid_msop=14184, frames=50, partial_frames=2,
                points=1361664, sequence_gaps=2, invalid_packets=0,
                duplicates=0, order_anomalies=0)


def send(port, report_path):
    # This process must never import Open3D or share the renderer's GIL.
    from e1r_decoder.replay import replay
    started = time.monotonic()
    count = replay("testdata/e1r_frames.pcap", dst_port=port, rate=1.0)
    evidence = dict(sent=count, rate=1.0, elapsed_seconds=time.monotonic()-started)
    Path(report_path).write_text(json.dumps(evidence, indent=2))
    print(json.dumps(evidence), flush=True)
    if count != EXPECTED["received"]:
        raise RuntimeError(f"Unexpected sender count: {count}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--send", type=int, metavar="PORT", help=argparse.SUPPRESS)
    parser.add_argument("--sender-report", default="output/viewer_smoke_sender.json")
    args = parser.parse_args()
    if args.send is not None:
        send(args.send, args.sender_report)
        return

    import open3d as o3d
    from e1r_decoder import viewer

    output = Path("output")
    output.mkdir(exist_ok=True)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as a, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as b:
        a.bind(("127.0.0.1", 0))
        b.bind(("127.0.0.1", 0))
        msop, difop = a.getsockname()[1], b.getsockname()[1]

    class CaptureVisualizer:
        def __init__(self):
            self.vis = o3d.visualization.Visualizer()
            self.created = False
        def __getattr__(self, key):
            return getattr(self.vis, key)
        def create_window(self, **kwargs):
            self.created = self.vis.create_window(**kwargs)
            return self.created
        def destroy_window(self):
            # Capturing an uninitialized window can segfault in Open3D.
            if self.created:
                try:
                    self.vis.capture_screen_image(str(output/"viewer_smoke.png"), do_render=True)
                finally:
                    self.vis.destroy_window()

    sender = None
    def ready():
        nonlocal sender
        sender = subprocess.Popen([sys.executable, "-m", "scripts.smoke_viewer",
                                   "--send", str(msop), "--sender-report", args.sender_report])

    backend = SimpleNamespace(visualization=SimpleNamespace(Visualizer=CaptureVisualizer),
                              geometry=o3d.geometry, utility=o3d.utility)
    viewer_args = SimpleNamespace(bind_ip="127.0.0.1", msop_port=msop, difop_port=difop,
                                  source_ip=None, duration=30, max_packets=EXPECTED["received"],
                                  width=1280, height=720, point_size=2, fps=30,
                                  stats_json=str(output/"viewer_smoke.json"))
    try:
        stats = viewer.run(viewer_args, backend, on_ready=ready)
        if sender is None:
            raise RuntimeError("Receiver did not become ready")
        if sender.wait(timeout=10) != 0:
            raise RuntimeError("Replay subprocess failed")
    finally:
        if sender is not None and sender.poll() is None:
            sender.terminate()
            sender.wait(timeout=5)
    for key, expected in EXPECTED.items():
        assert stats[key] == expected, (key, stats[key], expected)
    assert stats.get("udp_socket_drops", 0) == 0, stats
    assert stats["rendered_frames"] > 0, stats


if __name__ == "__main__":
    main()
