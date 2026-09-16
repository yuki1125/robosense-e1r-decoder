import socket
import struct
import threading
import time

import pytest

from e1r_decoder import E1RSensor
from e1r_decoder.constants import DIFOP_MAGIC


def free_ports():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as a, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as b:
        a.bind(('127.0.0.1', 0))
        b.bind(('127.0.0.1', 0))
        return a.getsockname()[1], b.getsockname()[1]


def test_udp_read_and_cleanup(packet_factory):
    msop, difop = free_ports()
    with E1RSensor(bind_ip='127.0.0.1', msop_port=msop, difop_port=difop) as sensor:
        with pytest.raises(TimeoutError):
            sensor.read(timeout=0.01)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
            imu = bytearray(256)
            imu[:8] = DIFOP_MAGIC
            struct.pack_into('>6f', imu, 208, 1, 2, 3, 4, 5, 6)
            sender.sendto(imu, ('127.0.0.1', difop))
            time.sleep(0.02)
            for seq in list(range(1, 30)) * 2 + [1]:
                sender.sendto(packet_factory(seq=seq), ('127.0.0.1', msop))
                time.sleep(0.001)
        frame, sample = sensor.read(timeout=2)
        assert frame.complete and len(frame.points) == 29 * 96
        assert frame.points['intensity'][0] == 42
        assert sample.accel_x_raw == 1 and sample.gyro_z_raw == 6
    assert not sensor._thread.is_alive()
    sensor.close()
    with pytest.raises(RuntimeError, match='closed'):
        sensor.read()
    for port in (msop, difop):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind(('127.0.0.1', port))


def test_latest_queue_and_no_imu(monkeypatch, packet_factory):
    emitted = threading.Event()
    def fake_receive(pipeline, *, stop_event, on_ready, **kwargs):
        on_ready()
        for seq in list(range(1, 30)) * 4 + [1]:
            pipeline.feed(packet_factory(seq=seq))
        emitted.set()
        stop_event.wait()
    monkeypatch.setattr('e1r_decoder.live.receive', fake_receive)
    with E1RSensor() as sensor:
        assert emitted.wait(2)
        frame, imu = sensor.read(timeout=1)
        assert frame.frame_index == 3 and imu is None
        assert sensor.dropped_frames == 2
        with pytest.raises(TimeoutError):
            sensor.read(timeout=0)


def test_startup_failure():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(('127.0.0.1', 0))
        sensor = E1RSensor(bind_ip='127.0.0.1', msop_port=sock.getsockname()[1])
        with pytest.raises(RuntimeError, match='failed to start') as exc:
            sensor.start()
        assert isinstance(exc.value.__cause__, OSError)
        assert not sensor._thread.is_alive()


def test_background_failure(monkeypatch):
    fail = threading.Event()
    def fake_receive(pipeline, *, on_ready, **kwargs):
        on_ready()
        fail.wait()
        raise OSError('receiver failed')
    monkeypatch.setattr('e1r_decoder.live.receive', fake_receive)
    with E1RSensor() as sensor:
        fail.set()
        with pytest.raises(RuntimeError, match='receiver failed'):
            sensor.read(timeout=2)


def test_close_unblocks_read(monkeypatch):
    def fake_receive(pipeline, *, on_ready, stop_event, **kwargs):
        on_ready()
        stop_event.wait()
    monkeypatch.setattr('e1r_decoder.live.receive', fake_receive)
    sensor = E1RSensor().start()
    errors = []
    def reader():
        try:
            sensor.read()
        except RuntimeError as error:
            errors.append(str(error))
    thread = threading.Thread(target=reader)
    thread.start()
    sensor.close()
    thread.join(2)
    assert not thread.is_alive() and errors == ['E1R receiver is closed']
    with pytest.raises(RuntimeError):
        sensor.start()


def test_partial_opt_in(monkeypatch, packet_factory):
    emitted = threading.Event()
    def fake_receive(pipeline, *, on_ready, stop_event, **kwargs):
        on_ready()
        for seq in list(range(14, 30)) + [1]:
            pipeline.feed(packet_factory(seq=seq))
        emitted.set()
        stop_event.wait()
    monkeypatch.setattr('e1r_decoder.live.receive', fake_receive)
    with E1RSensor(complete_only=False) as sensor:
        assert emitted.wait(2)
        frame, imu = sensor.read(timeout=1)
        assert not frame.complete and imu is None


def test_arguments_and_unstarted():
    with pytest.raises(ValueError):
        E1RSensor(queue_size=0)
    sensor = E1RSensor()
    with pytest.raises(RuntimeError):
        sensor.read(timeout=0)
    with pytest.raises(ValueError):
        sensor.read(timeout=-1)
    sensor.close()
