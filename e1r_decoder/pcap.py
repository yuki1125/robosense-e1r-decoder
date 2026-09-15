"""Streaming Ethernet/IPv4/IPv6 PCAP and PCAPNG UDP extraction."""
from collections import Counter
from dataclasses import dataclass
import dpkt

@dataclass
class UdpRecord:
    capture_timestamp: float
    payload: bytes
    source_ip: bytes
    destination_port: int

def read_pcap(path, stats=None):
    stats = stats if stats is not None else Counter()
    with open(path, "rb") as stream:
        magic = stream.read(24)
        if magic.startswith(b"version https://git-lfs"):
            raise ValueError("Git LFS pointer is not PCAP data")
        stream.seek(0)
        reader = dpkt.pcapng.Reader(stream) if magic[:4] == b"\x0a\x0d\x0d\x0a" else dpkt.pcap.Reader(stream)
        link = reader.datalink()
        if link != dpkt.pcap.DLT_EN10MB:
            raise ValueError(f"Unsupported PCAP link type: {link}; Ethernet required")
        for ts, raw in reader:
            stats["pcap_packets"] += 1
            try:
                ip = dpkt.ethernet.Ethernet(raw).data
                if not isinstance(ip, (dpkt.ip.IP, dpkt.ip6.IP6)):
                    continue
                if isinstance(ip, dpkt.ip.IP) and (ip.mf or ip.offset):
                    stats["fragmented_ip"] += 1
                    continue
                udp = ip.data
                if not isinstance(udp, dpkt.udp.UDP):
                    continue
                if udp.ulen < 8 or len(udp.data) != udp.ulen - 8:
                    stats["malformed_udp"] += 1
                    continue
                stats[f"udp_port_{udp.dport}"] += 1
                yield UdpRecord(float(ts), bytes(udp.data), ip.src, udp.dport)
            except (dpkt.UnpackError, ValueError, IndexError):
                stats["malformed_packet"] += 1
