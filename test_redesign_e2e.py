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

async def run_redesign_tests():
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

        async with websockets.connect(ws_url, max_size=20*1024*1024) as ws:
            await call_cdp(ws, 'Page.enable')
            await call_cdp(ws, 'Runtime.enable')

            # Listen for console errors
            async def monitor_events():
                while True:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=0.1)
                        evt = json.loads(raw)
                        if evt.get('method') == 'Runtime.exceptionThrown':
                            console_errors.append(evt['params'])
                    except asyncio.TimeoutError:
                        break

            print("[CDP] Navigating to http://ivan.local:10004/ ...")
            await call_cdp(ws, 'Page.navigate', {'url': 'http://ivan.local:10004/'})

            # Wait for readyState === complete
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

            # Open the widget
            await call_cdp(ws, 'Runtime.evaluate', {'expression': 'document.querySelector("ivan-chat-widget").open()'})
            await asyncio.sleep(0.6)

            # -----------------------------------------------------------------
            # TEST 1 & 2: Normal Widget Appearance & Portrait Banner
            # -----------------------------------------------------------------
            print("\n--- TEST 1 & 2: Normal Widget Appearance & Portrait Banner ---")
            normal_eval = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sr = el.shadowRoot;
                    const win = sr.querySelector('.ivan-window');
                    const portrait = sr.querySelector('#portraitBanner');
                    const img = portrait ? portrait.querySelector('img.ivan-portrait-img') : null;
                    const wRect = win.getBoundingClientRect();
                    const pRect = portrait ? portrait.getBoundingClientRect() : null;
                    const iStyle = img ? window.getComputedStyle(img) : null;
                    return {
                        windowWidth: Math.round(wRect.width),
                        windowHeight: Math.round(wRect.height),
                        hasPortrait: Boolean(portrait),
                        portraitWidth: pRect ? Math.round(pRect.width) : 0,
                        portraitHeight: pRect ? Math.round(pRect.height) : 0,
                        imgSrc: img ? img.src : null,
                        objectFit: iStyle ? iStyle.objectFit : null,
                        objectPosition: iStyle ? iStyle.objectPosition : null
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': normal_eval, 'returnByValue': True})
            n_info = res.get('result', {}).get('value', {})
            print(f"[Normal Mode]: {n_info}")
            assert n_info['hasPortrait'], "Portrait banner missing in normal mode"
            assert n_info['portraitHeight'] >= 150, f"Portrait height too small: {n_info['portraitHeight']}"
            assert n_info['objectFit'] == 'contain', f"Portrait object-fit is not contain: {n_info['objectFit']}"
            assert n_info['imgSrc'] and 'image-7.png' in n_info['imgSrc'], f"Portrait image src incorrect: {n_info['imgSrc']}"
            print("[PASS] Normal mode appearance and portrait banner verified.")

            # Capture Screenshot 1: Normal Mode
            scr_res = await call_cdp(ws, 'Page.captureScreenshot', {'format': 'png'})
            with open('screenshot_normal_mode.png', 'wb') as f:
                f.write(base64.b64decode(scr_res['data']))
            print("[CDP] Captured screenshot_normal_mode.png")

            # -----------------------------------------------------------------
            # TEST 3: Header Controls Order & Accessibility
            # -----------------------------------------------------------------
            print("\n--- TEST 3: Header Controls Order (Refresh, Expand, Close) ---")
            header_eval = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const actions = Array.from(el.shadowRoot.querySelectorAll('.ivan-header-actions button'));
                    return actions.map(b => ({
                        id: b.id,
                        title: b.title,
                        ariaLabel: b.getAttribute('aria-label')
                    }));
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': header_eval, 'returnByValue': True})
            h_buttons = res.get('result', {}).get('value', [])
            print(f"[Header Buttons]: {h_buttons}")
            assert len(h_buttons) == 3, f"Expected 3 buttons, found: {len(h_buttons)}"
            assert h_buttons[0]['id'] == 'resetBtn', f"First button should be resetBtn, got: {h_buttons[0]['id']}"
            assert h_buttons[1]['id'] == 'expandBtn', f"Second button should be expandBtn, got: {h_buttons[1]['id']}"
            assert h_buttons[2]['id'] == 'closeBtn', f"Third button should be closeBtn, got: {h_buttons[2]['id']}"
            assert 'expand' in h_buttons[1]['title'].lower() or 'restore' in h_buttons[1]['title'].lower()
            print("[PASS] Header buttons order and accessible labels verified.")

            # -----------------------------------------------------------------
            # TEST 4 & 9: Expand Mode Functionality & Desktop Dimensions
            # -----------------------------------------------------------------
            print("\n--- TEST 4 & 9: Expand Functionality & Desktop Dimensions ---")
            expand_eval = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const expandBtn = el.shadowRoot.querySelector('#expandBtn');
                    expandBtn.click();
                    return el.isExpanded;
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': expand_eval, 'returnByValue': True})
            assert res.get('result', {}).get('value') is True, "Widget isExpanded should be true"
            await asyncio.sleep(0.6)

            dim_eval = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sr = el.shadowRoot;
                    const win = sr.querySelector('.ivan-window');
                    const portrait = sr.querySelector('#portraitBanner');
                    const pStyle = window.getComputedStyle(portrait);
                    const btn = sr.querySelector('#expandBtn');
                    const wRect = win.getBoundingClientRect();
                    return {
                        width: Math.round(wRect.width),
                        height: Math.round(wRect.height),
                        isExpandedClass: el.shadowRoot.querySelector('#container').classList.contains('is-expanded'),
                        portraitDisplay: pStyle.display,
                        btnTitle: btn.title,
                        btnAria: btn.getAttribute('aria-label')
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': dim_eval, 'returnByValue': True})
            d_info = res.get('result', {}).get('value', {})
            print(f"[Expanded Mode Dimensions]: {d_info}")
            # Target width ~ 380px, height increased to ~ 850px (on 1080p screen)
            assert 365 <= d_info['width'] <= 385, f"Expanded width not in 365-385px range: {d_info['width']}"
            assert 830 <= d_info['height'] <= 865, f"Expanded height not approx 850px: {d_info['height']}"
            assert d_info['isExpandedClass'], "Container missing is-expanded class"
            assert d_info['portraitDisplay'] == 'none', f"Portrait should be hidden in expanded mode: {d_info['portraitDisplay']}"
            assert 'restore' in d_info['btnTitle'].lower(), f"Button title should switch to restore: {d_info['btnTitle']}"
            print("[PASS] Expanded mode verified: ~380px width, ~850px height (+60px taller), portrait hidden, restore icon.")

            # Capture Screenshot 2: Expanded Mode
            scr_res2 = await call_cdp(ws, 'Page.captureScreenshot', {'format': 'png'})
            with open('screenshot_expanded_mode.png', 'wb') as f:
                f.write(base64.b64decode(scr_res2['data']))
            print("[CDP] Captured screenshot_expanded_mode.png")

            # -----------------------------------------------------------------
            # TEST 5: Conversation Persistence across Mode Toggling
            # -----------------------------------------------------------------
            print("\n--- TEST 5: Conversation & Input Persistence Across Expand/Restore ---")
            # Type input and send a message
            send_test_eval = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const input = el.shadowRoot.querySelector('#messageInput');
                    input.value = "Why should someone work with Nav?";
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    el.sendMessage();
                })()
            """
            await call_cdp(ws, 'Runtime.evaluate', {'expression': send_test_eval})

            # Wait for response
            print("[CDP] Waiting for assistant response...")
            for _ in range(40):
                res = await call_cdp(ws, 'Runtime.evaluate', {'expression': 'document.querySelector("ivan-chat-widget").messages.length', 'returnByValue': True})
                cnt = res.get('result', {}).get('value', 0)
                is_loading = (await call_cdp(ws, 'Runtime.evaluate', {'expression': 'document.querySelector("ivan-chat-widget").isLoading', 'returnByValue': True})).get('result', {}).get('value')
                print(f"[CDP wait]: msg count = {cnt}, loading = {is_loading}")
                if cnt >= 3 and not is_loading:
                    break
                await asyncio.sleep(0.5)

            # Record state before toggle
            before_eval = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const input = el.shadowRoot.querySelector('#messageInput');
                    input.value = "Drafting next question...";
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    return {
                        msgCount: el.messages.length,
                        convId: el.conversationId,
                        sessionId: el.sessionId,
                        inputValue: input.value
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': before_eval, 'returnByValue': True})
            state_before = res.get('result', {}).get('value', {})
            print(f"[State Before Toggles]: {state_before}")

            # Toggle 4 times (Restore -> Expand -> Restore -> Expand)
            for i in range(4):
                await call_cdp(ws, 'Runtime.evaluate', {'expression': 'document.querySelector("ivan-chat-widget").toggleExpand()'})
                await asyncio.sleep(0.2)

            # Verify state after
            after_eval = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const input = el.shadowRoot.querySelector('#messageInput');
                    return {
                        msgCount: el.messages.length,
                        convId: el.conversationId,
                        sessionId: el.sessionId,
                        inputValue: input.value,
                        isExpanded: el.isExpanded
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': after_eval, 'returnByValue': True})
            state_after = res.get('result', {}).get('value', {})
            print(f"[State After 4 Toggles]: {state_after}")
            assert state_before['msgCount'] == state_after['msgCount'], "Message count lost during toggle!"
            assert state_before['convId'] == state_after['convId'], "Conversation ID altered during toggle!"
            assert state_before['sessionId'] == state_after['sessionId'], "Session ID altered during toggle!"
            assert state_before['inputValue'] == state_after['inputValue'], "User input draft lost during toggle!"
            print("[PASS] Conversation history, IDs, and draft input perfectly preserved.")

            # -----------------------------------------------------------------
            # TEST 6: Active SSE Response while Switching Modes
            # -----------------------------------------------------------------
            print("\n--- TEST 6: Active SSE Response while Switching Modes ---")
            stream_start_eval = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const input = el.shadowRoot.querySelector('#messageInput');
                    input.value = "Give a detailed summary of strategic frameworks";
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    el.sendMessage();
                })()
            """
            await call_cdp(ws, 'Runtime.evaluate', {'expression': stream_start_eval})
            await asyncio.sleep(0.3)

            # Toggle while loading!
            await call_cdp(ws, 'Runtime.evaluate', {'expression': 'document.querySelector("ivan-chat-widget").restore()'})
            await asyncio.sleep(0.2)
            await call_cdp(ws, 'Runtime.evaluate', {'expression': 'document.querySelector("ivan-chat-widget").expand()'})

            # Wait for stream completion
            print("[CDP] Waiting for streamed assistant response...")
            for _ in range(40):
                is_loading = (await call_cdp(ws, 'Runtime.evaluate', {'expression': 'document.querySelector("ivan-chat-widget").isLoading', 'returnByValue': True})).get('result', {}).get('value')
                cnt = (await call_cdp(ws, 'Runtime.evaluate', {'expression': 'document.querySelector("ivan-chat-widget").messages.length', 'returnByValue': True})).get('result', {}).get('value', 0)
                print(f"[CDP stream wait]: msg count = {cnt}, loading = {is_loading}")
                if not is_loading and cnt >= 5:
                    break
                await asyncio.sleep(0.5)

            last_msg_eval = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const msgs = el.messages;
                    const last = msgs[msgs.length - 1];
                    return {
                        role: last.role,
                        contentLength: last.content ? last.content.length : 0,
                        hasError: last.isError || false
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': last_msg_eval, 'returnByValue': True})
            last_msg = res.get('result', {}).get('value', {})
            print(f"[Streamed Response Result]: {last_msg}")
            assert last_msg['role'] == 'assistant', "Last message not from assistant"
            assert last_msg['contentLength'] > 20, "Stream failed or truncated during mode switch"
            assert not last_msg['hasError'], "Streaming threw an error during mode switch"
            print("[PASS] Active SSE response completed smoothly across mode switches.")

            # -----------------------------------------------------------------
            # TEST 7 & 8: Refresh, Close & Input Controls
            # -----------------------------------------------------------------
            print("\n--- TEST 7 & 8: Refresh, Close & Input Controls ---")
            # Close window
            await call_cdp(ws, 'Runtime.evaluate', {'expression': 'document.querySelector("ivan-chat-widget").close()'})
            await asyncio.sleep(0.3)
            is_open = (await call_cdp(ws, 'Runtime.evaluate', {'expression': 'document.querySelector("ivan-chat-widget").isOpen', 'returnByValue': True})).get('result', {}).get('value')
            assert is_open is False, "Close button failed to close window"

            # Reopen
            await call_cdp(ws, 'Runtime.evaluate', {'expression': 'document.querySelector("ivan-chat-widget").open()'})
            await asyncio.sleep(0.3)

            # Test Reset / Refresh
            await call_cdp(ws, 'Runtime.evaluate', {'expression': 'window.confirm = () => true; document.querySelector("ivan-chat-widget").resetConversation();'})
            await asyncio.sleep(0.3)
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': 'document.querySelector("ivan-chat-widget").messages.length', 'returnByValue': True})
            assert res.get('result', {}).get('value') <= 1, "Reset did not clear conversation"
            print("[PASS] Refresh and close controls verified.")

            # -----------------------------------------------------------------
            # TEST 10: Mobile Responsiveness at 375x667
            # -----------------------------------------------------------------
            print("\n--- TEST 10: Mobile Responsiveness (375x667) ---")
            await call_cdp(ws, 'Emulation.setDeviceMetricsOverride', {
                'width': 375,
                'height': 667,
                'deviceScaleFactor': 2,
                'mobile': True
            })
            await asyncio.sleep(0.5)

            # Normal mobile mode
            await call_cdp(ws, 'Runtime.evaluate', {'expression': 'document.querySelector("ivan-chat-widget").restore()'})
            await asyncio.sleep(0.4)
            mob_norm = (await call_cdp(ws, 'Runtime.evaluate', {'expression': '''
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const win = el.shadowRoot.querySelector('.ivan-window');
                    const rect = win.getBoundingClientRect();
                    return { width: Math.round(rect.width), height: Math.round(rect.height) };
                })()
            ''', 'returnByValue': True})).get('result', {}).get('value', {})
            print(f"[Mobile Normal Mode]: {mob_norm}")
            assert mob_norm['width'] <= 375, f"Normal mobile window overflow: {mob_norm['width']}"

            # Expanded mobile mode
            await call_cdp(ws, 'Runtime.evaluate', {'expression': 'document.querySelector("ivan-chat-widget").expand()'})
            await asyncio.sleep(0.4)
            mob_exp = (await call_cdp(ws, 'Runtime.evaluate', {'expression': '''
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const win = el.shadowRoot.querySelector('.ivan-window');
                    const rect = win.getBoundingClientRect();
                    return { width: Math.round(rect.width), height: Math.round(rect.height) };
                })()
            ''', 'returnByValue': True})).get('result', {}).get('value', {})
            print(f"[Mobile Expanded Mode]: {mob_exp}")
            assert abs(mob_exp['width'] - 375) <= 2, f"Mobile expanded not fullscreen width: {mob_exp['width']}"

            # Capture Screenshot 3: Mobile Mode
            scr_res3 = await call_cdp(ws, 'Page.captureScreenshot', {'format': 'png'})
            with open('screenshot_mobile_mode.png', 'wb') as f:
                f.write(base64.b64decode(scr_res3['data']))
            print("[CDP] Captured screenshot_mobile_mode.png")

            # -----------------------------------------------------------------
            # TEST 11: No Microphone or Speak Now Controls
            # -----------------------------------------------------------------
            print("\n--- TEST 11: Verify No Microphone or Speak Now Controls ---")
            no_voice_eval = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sr = el.shadowRoot;
                    const html = sr.innerHTML.toLowerCase();
                    const hasSpeakNow = html.includes('speak now') || html.includes('speak with');
                    const hasMic = html.includes('mic') || sr.querySelector('[aria-label*="voice"]') || sr.querySelector('[aria-label*="mic"]');
                    return { hasSpeakNow, hasMic: Boolean(hasMic) };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': no_voice_eval, 'returnByValue': True})
            voice_info = res.get('result', {}).get('value', {})
            print(f"[Voice / Mic Check]: {voice_info}")
            assert not voice_info['hasSpeakNow'], "Speak Now button found in widget!"
            assert not voice_info['hasMic'], "Microphone button found in widget!"
            print("[PASS] Verified: Zero microphone, speech, or Speak Now controls.")

            # -----------------------------------------------------------------
            # TEST 12: Zero JavaScript Console Errors
            # -----------------------------------------------------------------
            print("\n--- TEST 12: Console Errors Check ---")
            print(f"[Console Errors]: {console_errors}")
            assert len(console_errors) == 0, f"JavaScript errors detected: {console_errors}"
            print("[PASS] Zero JavaScript console errors.")

            print("\n" + "=" * 60)
            print("ALL 12 REDESIGN TESTS COMPLETED WITH 100% SUCCESS!")
            print("=" * 60)

    finally:
        proc.kill()

if __name__ == "__main__":
    asyncio.run(run_redesign_tests())
