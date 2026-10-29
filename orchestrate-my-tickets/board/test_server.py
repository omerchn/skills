import json
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

from server import serve


def call(base, path, token=None, body=None):
    req = urllib.request.Request(base + path, data=body and json.dumps(body).encode(),
                                 headers={"X-Board-Token": token} if token else {})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_board():
    d = Path(tempfile.mkdtemp())
    httpd, token = serve(d)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        assert call(base, "/?t=wrong")[0] == 403
        assert call(base, f"/?t={token}")[0] == 200
        assert call(base, "/state")[0] == 403
        assert json.loads(call(base, "/state", token)[1])["tickets"] == []
        (d / "board-state.json").write_text('{"tickets":[{"key":"CORE-1"}]}')
        assert json.loads(call(base, "/state", token)[1])["tickets"][0]["key"] == "CORE-1"

        ok = {"action": "approve", "ticket": "CORE-1", "item": "p1"}
        assert call(base, "/decision", None, ok)[0] == 403
        assert call(base, "/decision", "wrong", ok)[0] == 403
        assert call(base, "/decision", token, {"action": "rm -rf", "ticket": "CORE-1"})[0] == 400
        assert call(base, "/decision", token, {"action": "approve"})[0] == 400
        assert call(base, "/decision", token, ok)[0] == 200
        assert call(base, "/decision", token, {"action": "dispatch", "plan": {}})[0] == 200
        assert call(base, "/decision", token, {"action": "desk_review", "url": "https://github.com/o/r/pull/1"})[0] == 200
        assert call(base, "/decision", token, {"action": "desk_drop", "desk": 7})[0] == 200
        assert call(base, "/decision", token, {"action": "chat", "ticket": "CORE-1", "body": "hi"})[0] == 400

        decided = json.loads(call(base, "/decided", token)[1])
        assert decided == {"items": ["CORE-1:p1"], "desk": [7], "dispatched": []}
        assert call(base, "/decided")[0] == 403

        lines = [json.loads(l) for l in (d / "decisions.jsonl").read_text().splitlines()]
        assert [l["action"] for l in lines] == ["approve", "dispatch", "desk_review", "desk_drop"]
        assert all(l["id"] and l["ts"] for l in lines)
    finally:
        httpd.shutdown()
        httpd.server_close()

    again, token2 = serve(d)  # a restart serves the same URL
    assert (token2, again.server_address) == (token, httpd.server_address)
    assert oct((d / "server.json").stat().st_mode & 0o777) == "0o600"
    again.server_close()


if __name__ == "__main__":
    test_board()
    print("ok")
