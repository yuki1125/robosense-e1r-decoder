"""Desktop smoke test: real Open3D window + real localhost PCAP replay.

Run explicitly on a graphical desktop: python -m scripts.smoke_viewer
Writes output/viewer_smoke.json and output/viewer_smoke.png.
"""
from pathlib import Path
from types import SimpleNamespace
import threading
import socket
import open3d as o3d
from e1r_decoder import viewer
from e1r_decoder.replay import replay


def main():
    output = Path("output")
    output.mkdir(exist_ok=True)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as a, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as b:
        a.bind(("127.0.0.1", 0))
        b.bind(("127.0.0.1", 0))
        msop, difop = a.getsockname()[1], b.getsockname()[1]
    ready = threading.Event()
    errors = []
    original_receive = viewer.receive
    def receiver(*args, **kwargs):
        callback = kwargs["on_ready"]
        def on_ready():
            callback()
            ready.set()
        kwargs["on_ready"] = on_ready
        return original_receive(*args, **kwargs)
    viewer.receive = receiver
    def send():
        try:
            if not ready.wait(15):
                raise RuntimeError("receiver did not become ready")
            assert replay("testdata/e1r_frames.pcap", dst_port=msop) == 14184
        except Exception as error:
            errors.append(error)
    class CaptureVisualizer:
        def __init__(self):
            self.vis = o3d.visualization.Visualizer()
        def __getattr__(self, key):
            return getattr(self.vis, key)
        def destroy_window(self):
            self.vis.capture_screen_image(str(output/"viewer_smoke.png"), do_render=True)
            self.vis.destroy_window()
    backend = SimpleNamespace(visualization=SimpleNamespace(Visualizer=CaptureVisualizer),
                              geometry=o3d.geometry, utility=o3d.utility)
    args = SimpleNamespace(bind_ip="127.0.0.1", msop_port=msop, difop_port=difop,
                           source_ip=None, duration=8, width=1280, height=720,
                           point_size=2, fps=30, stats_json=str(output/"viewer_smoke.json"))
    sender = threading.Thread(target=send)
    sender.start()
    try:
        stats = viewer.run(args, backend)
    finally:
        sender.join()
        viewer.receive = original_receive
    assert not errors, errors
    assert stats["valid_msop"] == 14184
    assert stats["rendered_frames"] > 0


if __name__ == "__main__":
    main()
