"""Generate full-point synthetic duration fixtures from a short exported HTML.

Repeats measured geometry with shifted frame/point times; not a new measurement.
Runs offline browser checks separately via scripts.check_share_browser.
"""
import argparse
import base64
import gzip
import json
from pathlib import Path
import re

import numpy as np
from e1r_decoder.export_share import MARKER, safe_json


def make_fixture(source, target, seconds):
    text=source.read_text(encoding='utf-8-sig')
    manifest=json.loads(re.search(r'<script type="application/json" id="manifest">(.*?)</script>',text).group(1))
    payloads=re.findall(r'<script type="application/octet-stream" id="frame-\d+">(.*?)</script>',text)
    complete=[(f,gzip.decompress(base64.b64decode(payloads[i]))) for i,f in enumerate(manifest['frames']) if f['complete']]
    template=Path('e1r_decoder/share_viewer.html').read_text(encoding='utf-8-sig')
    prefix,suffix=template.split(MARKER)
    frames=[]
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('w',encoding='utf-8') as out:
        out.write(prefix)
        for i in range(round(seconds*10)):
            original,raw=complete[i%len(complete)]
            f=dict(original,index=i,time=i/10,end_time=(i+1)/10,
                   capture_start=1000+i/10,capture_end=1000+(i+1)/10)
            points=f['count']
            shift=i/10-original['time']
            timestamps=np.frombuffer(raw[13*points:],'<f8')+shift
            shifted=raw[:13*points]+timestamps.astype('<f8').tobytes()
            f.update(lidar_start=original['lidar_start']+shift,lidar_end=original['lidar_end']+shift)
            encoded=base64.b64encode(gzip.compress(shifted,mtime=0)).decode('ascii')
            out.write(f'<script type="application/octet-stream" id="frame-{i}">{encoded}</script>\n')
            frames.append(f)
            if (i+1)%600==0: print(f'{i+1} frames; {out.tell()/1e6:.1f} MB',flush=True)
        m=dict(manifest,frames=frames,points=sum(f['count'] for f in frames),duration=seconds,
               title=f'SYNTHETIC repeated capture: {seconds} seconds',stats={})
        out.write('<script type="application/json" id="manifest">'+safe_json(m)+'</script>\n'+suffix)
    print(f'{target}: {target.stat().st_size} bytes',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--seconds',type=int,choices=[60,600],required=True)
    a=p.parse_args()
    make_fixture(a.source,a.output,a.seconds)
