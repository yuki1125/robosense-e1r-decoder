"""Validate a local standalone HTML in installed Edge/Chrome, fully offline.

Optional developer dependency: pip install -e '.[browser-test]'
"""
import argparse
import json
from pathlib import Path
import time
import threading
import psutil
from playwright.sync_api import sync_playwright


def check(html, channel, output):
    output.mkdir(parents=True, exist_ok=True)
    peak = [0]
    stop = threading.Event()
    def sample_memory():
        while not stop.wait(0.1):
            total = 0
            for proc in psutil.Process().children(recursive=True):
                try:
                    if proc.name().lower() in ('chrome.exe', 'msedge.exe', 'chrome', 'msedge'):
                        total += proc.memory_info().rss
                except psutil.Error:
                    pass
            peak[0] = max(peak[0], total)
    monitor = threading.Thread(target=sample_memory, daemon=True)
    monitor.start()
    try:
        return _check(html, channel, output, peak)
    finally:
        stop.set()
        monitor.join()


def _check(html, channel, output, peak):
    with sync_playwright() as p:
        browser = p.chromium.launch(channel=channel, headless=True,
            args=['--enable-unsafe-swiftshader'])
        context = browser.new_context(viewport={'width':1280, 'height':800}, offline=True)
        page = context.new_page()
        requests, errors = [], []
        page.on('request', lambda req: requests.append(req.url) if req.url.startswith(('http:', 'https:')) else None)
        page.on('pageerror', lambda error: errors.append(str(error)))
        started = time.monotonic()
        page.goto(html.resolve().as_uri(), wait_until='load', timeout=180000)
        page.wait_for_function('() => window.e1rViewer && (e1rViewer.getState().current >= 0 || e1rViewer.getState().failed)', timeout=180000)
        initial = page.evaluate('e1rViewer.getState()')
        assert not initial['failed'], page.locator('#error').inner_text()
        load_seconds = time.monotonic()-started
        if initial['playing']:
            page.locator('#play').click()
        page.wait_for_function('() => !e1rViewer.getState().busy')
        initial = page.evaluate('e1rViewer.getState()')
        page.screenshot(path=str(output/(channel+'.png')))
        canvas = page.locator('#canvas').bounding_box()
        x,y = canvas['x']+canvas['width']/2, canvas['y']+canvas['height']/2
        page.mouse.move(x,y); page.mouse.down(); page.mouse.move(x+100,y+40,steps=5); page.mouse.up()
        changed = page.evaluate('e1rViewer.getState()')
        assert changed['camera'] != initial['camera']
        page.locator('#fit').click()
        seek_seconds=[]
        for index in [initial['frames']-1, initial['frames']//2, 0]:
            before=time.monotonic()
            page.locator('#seek').evaluate('(e, n) => { e.value=String(n); e.dispatchEvent(new Event("input")); }', index)
            page.wait_for_function('(i) => e1rViewer.getState().current===i && !e1rViewer.getState().busy', arg=index, timeout=30000)
            seek_seconds.append(time.monotonic()-before)
            state = page.evaluate('e1rViewer.getState()')
            assert state['cacheBytes'] <= 128*1024*1024 and state['cacheFrames'] <= 3
            assert state['drawn'] > 0
        page.locator('#next').click()
        page.wait_for_function('() => e1rViewer.getState().current === 1 && !e1rViewer.getState().busy')
        page.locator('#previous').click()
        page.wait_for_function('() => e1rViewer.getState().current === 0 && !e1rViewer.getState().busy')
        page.locator('#speed').select_option('2')
        page.locator('#play').click()
        page.wait_for_function('() => e1rViewer.getState().current >= 2')
        page.locator('#play').click()
        assert not errors, errors
        assert not requests, requests
        report=dict(status='PASS', channel=channel, browser=browser.version,
                    bytes=html.stat().st_size, load_seconds=load_seconds,
                    peak_browser_rss_bytes=peak[0], host_ram_bytes=psutil.virtual_memory().total,
                    seek_seconds=seek_seconds, state=page.evaluate('e1rViewer.getState()'),
                    external_requests=requests, page_errors=errors)
        (output/(channel+'.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report,indent=2))
        browser.close()
        return report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--html', type=Path, required=True)
    parser.add_argument('--channel', choices=['msedge','chrome'], default='msedge')
    parser.add_argument('--output', type=Path, default=Path('output/share-browser'))
    args=parser.parse_args()
    check(args.html,args.channel,args.output)


if __name__=='__main__':
    main()
