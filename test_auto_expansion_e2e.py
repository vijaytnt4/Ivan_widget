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

async def run_e2e_tests():
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
    network_requests = []

    try:
        tabs = requests.get('http://127.0.0.1:9222/json').json()
        target = [t for t in tabs if t.get('type') == 'page'][0]
        ws_url = target['webSocketDebuggerUrl']
        print(f"[CDP] Connected to Chrome: {ws_url}")

        async with websockets.connect(ws_url) as ws:
            await call_cdp(ws, 'Page.enable')
            await call_cdp(ws, 'Runtime.enable')
            await call_cdp(ws, 'Network.enable')

            async def listen_events():
                while True:
                    try:
                        raw = await ws.recv()
                        msg = json.loads(raw)
                        method = msg.get('method')
                        if method == 'Runtime.consoleAPICalled':
                            ptype = msg.get('params', {}).get('type')
                            if ptype in ['error', 'assert']:
                                console_errors.append(msg)
                        elif method == 'Network.requestWillBeSent':
                            req = msg.get('params', {}).get('request', {})
                            if 'ivan' in req.get('url', '').lower() or 'chat' in req.get('url', '').lower():
                                network_requests.append(req)
                    except:
                        break

            asyncio.create_task(listen_events())

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

            # Avoid alert/confirm dialog blocking
            await call_cdp(ws, 'Runtime.evaluate', {'expression': 'window.confirm = () => true; window.alert = () => true;'})

            # -----------------------------------------------------------------
            # TEST 1: Page Load & Compact Floating Card Mode
            # -----------------------------------------------------------------
            print("\n--- TEST 1: Page Load & Compact Floating Card Mode ---")
            # Open widget without sending messages
            await call_cdp(ws, 'Runtime.evaluate', {'expression': 'document.querySelector("ivan-chat-widget").open()'})
            await asyncio.sleep(0.5)

            eval_compact = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sr = el.shadowRoot;
                    const container = sr.querySelector('#container');
                    const win = sr.querySelector('#window');
                    const banner = sr.querySelector('#portraitBanner');
                    const rect = win.getBoundingClientRect();
                    const bannerRect = banner.getBoundingClientRect();
                    return {
                        isExpanded: el.isExpanded,
                        hasExpandedClass: container.classList.contains('is-expanded'),
                        isOpen: container.classList.contains('is-open'),
                        winWidth: Math.round(rect.width),
                        winHeight: Math.round(rect.height),
                        bannerVisible: bannerRect.height > 0 && window.getComputedStyle(banner).display !== 'none',
                        bannerHeight: Math.round(bannerRect.height)
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': eval_compact, 'returnByValue': True})
            compact_info = res.get('result', {}).get('value', {})
            print(f"[Initial Compact State]: {compact_info}")
            assert compact_info['isOpen'] == True, "Widget should be open"
            assert compact_info['isExpanded'] == False, "Widget should initially NOT be expanded"
            assert not compact_info['hasExpandedClass'], "Container should NOT have is-expanded class"
            assert compact_info['winWidth'] == 380, f"Compact width expected 380, got {compact_info['winWidth']}"
            assert compact_info['winHeight'] == 600, f"Compact height expected 600, got {compact_info['winHeight']}"
            assert compact_info['bannerVisible'] == True, "Portrait banner must be visible in compact mode"

            await capture_screenshot(ws, r"C:\Users\Anish\.gemini\antigravity\brain\2fb1f6ee-67b1-4770-affa-d6843cfe2d6a\screenshot_compact_mode.png")

            # -----------------------------------------------------------------
            # TEST 2: Empty / Whitespace Message Does NOT Auto-Expand
            # -----------------------------------------------------------------
            print("\n--- TEST 2: Empty / Whitespace Message Does NOT Auto-Expand ---")
            eval_empty = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sr = el.shadowRoot;
                    const input = sr.querySelector('#messageInput');
                    input.value = '   ';
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    const sendBtn = sr.querySelector('#sendBtn');
                    const wasDisabled = sendBtn.disabled;
                    // Attempt to call sendMessage with empty string
                    el.sendMessage('   ');
                    return {
                        wasDisabled,
                        isExpanded: el.isExpanded
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': eval_empty, 'returnByValue': True})
            empty_info = res.get('result', {}).get('value', {})
            print(f"[Empty Message Check]: {empty_info}")
            assert empty_info['isExpanded'] == False, "Empty message must not expand widget"
            assert empty_info['wasDisabled'] == True, "Send button must be disabled for whitespace"

            # -----------------------------------------------------------------
            # TEST 3: First Valid Message Triggers Immediate Auto-Expansion
            # -----------------------------------------------------------------
            print("\n--- TEST 3: First Valid Message Triggers Immediate Auto-Expansion ---")
            req_count_before = len(network_requests)
            
            # Send first valid message via UI send button
            eval_send_first = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sr = el.shadowRoot;
                    const input = sr.querySelector('#messageInput');
                    input.value = 'why people work with nav';
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    const sendBtn = sr.querySelector('#sendBtn');
                    sendBtn.click();
                    // Return state immediately after click
                    return {
                        isExpanded: el.isExpanded,
                        hasExpandedClass: sr.querySelector('#container').classList.contains('is-expanded')
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': eval_send_first, 'returnByValue': True})
            first_msg_res = res.get('result', {}).get('value', {})
            print(f"[Immediate Auto-Expansion State]: {first_msg_res}")
            assert first_msg_res['isExpanded'] == True, "Widget should expand immediately upon valid message"
            assert first_msg_res['hasExpandedClass'] == True, "Container must have is-expanded class immediately"

            # Allow CSS transition to complete (300ms transition)
            await asyncio.sleep(0.6)

            # Check dimensions of expanded panel
            eval_expanded_dims = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sr = el.shadowRoot;
                    const container = sr.querySelector('#container');
                    const win = sr.querySelector('#window');
                    const banner = sr.querySelector('#portraitBanner');
                    const expandBtn = sr.querySelector('#expandBtn');
                    const rect = win.getBoundingClientRect();
                    const bannerStyle = window.getComputedStyle(banner);
                    const winStyle = window.getComputedStyle(win);
                    return {
                        isExpanded: el.isExpanded,
                        winWidth: Math.round(rect.width),
                        winHeight: Math.round(rect.height),
                        viewportHeight: window.innerHeight,
                        bannerDisplay: bannerStyle.display,
                        expandBtnTitle: expandBtn.getAttribute('title'),
                        boxShadow: winStyle.boxShadow,
                        messagesCount: el.messages.length
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': eval_expanded_dims, 'returnByValue': True})
            exp_dims = res.get('result', {}).get('value', {})
            print(f"[Expanded Panel Dimensions]: {exp_dims}")
            assert exp_dims['isExpanded'] == True, "Must be expanded"
            # 420px width on desktop (min(420px, calc(100vw - 24px)))
            assert exp_dims['winWidth'] == 420, f"Expected 420px width, got {exp_dims['winWidth']}"
            # 1080 - 48 = 1032px height on 1080p viewport (calc(100vh - 48px))
            expected_h = exp_dims['viewportHeight'] - 48
            assert abs(exp_dims['winHeight'] - expected_h) <= 2, f"Expected {expected_h}px height, got {exp_dims['winHeight']}"
            assert exp_dims['bannerDisplay'] == 'none', "Portrait banner must be hidden in expanded panel"
            assert 'Restore' in exp_dims['expandBtnTitle'], "Expand button title should now offer restore"

            # -----------------------------------------------------------------
            # TEST 4: Streaming Assistant Response Into Expanded Panel
            # -----------------------------------------------------------------
            print("\n--- TEST 4: Streaming Assistant Response Into Expanded Panel ---")
            # Wait for assistant response to stream in
            for _ in range(30):
                res = await call_cdp(ws, 'Runtime.evaluate', {'expression': """
                    (() => {
                        const el = document.querySelector('ivan-chat-widget');
                        const lastMsg = el.messages[el.messages.length - 1];
                        return {
                            count: el.messages.length,
                            lastRole: lastMsg?.role,
                            lastContentLen: lastMsg?.content?.length || 0,
                            isStreaming: el.isStreaming
                        };
                    })()
                """, 'returnByValue': True})
                val = res.get('result', {}).get('value', {})
                if val.get('lastRole') == 'assistant' and not val.get('isStreaming') and val.get('lastContentLen') > 20:
                    print(f"[Stream Finished]: Message count {val.get('count')}, response len {val.get('lastContentLen')}")
                    break
                await asyncio.sleep(1.0)

            await capture_screenshot(ws, r"C:\Users\Anish\.gemini\antigravity\brain\2fb1f6ee-67b1-4770-affa-d6843cfe2d6a\screenshot_auto_expanded_panel.png")

            # -----------------------------------------------------------------
            # TEST 5: Enter Key Parity & Subsequent Message Preserves Expanded State
            # -----------------------------------------------------------------
            print("\n--- TEST 5: Enter Key Parity & Subsequent Message Preserves Expanded State ---")
            eval_enter = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sr = el.shadowRoot;
                    const input = sr.querySelector('#messageInput');
                    input.value = 'What services does Nav offer?';
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    // Dispatch Enter key event
                    input.dispatchEvent(new KeyboardEvent('keydown', {
                        key: 'Enter',
                        code: 'Enter',
                        keyCode: 13,
                        which: 13,
                        bubbles: true,
                        cancelable: true
                    }));
                    return {
                        isExpanded: el.isExpanded
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': eval_enter, 'returnByValue': True})
            enter_res = res.get('result', {}).get('value', {})
            print(f"[Enter Key Submit]: {enter_res}")
            assert enter_res['isExpanded'] == True, "Widget should remain expanded on subsequent message via Enter"

            # Wait briefly for response
            await asyncio.sleep(3)

            # -----------------------------------------------------------------
            # TEST 6: Manual Restore & Expand Button Toggling
            # -----------------------------------------------------------------
            print("\n--- TEST 6: Manual Restore & Expand Button Toggling ---")
            await call_cdp(ws, 'Runtime.evaluate', {'expression': "document.querySelector('ivan-chat-widget').shadowRoot.querySelector('#expandBtn').click()"})
            await asyncio.sleep(0.6)

            eval_toggle_restore = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sr = el.shadowRoot;
                    const rect = sr.querySelector('#window').getBoundingClientRect();
                    return {
                        isExpanded: el.isExpanded,
                        hasExpandedClass: sr.querySelector('#container').classList.contains('is-expanded'),
                        winWidth: Math.round(rect.width),
                        winHeight: Math.round(rect.height),
                        bannerDisplay: window.getComputedStyle(sr.querySelector('#portraitBanner')).display
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': eval_toggle_restore, 'returnByValue': True})
            restored_info = res.get('result', {}).get('value', {})
            print(f"[Manual Restore Result]: {restored_info}")
            assert restored_info['isExpanded'] == False, "Widget should be restored to compact"
            assert not restored_info['hasExpandedClass'], "Should remove is-expanded class"
            assert restored_info['winWidth'] == 380, f"Expected width 380, got {restored_info['winWidth']}"
            assert restored_info['winHeight'] == 600, f"Expected height 600, got {restored_info['winHeight']}"
            assert restored_info['bannerDisplay'] != 'none', "Portrait banner should be restored in compact mode"

            # Click again to re-expand
            await call_cdp(ws, 'Runtime.evaluate', {'expression': "document.querySelector('ivan-chat-widget').shadowRoot.querySelector('#expandBtn').click()"})
            await asyncio.sleep(0.6)
            eval_reexpand = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sr = el.shadowRoot;
                    const rect = sr.querySelector('#window').getBoundingClientRect();
                    return {
                        isExpanded: el.isExpanded,
                        winWidth: Math.round(rect.width)
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': eval_reexpand, 'returnByValue': True})
            reexp_info = res.get('result', {}).get('value', {})
            print(f"[Re-Expand Result]: {reexp_info}")
            assert reexp_info['isExpanded'] == True, "Widget should re-expand when button clicked"
            assert reexp_info['winWidth'] == 420, f"Expected width 420 upon re-expand, got {reexp_info['winWidth']}"
            print(f"[Re-Expand Result]: {reexp_info}")
            assert reexp_info['isExpanded'] == True, "Widget should re-expand when button clicked"

            # -----------------------------------------------------------------
            # TEST 7: Close & Reopen Chat Window
            # -----------------------------------------------------------------
            print("\n--- TEST 7: Close & Reopen Chat Window ---")
            eval_close = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sr = el.shadowRoot;
                    sr.querySelector('#closeBtn').click();
                    const container = sr.querySelector('#container');
                    const launcher = sr.querySelector('#launcherBtn');
                    return {
                        isOpen: el.isOpen,
                        containerHasOpen: container.classList.contains('is-open'),
                        launcherVisible: window.getComputedStyle(launcher).display !== 'none'
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': eval_close, 'returnByValue': True})
            close_info = res.get('result', {}).get('value', {})
            print(f"[Close Result]: {close_info}")
            assert close_info['isOpen'] == False, "Widget should be closed"
            assert not close_info['containerHasOpen'], "Container should not have is-open"
            assert close_info['launcherVisible'] == True, "Launcher must be visible when closed"

            # Reopen
            eval_reopen = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sr = el.shadowRoot;
                    sr.querySelector('#launcherBtn').click();
                    const container = sr.querySelector('#container');
                    return {
                        isOpen: el.isOpen,
                        isExpanded: el.isExpanded,
                        messagesCount: el.messages.length
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': eval_reopen, 'returnByValue': True})
            reopen_info = res.get('result', {}).get('value', {})
            print(f"[Reopen Result]: {reopen_info}")
            assert reopen_info['isOpen'] == True, "Widget should reopen"
            assert reopen_info['isExpanded'] == True, "Expanded state preserved upon reopen"
            assert reopen_info['messagesCount'] >= 3, "Conversation history preserved upon reopen"

            # -----------------------------------------------------------------
            # TEST 8: Mobile Viewport (<480px) Responsiveness
            # -----------------------------------------------------------------
            print("\n--- TEST 8: Mobile Viewport Responsiveness ---")
            # Emulate iPhone 12 (390 x 844) / 375 x 667
            await call_cdp(ws, 'Emulation.setDeviceMetricsOverride', {
                'width': 375,
                'height': 667,
                'deviceScaleFactor': 2,
                'mobile': True
            })
            await asyncio.sleep(0.5)

            eval_mobile = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sr = el.shadowRoot;
                    const win = sr.querySelector('#window');
                    const rect = win.getBoundingClientRect();
                    return {
                        winWidth: Math.round(rect.width),
                        winHeight: Math.round(rect.height),
                        viewportWidth: window.innerWidth,
                        viewportHeight: window.innerHeight,
                        noHorizontalOverflow: rect.width <= window.innerWidth
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': eval_mobile, 'returnByValue': True})
            mobile_info = res.get('result', {}).get('value', {})
            print(f"[Mobile Mode (375x667)]: {mobile_info}")
            assert mobile_info['winWidth'] == 375, f"Expected 375px width, got {mobile_info['winWidth']}"
            assert mobile_info['noHorizontalOverflow'] == True, "No horizontal overflow on mobile"

            await capture_screenshot(ws, r"C:\Users\Anish\.gemini\antigravity\brain\2fb1f6ee-67b1-4770-affa-d6843cfe2d6a\screenshot_mobile_auto_expanded.png")

            # Reset emulation
            await call_cdp(ws, 'Emulation.clearDeviceMetricsOverride')
            await asyncio.sleep(0.5)

            # -----------------------------------------------------------------
            # TEST 9: Visual & Theme Integrity
            # -----------------------------------------------------------------
            print("\n--- TEST 9: Theme Color and Avatar Integrity ---")
            eval_theme = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sr = el.shadowRoot;
                    const header = sr.querySelector('.ivan-header');
                    const sendBtn = sr.querySelector('#sendBtn');
                    const avatarImg = sr.querySelector('.ivan-header-avatar') || sr.querySelector('.ivan-portrait-img');
                    const hStyle = window.getComputedStyle(header);
                    return {
                        primaryColor: el.primaryColor,
                        headerBg: hStyle.backgroundColor,
                        hasAvatarImg: Boolean(avatarImg),
                        avatarSrc: avatarImg ? avatarImg.src : null,
                        avatarNaturalWidth: avatarImg ? avatarImg.naturalWidth : 0
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': eval_theme, 'returnByValue': True})
            theme_info = res.get('result', {}).get('value', {})
            print(f"[Theme & Avatar Info]: {theme_info}")
            assert theme_info['primaryColor'] == '#031b45', f"Expected primary color #031b45, got {theme_info['primaryColor']}"
            assert '3, 27, 69' in theme_info['headerBg'], f"Header bg must use rgb(3, 27, 69), got {theme_info['headerBg']}"
            assert theme_info['hasAvatarImg'] == True, "Avatar image must be present"
            assert theme_info['avatarNaturalWidth'] > 0, "Avatar image must load successfully"

            # -----------------------------------------------------------------
            # TEST 10: Host Page Document & CSS Isolation
            # -----------------------------------------------------------------
            print("\n--- TEST 10: Host Page Document & CSS Isolation ---")
            eval_isolation = """
                (() => {
                    // Check if host page body or html has received any unwanted scroll locks or styles
                    const body = document.body;
                    const html = document.documentElement;
                    return {
                        bodyOverflow: window.getComputedStyle(body).overflow,
                        htmlOverflow: window.getComputedStyle(html).overflow,
                        bodyWidth: document.body.clientWidth,
                        hasLeakClasses: body.classList.contains('is-expanded') || html.classList.contains('is-expanded')
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': eval_isolation, 'returnByValue': True})
            iso_info = res.get('result', {}).get('value', {})
            print(f"[Host Page Isolation]: {iso_info}")
            assert not iso_info['hasLeakClasses'], "Widget classes must not leak into host document body or html"

            print("\n=======================================================")
            print("ALL 10 VERIFICATION TESTS PASSED SUCCESSFULLY!")
            print(f"Total console errors: {len(console_errors)}")
            print("=======================================================\n")

    finally:
        proc.kill()

if __name__ == '__main__':
    asyncio.run(run_e2e_tests())

