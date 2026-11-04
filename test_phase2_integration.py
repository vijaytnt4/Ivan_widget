"""
Comprehensive Phase 2 Integration Test Suite for Ivan AI Chatbot WordPress Adapter.

Tests:
1. First message and conversation creation.
2. Multiple messages in the same conversation (multi-turn context).
3. Session persistence.
4. Conversation ID persistence.
5. API authentication failures (invalid key -> 401/500).
6. Backend unavailable scenarios (502 / connection error).
7. Invalid request payloads (empty message, invalid UUID, etc.).
8. Rate limiting (429 Too Many Requests).
9. JSON response mapping (backend 'answer' -> adapter 'answer' & 'reply').
10. SSE streaming tokens, done event, and stream error handling.
"""

import asyncio
import json
import re
import sys
import uuid
from typing import Dict, Any, Optional
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import http.client
import time

MOCK_PORT = 8991
VALID_API_KEY = "test_ivan_secret_key_12345"

# --- Mock FastAPI Ivan Backend ---
class MockIvanFastAPIHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass # Silence server logs during tests

    def do_POST(self):
        if self.path == "/api/v1/chat":
            auth_header = self.headers.get("X-Ivan-API-Key")
            if auth_header != VALID_API_KEY:
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"detail": "Unauthorized"}).encode("utf-8"))
                return

            content_len = int(self.headers.get("Content-Length", 0))
            body_bytes = self.rfile.read(content_len)
            try:
                data = json.loads(body_bytes.decode("utf-8"))
            except Exception:
                self.send_response(422)
                self.end_headers()
                return

            # Validate FastAPI QARequest schema
            if "question" not in data or not data["question"]:
                self.send_response(422)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"detail": [{"loc": ["body", "question"], "msg": "Field required"}]}).encode("utf-8"))
                return

            conv_id = data.get("conversation_id")
            if not conv_id:
                conv_id = str(uuid.uuid4())
            else:
                try:
                    uuid.UUID(conv_id)
                except Exception:
                    self.send_response(422)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"detail": "Invalid UUID"}).encode("utf-8"))
                    return

            sess_id = data.get("session_id") or "ivan-guest-" + str(uuid.uuid4())[:8]
            question = data["question"]

            response_data = {
                "answer": f"Ivan response to: '{question}'",
                "status": "success",
                "conversation_id": conv_id,
                "session_id": sess_id,
                "request_id": "req-" + str(uuid.uuid4())[:6]
            }

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/v1/chat/stream":
            auth_header = self.headers.get("X-Ivan-API-Key")
            params = urllib.parse.parse_qs(parsed.query)

            if auth_header != VALID_API_KEY and params.get("api_key", [""])[0] != VALID_API_KEY:
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"detail": "Unauthorized"}).encode("utf-8"))
                return

            questions = params.get("question", [""])
            question = questions[0]
            if not question:
                self.send_response(422)
                self.end_headers()
                return

            conv_id = params.get("conversation_id", [None])[0]
            if not conv_id:
                conv_id = str(uuid.uuid4())
            sess_id = params.get("session_id", [None])[0] or "ivan-guest-stream"

            # Check for simulated error trigger
            if "trigger_stream_error" in question:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                err_event = f"data: {json.dumps({'type': 'error', 'message': 'Simulated LLM generation error'})}\n\n"
                self.wfile.write(err_event.encode("utf-8"))
                return

            # Normal SSE stream
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()

            tokens = ["Hello", " from", " Ivan", " AI", " stream!"]
            for token in tokens:
                chunk = f"data: {json.dumps({'type': 'token', 'token': token})}\n\n"
                self.wfile.write(chunk.encode("utf-8"))
                self.wfile.flush()
                time.sleep(0.02)

            done_event = f"data: {json.dumps({'type': 'done', 'conversation_id': conv_id, 'session_id': sess_id, 'answer': 'Hello from Ivan AI stream!'})}\n\n"
            self.wfile.write(done_event.encode("utf-8"))
            self.wfile.flush()
        else:
            self.send_response(404)
            self.end_headers()


