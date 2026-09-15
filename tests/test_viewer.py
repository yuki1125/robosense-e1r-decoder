from types import SimpleNamespace
import threading
import numpy as np
import pytest
from e1r_decoder import viewer
from e1r_decoder.constants import POINT_DTYPE


def test_latest_mailbox_bounded():
    mailbox = viewer.LatestFrame()
    for i in range(100):
        mailbox.put(i)
    assert mailbox.take() == 99
    assert mailbox.take() is None
    assert mailbox.skipped == 99


def test_native_xyz_and_color_do_not_modify_points():
    points = np.zeros(3, dtype=POINT_DTYPE)
    points["x"] = [0, -5, np.nan]
    points["y"] = [0, 2, 1]
    points["intensity"] = [0, 255, 42]
    before = points.tobytes()
    xyz, colors = viewer.display_arrays(points)
    np.testing.assert_array_equal(xyz, [[0,0,0],[-5,2,0]])
    np.testing.assert_array_equal(colors, [[.25,.25,.25],[1,1,1]])
    assert points.tobytes() == before


def test_real_open3d_geometry():
    o3d = pytest.importorskip("open3d")
    points = np.zeros(96, dtype=POINT_DTYPE)
    points["x"] = np.linspace(-1,1,96)
    xyz, colors = viewer.display_arrays(points)
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(xyz)
    cloud.colors = o3d.utility.Vector3dVector(colors)
    np.testing.assert_array_equal(np.asarray(cloud.points), xyz)
    np.testing.assert_array_equal(np.asarray(cloud.colors), colors)


def test_receiver_failure_closes_visualizer(monkeypatch):
    main_thread = threading.get_ident()
    calls = []
    class FakeVisualizer:
        def create_window(self, **kwargs):
            return True
        def get_render_option(self):
            return SimpleNamespace()
        def poll_events(self):
            return True
        def update_renderer(self):
            assert threading.get_ident() == main_thread
        def destroy_window(self):
            calls.append("closed")
            assert threading.get_ident() == main_thread
    def fail(*args, **kwargs):
        assert threading.get_ident() != main_thread
        raise OSError("address in use")
    monkeypatch.setattr(viewer, "receive", fail)
    fake = SimpleNamespace(visualization=SimpleNamespace(Visualizer=FakeVisualizer),
                           geometry=SimpleNamespace(PointCloud=SimpleNamespace))
    args = SimpleNamespace(bind_ip="127.0.0.1", msop_port=6699, difop_port=7788,
                           source_ip=None, duration=0, width=100, height=100,
                           point_size=2, fps=30, stats_json=None)
    with pytest.raises(RuntimeError, match="address in use"):
        viewer.run(args, fake)
    assert calls == ["closed"]
