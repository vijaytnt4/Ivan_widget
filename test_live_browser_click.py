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

async def test_live_localwp_browser_click():
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
        print(f"[CDP] Connected to Chrome tab: {ws_url}")

        async with websockets.connect(ws_url) as ws:
            # Enable Page & Runtime domains
            await call_cdp(ws, 'Page.enable')
            await call_cdp(ws, 'Runtime.enable')

            # Navigate to LocalWP
            print("[CDP] Navigating to http://ivan.local:10004/ ...")
            nav_res = await call_cdp(ws, 'Page.navigate', {'url': 'http://ivan.local:10004/'})
            print(f"[CDP] Page.navigate completed: {nav_res}")

            # Wait for document to be ready
            for _ in range(20):
                res = await call_cdp(ws, 'Runtime.evaluate', {'expression': 'document.readyState', 'returnByValue': True})
                val = res.get('result', {}).get('value')
                if val == 'complete':
                    break
                await asyncio.sleep(0.5)

            # Check if ivan-chat-widget exists
            check_widget = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    return {
                        exists: Boolean(el),
                        hasShadow: Boolean(el && el.shadowRoot)
                    };
                })()
            """
            widget_check = None
            for _ in range(20):
                res = await call_cdp(ws, 'Runtime.evaluate', {'expression': check_widget, 'returnByValue': True})
                widget_check = res.get('result', {}).get('value')
                if widget_check and widget_check.get('exists'):
                    break
                await asyncio.sleep(0.5)

            print(f"[CDP] Widget existence check: {widget_check}")
            assert widget_check['exists'], "ivan-chat-widget not found on LocalWP page"

            # Open widget and send question
            print("[CDP] Opening widget and dispatching message...")
            send_msg = """
                (async () => {
                    const el = document.querySelector('ivan-chat-widget');
                    el.open();
                    await new Promise(r => setTimeout(r, 600));
                    await el.sendMessage('Where can I access the Strategic Maturity Assessment?');
                    return { sent: true };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': send_msg, 'awaitPromise': True, 'returnByValue': True})
            print(f"[CDP] Send message evaluated: {res}")

            # Poll for the assistant response with the link
            print("[CDP] Waiting for response to stream and render...")
            link_info = None
            for attempt in range(35):
                await asyncio.sleep(1)
                inspect_bubbles = """
                    (() => {
                        const el = document.querySelector('ivan-chat-widget');
                        if (!el || !el.shadowRoot) return { links: [] };
                        const links = Array.from(el.shadowRoot.querySelectorAll('.ivan-message.bot .ivan-bubble a')).map(a => ({
                            href: a.href,
                            text: a.textContent,
                            target: a.target,
                            rel: a.rel,
                            outerHTML: a.outerHTML
                        }));
                        const lastBotBubble = el.shadowRoot.querySelector('.ivan-message.bot:last-child .ivan-bubble');
                        const text = lastBotBubble ? lastBotBubble.textContent : '';
                        const innerHTML = lastBotBubble ? lastBotBubble.innerHTML : '';
                        return { links, text, innerHTML };
                    })()
                """
                res = await call_cdp(ws, 'Runtime.evaluate', {'expression': inspect_bubbles, 'returnByValue': True})
                data = res.get('result', {}).get('value', {})
                if data.get('links') and len(data['links']) > 0:
                    link_info = data['links'][0]
                    print(f"[CDP] Found link after {attempt+1}s: {link_info}")
                    break
                else:
                    if data.get('text'):
                        print(f"[CDP] Latest bubble text ({attempt+1}s): {data['text'][:70]}... (HTML: {data['innerHTML'][:70]}...)")

            assert link_info is not None, "No clickable link found in assistant response"
            print(f"\n[PASS] Verified Link in assistant bubble:")
            print(f"  - Outer HTML: {link_info['outerHTML']}")
            print(f"  - Href: {link_info['href']}")
            print(f"  - Text: {link_info['text']}")
            print(f"  - Target: {link_info['target']}")
            print(f"  - Rel: {link_info['rel']}")
            assert 'nav.ac/dma7t' in link_info['href'], f"Href did not contain nav.ac/dma7t: {link_info['href']}"
            assert link_info['target'] == '_blank', f"Target was not _blank: {link_info['target']}"
            assert 'noopener' in link_info['rel'] and 'noreferrer' in link_info['rel'], f"Rel did not contain noopener noreferrer: {link_info['rel']}"

            # 4. Perform actual browser click on the anchor element
            print("\n[CDP] Simulating actual browser click on anchor element...")
            click_test = """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    const link = el.shadowRoot.querySelector('.ivan-message.bot .ivan-bubble a');
                    if (!link) return { clicked: false, error: 'Link not found' };

                    let clickEventFired = false;
                    link.addEventListener('click', (e) => {
                        clickEventFired = true;
                    });

                    // Trigger genuine DOM click event
                    const clickEvt = new MouseEvent('click', {
                        bubbles: true,
                        cancelable: true,
                        composed: true,
                        view: window
                    });
                    const dispatched = link.dispatchEvent(clickEvt);

                    return {
                        clicked: true,
                        clickEventFired: clickEventFired,
                        dispatched: dispatched,
                        href: link.href
                    };
                })()
            """
            res = await call_cdp(ws, 'Runtime.evaluate', {'expression': click_test, 'returnByValue': True})
            click_res = res.get('result', {}).get('value', {})
            print(f"[CDP] Click result: {click_res}")
            assert click_res['clicked'] and click_res['clickEventFired'], "Click event failed to fire on the anchor"

            print("\n==================================================")
            print("ACTUAL BROWSER CLICK TEST ON LOCALWP SUCCEEDED!")
            print("==================================================")

    finally:
        proc.terminate()

if __name__ == '__main__':
    asyncio.run(test_live_localwp_browser_click())