"""Live Open3D display; decoding stays on the shared UDP pipeline."""
import argparse
import math
import threading
import time
import numpy as np
from .constants import MSOP_PORT, DIFOP_PORT
from .live import receive
from .pipeline import Pipeline
from .decode_pcap import report


class LatestFrame:
    """One-slot mailbox: slow rendering never queues old frames."""
    def __init__(self):
        self.lock = threading.Lock()
        self.frame = None
        self.skipped = 0

    def put(self, frame):
        with self.lock:
            if self.frame is not None:
                self.skipped += 1
            self.frame = frame

    def take(self):
        with self.lock:
            frame, self.frame = self.frame, None
            return frame


def display_arrays(points):
    """Native XYZ and grayscale intensity; finite mask is display-only."""
    xyz = np.column_stack([points[k] for k in "xyz"]).astype(np.float64)
    finite = np.isfinite(xyz).all(axis=1)
    intensity = points["intensity"][finite].astype(np.float64) / 255.0
    # Display-only contrast: even zero-intensity measurements remain visible.
    brightness = 0.25 + 0.75 * np.sqrt(intensity)
    return xyz[finite], np.repeat(brightness[:, None], 3, axis=1)


def run(args, o3d):
    mailbox = LatestFrame()
    stop = threading.Event()
    done = threading.Event()
    errors = []
    stats = {}
    pipeline = Pipeline(mailbox.put)
    rendered = 0

    def worker():
        try:
            receive(pipeline, bind_ip=args.bind_ip, msop_port=args.msop_port,
                    difop_port=args.difop_port, source_ip=args.source_ip,
                    duration=args.duration, stop_event=stop,
                    on_ready=lambda: print("READY: UDP receiver / Open3D viewer", flush=True))
        except Exception as error:
            errors.append(error)
        finally:
            stats.update(pipeline.finish())
            done.set()

    vis = o3d.visualization.Visualizer()
    thread = None
    try:
        if not vis.create_window(window_name="RoboSense E1R - native XYZ / intensity",
                                 width=args.width, height=args.height):
            raise RuntimeError("Open3D window initialization failed; a desktop/OpenGL context is required")
        options = vis.get_render_option()
        options.background_color = np.array([0.08, 0.08, 0.08])
        options.point_size = args.point_size
        cloud = o3d.geometry.PointCloud()
        added = False
        fitted_complete = False
        thread = threading.Thread(target=worker, name="e1r-udp")
        thread.start()
        while True:
            started = time.monotonic()
            if not vis.poll_events():
                break
            # Snapshot completion before taking the final mailbox entry.
            finished = done.is_set()
            frame = mailbox.take()
            if frame is not None:
                xyz, colors = display_arrays(frame.points)
                cloud.points = o3d.utility.Vector3dVector(xyz)
                cloud.colors = o3d.utility.Vector3dVector(colors)
                if len(xyz) and not added:
                    if not vis.add_geometry(cloud):
                        raise RuntimeError("Open3D could not add the point cloud")
                    added = True
                elif added:
                    vis.update_geometry(cloud)
                if len(xyz) and frame.complete and not fitted_complete:
                    vis.reset_view_point(reset_bounding_box=True)
                    fitted_complete = True
                rendered += 1
            vis.update_renderer()
            if finished:
                break
            time.sleep(max(0, 1/args.fps-(time.monotonic()-started)))
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        if thread is not None:
            thread.join()
        vis.destroy_window()  # Open3D requires the main thread.
        stats.update(rendered_frames=rendered, display_skipped_frames=mailbox.skipped)
        report(stats, args.stats_json)
    if errors:
        raise RuntimeError(f"UDP receiver failed: {errors[0]}") from errors[0]
    return stats


def main():
    parser = argparse.ArgumentParser(description="Display live E1R point clouds with Open3D")
    parser.add_argument("--bind-ip", default="0.0.0.0")
    parser.add_argument("--msop-port", type=int, default=MSOP_PORT)
    parser.add_argument("--difop-port", type=int, default=DIFOP_PORT)
    parser.add_argument("--source-ip")
    parser.add_argument("--fps", type=float, default=30, help="Maximum display updates per second")
    parser.add_argument("--point-size", type=float, default=2.0)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--duration", type=float, default=0, help="Stop after N seconds; 0 waits until window closes")
    parser.add_argument("--stats-json")
    args = parser.parse_args()
    for name in ("fps", "point_size", "width", "height"):
        value = getattr(args, name)
        if not math.isfinite(value) or value <= 0:
            parser.error(f"{name} must be positive and finite")
    if not math.isfinite(args.duration) or args.duration < 0:
        parser.error("duration must be nonnegative and finite")
    try:
        import open3d as o3d
    except ImportError:
        parser.exit(1, "Open3D is required: python -m pip install -e '.[viewer]'\n")
    try:
        run(args, o3d)
    except (OSError, RuntimeError) as error:
        parser.exit(1, f"Viewer error: {error}\n")


if __name__ == "__main__":
    main()
