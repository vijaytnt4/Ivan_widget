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

async def capture_screenshot(ws, filepath):
    res = await call_cdp(ws, 'Page.captureScreenshot', {'format': 'png'})
    img_data = base64.b64decode(res['data'])
    with open(filepath, 'wb') as f:
        f.write(img_data)
    print(f"[Screenshot] Saved to {filepath}")

async def run_animation_tests():
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

    try:
        tabs = requests.get('http://127.0.0.1:9222/json').json()
        target = [t for t in tabs if t.get('type') == 'page'][0]
        ws_url = target['webSocketDebuggerUrl']
        print(f"[CDP] Connected to Chrome: {ws_url}")

        async with websockets.connect(ws_url) as ws:
            await call_cdp(ws, 'Page.enable')
            await call_cdp(ws, 'Runtime.enable')

            print("[CDP] Navigating to http://ivan.local:10004/ ...")
            await call_cdp(ws, 'Page.navigate', {'url': 'http://ivan.local:10004/'})

            # Wait for readyState complete
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

            await call_cdp(ws, 'Runtime.evaluate', {'expression': 'window.confirm = () => true; window.alert = () => true;'})

            # -----------------------------------------------------------------
            # TEST 1: Initial closed state - animation paused
            # -----------------------------------------------------------------
            print("\n--- TEST 1: Initial closed state - animation paused ---")
            eval_closed = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sr = el.shadowRoot;
                    const img = sr.querySelector('.ivan-portrait-img');
                    const style = img ? window.getComputedStyle(img) : null;
                    return {
                        hasImg: Boolean(img),
                        playState: style ? style.animationPlayState : null,
                        animationName: style ? style.animationName : null
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': eval_closed, 'returnByValue': True})
            closed_info = res.get('result', {}).get('value', {})
            print(f"[Closed State]: {closed_info}")
            assert closed_info['playState'] == 'paused', "Animation must be paused when widget is closed"

            # -----------------------------------------------------------------
            # TEST 2: Open widget - Portrait idle animation running & properties
            # -----------------------------------------------------------------
            print("\n--- TEST 2: Open widget - Portrait idle animation active ---")
            await call_cdp(ws, 'Runtime.evaluate', {'expression': 'document.querySelector("ivan-chat-widget").open()'})
            await asyncio.sleep(0.5)

            eval_open_anim = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sr = el.shadowRoot;
                    const img = sr.querySelector('.ivan-portrait-img');
                    const headerImg = sr.querySelector('.ivan-header-avatar');
                    const style = img ? window.getComputedStyle(img) : null;
                    const hStyle = headerImg ? window.getComputedStyle(headerImg) : null;
                    return {
                        hasImg: Boolean(img),
                        imgSrc: img ? img.src : null,
                        naturalWidth: img ? img.naturalWidth : 0,
                        naturalHeight: img ? img.naturalHeight : 0,
                        animationName: style ? style.animationName : null,
                        animationDuration: style ? style.animationDuration : null,
                        animationTimingFunction: style ? style.animationTimingFunction : null,
                        animationIterationCount: style ? style.animationIterationCount : null,
                        animationPlayState: style ? style.animationPlayState : null,
                        transformOrigin: style ? style.transformOrigin : null,
                        headerAnimationName: hStyle ? hStyle.animationName : null,
                        headerPlayState: hStyle ? hStyle.animationPlayState : null
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': eval_open_anim, 'returnByValue': True})
            anim_info = res.get('result', {}).get('value', {})
            print(f"[Open State Animation Info]: {anim_info}")
            assert anim_info['hasImg'] == True, "Portrait image must exist"
            assert anim_info['naturalWidth'] > 0 and anim_info['naturalHeight'] > 0, "Image must be loaded"
            assert 'ivan-portrait-idle' in anim_info['animationName'], f"Expected ivan-portrait-idle, got {anim_info['animationName']}"
            assert '4.5s' in anim_info['animationDuration'], f"Expected 4.5s duration, got {anim_info['animationDuration']}"
            assert anim_info['animationIterationCount'] == 'infinite', "Must be infinite loop"
            assert anim_info['animationPlayState'] == 'running', "Must be running when open"
            assert 'ivan-header-avatar-idle' in anim_info['headerAnimationName'], "Header avatar must have idle animation"

            await capture_screenshot(ws, r"C:\Users\Anish\.gemini\antigravity\brain\2fb1f6ee-67b1-4770-affa-d6843cfe2d6a\screenshot_avatar_idle_animation.png")

            # -----------------------------------------------------------------
            # TEST 3: Animation Movement Sampling across cycle
            # -----------------------------------------------------------------
            print("\n--- TEST 3: Sampling animation transform across 4 seconds ---")
            transforms = []
            rects = []
            for step in range(5):
                res = await call_cdp(ws, 'Runtime.evaluate', {'expression': """
                    (() => {
                        const img = document.querySelector('ivan-chat-widget').shadowRoot.querySelector('.ivan-portrait-img');
                        const rect = img.getBoundingClientRect();
                        return {
                            transform: window.getComputedStyle(img).transform,
                            top: Math.round(rect.top * 10) / 10,
                            height: Math.round(rect.height * 10) / 10
                        };
                    })()
                """, 'returnByValue': True})
                val = res.get('result', {}).get('value', {})
                transforms.append(val.get('transform'))
                rects.append(val.get('top'))
                await asyncio.sleep(0.9)
            
            print(f"[Sampled Transforms]: {transforms}")
            print(f"[Sampled Tops]: {rects}")
            # Ensure transforms were active matrices (matrix(a, b, c, d, tx, ty))
            assert all(t.startswith('matrix') for t in transforms), "Transforms must be active matrix values"

            # -----------------------------------------------------------------
            # TEST 4: Reduced Motion Preference (@media prefers-reduced-motion)
            # -----------------------------------------------------------------
            print("\n--- TEST 4: Emulate prefers-reduced-motion: reduce ---")
            await call_cdp(ws, 'Emulation.setEmulatedMedia', {
                'media': 'screen',
                'features': [{'name': 'prefers-reduced-motion', 'value': 'reduce'}]
            })
            await asyncio.sleep(0.5)

            eval_reduced = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sr = el.shadowRoot;
                    const img = sr.querySelector('.ivan-portrait-img');
                    const headerImg = sr.querySelector('.ivan-header-avatar');
                    const style = window.getComputedStyle(img);
                    const hStyle = window.getComputedStyle(headerImg);
                    return {
                        imgAnimationName: style.animationName,
                        headerAnimationName: hStyle.animationName
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': eval_reduced, 'returnByValue': True})
            reduced_info = res.get('result', {}).get('value', {})
            print(f"[Reduced Motion Info]: {reduced_info}")
            assert reduced_info['imgAnimationName'] == 'none', "Portrait animation must be disabled under reduced motion"
            assert reduced_info['headerAnimationName'] == 'none', "Header animation must be disabled under reduced motion"

            # Clear emulation
            await call_cdp(ws, 'Emulation.setEmulatedMedia', {'media': '', 'features': []})
            await asyncio.sleep(0.5)

            # -----------------------------------------------------------------
            # TEST 5: Automatic Expansion and Messaging with Animation
            # -----------------------------------------------------------------
            print("\n--- TEST 5: Messaging & Auto-Expansion with animation intact ---")
            eval_send = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sr = el.shadowRoot;
                    const input = sr.querySelector('#messageInput');
                    input.value = 'Testing idle animation with message submission';
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    sr.querySelector('#sendBtn').click();
                    return {
                        isExpanded: el.isExpanded
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': eval_send, 'returnByValue': True})
            send_res = res.get('result', {}).get('value', {})
            print(f"[Auto-Expanded]: {send_res}")
            assert send_res['isExpanded'] == True, "Must expand"

            # Wait for assistant response
            for _ in range(25):
                await asyncio.sleep(1.0)
                res = await call_cdp(ws, 'Runtime.evaluate', {'expression': """
                    (() => {
                        const el = document.querySelector('ivan-chat-widget');
                        const lastMsg = el.messages[el.messages.length - 1];
                        return {
                            lastRole: lastMsg?.role,
                            isLoading: el.isLoading,
                            contentLen: lastMsg?.content?.length || 0
                        };
                    })()
                """, 'returnByValue': True})
                status = res.get('result', {}).get('value', {})
                if status.get('lastRole') == 'assistant' and not status.get('isLoading') and status.get('contentLen') > 5:
                    print(f"[Response Received in Expanded Panel]: {status}")
                    break

            assert status.get('lastRole') == 'assistant', "Assistant response must be received"

            # -----------------------------------------------------------------
            # TEST 6: Restore to compact view - portrait animation resumes
            # -----------------------------------------------------------------
            print("\n--- TEST 6: Restore to compact view - portrait animation resumes ---")
            await call_cdp(ws, 'Runtime.evaluate', {'expression': "document.querySelector('ivan-chat-widget').shadowRoot.querySelector('#expandBtn').click()"})
            await asyncio.sleep(0.6)

            eval_restored = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sr = el.shadowRoot;
                    const img = sr.querySelector('.ivan-portrait-img');
                    const style = window.getComputedStyle(img);
                    return {
                        isExpanded: el.isExpanded,
                        bannerDisplay: window.getComputedStyle(sr.querySelector('#portraitBanner')).display,
                        animationName: style.animationName,
                        animationPlayState: style.animationPlayState
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': eval_restored, 'returnByValue': True})
            restored_val = res.get('result', {}).get('value', {})
            print(f"[Restored State]: {restored_val}")
            assert restored_val['isExpanded'] == False, "Must be restored to compact view"
            assert restored_val['bannerDisplay'] == 'block', "Banner must be visible"
            assert 'ivan-portrait-idle' in restored_val['animationName'], "Animation active upon restore"
            assert restored_val['animationPlayState'] == 'running', "Animation running upon restore"

            # -----------------------------------------------------------------
            # TEST 7: Close widget - animation pauses
            # -----------------------------------------------------------------
            print("\n--- TEST 7: Close widget - animation pauses ---")
            await call_cdp(ws, 'Runtime.evaluate', {'expression': "document.querySelector('ivan-chat-widget').shadowRoot.querySelector('#closeBtn').click()"})
            await asyncio.sleep(0.5)

            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sr = el.shadowRoot;
                    const img = sr.querySelector('.ivan-portrait-img');
                    const style = window.getComputedStyle(img);
                    return {
                        isOpen: el.isOpen,
                        playState: style.animationPlayState
                    };
                })()
            """, 'returnByValue': True})
            close_val = res.get('result', {}).get('value', {})
            print(f"[Final Closed State]: {close_val}")
            assert close_val['isOpen'] == False, "Must be closed"
            assert close_val['playState'] == 'paused', "Animation must pause when closed"

            print("\n=======================================================")
            print("ALL AVATAR IDLE ANIMATION TESTS PASSED SUCCESSFULLY!")
            print("=======================================================\n")

    finally:
        proc.kill()

if __name__ == '__main__':
    asyncio.run(run_animation_tests())

