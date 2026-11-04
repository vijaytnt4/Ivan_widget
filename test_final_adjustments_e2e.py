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

async def run_final_adjustments_tests():
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

            # -----------------------------------------------------------------
            # TEST 1: Initial state - Launcher is visible when chat closed
            # -----------------------------------------------------------------
            print("\n--- TEST 1: Launcher Visible When Chat Closed ---")
            check_init_launcher = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const launcher = el.shadowRoot.querySelector('#launcherBtn');
                    const lStyle = window.getComputedStyle(launcher);
                    const win = el.shadowRoot.querySelector('#window');
                    const wStyle = window.getComputedStyle(win);
                    return {
                        launcherDisplay: lStyle.display,
                        launcherVisibility: lStyle.visibility,
                        windowOpacity: wStyle.opacity,
                        windowVisibility: wStyle.visibility
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': check_init_launcher, 'returnByValue': True})
            init_info = res.get('result', {}).get('value', {})
            print(f"[Initial Launcher State]: {init_info}")
            assert init_info['launcherDisplay'] in ['flex', 'block'], f"Launcher should be visible initially: {init_info}"
            assert init_info['windowOpacity'] == '0', f"Window should be hidden initially: {init_info}"
            print("[PASS] Launcher initially visible and window hidden.")

            # -----------------------------------------------------------------
            # TEST 2: Open Chat - Launcher Disappears Completely
            # -----------------------------------------------------------------
            print("\n--- TEST 2: Floating Launcher Disappears When Chat Opens ---")
            # Click launcher or open()
            await call_cdp(ws, 'Runtime.evaluate', {'expression': 'document.querySelector("ivan-chat-widget").open()'})
            await asyncio.sleep(0.4)

            check_open_launcher = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const launcher = el.shadowRoot.querySelector('#launcherBtn');
                    const lStyle = window.getComputedStyle(launcher);
                    const win = el.shadowRoot.querySelector('#window');
                    const wStyle = window.getComputedStyle(win);
                    const wRect = win.getBoundingClientRect();
                    return {
                        launcherDisplay: lStyle.display,
                        windowOpacity: wStyle.opacity,
                        windowVisibility: wStyle.visibility,
                        windowBottomOffset: Math.round(window.innerHeight - wRect.bottom),
                        windowRightOffset: Math.round(window.innerWidth - wRect.right)
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': check_open_launcher, 'returnByValue': True})
            open_info = res.get('result', {}).get('value', {})
            print(f"[Open Launcher State]: {open_info}")
            assert open_info['launcherDisplay'] == 'none', f"Floating launcher must be hidden when chat open: {open_info['launcherDisplay']}"
            assert open_info['windowOpacity'] == '1', f"Window should be visible: {open_info['windowOpacity']}"
            assert abs(open_info['windowBottomOffset'] - 24) <= 4, f"Window bottom offset should be ~24px: {open_info['windowBottomOffset']}"
            print("[PASS] Floating launcher completely hidden when chat is open; window cleanly positioned at bottom: 24px.")

            # -----------------------------------------------------------------
            # TEST 3: Header Close Button Closes Window and Restores Launcher
            # -----------------------------------------------------------------
            print("\n--- TEST 3: Header Close Button Closes Window & Restores Launcher ---")
            close_click_eval = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const closeBtn = el.shadowRoot.querySelector('#closeBtn');
                    closeBtn.click();
                })()
            """
            await call_cdp(ws, 'Runtime.evaluate', {'expression': close_click_eval})
            await asyncio.sleep(0.4)

            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': check_init_launcher, 'returnByValue': True})
            after_close_info = res.get('result', {}).get('value', {})
            print(f"[After Header Close Click]: {after_close_info}")
            assert after_close_info['launcherDisplay'] in ['flex', 'block'], f"Launcher should be restored after close: {after_close_info}"
            assert after_close_info['windowOpacity'] == '0', f"Window should be hidden: {after_close_info}"
            print("[PASS] Header close button successfully closes window and restores floating launcher.")

            # Re-open chat
            await call_cdp(ws, 'Runtime.evaluate', {'expression': 'document.querySelector("ivan-chat-widget").open()'})
            await asyncio.sleep(0.4)

            # -----------------------------------------------------------------
            # TEST 4: Footer Disclaimer Removed Completely
            # -----------------------------------------------------------------
            print("\n--- TEST 4: Footer Disclaimer Removed in Normal Mode ---")
            check_disclaimer_eval = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sr = el.shadowRoot;
                    const brandNote = sr.querySelector('.ivan-brand-note');
                    const footerText = sr.querySelector('.ivan-footer').textContent;
                    return {
                        brandNoteExists: Boolean(brandNote),
                        brandNoteDisplay: brandNote ? window.getComputedStyle(brandNote).display : null,
                        hasMistakesText: footerText.includes('make mistakes') || footerText.includes('Powered by Ivan AI')
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': check_disclaimer_eval, 'returnByValue': True})
            disc_info = res.get('result', {}).get('value', {})
            print(f"[Disclaimer Check Normal Mode]: {disc_info}")
            assert not disc_info['brandNoteExists'] or disc_info['brandNoteDisplay'] == 'none', "Brand note must not be displayed"
            assert not disc_info['hasMistakesText'], f"Footer still contains disclaimer text: {disc_info}"
            print("[PASS] Footer disclaimer completely removed from normal mode.")

            # -----------------------------------------------------------------
            # TEST 5: Input Area Alignment and Spacing
            # -----------------------------------------------------------------
            print("\n--- TEST 5: Input Container Alignment & Spacing ---")
            check_input_eval = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sr = el.shadowRoot;
                    const footer = sr.querySelector('.ivan-footer');
                    const inputContainer = sr.querySelector('.ivan-input-container');
                    const textarea = sr.querySelector('#messageInput');
                    const sendBtn = sr.querySelector('#sendBtn');
                    const fRect = footer.getBoundingClientRect();
                    const iRect = inputContainer.getBoundingClientRect();
                    const tRect = textarea.getBoundingClientRect();
                    const sRect = sendBtn.getBoundingClientRect();
                    return {
                        footerHeight: Math.round(fRect.height),
                        inputContainerHeight: Math.round(iRect.height),
                        textareaHeight: Math.round(tRect.height),
                        sendBtnSize: Math.round(sRect.width),
                        sendBtnAligned: Math.abs(tRect.bottom - sRect.bottom) < 15
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': check_input_eval, 'returnByValue': True})
            input_info = res.get('result', {}).get('value', {})
            print(f"[Input Area Layout]: {input_info}")
            assert 50 <= input_info['footerHeight'] <= 75, f"Footer height without disclaimer should be ~55-70px, got {input_info['footerHeight']}"
            assert input_info['sendBtnAligned'], "Send button and textarea are misaligned"
            print("[PASS] Input container and send button properly positioned and aligned without excess footer spacing.")

            # -----------------------------------------------------------------
            # TEST 6: Expanded Mode Height (+50-70px) and Launcher Still Hidden
            # -----------------------------------------------------------------
            print("\n--- TEST 6: Expanded Mode Height & No Launcher Interference ---")
            # Expand chat
            await call_cdp(ws, 'Runtime.evaluate', {'expression': 'document.querySelector("ivan-chat-widget").expand()'})
            await asyncio.sleep(0.4)

            check_expanded_eval = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sr = el.shadowRoot;
                    const win = sr.querySelector('#window');
                    const launcher = sr.querySelector('#launcherBtn');
                    const lStyle = window.getComputedStyle(launcher);
                    const wRect = win.getBoundingClientRect();
                    const footerText = sr.querySelector('.ivan-footer').textContent;
                    return {
                        width: Math.round(wRect.width),
                        height: Math.round(wRect.height),
                        launcherDisplay: lStyle.display,
                        hasMistakesText: footerText.includes('make mistakes') || footerText.includes('Powered by Ivan AI'),
                        windowTop: Math.round(wRect.top),
                        windowBottom: Math.round(window.innerHeight - wRect.bottom)
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': check_expanded_eval, 'returnByValue': True})
            exp_info = res.get('result', {}).get('value', {})
            print(f"[Expanded Mode Metrics]: {exp_info}")
            # Verified width ~ 380px and height ~ 850px (+60px from previous 790px)
            assert 365 <= exp_info['width'] <= 385, f"Expanded width not ~380px: {exp_info['width']}"
            assert 830 <= exp_info['height'] <= 865, f"Expanded height not ~850px: {exp_info['height']}"
            assert exp_info['launcherDisplay'] == 'none', "Launcher must be hidden in expanded mode"
            assert not exp_info['hasMistakesText'], "Footer disclaimer must be absent in expanded mode"
            assert exp_info['windowTop'] >= 20, f"Expanded panel overflowing top of viewport: {exp_info['windowTop']}"
            print("[PASS] Expanded panel height is ~850px (+60px increase), within viewport, launcher hidden.")

            # Capture fresh screenshot of expanded mode
            scr_exp = await call_cdp(ws, 'Page.captureScreenshot', {'format': 'png'})
            with open('screenshot_expanded_mode.png', 'wb') as f:
                f.write(base64.b64decode(scr_exp['data']))
            print("[CDP] Captured updated screenshot_expanded_mode.png")

            # Restore compact mode
            await call_cdp(ws, 'Runtime.evaluate', {'expression': 'document.querySelector("ivan-chat-widget").restore()'})
            await asyncio.sleep(0.4)

            # Capture fresh screenshot of normal mode
            scr_norm = await call_cdp(ws, 'Page.captureScreenshot', {'format': 'png'})
            with open('screenshot_normal_mode.png', 'wb') as f:
                f.write(base64.b64decode(scr_norm['data']))
            print("[CDP] Captured updated screenshot_normal_mode.png")

            # -----------------------------------------------------------------
            # TEST 7: Mobile Responsiveness (<480px)
            # -----------------------------------------------------------------
            print("\n--- TEST 7: Mobile Responsiveness (<480px) ---")
            await call_cdp(ws, 'Emulation.setDeviceMetricsOverride', {
                'width': 375,
                'height': 667,
                'deviceScaleFactor': 2,
                'mobile': True
            })
            await asyncio.sleep(0.5)

            mobile_compact_eval = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sr = el.shadowRoot;
                    const win = sr.querySelector('#window');
                    const launcher = sr.querySelector('#launcherBtn');
                    const lStyle = window.getComputedStyle(launcher);
                    const wRect = win.getBoundingClientRect();
                    return {
                        width: Math.round(wRect.width),
                        height: Math.round(wRect.height),
                        launcherDisplay: lStyle.display,
                        bottomOffset: Math.round(window.innerHeight - wRect.bottom)
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': mobile_compact_eval, 'returnByValue': True})
            m_comp = res.get('result', {}).get('value', {})
            print(f"[Mobile Compact Mode]: {m_comp}")
            assert m_comp['width'] <= 375, f"Mobile compact width overflowed: {m_comp['width']}"
            assert m_comp['launcherDisplay'] == 'none', f"Launcher must remain hidden on mobile: {m_comp['launcherDisplay']}"
            assert abs(m_comp['bottomOffset'] - 16) <= 4, f"Mobile compact should sit 16px from bottom: {m_comp['bottomOffset']}"
            print("[PASS] Mobile compact view sits at bottom: 16px with floating launcher hidden.")

            # Expand on mobile
            await call_cdp(ws, 'Runtime.evaluate', {'expression': 'document.querySelector("ivan-chat-widget").expand()'})
            await asyncio.sleep(0.4)

            mobile_exp_eval = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sr = el.shadowRoot;
                    const win = sr.querySelector('#window');
                    const wRect = win.getBoundingClientRect();
                    return {
                        width: Math.round(wRect.width),
                        height: Math.round(wRect.height)
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': mobile_exp_eval, 'returnByValue': True})
            m_exp = res.get('result', {}).get('value', {})
            print(f"[Mobile Expanded Mode]: {m_exp}")
            assert abs(m_exp['width'] - 375) <= 2, f"Mobile expanded should be 375px: {m_exp['width']}"
            assert abs(m_exp['height'] - 667) <= 2, f"Mobile expanded should be 667px: {m_exp['height']}"
            print("[PASS] Mobile expanded view fills 100vw x 100dvh without overflow.")

            scr_mob = await call_cdp(ws, 'Page.captureScreenshot', {'format': 'png'})
            with open('screenshot_mobile_mode.png', 'wb') as f:
                f.write(base64.b64decode(scr_mob['data']))
            print("[CDP] Captured updated screenshot_mobile_mode.png")

            # -----------------------------------------------------------------
            # TEST 8: Zero Console Errors
            # -----------------------------------------------------------------
            print("\n--- TEST 8: Zero JavaScript Console Errors ---")
            print(f"[Console Errors Found]: {console_errors}")
            assert len(console_errors) == 0, f"Found {len(console_errors)} console errors: {console_errors}"
            print("[PASS] Zero console errors across all test steps.")

            print("\n" + "=" * 60)
            print("ALL 8 FINAL UI ADJUSTMENT TESTS PASSED WITH 100% SUCCESS!")
            print("=" * 60)

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except:
            proc.kill()

if __name__ == '__main__':
    asyncio.run(run_final_adjustments_tests())

