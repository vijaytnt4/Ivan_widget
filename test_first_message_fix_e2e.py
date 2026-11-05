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

async def get_network_request_count(ws):
    res = await call_cdp(ws, 'Runtime.evaluate', {
        'expression': "window.performance.getEntriesByType('resource').filter(e => e.name.includes('/wp-json/ivan/v1/chat')).length",
        'returnByValue': True
    })
    return res.get('result', {}).get('value', 0)

async def capture_screenshot(ws, filepath):
    res = await call_cdp(ws, 'Page.captureScreenshot', {'format': 'png'})
    img_data = base64.b64decode(res['data'])
    with open(filepath, 'wb') as f:
        f.write(img_data)
    print(f"[Screenshot] Saved to {filepath}")

async def run_regression_suite():
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
    network_responses = []

    try:
        tabs = requests.get('http://127.0.0.1:9222/json').json()
        target = [t for t in tabs if t.get('type') == 'page'][0]
        ws_url = target['webSocketDebuggerUrl']
        print(f"[CDP] Connected to Chrome: {ws_url}")

        async with websockets.connect(ws_url) as ws:
            await call_cdp(ws, 'Page.enable')
            await call_cdp(ws, 'Runtime.enable')
            await call_cdp(ws, 'Network.enable')

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

            await call_cdp(ws, 'Runtime.evaluate', {'expression': 'window.confirm = () => true; window.alert = () => true;'})

            # -----------------------------------------------------------------
            # TEST 1: Empty message - No expansion and no API request
            # -----------------------------------------------------------------
            print("\n--- TEST 1: Empty message / whitespace does NOT expand or trigger API ---")
            await call_cdp(ws, 'Runtime.evaluate', {'expression': 'document.querySelector("ivan-chat-widget").open()'})
            await asyncio.sleep(0.5)

            reqs_before = await get_network_request_count(ws)
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sr = el.shadowRoot;
                    const input = sr.querySelector('#messageInput');
                    input.value = '   ';
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    const wasDisabled = sr.querySelector('#sendBtn').disabled;
                    el.sendMessage('   ');
                    return {
                        isExpanded: el.isExpanded,
                        wasDisabled,
                        messagesCount: el.messages.length
                    };
                })()
            """, 'returnByValue': True})
            empty_val = res.get('result', {}).get('value', {})
            print(f"[Empty Message Result]: {empty_val}")
            assert empty_val['isExpanded'] == False, "Widget must not expand for empty message"
            assert empty_val['wasDisabled'] == True, "Send button must remain disabled"
            reqs_after = await get_network_request_count(ws)
            assert reqs_after == reqs_before, "No network request should be sent for empty message"

            # -----------------------------------------------------------------
            # TEST 2: First message via Send button - Expands and receives Ivan's response
            # -----------------------------------------------------------------
            print("\n--- TEST 2: First message using Send button expands and receives Ivan response ---")
            reqs_before = await get_network_request_count(ws)
            eval_send_btn = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sr = el.shadowRoot;
                    const input = sr.querySelector('#messageInput');
                    input.value = 'Hello from Send button test';
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    sr.querySelector('#sendBtn').click();
                    return {
                        isExpanded: el.isExpanded,
                        isLoading: el.isLoading,
                        hasExpandedClass: sr.querySelector('#container').classList.contains('is-expanded')
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': eval_send_btn, 'returnByValue': True})
            send_val = res.get('result', {}).get('value', {})
            print(f"[Send Button Click Result]: {send_val}")
            assert send_val['isExpanded'] == True, "Chatbot must auto-expand immediately"
            assert send_val['hasExpandedClass'] == True, "Container must have is-expanded class"
            assert send_val['isLoading'] == True, "Loading state must be active"

            # Wait for response to arrive and finish streaming
            for i in range(25):
                await asyncio.sleep(1.0)
                res = await call_cdp(ws, 'Runtime.evaluate', {'expression': """
                    (() => {
                        const el = document.querySelector('ivan-chat-widget');
                        const lastMsg = el.messages[el.messages.length - 1];
                        return {
                            count: el.messages.length,
                            lastRole: lastMsg?.role,
                            lastContent: lastMsg?.content,
                            isLoading: el.isLoading
                        };
                    })()
                """, 'returnByValue': True})
                status = res.get('result', {}).get('value', {})
                if status.get('lastRole') == 'assistant' and not status.get('isLoading') and len(status.get('lastContent', '')) > 5:
                    print(f"[First Response Received]: {status}")
                    break
            
            assert status.get('lastRole') == 'assistant', "Assistant response must be received"
            assert len(status.get('lastContent', '')) > 5, "Assistant response content must not be empty"
            assert status.get('isLoading') == False, "Loading state must be cleared"
            reqs_after = await get_network_request_count(ws)
            assert reqs_after == reqs_before + 1, f"Expected 1 request, got {reqs_after - reqs_before}"

            await capture_screenshot(ws, r"C:\Users\Anish\.gemini\antigravity\brain\2fb1f6ee-67b1-4770-affa-d6843cfe2d6a\screenshot_first_message_response.png")

            # -----------------------------------------------------------------
            # TEST 3: Subsequent message via Enter key - Remains expanded and receives response
            # -----------------------------------------------------------------
            print("\n--- TEST 3: Enter key parity & subsequent message preserves expanded state ---")
            reqs_before = await get_network_request_count(ws)
            eval_enter = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sr = el.shadowRoot;
                    const input = sr.querySelector('#messageInput');
                    input.value = 'What services do you provide?';
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    input.dispatchEvent(new KeyboardEvent('keydown', {
                        key: 'Enter',
                        code: 'Enter',
                        keyCode: 13,
                        which: 13,
                        bubbles: true,
                        cancelable: true
                    }));
                    return {
                        isExpanded: el.isExpanded,
                        isLoading: el.isLoading
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': eval_enter, 'returnByValue': True})
            enter_val = res.get('result', {}).get('value', {})
            print(f"[Enter Key Submit Result]: {enter_val}")
            assert enter_val['isExpanded'] == True, "Must stay expanded"
            assert enter_val['isLoading'] == True, "Must set loading state"

            for i in range(25):
                await asyncio.sleep(1.0)
                res = await call_cdp(ws, 'Runtime.evaluate', {'expression': """
                    (() => {
                        const el = document.querySelector('ivan-chat-widget');
                        const lastMsg = el.messages[el.messages.length - 1];
                        return {
                            count: el.messages.length,
                            lastRole: lastMsg?.role,
                            lastContent: lastMsg?.content,
                            isLoading: el.isLoading
                        };
                    })()
                """, 'returnByValue': True})
                status = res.get('result', {}).get('value', {})
                if status.get('lastRole') == 'assistant' and not status.get('isLoading') and len(status.get('lastContent', '')) > 5:
                    print(f"[Subsequent Response Received]: count={status['count']}, content len={len(status['lastContent'])}")
                    break

            assert status.get('lastRole') == 'assistant', "Assistant response for second turn must be received"
            reqs_after = await get_network_request_count(ws)
            assert reqs_after == reqs_before + 1, "Exactly one additional API request sent"

            # -----------------------------------------------------------------
            # TEST 4: Rapid double-click prevention
            # -----------------------------------------------------------------
            print("\n--- TEST 4: Rapid double-click produces only one request ---")
            reqs_before = await get_network_request_count(ws)
            eval_double = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sr = el.shadowRoot;
                    const input = sr.querySelector('#messageInput');
                    input.value = 'Rapid double click test';
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    const btn = sr.querySelector('#sendBtn');
                    // Click twice consecutively
                    btn.click();
                    btn.click();
                    return {
                        isLoading: el.isLoading
                    };
                })()
            """
            await call_cdp(ws, 'Runtime.evaluate', {'expression': eval_double, 'returnByValue': True})

            # Wait for response to finish
            for _ in range(25):
                await asyncio.sleep(1.0)
                res = await call_cdp(ws, 'Runtime.evaluate', {'expression': 'Boolean(!document.querySelector("ivan-chat-widget").isLoading)', 'returnByValue': True})
                if res.get('result', {}).get('value'):
                    break

            # Exactly 1 network request should have been dispatched despite rapid double click
            reqs_after = await get_network_request_count(ws)
            assert reqs_after == reqs_before + 1, f"Expected 1 request, got {reqs_after - reqs_before}"

            # -----------------------------------------------------------------
            # TEST 5: Manual Restore and Re-Expand during conversation
            # -----------------------------------------------------------------
            print("\n--- TEST 5: Restore and Re-Expand during conversation ---")
            # Restore to compact
            await call_cdp(ws, 'Runtime.evaluate', {'expression': "document.querySelector('ivan-chat-widget').shadowRoot.querySelector('#expandBtn').click()"})
            await asyncio.sleep(0.6)
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sr = el.shadowRoot;
                    const rect = sr.querySelector('#window').getBoundingClientRect();
                    return {
                        isExpanded: el.isExpanded,
                        winWidth: Math.round(rect.width),
                        winHeight: Math.round(rect.height),
                        messagesCount: el.messages.length
                    };
                })()
            """, 'returnByValue': True})
            res_val = res.get('result', {}).get('value', {})
            print(f"[Restored Compact State]: {res_val}")
            assert res_val['isExpanded'] == False, "Must be compact"
            assert res_val['winWidth'] == 380, f"Expected 380, got {res_val['winWidth']}"

            # Re-expand
            await call_cdp(ws, 'Runtime.evaluate', {'expression': "document.querySelector('ivan-chat-widget').shadowRoot.querySelector('#expandBtn').click()"})
            await asyncio.sleep(0.6)
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sr = el.shadowRoot;
                    const rect = sr.querySelector('#window').getBoundingClientRect();
                    return {
                        isExpanded: el.isExpanded,
                        winWidth: Math.round(rect.width)
                    };
                })()
            """, 'returnByValue': True})
            reexp_val = res.get('result', {}).get('value', {})
            print(f"[Re-Expanded State]: {reexp_val}")
            assert reexp_val['isExpanded'] == True, "Must be expanded"
            assert reexp_val['winWidth'] == 420, f"Expected 420, got {reexp_val['winWidth']}"

            # -----------------------------------------------------------------
            # TEST 6: Non-streaming (Unary JSON) mode verification
            # -----------------------------------------------------------------
            print("\n--- TEST 6: Unary / Non-Streaming mode verification ---")
            reqs_before = await get_network_request_count(ws)
            # Switch stream to false temporarily on widget
            eval_unary = """
                (async () => {
                    const el = document.querySelector('ivan-chat-widget');
                    el.setAttribute('stream', 'false');
                    await el.sendMessage('Unary test without streaming');
                    return {
                        isExpanded: el.isExpanded,
                        lastMsg: el.messages[el.messages.length - 1]
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': eval_unary, 'awaitPromise': True, 'returnByValue': True})
            unary_val = res.get('result', {}).get('value', {})
            print(f"[Unary Result]: role={unary_val.get('lastMsg', {}).get('role')}, text len={len(unary_val.get('lastMsg', {}).get('content', ''))}")
            assert unary_val.get('lastMsg', {}).get('role') == 'assistant', "Assistant response received via unary JSON"
            reqs_after = await get_network_request_count(ws)
            assert reqs_after == reqs_before + 1, "Unary request dispatched"

            # Reset stream mode to true
            await call_cdp(ws, 'Runtime.evaluate', {'expression': "document.querySelector('ivan-chat-widget').removeAttribute('stream')"})

            # -----------------------------------------------------------------
            # TEST 7: Backend error handling and retry mechanism
            # -----------------------------------------------------------------
            print("\n--- TEST 7: Backend error display and retry capability ---")
            # Point to an invalid endpoint temporarily to verify error bubble
            eval_err = """
                (async () => {
                    const el = document.querySelector('ivan-chat-widget');
                    const origUrl = el.apiUrl;
                    el.setAttribute('api-url', 'http://ivan.local:10004/wp-json/ivan/v1/invalid-endpoint-for-test');
                    await el.sendMessage('This should trigger error handling');
                    const errBubble = el.shadowRoot.querySelector('.ivan-message.error');
                    const retryBtn = errBubble ? errBubble.querySelector('.ivan-retry-btn') : null;
                    const lastMsg = el.messages[el.messages.length - 1];
                    // Restore valid apiUrl
                    el.removeAttribute('api-url');
                    return {
                        lastMsgIsError: Boolean(lastMsg?.isError),
                        hasErrorBubble: Boolean(errBubble),
                        hasRetryBtn: Boolean(retryBtn),
                        isLoading: el.isLoading
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': eval_err, 'awaitPromise': True, 'returnByValue': True})
            err_val = res.get('result', {}).get('value', {})
            print(f"[Error Handling Result]: {err_val}")
            assert err_val['lastMsgIsError'] == True, "Last message must be marked as error"
            assert err_val['hasErrorBubble'] == True, "Error bubble must be rendered"
            assert err_val['hasRetryBtn'] == True, "Retry button must be rendered"
            assert err_val['isLoading'] == False, "Loading indicator must be removed on error"

            # -----------------------------------------------------------------
            # TEST 8: Mobile Viewport (<480px) message submission & response
            # -----------------------------------------------------------------
            print("\n--- TEST 8: Mobile viewport (375x667) submission & response ---")
            await call_cdp(ws, 'Emulation.setDeviceMetricsOverride', {
                'width': 375,
                'height': 667,
                'deviceScaleFactor': 2,
                'mobile': True
            })
            await asyncio.sleep(0.5)

            reqs_before = await get_network_request_count(ws)
            eval_mobile_send = """
                (async () => {
                    const el = document.querySelector('ivan-chat-widget');
                    const sr = el.shadowRoot;
                    const rect = sr.querySelector('#window').getBoundingClientRect();
                    await el.sendMessage('Mobile message test');
                    return {
                        winWidth: Math.round(rect.width),
                        lastMsg: el.messages[el.messages.length - 1]
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': eval_mobile_send, 'awaitPromise': True, 'returnByValue': True})
            mob_val = res.get('result', {}).get('value', {})
            print(f"[Mobile Submission Result]: winWidth={mob_val.get('winWidth')}, role={mob_val.get('lastMsg', {}).get('role')}")
            assert mob_val.get('winWidth') == 375, f"Mobile width must be 375, got {mob_val.get('winWidth')}"
            assert mob_val.get('lastMsg', {}).get('role') == 'assistant', "Mobile message must receive response"
            reqs_after = await get_network_request_count(ws)
            assert reqs_after == reqs_before + 1, "Mobile request dispatched"

            await capture_screenshot(ws, r"C:\Users\Anish\.gemini\antigravity\brain\2fb1f6ee-67b1-4770-affa-d6843cfe2d6a\screenshot_mobile_response.png")

            await call_cdp(ws, 'Emulation.clearDeviceMetricsOverride')

            final_req_count = await get_network_request_count(ws)
            print("\n=======================================================")
            print("ALL REGRESSION AND ERROR HANDLING TESTS PASSED!")
            print(f"Total network chat requests dispatched & verified: {final_req_count}")
            print("=======================================================\n")

    finally:
        proc.kill()

if __name__ == '__main__':
    asyncio.run(run_regression_suite())

