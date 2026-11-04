import subprocess
import time
import json
import asyncio
import tempfile
import websockets
import requests

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

async def run_theme_verification():
    temp_dir = tempfile.mkdtemp()
    chrome_path = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    proc = subprocess.Popen([
        chrome_path,
        '--headless=new',
        '--remote-debugging-port=9222',
        f'--user-data-dir={temp_dir}',
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

            # -----------------------------------------------------------------
            # TEST 1: Floating Launcher Color & White Contrast
            # -----------------------------------------------------------------
            print("\n--- TEST 1: Floating Launcher Background & Contrast ---")
            launcher_eval = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const launcher = el.shadowRoot.querySelector('#launcherBtn');
                    const style = window.getComputedStyle(launcher);
                    const chatProp = window.getComputedStyle(el).getPropertyValue('--ivan-primary').trim();
                    return {
                        background: style.backgroundColor,
                        color: style.color,
                        primaryProp: chatProp
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': launcher_eval, 'returnByValue': True})
            l_info = res.get('result', {}).get('value', {})
            print(f"[Launcher]: {l_info}")
            # rgb(3, 27, 69) is #031b45
            assert 'rgb(3, 27, 69)' in l_info['background'], f"Launcher background is not #031b45: {l_info['background']}"
            assert 'rgb(255, 255, 255)' in l_info['color'], f"Launcher text/icon color is not white: {l_info['color']}"
            assert l_info['primaryProp'].lower() == '#031b45', f"--ivan-primary CSS var is not #031b45: {l_info['primaryProp']}"
            print("[PASS] Launcher verified with #031b45 background and white icon contrast.")

            # -----------------------------------------------------------------
            # TEST 2: Chat Window Header Background & Status Indicator
            # -----------------------------------------------------------------
            print("\n--- TEST 2: Chat Header Background, Text & Status Indicator ---")
            await call_cdp(ws, 'Runtime.evaluate', {'expression': 'document.querySelector("ivan-chat-widget").open()'})
            await asyncio.sleep(0.5)

            header_eval = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const header = el.shadowRoot.querySelector('.ivan-header');
                    const title = el.shadowRoot.querySelector('#headerTitle');
                    const statusDot = el.shadowRoot.querySelector('.ivan-status-indicator');
                    const hStyle = window.getComputedStyle(header);
                    const tStyle = window.getComputedStyle(title);
                    const dStyle = window.getComputedStyle(statusDot);
                    return {
                        headerBg: hStyle.backgroundColor,
                        titleColor: tStyle.color,
                        statusDotBg: dStyle.backgroundColor,
                        statusDotBoxShadow: dStyle.boxShadow
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': header_eval, 'returnByValue': True})
            h_info = res.get('result', {}).get('value', {})
            print(f"[Header]: {h_info}")
            assert 'rgb(3, 27, 69)' in h_info['headerBg'], f"Header background is not #031b45: {h_info['headerBg']}"
            assert 'rgb(255, 255, 255)' in h_info['titleColor'], f"Header title text is not white: {h_info['titleColor']}"
            # Status dot is green (#34d399 -> rgb(52, 211, 153))
            assert 'rgb(52, 211, 153)' in h_info['statusDotBg'], f"Green status indicator altered: {h_info['statusDotBg']}"
            print("[PASS] Chat header verified: #031b45 background, white readable text, green status dot intact.")

            # -----------------------------------------------------------------
            # TEST 3: Send Message Button Color, States & Icon
            # -----------------------------------------------------------------
            print("\n--- TEST 3: Send Message Button Color, Disabled & Focus ---")
            send_eval = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sendBtn = el.shadowRoot.querySelector('#sendBtn');
                    const input = el.shadowRoot.querySelector('#messageInput');
                    const sStyle = window.getComputedStyle(sendBtn);
                    const svg = sendBtn.querySelector('svg');
                    const svgStyle = window.getComputedStyle(svg);
                    return {
                        sendBg: sStyle.backgroundColor,
                        sendColor: sStyle.color,
                        svgFill: svgStyle.fill,
                        disabled: sendBtn.disabled,
                        opacity: sStyle.opacity
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': send_eval, 'returnByValue': True})
            s_info = res.get('result', {}).get('value', {})
            print(f"[Send Button]: {s_info}")
            assert 'rgb(3, 27, 69)' in s_info['sendBg'], f"Send button background is not #031b45: {s_info['sendBg']}"
            assert 'rgb(255, 255, 255)' in s_info['sendColor'] or 'currentColor' in s_info['svgFill'] or 'rgb(255, 255, 255)' in s_info['svgFill'], f"Send button icon is not white: {s_info}"
            assert s_info['disabled'] is True, "Empty input should have disabled send button"
            assert float(s_info['opacity']) <= 0.5, f"Disabled send button opacity should be muted: {s_info['opacity']}"
            print("[PASS] Send button verified: #031b45 background, white icon, proper disabled state.")

            # -----------------------------------------------------------------
            # TEST 4: Input Focus Accent & Focus-Within Border
            # -----------------------------------------------------------------
            print("\n--- TEST 4: Input Container Focus-Within Accent ---")
            input_eval = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const input = el.shadowRoot.querySelector('#messageInput');
                    input.focus();
                    const container = el.shadowRoot.querySelector('.ivan-input-container');
                    const style = window.getComputedStyle(container);
                    return {
                        borderColor: style.borderColor,
                        boxShadow: style.boxShadow
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': input_eval, 'returnByValue': True})
            i_info = res.get('result', {}).get('value', {})
            print(f"[Input Container Focus]: {i_info}")
            assert 'rgb(3, 27, 69)' in i_info['borderColor'], f"Input container focus border is not #031b45: {i_info['borderColor']}"
            assert 'rgba(3, 27, 69' in i_info['boxShadow'] or 'rgb(3, 27, 69)' in i_info['boxShadow'], f"Input focus glow does not use #031b45: {i_info['boxShadow']}"
            print("[PASS] Input container focus state verified with #031b45 accent.")

            # -----------------------------------------------------------------
            # TEST 5: User Message Bubble Theme Color
            # -----------------------------------------------------------------
            print("\n--- TEST 5: User Message Bubble Theme Color ---")
            # Send a user message and check the bubble color
            send_msg_eval = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const input = el.shadowRoot.querySelector('#messageInput');
                    input.value = "Theme test message";
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    el.sendMessage();
                    const userMsg = el.shadowRoot.querySelector('.ivan-message.user .ivan-bubble');
                    if (!userMsg) return { found: false };
                    const style = window.getComputedStyle(userMsg);
                    return {
                        found: true,
                        bg: style.backgroundColor,
                        color: style.color
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': send_msg_eval, 'returnByValue': True})
            u_info = res.get('result', {}).get('value', {})
            print(f"[User Message Bubble]: {u_info}")
            assert u_info.get('found'), "User message bubble not found"
            assert 'rgb(3, 27, 69)' in u_info['bg'], f"User message bubble background is not #031b45: {u_info['bg']}"
            assert 'rgb(255, 255, 255)' in u_info['color'], f"User message bubble text is not white: {u_info['color']}"
            print("[PASS] User message bubble verified with #031b45 background and white text.")

            # -----------------------------------------------------------------
            # TEST 6: Mobile Viewport (<480px) Responsiveness & Theme Integrity
            # -----------------------------------------------------------------
            print("\n--- TEST 6: Mobile Viewport (<480px) Theme & Layout ---")
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
                    const win = el.shadowRoot.querySelector('.ivan-window');
                    const header = el.shadowRoot.querySelector('.ivan-header');
                    const wRect = win.getBoundingClientRect();
                    const hStyle = window.getComputedStyle(header);
                    return {
                        windowWidth: wRect.width,
                        windowHeight: wRect.height,
                        headerBg: hStyle.backgroundColor
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': mobile_eval, 'returnByValue': True})
            m_info = res.get('result', {}).get('value', {})
            print(f"[Mobile View]: {m_info}")
            assert abs(m_info['windowWidth'] - 375) <= 2 or abs(m_info['windowWidth'] - 343) <= 2, f"Window width unexpected on mobile: {m_info['windowWidth']}"
            assert 'rgb(3, 27, 69)' in m_info['headerBg'], f"Header background corrupted on mobile: {m_info['headerBg']}"
            print("[PASS] Mobile layout (<480px) responsive and #031b45 theme intact.")

            print("\n" + "=" * 50)
            print("ALL THEME COLOR VERIFICATION TESTS PASSED (100%)!")
            print("=" * 50)

    finally:
        proc.kill()

if __name__ == "__main__":
    asyncio.run(run_theme_verification())

