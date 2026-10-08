import socket
import threading

import dpkt
import numpy as np
import pytest

from e1r_decoder import playback


def write_capture(path, payloads, *, pcapng=False, port=6699, spacing=0.001):
    with path.open("wb") as stream:
        writer = (dpkt.pcapng.Writer if pcapng else dpkt.pcap.Writer)(stream)
        for i, payload in enumerate(payloads):
            udp = dpkt.udp.UDP(sport=6699, dport=port, data=payload, ulen=8+len(payload))
            ip = dpkt.ip.IP(src=socket.inet_aton("192.168.1.200"),
                            dst=socket.inet_aton("192.168.1.100"), p=17, data=udp)
            ip.len = len(ip)
            eth = dpkt.ethernet.Ethernet(type=dpkt.ethernet.ETH_TYPE_IP, data=ip)
            writer.writepkt(bytes(eth), ts=1000+i*spacing)


@pytest.mark.parametrize("pcapng", [False, True])
def test_both_formats_and_final_partial(tmp_path, packet_factory, pcapng):
    path = tmp_path / ("scan.pcapng" if pcapng else "scan.pcap")
    write_capture(path, (packet_factory(seq=n) for n in list(range(1, 30))*2+[1]),
                  pcapng=pcapng, port=9000)
    frames = []
    stats = playback.play_capture(path, frames.append, rate=0, msop_port=9000,
                                  source_ip="192.168.1.200")
    assert stats["valid_msop"] == 59 and stats["playback_passes"] == 1
    assert [f.complete for f in frames] == [False, True, False]
    assert [f.packet_count for f in frames] == [29, 29, 1]
    assert frames[1].points["intensity"][0] == 42


def test_repeated_passes_reset_assembler(tmp_path, packet_factory):
    path = tmp_path / "scan.pcap"
    write_capture(path, [packet_factory()])
    stop = threading.Event()
    frames = []
    def emit(frame):
        frames.append(frame)
        if len(frames) == 3:
            stop.set()
    playback.play_capture(path, emit, rate=0, loop=True, stop_event=stop)
    assert len(frames) == 3
    assert all(f.frame_index == 0 and f.packet_count == 1 for f in frames)


@pytest.mark.parametrize("mode", ["empty", "invalid", "wrong_port", "wrong_source"])
def test_no_valid_msop_fails_without_looping(tmp_path, packet_factory, mode):
    path = tmp_path / "scan.pcap"
    packets = [] if mode == "empty" else [b"bad" if mode == "invalid" else packet_factory()]
    write_capture(path, packets, port=1234 if mode == "wrong_port" else 6699)
    with pytest.raises(ValueError, match="No valid E1R"):
        playback.play_capture(path, lambda f: None, loop=True, rate=0,
                              source_ip="192.168.1.201" if mode == "wrong_source" else None)


def test_capture_timing_rate_and_interrupt(tmp_path, packet_factory, monkeypatch):
    path = tmp_path / "scan.pcap"
    write_capture(path, [packet_factory(), packet_factory(seq=2)], spacing=10)
    now = [0.0]
    monkeypatch.setattr(playback.time, "monotonic", lambda: now[0])
    class ClockStop:
        def is_set(self):
            return False
        def wait(self, seconds):
            now[0] += seconds
            return False
    stats = playback.play_capture(path, lambda f: None, rate=2, stop_event=ClockStop())
    assert now[0] == 5 and stats["valid_msop"] == 2
    now[0] = 0
    stats = playback.play_capture(path, lambda f: None, duration=1, stop_event=ClockStop())
    assert now[0] == 1 and stats["valid_msop"] == 1
    class CancelStop(ClockStop):
        def wait(self, seconds):
            return seconds > 0
    stats = playback.play_capture(path, lambda f: None, stop_event=CancelStop())
    assert stats["valid_msop"] == 1


def test_public_capture_pcapng_matches_pcap(tmp_path):
    """Same real measurements, converted container; no claim of real DIFOP."""
    from pathlib import Path
    source = Path("testdata/e1r_frames.pcap")
    converted = tmp_path / "e1r.pcapng"
    with source.open("rb") as src, converted.open("wb") as dst:
        writer = dpkt.pcapng.Writer(dst)
        for timestamp, data in dpkt.pcap.Reader(src):
            writer.writepkt(data, ts=float(timestamp))
    expected, actual = [], []
    a = playback.play_capture(source, expected.append, rate=0)
    b = playback.play_capture(converted, actual.append, rate=0)
    assert a == b and a["valid_msop"] == 14184 and len(actual) == 50
    for left, right in zip(expected, actual):
        assert left.complete == right.complete and left.sequences == right.sequences
        np.testing.assert_array_equal(left.points, right.points)
