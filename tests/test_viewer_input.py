"""Integration regressions for GIL stalls and spawned receiver lifecycle."""
import ctypes
import multiprocessing
import socket
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest

from e1r_decoder import viewer
from e1r_decoder.viewer_input import receive_isolated
from test_udp import free_ports


def options(**extra):
    msop, difop = free_ports()
    return dict(bind_ip="127.0.0.1", msop_port=msop, difop_port=difop,
                source_ip=None, **extra)


def assert_reaped():
    assert not [p for p in multiprocessing.active_children() if p.name == "e1r-udp"]


def test_bind_failure_is_reported_and_reaped():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as occupied:
        occupied.bind(("127.0.0.1", 0))
        opts = options()
        opts["msop_port"] = occupied.getsockname()[1]
        with pytest.raises(RuntimeError, match="OSError"):
            receive_isolated(opts, lambda frame: None, stop_event=threading.Event())
    assert_reaped()


def test_stop_before_any_packet_releases_ports():
    opts = options()
    stop = threading.Event()
    stats = receive_isolated(opts, lambda frame: None,
                             stop_event=stop, on_ready=stop.set)
    assert stats["valid_msop"] == 0
    assert stats["frames"] == 0
    assert_reaped()
    for port in (opts["msop_port"], opts["difop_port"]):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind(("127.0.0.1", port))


def test_child_crash_is_reported_and_reaped():
    def crash():
        child = next(p for p in multiprocessing.active_children() if p.name == "e1r-udp")
        child.terminate()
    with pytest.raises(RuntimeError, match="UDP input process"):
        receive_isolated(options(), lambda frame: None,
                         stop_event=threading.Event(), on_ready=crash)
    assert_reaped()


@pytest.mark.skipif(sys.platform != "linux", reason="Uses Linux usleep while retaining the GIL")
def test_viewer_receives_1x_replay_during_gil_holding_render(tmp_path):
    # time.sleep releases the GIL and cannot reproduce this bug. PyDLL retains
    # it, like Open3D's Visualizer bindings. Only this test's socket is capped.
    hold_gil = ctypes.PyDLL(None).usleep
    hold_gil.argtypes = [ctypes.c_uint]
    hold_gil.restype = ctypes.c_int
    state = dict(armed=False, stalled=False, closed=False)
    class Visualizer:
        def create_window(self, **kwargs): return True
        def get_render_option(self): return SimpleNamespace()
        def poll_events(self):
            if state["armed"] and not state["stalled"]:
                state["stalled"] = True
                hold_gil(300000)
            return True
        def add_geometry(self, cloud):
            state["armed"] = True
            return True
        def update_geometry(self, cloud): pass
        def reset_view_point(self, **kwargs): pass
        def update_renderer(self): pass
        def destroy_window(self): state["closed"] = True
    backend = SimpleNamespace(visualization=SimpleNamespace(Visualizer=Visualizer),
                              geometry=SimpleNamespace(PointCloud=SimpleNamespace),
                              utility=SimpleNamespace(Vector3dVector=lambda x: x))
    args = SimpleNamespace(**options(duration=20, max_packets=14184,
                                     receive_buffer_bytes=212992),
                           width=100, height=100, point_size=2, fps=30,
                           stats_json=str(tmp_path/"stats.json"))
    sender = None
    def ready():
        nonlocal sender
        sender = subprocess.Popen([sys.executable, "-m", "e1r_decoder.replay",
                                   "--pcap", "testdata/e1r_frames.pcap",
                                   "--dst-port", str(args.msop_port), "--rate", "1"])
    try:
        stats = viewer.run(args, backend, on_ready=ready)
        assert sender is not None and sender.wait(timeout=5) == 0
    finally:
        if sender is not None and sender.poll() is None:
            sender.terminate()
            sender.wait(timeout=5)
    assert state["stalled"] and state["closed"]
    assert stats["valid_msop"] == stats["received"] == 14184
    assert stats["frames"] == 50 and stats["partial_frames"] == 2
    assert stats["points"] == 1361664 and stats["sequence_gaps"] == 2
    assert stats["invalid_packets"] == 0
    assert stats["msop_rcvbuf_bytes"] <= 425984
    assert stats["udp_socket_drops"] == 0
    assert stats["rendered_frames"] > 0
    assert stats["rendered_frames"] + stats["display_skipped_frames"] == stats["frames"]
    assert_reaped()
