#!/usr/bin/env python3
"""Sprint board for orchestrate-my-tickets.

The session writes <dir>/board-state.json; the page POSTs decisions, which land one JSON
object per line in <dir>/decisions.jsonl for the session to tail.

    python3 server.py --dir <run>/board [--port 0]

The port and token are kept in <dir>/server.json, so a restart (or a reboot) serves the same URL.
"""
import argparse
import hmac
import json
import secrets
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).parent
ACTIONS = {
    "approve", "edit_approve", "send_back", "drop", "answer",
    "stop_agent", "move_to_waiting", "dispatch", "promote",
    "desk_decide", "desk_drop", "desk_review", "desk_start", "desk_stop",
}
NO_TICKET = {"dispatch", "promote", "desk_decide", "desk_drop", "desk_review", "desk_start", "desk_stop"}
MAX_BODY = 1_000_000


def make_handler(state_dir: Path, token: str):
    lock = threading.Lock()
    decisions = state_dir / "decisions.jsonl"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def _send(self, code, body=b"", ctype="application/json"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _authed(self, query_token=None):
            # Custom header forces a CORS preflight we never answer, so other sites can't post.
            got = self.headers.get("X-Board-Token") or query_token or ""
            return hmac.compare_digest(got, token)

        def do_GET(self):
            url = urlparse(self.path)
            if url.path == "/":
                if not self._authed(parse_qs(url.query).get("t", [None])[0]):
                    return self._send(403, b"bad token", "text/plain")
                return self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
            if url.path == "/decided":
                # Lets a reloaded page keep showing decisions it already sent.
                if not self._authed():
                    return self._send(403, b'{"error":"bad token"}')
                out = {"items": [], "desk": [], "dispatched": []}
                for line in decisions.read_text().splitlines():
                    try:
                        d = json.loads(line)
                    except ValueError:
                        continue
                    if d.get("item"):
                        out["items"].append(f'{d.get("ticket")}:{d["item"]}')
                    elif d.get("action") in ("desk_decide", "desk_drop"):
                        out["desk"].append(d.get("desk"))
                    elif d.get("action") == "dispatch":
                        out["dispatched"] += list((d.get("plan") or {}).keys())
                return self._send(200, json.dumps(out).encode())
            if url.path == "/state":
                if not self._authed():
                    return self._send(403, b'{"error":"bad token"}')
                try:
                    return self._send(200, (state_dir / "board-state.json").read_bytes())
                except FileNotFoundError:
                    return self._send(200, b'{"run":{"phase":"starting"},"columns":[],"tickets":[]}')
            self._send(404, b'{"error":"not found"}')

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > MAX_BODY:
                return self._send(413, b'{"error":"bad size"}')
            # Read the body before any rejection, or the client sees a reset instead of the status.
            body = self.rfile.read(length)
            if urlparse(self.path).path != "/decision":
                return self._send(404, b'{"error":"not found"}')
            if not self._authed():
                return self._send(403, b'{"error":"bad token"}')
            try:
                d = json.loads(body)
            except ValueError:
                return self._send(400, b'{"error":"not json"}')
            if not isinstance(d, dict) or d.get("action") not in ACTIONS:
                return self._send(400, b'{"error":"unknown action"}')
            if d["action"] not in NO_TICKET and not isinstance(d.get("ticket"), str):
                return self._send(400, b'{"error":"ticket required"}')
            d["id"] = uuid.uuid4().hex
            d["ts"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            with lock, decisions.open("a") as f:
                f.write(json.dumps(d) + "\n")
            self._send(200, json.dumps({"id": d["id"]}).encode())

    return Handler


def serve(state_dir: Path, port: int = 0, token: str | None = None):
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "decisions.jsonl").touch()
    saved = state_dir / "server.json"
    try:
        old = json.loads(saved.read_text())
    except (OSError, ValueError):
        old = {}
    token = token or old.get("token") or secrets.token_urlsafe(24)
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", port or old.get("port", 0)), make_handler(state_dir, token))
    except OSError:  # saved port taken: same token, new port
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(state_dir, token))
    saved.touch(mode=0o600)
    saved.write_text(json.dumps({"port": httpd.server_address[1], "token": token}))
    return httpd, token


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, type=Path)
    ap.add_argument("--port", type=int, default=0)
    a = ap.parse_args()
    httpd, token = serve(a.dir, a.port)
    print(f"BOARD_URL=http://127.0.0.1:{httpd.server_address[1]}/?t={token}", flush=True)
    httpd.serve_forever()
