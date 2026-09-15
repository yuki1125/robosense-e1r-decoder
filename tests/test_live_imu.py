import json
import socket
import struct
import subprocess
import sys
import time
from e1r_decoder.constants import DIFOP_MAGIC
from test_udp import free_ports

def test_live_synthetic_imu(tmp_path):
    msop, difop = free_ports()
    log_path = tmp_path/"log.txt"
    with log_path.open("w") as log:
        proc = subprocess.Popen([sys.executable,"-m","e1r_decoder.live","--bind-ip","127.0.0.1",
            "--msop-port",str(msop),"--difop-port",str(difop),"--max-packets","2",
            "--duration","5","--output",str(tmp_path)], stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic()+5
            while "READY" not in log_path.read_text():
                assert proc.poll() is None and time.monotonic() < deadline
                time.sleep(.02)
            payload = bytearray(256)
            payload[:8] = DIFOP_MAGIC
            struct.pack_into(">6f", payload, 208, 1,2,3,4,5,6)
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.sendto(b"bad", ("127.0.0.1", msop))
                s.sendto(payload, ("127.0.0.1", difop))
            proc.wait(timeout=8)
            assert proc.returncode == 0, log_path.read_text()
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
    imu = json.loads((tmp_path/"imu.jsonl").read_text())
    assert imu["accel_x_raw"] == 1 and imu["gyro_z_raw"] == 6
    assert imu["capture_timestamp"] is None and imu["receive_timestamp"] > 0
