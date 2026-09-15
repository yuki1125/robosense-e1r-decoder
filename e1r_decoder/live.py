import argparse
import selectors
import socket
import time
from .constants import MSOP_PORT, DIFOP_PORT
from .decode_pcap import output_args, make_pipeline, report

def receive(pipeline, *, bind_ip="0.0.0.0", msop_port=MSOP_PORT,
            difop_port=DIFOP_PORT, source_ip=None, max_packets=0,
            duration=0, stop_event=None, on_ready=lambda: None):
    """Shared blocking receiver. Caller owns pipeline.finish() and reporting."""
    with selectors.DefaultSelector() as selector:
        sockets = []
        try:
            for port, kind in ((msop_port, MSOP_PORT), (difop_port, DIFOP_PORT)):
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sockets.append(sock)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
                sock.bind((bind_ip, port))
                sock.setblocking(False)
                selector.register(sock, selectors.EVENT_READ, kind)
            started = time.monotonic()
            on_ready()
            while not duration or time.monotonic()-started < duration:
                if stop_event is not None and stop_event.is_set():
                    break
                for key, _ in selector.select(0.1):
                    payload, address = key.fileobj.recvfrom(65535)
                    if source_ip and address[0] != source_ip:
                        pipeline.stats["source_filtered"] += 1
                        continue
                    pipeline.feed(payload, key.data, receive_timestamp=time.time())
                    if max_packets and pipeline.stats["received"] >= max_packets:
                        return
        finally:
            for sock in sockets:
                sock.close()

def main():
    p = argparse.ArgumentParser(description="Receive E1R MSOP and DIFOP UDP")
    p.add_argument("--bind-ip", default="0.0.0.0")
    p.add_argument("--msop-port", type=int, default=MSOP_PORT)
    p.add_argument("--difop-port", type=int, default=DIFOP_PORT)
    p.add_argument("--source-ip", help="Optional sensor IPv4 address filter")
    p.add_argument("--max-packets", type=int, default=0)
    p.add_argument("--duration", type=float, default=0)
    output_args(p)
    args = p.parse_args()
    pipeline = make_pipeline(args)
    try:
        receive(pipeline, bind_ip=args.bind_ip, msop_port=args.msop_port,
                difop_port=args.difop_port, source_ip=args.source_ip,
                max_packets=args.max_packets, duration=args.duration,
                on_ready=lambda: print("READY", flush=True))
    except KeyboardInterrupt:
        pass
    finally:
        report(pipeline.finish(), args.stats_json)

if __name__ == "__main__":
    main()
