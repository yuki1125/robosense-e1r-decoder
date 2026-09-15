import argparse
import json
import dpkt
from .pcap import read_pcap
from .pipeline import Pipeline
from .output import save_frame, save_imu
from .constants import MSOP_PORT, DIFOP_PORT

def output_args(parser):
    parser.add_argument("--output")
    parser.add_argument("--format", choices=("npz", "pcd", "both"), default="npz")
    parser.add_argument("--debug", type=int, default=0, metavar="N")
    parser.add_argument("--stats-json")

def make_pipeline(args):
    def frame(f):
        print(f"Frame {f.frame_index}: packets={f.packet_count} points={len(f.points)} "
              f"start={f.start_timestamp:.9f} end={f.end_timestamp:.9f} "
              f"complete={f.complete} reasons={','.join(f.reasons)}")
        if args.output:
            save_frame(f, args.output, ("npz", "pcd") if args.format == "both" else (args.format,))
    def imu(i):
        if args.output:
            save_imu(i, args.output)
    return Pipeline(frame, imu, args.debug)

def report(stats, path=None):
    print(json.dumps(stats, indent=2))
    if path:
        from pathlib import Path
        Path(path).write_text(json.dumps(stats, indent=2), encoding="utf-8")

def main():
    p = argparse.ArgumentParser(description="Decode E1R PCAP in native coordinates")
    p.add_argument("--pcap", required=True)
    output_args(p)
    args = p.parse_args()
    pipeline = make_pipeline(args)
    try:
        for rec in read_pcap(args.pcap, pipeline.stats):
            if rec.destination_port in (MSOP_PORT, DIFOP_PORT):
                pipeline.feed(rec.payload, rec.destination_port, rec.capture_timestamp)
    except (ValueError, OSError, dpkt.UnpackError) as error:
        report(pipeline.finish(), args.stats_json)
        p.exit(1, f"PCAP error: {error}\n")
    report(pipeline.finish(), args.stats_json)

if __name__ == "__main__":
    main()
