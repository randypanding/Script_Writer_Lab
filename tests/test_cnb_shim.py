"""L-SHIM · CNB shim 的 OpenAI 兼容行为。实现目标: src/lab/cnb_shim.py"""
import json
import urllib.request

from lab import cnb_shim, swarm


def _post(port: int, payload: dict):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _serve_bg(monkeypatch, reply_text):
    monkeypatch.setattr(swarm, "run_task", lambda *a, **k: reply_text)
    from http.server import ThreadingHTTPServer
    server = ThreadingHTTPServer(("127.0.0.1", 0), cnb_shim.ShimHandler)
    import threading
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_openai_shape_and_mention_strip(monkeypatch):
    server = _serve_bg(monkeypatch, "@cnb.dQQ3yYJOAGA(潘鼎) 这是生成的小说正文。")
    try:
        port = server.server_address[1]
        out = _post(port, {"model": "x", "messages": [
            {"role": "system", "content": "你是写手"}, {"role": "user", "content": "写一段"}]})
        assert out["choices"][0]["message"]["content"] == "这是生成的小说正文。"
        assert out["usage"]["prompt_tokens"] == 0
    finally:
        server.shutdown()


def test_oversize_instruction_fast_fails(monkeypatch):
    server = _serve_bg(monkeypatch, "不会用到")
    try:
        port = server.server_address[1]
        big = "长" * (cnb_shim.MAX_INSTRUCTION_CHARS + 1)
        try:
            _post(port, {"model": "x", "messages": [{"role": "user", "content": big}]})
            raise AssertionError("应当 500")
        except urllib.error.HTTPError as e:
            assert e.code == 500
            assert "护栏" in e.read().decode("utf-8")
    finally:
        server.shutdown()
