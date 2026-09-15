import argparse
import socket
import time
from .pcap import read_pcap
from .constants import MSOP_PORT

def replay(path, dst_ip="127.0.0.1", dst_port=MSOP_PORT, rate=1.0, source_port=MSOP_PORT):
    count = 0
    first = None
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        for rec in read_pcap(path):
            if rec.destination_port != source_port:
                continue
            if first is None:
                first, start = rec.capture_timestamp, time.monotonic()
            if rate > 0:
                delay = start + (rec.capture_timestamp-first)/rate - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
            sock.sendto(rec.payload, (dst_ip, dst_port))
            count += 1
    return count

def main():
    p = argparse.ArgumentParser(description="Replay captured E1R UDP payloads")
    p.add_argument("--pcap", required=True)
    p.add_argument("--dst-ip", default="127.0.0.1")
    p.add_argument("--dst-port", type=int, default=MSOP_PORT)
    p.add_argument("--source-port", type=int, default=MSOP_PORT)
    group = p.add_mutually_exclusive_group()
    group.add_argument("--realtime", action="store_true")
    group.add_argument("--rate", type=float, default=1.0)
    args = p.parse_args()
    if args.rate < 0 or not __import__('math').isfinite(args.rate):
        p.error("rate must be finite and nonnegative")
    print(f"Sent packets: {replay(args.pcap, args.dst_ip, args.dst_port, args.rate, args.source_port)}")

if __name__ == "__main__":
    main()
