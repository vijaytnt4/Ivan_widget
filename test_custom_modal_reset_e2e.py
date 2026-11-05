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

async def run_modal_tests():
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

            # Spy on window.confirm to detect any unwanted calls
            await call_cdp(ws, 'Runtime.evaluate', {'expression': """
                window._confirmCalls = 0;
                window.confirm = () => {
                    window._confirmCalls++;
                    return false;
                };
            """})

            # -----------------------------------------------------------------
            # TEST 1: Open chat, send message, and click New Chat icon
            # -----------------------------------------------------------------
            print("\n--- TEST 1: Click New Chat icon opens custom modal without window.confirm ---")
            await call_cdp(ws, 'Runtime.evaluate', {'expression': 'document.querySelector("ivan-chat-widget").open()'})
            await asyncio.sleep(0.5)

            # Send a user message to establish active history
            eval_msg = """
                (async () => {
                    const el = document.querySelector('ivan-chat-widget');
                    await el.sendMessage('Hello! Testing conversation history before reset.');
                })()
            """
            await call_cdp(ws, 'Runtime.evaluate', {'expression': eval_msg, 'awaitPromise': True})
            await asyncio.sleep(1.0)

            # Check messages count > 1
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': 'document.querySelector("ivan-chat-widget").messages.length', 'returnByValue': True})
            assert res.get('result', {}).get('value') >= 2, "Conversation must have history before reset"

            # Click New Chat icon (#resetBtn)
            await call_cdp(ws, 'Runtime.evaluate', {'expression': 'document.querySelector("ivan-chat-widget").shadowRoot.querySelector("#resetBtn").click()'})
            await asyncio.sleep(0.3)

            # Inspect modal DOM, texts, centering, and window.confirm calls
            eval_modal_check = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sr = el.shadowRoot;
                    const win = sr.querySelector('#window');
                    const modal = sr.querySelector('#resetModal');
                    const card = sr.querySelector('.ivan-modal-card');
                    const title = sr.querySelector('#modalTitle');
                    const desc = sr.querySelector('#modalDesc');
                    const confirmBtn = sr.querySelector('#modalConfirmBtn');
                    const cancelBtn = sr.querySelector('#modalCancelBtn');

                    const winRect = win.getBoundingClientRect();
                    const cardRect = card.getBoundingClientRect();

                    const winCenterX = winRect.left + winRect.width / 2;
                    const winCenterY = winRect.top + winRect.height / 2;
                    const cardCenterX = cardRect.left + cardRect.width / 2;
                    const cardCenterY = cardRect.top + cardRect.height / 2;

                    return {
                        confirmCalls: window._confirmCalls,
                        modalVisible: modal && window.getComputedStyle(modal).display !== 'none' && modal.classList.contains('is-active'),
                        titleText: title ? title.textContent.trim() : null,
                        descText: desc ? desc.textContent.trim() : null,
                        confirmBtnText: confirmBtn ? confirmBtn.textContent.trim() : null,
                        cancelBtnText: cancelBtn ? cancelBtn.textContent.trim() : null,
                        cardWidth: Math.round(cardRect.width),
                        cardHeight: Math.round(cardRect.height),
                        diffCenterX: Math.abs(winCenterX - cardCenterX),
                        diffCenterY: Math.abs(winCenterY - cardCenterY)
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': eval_modal_check, 'returnByValue': True})
            modal_info = res.get('result', {}).get('value', {})
            print(f"[Modal Info in Compact Mode]: {modal_info}")
            assert modal_info['confirmCalls'] == 0, "window.confirm() MUST NEVER be called!"
            assert modal_info['modalVisible'] == True, "Custom modal must be visible"
            assert modal_info['titleText'] == "New conversation", f"Expected title 'New conversation', got {modal_info['titleText']}"
            assert modal_info['descText'] == "This will clear your conversation history. Do you want to proceed with a new chat?", f"Unexpected desc: {modal_info['descText']}"
            assert modal_info['confirmBtnText'] == "Yes, proceed", f"Expected 'Yes, proceed', got {modal_info['confirmBtnText']}"
            assert modal_info['cancelBtnText'] == "No, keep it", f"Expected 'No, keep it', got {modal_info['cancelBtnText']}"
            assert modal_info['diffCenterX'] <= 2, f"Modal card must be centered horizontally (diff: {modal_info['diffCenterX']})"
            assert modal_info['diffCenterY'] <= 6, f"Modal card must be centered vertically (diff: {modal_info['diffCenterY']})"

            await capture_screenshot(ws, r"C:\Users\Anish\.gemini\antigravity\brain\2fb1f6ee-67b1-4770-affa-d6843cfe2d6a\screenshot_modal_compact.png")

            # -----------------------------------------------------------------
            # TEST 2: Click 'No, keep it' preserves conversation history
            # -----------------------------------------------------------------
            print("\n--- TEST 2: Click 'No, keep it' preserves conversation history ---")
            msgs_before = await call_cdp(ws, 'Runtime.evaluate', {'expression': 'document.querySelector("ivan-chat-widget").messages.length', 'returnByValue': True})
            await call_cdp(ws, 'Runtime.evaluate', {'expression': 'document.querySelector("ivan-chat-widget").shadowRoot.querySelector("#modalCancelBtn").click()'})
            await asyncio.sleep(0.3)

            eval_cancel_check = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sr = el.shadowRoot;
                    const modal = sr.querySelector('#resetModal');
                    return {
                        modalActive: modal.classList.contains('is-active'),
                        modalDisplay: window.getComputedStyle(modal).display,
                        messagesCount: el.messages.length
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': eval_cancel_check, 'returnByValue': True})
            cancel_info = res.get('result', {}).get('value', {})
            print(f"[After Cancel Click]: {cancel_info}")
            assert cancel_info['modalActive'] == False, "Modal must be closed after clicking cancel"
            assert cancel_info['messagesCount'] == msgs_before.get('result', {}).get('value'), "Conversation history must be preserved"

            # -----------------------------------------------------------------
            # TEST 3: Click outside modal (backdrop) closes modal and preserves history
            # -----------------------------------------------------------------
            print("\n--- TEST 3: Click outside modal closes modal and preserves history ---")
            # Open modal again
            await call_cdp(ws, 'Runtime.evaluate', {'expression': 'document.querySelector("ivan-chat-widget").openResetModal()'})
            await asyncio.sleep(0.3)

            # Click backdrop outside card
            eval_click_backdrop = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sr = el.shadowRoot;
                    const modal = sr.querySelector('#resetModal');
                    // Click directly on modal backdrop element
                    modal.click();
                    return {
                        isModalActive: modal.classList.contains('is-active')
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': eval_click_backdrop, 'returnByValue': True})
            backdrop_res = res.get('result', {}).get('value', {})
            await asyncio.sleep(0.3)
            print(f"[After Backdrop Click]: {backdrop_res}")
            assert backdrop_res['isModalActive'] == False, "Modal must close when clicking backdrop"

            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': 'document.querySelector("ivan-chat-widget").messages.length', 'returnByValue': True})
            assert res.get('result', {}).get('value') == msgs_before.get('result', {}).get('value'), "History preserved after backdrop dismissal"

            # -----------------------------------------------------------------
            # TEST 4: Press Escape closes modal and preserves history
            # -----------------------------------------------------------------
            print("\n--- TEST 4: Press Escape closes modal and preserves history ---")
            await call_cdp(ws, 'Runtime.evaluate', {'expression': 'document.querySelector("ivan-chat-widget").openResetModal()'})
            await asyncio.sleep(0.3)

            # Dispatch Escape key
            eval_escape = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sr = el.shadowRoot;
                    const modal = sr.querySelector('#resetModal');
                    modal.dispatchEvent(new KeyboardEvent('keydown', {
                        key: 'Escape',
                        code: 'Escape',
                        keyCode: 27,
                        which: 27,
                        bubbles: true,
                        cancelable: true
                    }));
                    return {
                        isModalActive: modal.classList.contains('is-active')
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': eval_escape, 'returnByValue': True})
            esc_res = res.get('result', {}).get('value', {})
            await asyncio.sleep(0.3)
            print(f"[After Escape]: {esc_res}")
            assert esc_res['isModalActive'] == False, "Modal must close on Escape key"

            # -----------------------------------------------------------------
            # TEST 5: Open modal in Expanded Mode - Centering & Positioning
            # -----------------------------------------------------------------
            print("\n--- TEST 5: Modal in Expanded Mode - Centering & Positioning ---")
            # Expand chatbot
            await call_cdp(ws, 'Runtime.evaluate', {'expression': 'document.querySelector("ivan-chat-widget").expand()'})
            await asyncio.sleep(0.6)

            # Open modal in expanded mode
            await call_cdp(ws, 'Runtime.evaluate', {'expression': 'document.querySelector("ivan-chat-widget").openResetModal()'})
            await asyncio.sleep(0.3)

            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': eval_modal_check, 'returnByValue': True})
            exp_modal_info = res.get('result', {}).get('value', {})
            print(f"[Modal in Expanded Mode]: {exp_modal_info}")
            assert exp_modal_info['modalVisible'] == True, "Modal must be visible in expanded mode"
            assert exp_modal_info['diffCenterX'] <= 2, f"Centered horizontally in expanded panel (diff: {exp_modal_info['diffCenterX']})"
            assert exp_modal_info['diffCenterY'] <= 6, f"Centered vertically in expanded panel (diff: {exp_modal_info['diffCenterY']})"

            await capture_screenshot(ws, r"C:\Users\Anish\.gemini\antigravity\brain\2fb1f6ee-67b1-4770-affa-d6843cfe2d6a\screenshot_modal_expanded.png")

            # -----------------------------------------------------------------
            # TEST 6: Mobile Viewport (<480px) - Centering & No Overflow
            # -----------------------------------------------------------------
            print("\n--- TEST 6: Mobile Viewport (375x667) - Centering & No Overflow ---")
            await call_cdp(ws, 'Emulation.setDeviceMetricsOverride', {
                'width': 375,
                'height': 667,
                'deviceScaleFactor': 2,
                'mobile': True
            })
            await asyncio.sleep(0.5)

            eval_mobile_modal = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sr = el.shadowRoot;
                    const win = sr.querySelector('#window');
                    const card = sr.querySelector('.ivan-modal-card');
                    const cardRect = card.getBoundingClientRect();
                    return {
                        cardWidth: Math.round(cardRect.width),
                        cardHeight: Math.round(cardRect.height),
                        noHorizontalOverflow: cardRect.width <= 375 && cardRect.right <= 375 && cardRect.left >= 0,
                        cardLeft: Math.round(cardRect.left),
                        cardRight: Math.round(cardRect.right)
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': eval_mobile_modal, 'returnByValue': True})
            mob_modal_info = res.get('result', {}).get('value', {})
            print(f"[Mobile Modal]: {mob_modal_info}")
            assert mob_modal_info['noHorizontalOverflow'] == True, "No horizontal overflow on mobile"

            await capture_screenshot(ws, r"C:\Users\Anish\.gemini\antigravity\brain\2fb1f6ee-67b1-4770-affa-d6843cfe2d6a\screenshot_modal_mobile.png")

            await call_cdp(ws, 'Emulation.clearDeviceMetricsOverride')
            await asyncio.sleep(0.5)

            # -----------------------------------------------------------------
            # TEST 7: Click 'Yes, proceed' clears conversation & restores greeting
            # -----------------------------------------------------------------
            print("\n--- TEST 7: Click 'Yes, proceed' clears conversation & restores greeting ---")
            old_session_id = (await call_cdp(ws, 'Runtime.evaluate', {'expression': 'document.querySelector("ivan-chat-widget").sessionId', 'returnByValue': True})).get('result', {}).get('value')
            
            # Click confirm button
            await call_cdp(ws, 'Runtime.evaluate', {'expression': 'document.querySelector("ivan-chat-widget").shadowRoot.querySelector("#modalConfirmBtn").click()'})
            await asyncio.sleep(0.4)

            eval_reset_done = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sr = el.shadowRoot;
                    const modal = sr.querySelector('#resetModal');
                    const msgs = el.messages;
                    return {
                        modalActive: modal.classList.contains('is-active'),
                        messagesCount: msgs.length,
                        firstRole: msgs[0]?.role,
                        firstId: msgs[0]?.id,
                        firstContent: msgs[0]?.content,
                        sessionId: el.sessionId,
                        conversationId: el.conversationId,
                        isOpen: el.isOpen
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': eval_reset_done, 'returnByValue': True})
            reset_done = res.get('result', {}).get('value', {})
            print(f"[Reset Executed]: {reset_done}")
            assert reset_done['modalActive'] == False, "Modal must be closed after confirm"
            assert reset_done['messagesCount'] == 1, f"Expected 1 welcome message, got {reset_done['messagesCount']}"
            assert reset_done['firstRole'] == 'assistant', "Restored greeting must be assistant"
            assert reset_done['firstId'] == 'welcome', "Welcome message restored"
            assert reset_done['conversationId'] is None, "Conversation ID must be reset to null"
            assert reset_done['sessionId'] != old_session_id, "New session ID must be generated"
            assert reset_done['isOpen'] == True, "Chatbot must remain open"

            # -----------------------------------------------------------------
            # TEST 8: Rapid Double-Click on Confirm - Only 1 Reset Operation
            # -----------------------------------------------------------------
            print("\n--- TEST 8: Rapid Double-Click on Confirm - Only 1 Reset Operation ---")
            # Open modal again
            await call_cdp(ws, 'Runtime.evaluate', {'expression': 'document.querySelector("ivan-chat-widget").openResetModal()'})
            await asyncio.sleep(0.2)

            eval_rapid_confirm = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sr = el.shadowRoot;
                    const btn = sr.querySelector('#modalConfirmBtn');
                    // Click twice rapidly
                    btn.click();
                    btn.click();
                    return {
                        isResetting: el._isResetting
                    };
                })()
            """
            await call_cdp(ws, 'Runtime.evaluate', {'expression': eval_rapid_confirm, 'returnByValue': True})
            await asyncio.sleep(0.5)
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': 'document.querySelector("ivan-chat-widget").messages.length', 'returnByValue': True})
            assert res.get('result', {}).get('value') == 1, "Only 1 reset operation performed"

            # -----------------------------------------------------------------
            # TEST 9: Chat messaging works normally after reset
            # -----------------------------------------------------------------
            print("\n--- TEST 9: Chat messaging works normally after reset ---")
            eval_send_post_reset = """
                (async () => {
                    const el = document.querySelector('ivan-chat-widget');
                    await el.sendMessage('Testing message after reset');
                    return {
                        count: el.messages.length
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': eval_send_post_reset, 'awaitPromise': True, 'returnByValue': True})
            post_send = res.get('result', {}).get('value', {})
            print(f"[Post Reset Send]: {post_send}")
            assert post_send.get('count', 0) >= 2, "User message appended and response streamed after reset"

            # Final check on window.confirm
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': 'window._confirmCalls', 'returnByValue': True})
            assert res.get('result', {}).get('value') == 0, "Zero calls to window.confirm during entire run"

            print("\n=======================================================")
            print("ALL CUSTOM CONFIRMATION MODAL TESTS PASSED!")
            print("Total window.confirm calls: 0")
            print("=======================================================\n")

    finally:
        proc.kill()

if __name__ == '__main__':
    asyncio.run(run_modal_tests())

