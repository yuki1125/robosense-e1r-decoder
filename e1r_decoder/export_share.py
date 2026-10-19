"""Lossless, standalone HTML export. No Open3D or browser needed to export."""
import argparse
import base64
import gzip
import ipaddress
import json
import math
import os
from pathlib import Path
import tempfile

import numpy as np

from .constants import MSOP_PORT, DIFOP_PORT
from .pcap import read_pcap
from .pipeline import Pipeline

FORMAT_VERSION = 1
POINT_BYTES = 21  # interleaved xyz <f4, intensity u1, timestamp <f8 (three arrays)
MARKER = '<!-- E1R_DATA -->'


def encode_points(points):
    """No downsampling or quantization; timestamps follow the uint8 array."""
    xyz = np.column_stack([points[k] for k in 'xyz']).astype('<f4')
    return (xyz.tobytes() + points['intensity'].astype('u1').tobytes()
            + points['timestamp'].astype('<f8').tobytes())


def safe_json(value):
    return json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(',', ':')).replace('<', '\\u003c')


def export_share(pcap, output, *, msop_port=MSOP_PORT, difop_port=DIFOP_PORT,
                 source_ip=None, overwrite=False, progress=print):
    source, target = Path(pcap), Path(output)
    if source.resolve() == target.resolve():
        raise ValueError('Input and output must be different files')
    if target.exists() and not overwrite:
        raise FileExistsError(f'{target} exists; use --overwrite')
    if msop_port == difop_port or not all(0 < p < 65536 for p in (msop_port, difop_port)):
        raise ValueError('MSOP/DIFOP must be distinct ports in 1..65535')
    address = ipaddress.ip_address(source_ip).packed if source_ip else None
    template = Path(__file__).with_name('share_viewer.html').read_text(encoding='utf-8')
    prefix, suffix = template.split(MARKER)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.e1r-share-', suffix='.tmp', dir=target.parent)
    temporary = Path(temporary)
    index, total_points, origin, previous_time, capture_regressions = [], 0, None, 0.0, 0
    sensor_address, previous_capture = None, None
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(prefix)

            def on_frame(frame):
                nonlocal origin, total_points, previous_time
                start, end = frame.capture_start_timestamp, frame.capture_end_timestamp
                if start is None or end is None or not math.isfinite(start) or not math.isfinite(end):
                    raise ValueError('Frame has no finite capture timestamps')
                if origin is None:
                    origin = start
                relative = max(previous_time, start-origin, 0.0)
                previous_time = relative
                raw = encode_points(frame.points)
                encoded = base64.b64encode(gzip.compress(raw, compresslevel=6, mtime=0)).decode('ascii')
                number = len(index)
                stream.write(f'<script type="application/octet-stream" id="frame-{number}">{encoded}</script>\n')
                bounds = np.column_stack([frame.points[k] for k in 'xyz'])
                bounds = bounds[np.isfinite(bounds).all(axis=1)]
                bbox = [bounds.min(axis=0).tolist(), bounds.max(axis=0).tolist()] if len(bounds) else None
                index.append(dict(index=number, count=len(frame.points), time=relative,
                                  end_time=max(relative, end-origin), capture_start=start, capture_end=end,
                                  lidar_start=frame.start_timestamp, lidar_end=frame.end_timestamp,
                                  complete=frame.complete, reasons=frame.reasons, bounds=bbox,
                                  nonfinite=len(frame.points)-len(bounds), bytes=len(raw)))
                total_points += len(frame.points)
                if progress and (number == 0 or (number+1) % 100 == 0):
                    progress(f'Frames: {number+1}, points: {total_points}, HTML: {stream.tell()/1e6:.1f} MB')

            pipeline = Pipeline(on_frame=on_frame)
            for record in read_pcap(source, pipeline.stats):
                if address is not None and record.source_ip != address:
                    pipeline.stats['source_filtered'] += 1
                    continue
                if record.destination_port not in (msop_port, difop_port):
                    continue
                if not math.isfinite(record.capture_timestamp):
                    raise ValueError('Non-finite capture timestamp')
                if record.destination_port == msop_port:
                    if sensor_address is None:
                        sensor_address = record.source_ip
                    elif sensor_address != record.source_ip:
                        raise ValueError('Multiple MSOP sources; select one with --source-ip')
                    if previous_capture is not None and record.capture_timestamp < previous_capture:
                        capture_regressions += 1
                    previous_capture = record.capture_timestamp
                port = MSOP_PORT if record.destination_port == msop_port else DIFOP_PORT
                pipeline.feed(record.payload, port, record.capture_timestamp)
            stats = pipeline.finish()
            if not index:
                raise ValueError('No valid E1R point frames found; check capture, ports and source IP')
            manifest = dict(version=FORMAT_VERSION, layout='xyz-f32le,intensity-u8,timestamp-f64le',
                            title=source.name, points=total_points, frames=index,
                            capture_regressions=capture_regressions,
                            duration=max(item['end_time'] for item in index), stats=stats)
            stream.write('<script type="application/json" id="manifest">'+safe_json(manifest)+'</script>\n')
            stream.write(suffix)
        if overwrite:
            os.replace(temporary, target)
        else:
            # Publish without replacing a file created by another process meanwhile.
            os.link(temporary, target)
            temporary.unlink()
        result = dict(frames=len(index), points=total_points, bytes=target.stat().st_size,
                      capture_regressions=capture_regressions, output=str(target))
        if progress:
            progress(json.dumps(result, ensure_ascii=False))
        return result
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description='Export E1R PCAP/PCAPNG as a standalone offline 3D HTML')
    parser.add_argument('--pcap', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--msop-port', type=int, default=MSOP_PORT)
    parser.add_argument('--difop-port', type=int, default=DIFOP_PORT)
    parser.add_argument('--source-ip')
    parser.add_argument('--overwrite', action='store_true')
    args = parser.parse_args()
    try:
        export_share(args.pcap, args.output, msop_port=args.msop_port, difop_port=args.difop_port,
                     source_ip=args.source_ip, overwrite=args.overwrite)
    except (OSError, ValueError) as error:
        parser.exit(1, f'Export error: {error}\n')


if __name__ == '__main__':
    main()