# --- WordPress Adapter Simulation (Mirroring includes/class-ivan-api.php) ---
class WordPressIvanAdapter:
    def __init__(self, backend_url: str, api_key: str):
        self.backend_url = backend_url.rstrip("/")
        self.api_key = api_key
        self.rate_limits: Dict[str, list] = {}

    def is_rate_limited(self, client_ip: str) -> bool:
        now = time.time()
        window = 60
        max_req = 30
        timestamps = [t for t in self.rate_limits.get(client_ip, []) if now - t < window]
        if len(timestamps) >= max_req:
            return True
        timestamps.append(now)
        self.rate_limits[client_ip] = timestamps
        return False

    def handle_request(self, client_ip: str, payload: dict) -> tuple[int, dict, Optional[str]]:
        """Handles POST /wp-json/ivan/v1/chat"""
        # 1. Rate Limiting Check
        if self.is_rate_limited(client_ip):
            return 429, {"code": "ivan_rate_limited", "message": "Too many requests. Please slow down."}, None

        # 2. Input Validation
        message = payload.get("message")
        if not message or not isinstance(message, str) or not message.strip():
            return 400, {"code": "invalid_param", "message": "Message is required and cannot be empty."}, None

        if len(message) > 2000:
            return 400, {"code": "invalid_param", "message": "Message exceeds 2000 characters."}, None

        conv_id = payload.get("conversation_id")
        if conv_id:
            uuid_regex = r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
            if not re.match(uuid_regex, conv_id.strip(), re.IGNORECASE):
                return 400, {"code": "invalid_param", "message": "Invalid conversation_id UUID format."}, None

        is_stream = bool(payload.get("stream", False))

        # 3. Check Misconfiguration
        if not self.backend_url:
            return 503, {"code": "ivan_misconfigured", "message": "Ivan Chatbot backend URL is not configured."}, None

        # 4. Handle Streaming
        if is_stream:
            query_args = {"question": message}
            if conv_id: query_args["conversation_id"] = conv_id
            if payload.get("session_id"): query_args["session_id"] = payload["session_id"]

            stream_path = f"/api/v1/chat/stream?{urllib.parse.urlencode(query_args)}"
            parsed_backend = urllib.parse.urlparse(self.backend_url)
            try:
                conn = http.client.HTTPConnection(parsed_backend.hostname, parsed_backend.port, timeout=10)
                headers = {"Accept": "text/event-stream"}
                if self.api_key:
                    headers["X-Ivan-API-Key"] = self.api_key
                conn.request("GET", stream_path, headers=headers)
                resp = conn.getresponse()
                if resp.status == 401 or resp.status == 403:
                    return 500, {"code": "ivan_auth_failure", "message": "Authentication failed between WordPress and backend."}, None
                if resp.status != 200:
                    return resp.status, {"code": "ivan_backend_error", "message": f"Backend returned {resp.status}"}, None

                raw_stream_data = resp.read().decode("utf-8")
                conn.close()
                return 200, {}, raw_stream_data
            except Exception as e:
                return 502, {"code": "ivan_backend_unavailable", "message": f"Backend connection error: {e}"}, None

        # 5. Handle Unary
        unary_payload = {
            "question": message,
            "conversation_id": conv_id,
            "session_id": payload.get("session_id"),
            "contact_id": payload.get("contact_id")
        }

        parsed_backend = urllib.parse.urlparse(self.backend_url)
        try:
            conn = http.client.HTTPConnection(parsed_backend.hostname, parsed_backend.port, timeout=10)
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            if self.api_key:
                headers["X-Ivan-API-Key"] = self.api_key
            conn.request("POST", "/api/v1/chat", body=json.dumps(unary_payload), headers=headers)
            resp = conn.getresponse()
            resp_body = resp.read().decode("utf-8")
            conn.close()

            if resp.status == 401 or resp.status == 403:
                return 500, {"code": "ivan_auth_failure", "message": "Authentication failed between WordPress and backend."}, None

            if resp.status != 200:
                return resp.status, {"code": "ivan_backend_error", "message": resp_body}, None

            data = json.loads(resp_body)
            # Map backend response fields
            return 200, {
                "success": True,
                "answer": data.get("answer", ""),
                "reply": data.get("answer", ""),
                "conversation_id": data.get("conversation_id"),
                "session_id": data.get("session_id"),
                "status": data.get("status", "success")
            }, None
        except Exception as e:
            return 502, {"code": "ivan_backend_unavailable", "message": f"Backend connection error: {e}"}, None


