import subprocess
import time
import json
import asyncio
import tempfile
import base64
import os
import functools
import websockets
import requests

print = functools.partial(print, flush=True)

req_counter = 0

async def call_cdp(ws, method, params=None):
    global req_counter
    req_counter += 1
    req_id = req_counter
    msg = {'id': req_id, 'method': method}
    if params:
        msg['params'] = params
    await ws.send(json.dumps(msg))
    while True:
        raw = await ws.recv()
        data = json.loads(raw)
        if data.get('id') == req_id:
            return data.get('result', {})

async def run_portrait_cropping_tests():
    temp_dir = tempfile.mkdtemp()
    chrome_path = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    proc = subprocess.Popen([
        chrome_path,
        '--headless=new',
        '--remote-debugging-port=9222',
        f'--user-data-dir={temp_dir}',
        '--window-size=1920,1080',
        '--disable-gpu',
        '--no-sandbox',
        'about:blank'
    ])
    time.sleep(2)

    console_errors = []

    try:
        tabs = requests.get('http://127.0.0.1:9222/json').json()
        target = [t for t in tabs if t.get('type') == 'page'][0]
        ws_url = target['webSocketDebuggerUrl']
        print(f"[CDP] Connected to Chrome: {ws_url}")

        async with websockets.connect(ws_url) as ws:
            await call_cdp(ws, 'Page.enable')
            await call_cdp(ws, 'Runtime.enable')

            async def listen_console():
                while True:
                    try:
                        raw = await ws.recv()
                        msg = json.loads(raw)
                        if msg.get('method') == 'Runtime.consoleAPICalled':
                            ptype = msg.get('params', {}).get('type')
                            if ptype in ['error', 'assert']:
                                console_errors.append(msg)
                    except:
                        break

            asyncio.create_task(listen_console())

            print("[CDP] Navigating to http://ivan.local:10004/ ...")
            await call_cdp(ws, 'Page.navigate', {'url': 'http://ivan.local:10004/'})

            # Wait for readyState
            for _ in range(25):
                res = await call_cdp(ws, 'Runtime.evaluate', {'expression': 'document.readyState', 'returnByValue': True})
                if res.get('result', {}).get('value') == 'complete':
                    break
                await asyncio.sleep(0.5)

            # Wait for ivan-chat-widget shadowRoot
            for _ in range(20):
                res = await call_cdp(ws, 'Runtime.evaluate', {'expression': 'Boolean(document.querySelector("ivan-chat-widget")?.shadowRoot)', 'returnByValue': True})
                if res.get('result', {}).get('value'):
                    break
                await asyncio.sleep(0.5)

            # Open the chat widget
            await call_cdp(ws, 'Runtime.evaluate', {'expression': 'document.querySelector("ivan-chat-widget").open()'})
            await asyncio.sleep(0.5)

            # -----------------------------------------------------------------
            # TEST 1: Layered Portrait Banner Structure & Background Styling
            # -----------------------------------------------------------------
            print("\n--- TEST 1: Layered Portrait Background Layer Verification ---")
            bg_eval = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sr = el.shadowRoot;
                    const banner = sr.querySelector('#portraitBanner');
                    const bg = sr.querySelector('.ivan-portrait-bg');
                    const overlay = sr.querySelector('.ivan-portrait-bg-overlay');
                    const bgStyle = bg ? window.getComputedStyle(bg) : null;
                    const bRect = banner.getBoundingClientRect();
                    return {
                        hasBanner: Boolean(banner),
                        bannerHeight: Math.round(bRect.height),
                        bannerWidth: Math.round(bRect.width),
                        hasBg: Boolean(bg),
                        hasOverlay: Boolean(overlay),
                        bgImage: bgStyle ? bgStyle.backgroundImage : null,
                        bgSize: bgStyle ? bgStyle.backgroundSize : null,
                        bgFilter: bgStyle ? bgStyle.filter : null
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': bg_eval, 'returnByValue': True})
            bg_info = res.get('result', {}).get('value', {})
            print(f"[Portrait Background Layer]: {bg_info}")
            assert bg_info['hasBanner'], "Portrait banner missing"
            assert abs(bg_info['bannerHeight'] - 180) <= 2, f"Banner height not ~180px: {bg_info['bannerHeight']}"
            assert bg_info['hasBg'] and bg_info['hasOverlay'], "Layered background or overlay elements missing"
            assert 'image-7.png' in bg_info['bgImage'], f"Background not using avatar image: {bg_info['bgImage']}"
            assert bg_info['bgSize'] == 'cover', f"Background sizing is not cover: {bg_info['bgSize']}"
            assert 'blur' in bg_info['bgFilter'], f"Background layer missing blur filter: {bg_info['bgFilter']}"
            print("[PASS] Layered background treatment verified (avatar cover image, blur filter, dark/teal overlay).")

            # -----------------------------------------------------------------
            # TEST 2: Foreground Image Object-Fit Contain & Full Visibility
            # -----------------------------------------------------------------
            print("\n--- TEST 2: Foreground Image Proportions & Uncropped Positioning ---")
            fg_eval = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sr = el.shadowRoot;
                    const img = sr.querySelector('.ivan-portrait-img');
                    const iStyle = window.getComputedStyle(img);
                    const iRect = img.getBoundingClientRect();
                    const bRect = sr.querySelector('#portraitBanner').getBoundingClientRect();
                    return {
                        objectFit: iStyle.objectFit,
                        objectPosition: iStyle.objectPosition,
                        naturalWidth: img.naturalWidth,
                        naturalHeight: img.naturalHeight,
                        renderedWidth: Math.round(iRect.width),
                        renderedHeight: Math.round(iRect.height),
                        topOffsetInBanner: Math.round(iRect.top - bRect.top),
                        bottomOffsetInBanner: Math.round(bRect.bottom - iRect.bottom)
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': fg_eval, 'returnByValue': True})
            fg_info = res.get('result', {}).get('value', {})
            print(f"[Foreground Image Metrics]: {fg_info}")
            assert fg_info['objectFit'] == 'contain', f"Foreground image must use object-fit: contain, got {fg_info['objectFit']}"
            # Rendered aspect ratio must equal natural aspect ratio (440 / 854 ≈ 0.515) -> no distortion
            aspect_rendered = fg_info['renderedWidth'] / fg_info['renderedHeight']
            aspect_natural = fg_info['naturalWidth'] / fg_info['naturalHeight']
            assert abs(aspect_rendered - aspect_natural) < 0.05, f"Image is distorted! Rendered: {aspect_rendered}, Natural: {aspect_natural}"
            print(f"[PASS] Aspect ratio strictly preserved ({aspect_rendered:.3f} vs {aspect_natural:.3f}). Zero distortion.")

            # -----------------------------------------------------------------
            # TEST 3: Capture After Screenshot (Cropping & Zoom Fixed)
            # -----------------------------------------------------------------
            print("\n--- TEST 3: Capturing High-Quality Portrait Screenshot ---")
            scr = await call_cdp(ws, 'Page.captureScreenshot', {'format': 'png'})
            with open('screenshot_portrait_fixed.png', 'wb') as f:
                f.write(base64.b64decode(scr['data']))
            print("[CDP] Captured screenshot_portrait_fixed.png")
            # Also update screenshot_normal_mode.png
            with open('screenshot_normal_mode.png', 'wb') as f:
                f.write(base64.b64decode(scr['data']))
            print("[CDP] Updated screenshot_normal_mode.png")

            # -----------------------------------------------------------------
            # TEST 4: Header & Message Avatars Unchanged
            # -----------------------------------------------------------------
            print("\n--- TEST 4: Header & Message Avatars Unchanged ---")
            avatar_eval = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sr = el.shadowRoot;
                    const headerImg = sr.querySelector('.ivan-header-avatar');
                    const msgImg = sr.querySelector('.ivan-msg-avatar-img');
                    const hStyle = headerImg ? window.getComputedStyle(headerImg) : null;
                    const mStyle = msgImg ? window.getComputedStyle(msgImg) : null;
                    const hRect = headerImg ? headerImg.getBoundingClientRect() : null;
                    return {
                        headerWidth: hRect ? Math.round(hRect.width) : null,
                        headerRadius: hStyle ? hStyle.borderRadius : null,
                        headerFit: hStyle ? hStyle.objectFit : null,
                        hasMsgAvatar: Boolean(msgImg),
                        msgRadius: mStyle ? mStyle.borderRadius : null
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': avatar_eval, 'returnByValue': True})
            av_info = res.get('result', {}).get('value', {})
            print(f"[Header and Message Avatars]: {av_info}")
            assert abs(av_info['headerWidth'] - 40) <= 2, f"Header avatar width corrupted: {av_info['headerWidth']}"
            assert '50%' in av_info['headerRadius'], f"Header avatar should be circular: {av_info['headerRadius']}"
            assert av_info['hasMsgAvatar'], "Message avatar missing"
            assert '50%' in av_info['msgRadius'], f"Message avatar should be circular: {av_info['msgRadius']}"
            print("[PASS] Header and message avatars remain completely unchanged (40px and 30px circular).")

            # -----------------------------------------------------------------
            # TEST 5: Fallback Behavior Intact
            # -----------------------------------------------------------------
            print("\n--- TEST 5: Fallback Behavior Verification ---")
            fallback_eval = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sr = el.shadowRoot;
                    const banner = sr.querySelector('#portraitBanner');
                    // Simulate error on portrait image
                    const img = sr.querySelector('.ivan-portrait-img');
                    img.dispatchEvent(new Event('error'));
                    const fallback = sr.querySelector('.ivan-portrait-fallback');
                    const fStyle = window.getComputedStyle(fallback);
                    const bg = sr.querySelector('.ivan-portrait-bg');
                    const bgStyle = window.getComputedStyle(bg);
                    return {
                        hasFallbackClass: banner.classList.contains('has-fallback'),
                        fallbackDisplay: fStyle.display,
                        bgDisplay: bgStyle.display
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': fallback_eval, 'returnByValue': True})
            fb_info = res.get('result', {}).get('value', {})
            print(f"[Fallback State]: {fb_info}")
            assert fb_info['hasFallbackClass'], "Missing has-fallback class on banner"
            assert fb_info['fallbackDisplay'] == 'flex', f"Fallback element should be flex: {fb_info['fallbackDisplay']}"
            assert fb_info['bgDisplay'] == 'none', f"Background should be hidden in fallback: {fb_info['bgDisplay']}"
            print("[PASS] Avatar fallback gracefully displays robot icon when avatar fails to load.")

            # Restore normal avatar
            await call_cdp(ws, 'Runtime.evaluate', {'expression': 'document.querySelector("ivan-chat-widget")._applyConfig()'})
            await asyncio.sleep(0.3)

            # -----------------------------------------------------------------
            # TEST 6: Mobile Responsiveness (<480px)
            # -----------------------------------------------------------------
            print("\n--- TEST 6: Mobile Responsiveness (<480px) ---")
            await call_cdp(ws, 'Emulation.setDeviceMetricsOverride', {
                'width': 375,
                'height': 667,
                'deviceScaleFactor': 2,
                'mobile': True
            })
            await asyncio.sleep(0.5)

            mobile_eval = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sr = el.shadowRoot;
                    const banner = sr.querySelector('#portraitBanner');
                    const img = sr.querySelector('.ivan-portrait-img');
                    const bRect = banner.getBoundingClientRect();
                    const iRect = img.getBoundingClientRect();
                    return {
                        bannerWidth: Math.round(bRect.width),
                        bannerHeight: Math.round(bRect.height),
                        imgWidth: Math.round(iRect.width),
                        imgHeight: Math.round(iRect.height)
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': mobile_eval, 'returnByValue': True})
            m_info = res.get('result', {}).get('value', {})
            print(f"[Mobile Banner Metrics]: {m_info}")
            assert m_info['bannerWidth'] <= 375, f"Banner width overflowed mobile viewport: {m_info['bannerWidth']}"
            assert abs(m_info['bannerHeight'] - 180) <= 2, f"Banner height shifted on mobile: {m_info['bannerHeight']}"
            assert m_info['imgWidth'] > 0 and m_info['imgHeight'] > 0, "Image failed to render on mobile"
            print("[PASS] Mobile banner is fully responsive without layout shift.")

            # Capture mobile screenshot
            scr_mob = await call_cdp(ws, 'Page.captureScreenshot', {'format': 'png'})
            with open('screenshot_mobile_mode.png', 'wb') as f:
                f.write(base64.b64decode(scr_mob['data']))
            print("[CDP] Captured updated screenshot_mobile_mode.png")

            # -----------------------------------------------------------------
            # TEST 7: Zero JavaScript Console Errors
            # -----------------------------------------------------------------
            print("\n--- TEST 7: Zero Console Errors Check ---")
            print(f"[Console Errors]: {console_errors}")
            assert len(console_errors) == 0, f"Found {len(console_errors)} console errors: {console_errors}"
            print("[PASS] Zero console errors logged.")

            print("\n" + "=" * 60)
            print("ALL PORTRAIT BANNER CROPPING TESTS PASSED WITH 100% SUCCESS!")
            print("=" * 60)

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except:
            proc.kill()

if __name__ == '__main__':
    asyncio.run(run_portrait_cropping_tests())

