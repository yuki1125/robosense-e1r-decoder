import base64
import gzip
import json
from pathlib import Path
import re

import dpkt
import numpy as np
import pytest

from e1r_decoder.export_share import export_share, encode_points
from e1r_decoder.constants import POINT_DTYPE
from e1r_decoder.pcap import read_pcap
from e1r_decoder.pipeline import Pipeline
from test_playback import write_capture


def read_html(path):
    html = path.read_text(encoding='utf-8-sig')
    manifest = json.loads(re.search(r'<script type="application/json" id="manifest">(.*?)</script>', html).group(1))
    encoded = re.findall(r'<script type="application/octet-stream" id="frame-\d+">(.*?)</script>', html)
    return manifest, [gzip.decompress(base64.b64decode(text, validate=True)) for text in encoded]


@pytest.mark.parametrize('pcapng', [False, True])
def test_lossless_public_capture(tmp_path, pcapng):
    import dpkt
    original = Path('testdata/e1r_frames.pcap')
    source = original
    if pcapng:
        source = tmp_path/'input.pcapng'
        with original.open('rb') as src, source.open('wb') as dst:
            writer = dpkt.pcapng.Writer(dst)
            for timestamp, packet in dpkt.pcap.Reader(src):
                writer.writepkt(packet, ts=float(timestamp))
    expected = []
    pipeline = Pipeline(on_frame=expected.append)
    for rec in read_pcap(source):
        pipeline.feed(rec.payload, rec.destination_port, rec.capture_timestamp)
    pipeline.finish()
    target = tmp_path/'share.html'
    result = export_share(source, target, progress=None)
    manifest, decoded = read_html(target)
    assert result['frames'] == 50 and result['points'] == 1361664
    assert len(decoded) == len(expected)
    for frame, meta, raw in zip(expected, manifest['frames'], decoded):
        assert raw == encode_points(frame.points)
        assert meta['complete'] == frame.complete
        assert meta['capture_start'] == frame.capture_start_timestamp
        assert meta['capture_end'] == frame.capture_end_timestamp
        assert meta['count'] == len(frame.points)
    assert manifest['frames'][0]['time'] == 0
    assert not manifest['frames'][0]['complete'] and not manifest['frames'][-1]['complete']
    assert b'<script src=' not in target.read_bytes()


def test_zero_and_nonfinite_preserved():
    points = np.zeros(3, dtype=POINT_DTYPE)
    points['x'] = [0, np.inf, np.nan]
    points['timestamp'] = [1.000001, 1e9+.000001, 100]
    raw = encode_points(points)
    assert len(raw) == 63
    np.testing.assert_array_equal(np.frombuffer(raw[:36], '<f4').reshape(-1, 3)[:,0], points['x'])
    np.testing.assert_array_equal(np.frombuffer(raw[39:], '<f8'), points['timestamp'])


def test_overwrite_and_atomic_failure(tmp_path, packet_factory):
    source, output = tmp_path/'capture.pcap', tmp_path/'share.html'
    write_capture(source, [packet_factory()])
    output.write_text('old')
    with pytest.raises(FileExistsError):
        export_share(source, output, progress=None)
    def interrupt(message):
        raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        export_share(source, output, overwrite=True, progress=interrupt)
    assert output.read_text() == 'old'
    assert not list(tmp_path.glob('.e1r-share-*'))
    export_share(source, output, overwrite=True, progress=None)
    assert read_html(output)[0]['points'] == 96
    with pytest.raises(ValueError, match='different'):
        export_share(source, source, overwrite=True)


def test_empty_and_source_filter(tmp_path, packet_factory):
    source, target = tmp_path/'capture.pcap', tmp_path/'share.html'
    write_capture(source, [])
    with pytest.raises(ValueError, match='No valid'):
        export_share(source, target, progress=None)
    assert not target.exists() and not list(tmp_path.glob('.e1r-share-*'))
    write_capture(source, [packet_factory()], port=9999)
    with pytest.raises(ValueError, match='No valid'):
        export_share(source, target, progress=None)
    result = export_share(source, target, msop_port=9999, source_ip='192.168.1.200', progress=None)
    assert result['points'] == 96


def test_capture_regression(tmp_path, packet_factory):
    source, target = tmp_path/'capture.pcap', tmp_path/'share.html'
    write_capture(source, (packet_factory(seq=n) for n in list(range(1,30))*3), spacing=-0.001)
    result = export_share(source, target, progress=None)
    manifest, _ = read_html(target)
    times = [f['time'] for f in manifest['frames']]
    assert times == sorted(times)
    assert result['capture_regressions'] == 86


def test_truncated_capture_not_published(tmp_path):
    source, target = tmp_path/'capture.pcapng', tmp_path/'share.html'
    source.write_bytes(b'\x0a\x0d\x0d\x0a')
    with pytest.raises((ValueError, dpkt.UnpackError)):
        export_share(source, target, progress=None)
    assert not target.exists() and not list(tmp_path.glob('.e1r-share-*'))
