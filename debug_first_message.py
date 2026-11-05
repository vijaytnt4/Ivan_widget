import subprocess
import time
import json
import asyncio
import tempfile
import functools
import websockets
import requests

print = functools.partial(print, flush=True)

async def debug_send():
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

        async with websockets.connect(ws_url) as ws:
            req_id = 0
            async def call(method, params=None):
                nonlocal req_id
                req_id += 1
                msg = {'id': req_id, 'method': method}
                if params: msg['params'] = params
                await ws.send(json.dumps(msg))
                while True:
                    raw = await ws.recv()
                    data = json.loads(raw)
                    if data.get('id') == req_id:
                        return data.get('result', {})

            await call('Page.enable')
            await call('Runtime.enable')
            await call('Network.enable')

            async def listen():
                while True:
                    try:
                        raw = await ws.recv()
                        msg = json.loads(raw)
                        method = msg.get('method')
                        if method == 'Runtime.consoleAPICalled':
                            args = [a.get('value') or a.get('description') for a in msg.get('params', {}).get('args', [])]
                            print(f"[CONSOLE {msg.get('params',{}).get('type')}]", *args)
                        elif method == 'Runtime.exceptionThrown':
                            print(f"[EXCEPTION]", msg.get('params', {}).get('exceptionDetails', {}))
                        elif method == 'Network.requestWillBeSent':
                            req = msg.get('params', {}).get('request', {})
                            print(f"[NETWORK REQ] {req.get('method')} {req.get('url')}")
                        elif method == 'Network.responseReceived':
                            resp = msg.get('params', {}).get('response', {})
                            print(f"[NETWORK RESP] {resp.get('status')} {resp.get('statusText')} {resp.get('url')} Content-Type: {resp.get('headers',{}).get('content-type')}")
                        elif method == 'Network.loadingFailed':
                            print(f"[NETWORK FAIL]", msg.get('params', {}))
                    except:
                        break

            asyncio.create_task(listen())

            await call('Page.navigate', {'url': 'http://ivan.local:10004/'})
            await asyncio.sleep(3)

            # Check config on the widget
            res = await call('Runtime.evaluate', {'expression': """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    return {
                        apiUrl: el.apiUrl,
                        isStreamingEnabled: el.isStreamingEnabled,
                        sessionId: el.sessionId,
                        conversationId: el.conversationId,
                        windowIvanChatSettings: window.ivanChatSettings
                    };
                })()
            """, 'returnByValue': True})
            print("[CONFIG CHECK]", res.get('result', {}).get('value'))

            # Open widget
            await call('Runtime.evaluate', {'expression': 'document.querySelector("ivan-chat-widget").open()'})
            await asyncio.sleep(1)

            # Call sendMessage directly and inspect what it returns/throws
            print("\n--- Triggering sendMessage('test message') ---")
            eval_send = """
                (async () => {
                    const el = document.querySelector('ivan-chat-widget');
                    try {
                        console.log('Calling sendMessage...');
                        const p = el.sendMessage('test message');
                        console.log('sendMessage returned promise:', p);
                        await p;
                        console.log('sendMessage promise resolved!');
                        return { success: true, messages: el.messages };
                    } catch (e) {
                        console.error('sendMessage promise rejected:', e);
                        return { error: String(e) };
                    }
                })()
            """
            res = await call('Runtime.evaluate', {'expression': eval_send, 'awaitPromise': True, 'returnByValue': True})
            print("[SEND RESULT]", res.get('result', {}).get('value'))

            await asyncio.sleep(5)
            # Final messages check
            res = await call('Runtime.evaluate', {'expression': """
                (() => {
                    const el = document.querySelector('ivan-chat-widget');
                    return {
                        isLoading: el.isLoading,
                        isExpanded: el.isExpanded,
                        messages: el.messages
                    };
                })()
            """, 'returnByValue': True})
            print("[FINAL STATE]", res.get('result', {}).get('value'))

    finally:
        proc.kill()

if __name__ == '__main__':
    asyncio.run(debug_send())

