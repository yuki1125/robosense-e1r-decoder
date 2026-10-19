"""Live and PCAP/PCAPNG Open3D display using the common decoder."""
import argparse
import math
import threading
import time
import numpy as np
from .constants import MSOP_PORT, DIFOP_PORT
from .mailbox import LatestFrame
from .viewer_input import receive_isolated
from .decode_pcap import report
from .playback import play_capture


def display_arrays(points):
    """Native XYZ and grayscale intensity; finite mask is display-only."""
    xyz = np.column_stack([points[k] for k in "xyz"]).astype(np.float64)
    finite = np.isfinite(xyz).all(axis=1)
    intensity = points["intensity"][finite].astype(np.float64) / 255.0
    # Display-only contrast: even zero-intensity measurements remain visible.
    brightness = 0.25 + 0.75 * np.sqrt(intensity)
    return xyz[finite], np.repeat(brightness[:, None], 3, axis=1)


def run(args, o3d, *, on_ready=lambda: None):
    mailbox = LatestFrame()
    stop = threading.Event()
    done = threading.Event()
    errors = []
    stats = {}
    rendered = 0
    capture = getattr(args, "pcap", None)

    def worker():
        try:
            if capture:
                print(f"PLAYBACK: {capture}", flush=True)
                stats.update(play_capture(
                    capture, mailbox.put, stop_event=stop, rate=args.rate,
                    loop=args.loop, duration=args.duration,
                    msop_port=args.msop_port, difop_port=args.difop_port,
                    source_ip=args.source_ip))
            else:
                def ready():
                    print("READY: UDP receiver / Open3D viewer", flush=True)
                    on_ready()
                options = dict(bind_ip=args.bind_ip, msop_port=args.msop_port,
                               difop_port=args.difop_port, source_ip=args.source_ip,
                               duration=args.duration,
                               max_packets=getattr(args, "max_packets", 0),
                               receive_buffer_bytes=getattr(args, "receive_buffer_bytes", 4 * 1024 * 1024))
                stats.update(receive_isolated(options, mailbox.put,
                                             stop_event=stop, on_ready=ready))
        except Exception as error:
            errors.append(error)
        finally:
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
        thread = threading.Thread(target=worker, name="e1r-input")
        deadline = time.monotonic() + args.duration if args.duration else math.inf
        thread.start()
        announced_end = False
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
                if errors or not capture or getattr(args, "exit_on_end", False):
                    break
                if not announced_end:
                    print("Playback finished. Close the window or press Ctrl+C to exit.", flush=True)
                    announced_end = True
            if time.monotonic() >= deadline:
                break
            time.sleep(max(0, 1/args.fps-(time.monotonic()-started)))
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        if thread is not None:
            thread.join()
        vis.destroy_window()  # Open3D requires the main thread.
        stats.update(rendered_frames=rendered, display_skipped_frames=mailbox.skipped + stats.get("input_skipped_frames", 0))
        report(stats, args.stats_json)
    if errors:
        raise RuntimeError(f"Input failed: {errors[0]}") from errors[0]
    return stats


def main():
    parser = argparse.ArgumentParser(description="Display live or captured E1R point clouds with Open3D")
    parser.add_argument("--pcap", help="PCAP or PCAPNG file; omit for live UDP reception")
    parser.add_argument("--rate", type=float, default=1.0, help="File playback speed; 0 decodes without waiting")
    parser.add_argument("--loop", action="store_true", help="Repeat file playback")
    parser.add_argument("--exit-on-end", action="store_true", help="Close when file playback finishes")
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
    if not math.isfinite(args.rate) or args.rate < 0:
        parser.error("rate must be finite and nonnegative")
    if not args.pcap and (args.loop or args.exit_on_end or args.rate != 1):
        parser.error("--loop, --exit-on-end and --rate require --pcap")
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
