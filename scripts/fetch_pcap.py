"""Download the pinned LFS object, checking identity before installation."""
import hashlib
from pathlib import Path
import urllib.request
from .inspect_pcap import EXPECTED_SHA, EXPECTED_SIZE

URL = ("https://media.githubusercontent.com/media/EdgeFirstAI/lidarpub/"
       "c7d4da23d6c9b33a06dda70e623b28cfbf767f65/testdata/e1r_frames.pcap")

def main():
    destination = Path("testdata/e1r_frames.pcap")
    if destination.exists():
        data = destination.read_bytes()
    else:
        with urllib.request.urlopen(URL, timeout=60) as response:
            data = response.read()
    if len(data) != EXPECTED_SIZE or hashlib.sha256(data).hexdigest() != EXPECTED_SHA:
        raise ValueError("PCAP size/SHA256 mismatch (possibly an LFS pointer); refusing to use it")
    destination.parent.mkdir(exist_ok=True)
    if not destination.exists():
        destination.write_bytes(data)
    print(f"Verified {destination}: {EXPECTED_SIZE} bytes, sha256={EXPECTED_SHA}")

if __name__ == "__main__":
    main()