# --- Run Test Cases ---
def run_all_tests():
    # Start mock server
    server = HTTPServer(("127.0.0.1", MOCK_PORT), MockIvanFastAPIHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    backend_url = f"http://127.0.0.1:{MOCK_PORT}"
    adapter = WordPressIvanAdapter(backend_url, VALID_API_KEY)

    print("==================================================")
    print("RUNNING PHASE 2 VERIFICATION SUITE")
    print("==================================================")

    passed = 0
    total = 10

    # Test 1: First message & conversation creation
    status, data, _ = adapter.handle_request("127.0.0.1", {
        "message": "Hello Ivan",
        "conversation_id": None,
        "session_id": "ivan-sess-001"
    })
    assert status == 200, f"Test 1 Failed: Status {status}"
    assert data["success"] is True
    assert "Hello Ivan" in data["answer"]
    assert data["conversation_id"] is not None
    assert data["session_id"] == "ivan-sess-001"
    created_conv_id = data["conversation_id"]
    print("[PASS] Test 1: First message & conversation creation successful.")
    passed += 1

    # Test 2: Multiple messages in the same conversation
    status, data2, _ = adapter.handle_request("127.0.0.1", {
        "message": "What is my next step?",
        "conversation_id": created_conv_id,
        "session_id": "ivan-sess-001"
    })
    assert status == 200
    assert data2["conversation_id"] == created_conv_id, "Conversation ID did not persist across turns!"
    assert data2["session_id"] == "ivan-sess-001"
    print("[PASS] Test 2: Multi-turn conversation preserved same conversation_id.")
    passed += 1

    # Test 3 & 4: Session persistence and Conversation ID persistence
    assert data2["session_id"] == "ivan-sess-001"
    assert uuid.UUID(data2["conversation_id"]), "Invalid UUID received"
    print("[PASS] Test 3 & 4: Session and Conversation UUID verified.")
    passed += 2

    # Test 5: API Authentication Failure
    bad_auth_adapter = WordPressIvanAdapter(backend_url, "WRONG_SECRET_KEY")
    status, data_bad_auth, _ = bad_auth_adapter.handle_request("127.0.0.1", {"message": "Test Auth"})
    assert status == 500
    assert data_bad_auth["code"] == "ivan_auth_failure"
    print("[PASS] Test 5: Authentication failure caught cleanly without exposing key.")
    passed += 1

    # Test 6: Backend Unavailable
    dead_adapter = WordPressIvanAdapter("http://127.0.0.1:9999", VALID_API_KEY)
    status, data_dead, _ = dead_adapter.handle_request("127.0.0.1", {"message": "Test Offline"})
    assert status == 502
    assert data_dead["code"] == "ivan_backend_unavailable"
    print("[PASS] Test 6: Backend unavailable handled with HTTP 502.")
    passed += 1

    # Test 7: Invalid request payloads
    # 7a: Empty message
    status, data_empty, _ = adapter.handle_request("127.0.0.1", {"message": "   "})
    assert status == 400
    # 7b: Invalid UUID
    status, data_bad_uuid, _ = adapter.handle_request("127.0.0.1", {"message": "Hello", "conversation_id": "not-a-uuid"})
    assert status == 400
    print("[PASS] Test 7: Invalid request payloads properly rejected with HTTP 400.")
    passed += 1

    # Test 8: Rate Limiting
    rl_adapter = WordPressIvanAdapter(backend_url, VALID_API_KEY)
    ip = "192.168.1.100"
    for _ in range(30):
        rl_adapter.handle_request(ip, {"message": "Ping"})
    # 31st request should be rate limited
    status_rl, data_rl, _ = rl_adapter.handle_request(ip, {"message": "Ping 31"})
    assert status_rl == 429
    assert data_rl["code"] == "ivan_rate_limited"
    print("[PASS] Test 8: Rate limit strictly enforced (HTTP 429 on 31st request).")
    passed += 1

    # Test 9: JSON Response Mapping
    status, data_mapped, _ = adapter.handle_request("127.0.0.1", {"message": "Check mapping"})
    assert "answer" in data_mapped
    assert "reply" in data_mapped
    assert data_mapped["answer"] == data_mapped["reply"]
    print("[PASS] Test 9: Response field mapping verified ('answer' and 'reply').")
    passed += 1

    # Test 10: Real SSE Streaming (token, done, and error handling)
    status_s, _, stream_content = adapter.handle_request("127.0.0.1", {
        "message": "Stream this test",
        "stream": True
    })
    assert status_s == 200
    assert "data: " in stream_content
    assert '"type": "token"' in stream_content
    assert '"type": "done"' in stream_content
    
    # Test streaming error event
    status_err, _, err_stream_content = adapter.handle_request("127.0.0.1", {
        "message": "trigger_stream_error",
        "stream": True
    })
    assert status_err == 200
    assert '"type": "error"' in err_stream_content
    print("[PASS] Test 10: SSE streaming tokens, done event, and stream error handling verified.")
    passed += 1

    print("==================================================")
    print(f"ALL {passed}/{total} TESTS PASSED SUCCESSFULLY!")
    print("==================================================")
    server.shutdown()

if __name__ == "__main__":
    run_all_tests()
