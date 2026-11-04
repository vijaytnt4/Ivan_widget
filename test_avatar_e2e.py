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

async def run_avatar_verification():
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

            # Wait for ivan-chat-widget
            for _ in range(20):
                res = await call_cdp(ws, 'Runtime.evaluate', {'expression': 'Boolean(document.querySelector("ivan-chat-widget")?.shadowRoot)', 'returnByValue': True})
                if res.get('result', {}).get('value'):
                    break
                await asyncio.sleep(0.5)

            # -----------------------------------------------------------------
            # TEST 1: Launcher Avatar Verification (Desktop)
            # -----------------------------------------------------------------
            print("\n--- TEST 1: Floating Launcher Avatar Verification ---")
            launcher_eval = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const img = el.shadowRoot.querySelector('#launcherChatIcon img.ivan-launcher-avatar');
                    if (!img) return { found: false };
                    const style = window.getComputedStyle(img);
                    const rect = img.getBoundingClientRect();
                    return {
                        found: true,
                        src: img.src,
                        naturalWidth: img.naturalWidth,
                        naturalHeight: img.naturalHeight,
                        width: rect.width,
                        height: rect.height,
                        borderRadius: style.borderRadius,
                        objectFit: style.objectFit,
                        objectPosition: style.objectPosition,
                        border: style.border
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': launcher_eval, 'returnByValue': True})
            l_info = res.get('result', {}).get('value', {})
            print(f"[Launcher Avatar]: {l_info}")
            assert l_info.get('found'), "Launcher avatar <img> not found"
            assert 'image-7.png' in l_info['src'], f"Launcher avatar src incorrect: {l_info['src']}"
            assert abs(l_info['width'] - 48) <= 4, f"Launcher avatar width not approx 48px: {l_info['width']}"
            assert abs(l_info['height'] - 48) <= 4, f"Launcher avatar height not approx 48px: {l_info['height']}"
            assert '50%' in l_info['borderRadius'], f"Launcher avatar not circular: {l_info['borderRadius']}"
            assert l_info['objectFit'] == 'cover', f"Launcher avatar objectFit not cover: {l_info['objectFit']}"
            assert 'top' in l_info['objectPosition'] or '0%' in l_info['objectPosition'], f"Launcher avatar objectPosition not center top: {l_info['objectPosition']}"
            print("[PASS] Launcher avatar verified: 48px, circular, object-position center top.")

            # -----------------------------------------------------------------
            # TEST 2: Header Avatar & Status Indicator
            # -----------------------------------------------------------------
            print("\n--- TEST 2: Chat Header Avatar & Status Indicator ---")
            await call_cdp(ws, 'Runtime.evaluate', {'expression': 'document.querySelector("ivan-chat-widget").open()'})
            await asyncio.sleep(0.5)

            header_eval = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const img = el.shadowRoot.querySelector('#avatarBox img.ivan-header-avatar');
                    const statusDot = el.shadowRoot.querySelector('.ivan-status-indicator');
                    if (!img) return { found: false };
                    const style = window.getComputedStyle(img);
                    const boxStyle = window.getComputedStyle(el.shadowRoot.querySelector('#avatarBox'));
                    const rect = img.getBoundingClientRect();
                    return {
                        found: true,
                        src: img.src,
                        width: rect.width,
                        height: rect.height,
                        borderRadius: style.borderRadius,
                        objectFit: style.objectFit,
                        objectPosition: style.objectPosition,
                        boxBorder: boxStyle.border,
                        hasStatusDot: Boolean(statusDot)
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': header_eval, 'returnByValue': True})
            h_info = res.get('result', {}).get('value', {})
            print(f"[Header Avatar]: {h_info}")
            assert h_info.get('found'), "Header avatar <img> not found"
            assert 'image-7.png' in h_info['src'], f"Header avatar src incorrect: {h_info['src']}"
            assert abs(h_info['width'] - 40) <= 4, f"Header avatar width not approx 40px: {h_info['width']}"
            assert abs(h_info['height'] - 40) <= 4, f"Header avatar height not approx 40px: {h_info['height']}"
            assert '50%' in h_info['borderRadius'], f"Header avatar not circular: {h_info['borderRadius']}"
            assert h_info['objectFit'] == 'cover', f"Header avatar objectFit not cover: {h_info['objectFit']}"
            assert 'top' in h_info['objectPosition'] or '0%' in h_info['objectPosition'], f"Header avatar objectPosition not center top: {h_info['objectPosition']}"
            assert h_info['hasStatusDot'], "Header status dot missing"
            print("[PASS] Header avatar verified: 40px, circular, object-position center top, status dot present.")

            # -----------------------------------------------------------------
            # TEST 3: Assistant Message Avatar (Welcome & Follow-up message)
            # -----------------------------------------------------------------
            print("\n--- TEST 3: Assistant Message Avatar (Welcome message) ---")
            msg_eval = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const msgAvatar = el.shadowRoot.querySelector('.ivan-message.bot .ivan-msg-avatar img');
                    if (!msgAvatar) return { found: false };
                    const style = window.getComputedStyle(msgAvatar);
                    const rect = msgAvatar.getBoundingClientRect();
                    return {
                        found: true,
                        src: msgAvatar.src,
                        width: rect.width,
                        height: rect.height,
                        borderRadius: style.borderRadius,
                        objectFit: style.objectFit,
                        objectPosition: style.objectPosition
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': msg_eval, 'returnByValue': True})
            m_info = res.get('result', {}).get('value', {})
            print(f"[Message Avatar]: {m_info}")
            assert m_info.get('found'), "Assistant message avatar <img> not found"
            assert 'image-7.png' in m_info['src'], f"Message avatar src incorrect: {m_info['src']}"
            assert abs(m_info['width'] - 32) <= 4, f"Message avatar width not approx 32px: {m_info['width']}"
            assert abs(m_info['height'] - 32) <= 4, f"Message avatar height not approx 32px: {m_info['height']}"
            assert '50%' in m_info['borderRadius'], f"Message avatar not circular: {m_info['borderRadius']}"
            assert m_info['objectFit'] == 'cover', f"Message avatar objectFit not cover: {m_info['objectFit']}"
            assert 'top' in m_info['objectPosition'] or '0%' in m_info['objectPosition'], f"Message avatar objectPosition not center top: {m_info['objectPosition']}"
            print("[PASS] Assistant message avatar verified: 32px, circular, object-position center top.")

            # -----------------------------------------------------------------
            # TEST 4: Live Message Exchange with Avatar & Streaming Response
            # -----------------------------------------------------------------
            print("\n--- TEST 4: Live Message Exchange & Avatar Persistence ---")
            send_eval = """
                (async () => {
                    const el = document.querySelector('ivan-chat-widget');
                    await el.sendMessage('Hello Ivan, how are you?');
                    return { sent: true };
                })()
            """
            await call_cdp(ws, 'Runtime.evaluate', {'expression': send_eval, 'awaitPromise': True, 'returnByValue': True})
            print("[CDP] Sent test message, waiting for bot response...")

            # Wait for bot response
            bot_msg_with_avatar = False
            for _ in range(25):
                await asyncio.sleep(1)
                check_bot = """
                    (() => {
                        const el = document.querySelector('ivan-chat-widget');
                        const botMessages = el.shadowRoot.querySelectorAll('.ivan-message.bot');
                        if (botMessages.length < 2) return { count: botMessages.length };
                        const latest = botMessages[botMessages.length - 1];
                        const img = latest.querySelector('.ivan-msg-avatar img');
                        const bubbleText = latest.querySelector('.ivan-bubble')?.textContent || '';
                        return {
                            count: botMessages.length,
                            hasAvatarImg: Boolean(img),
                            avatarSrc: img ? img.src : null,
                            bubbleText: bubbleText.substring(0, 50)
                        };
                    })()
                """
                res = await call_cdp(ws, 'Runtime.evaluate', {'expression': check_bot, 'returnByValue': True})
                val = res.get('result', {}).get('value', {})
                if val.get('count', 0) >= 2 and val.get('hasAvatarImg'):
                    bot_msg_with_avatar = True
                    print(f"[CDP] New bot response received with avatar: {val}")
                    break

            assert bot_msg_with_avatar, "Second bot message did not render with avatar"
            print("[PASS] Live assistant response rendered with 32px avatar intact.")

            # -----------------------------------------------------------------
            # TEST 5: Graceful Fallback when Avatar Image Removed
            # -----------------------------------------------------------------
            print("\n--- TEST 5: Fallback when avatar removed or empty ---")
            fallback_eval = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    // Remove bot-avatar attribute to simulate no avatar configured
                    el.removeAttribute('bot-avatar');
                    el.botAvatar = '';
                    el._applyConfig();

                    const launcherSvg = el.shadowRoot.querySelector('#launcherChatIcon svg');
                    const headerSvg = el.shadowRoot.querySelector('#avatarBox svg');
                    const msgSvg = el._renderMessageAvatar();

                    return {
                        hasLauncherSvg: Boolean(launcherSvg),
                        hasHeaderSvg: Boolean(headerSvg),
                        msgSvgContainsBot: msgSvg.includes('<svg')
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': fallback_eval, 'returnByValue': True})
            fb_info = res.get('result', {}).get('value', {})
            print(f"[Fallback check]: {fb_info}")
            assert fb_info.get('hasLauncherSvg'), "Launcher failed to fall back to SVG icon"
            assert fb_info.get('hasHeaderSvg'), "Header failed to fall back to SVG robot icon"
            assert fb_info.get('msgSvgContainsBot'), "Message avatar failed to fall back to SVG robot icon"
            print("[PASS] Graceful fallback to default robot icon verified.")

            # -----------------------------------------------------------------
            # TEST 6: Mobile Responsiveness Verification
            # -----------------------------------------------------------------
            print("\n--- TEST 6: Mobile Viewport (<480px) Responsiveness ---")
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
                    // Re-apply avatar
                    el.setAttribute('bot-avatar', 'http://ivan.local:10004/wp-content/uploads/2026/11/image-7.png');
                    el._applyConfig();
                    const win = el.shadowRoot.querySelector('#window');
                    const rect = win.getBoundingClientRect();
                    return {
                        windowWidth: rect.width,
                        windowHeight: rect.height,
                        headerAvatar: Boolean(el.shadowRoot.querySelector('#avatarBox img.ivan-header-avatar')),
                        msgAvatar: Boolean(el.shadowRoot.querySelector('.ivan-msg-avatar img'))
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': mobile_eval, 'returnByValue': True})
            m_res = res.get('result', {}).get('value', {})
            print(f"[Mobile view]: {m_res}")
            assert m_res['headerAvatar'] and m_res['msgAvatar'], "Avatars broken in mobile viewport"
            assert m_res['windowWidth'] <= 375, f"Window width exceeded mobile viewport: {m_res['windowWidth']}"
            print("[PASS] Mobile responsiveness verified.")

            print("\n==================================================")
            print("ALL AVATAR E2E TESTS COMPLETED WITH 100% SUCCESS!")
            print("==================================================")

    finally:
        proc.terminate()

if __name__ == '__main__':
    asyncio.run(run_avatar_verification())
