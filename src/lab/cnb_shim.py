"""L-SHIM · CNB shim:本地 OpenAI 兼容端点,把 chat.completions 请求桥到 CNB 沙箱集群。

用途(ADR-0001 L-D9 的补充:一切生成走免费路径):SW 的 ModelRouter / lab 的任何
OpenAI 客户端指向 http://127.0.0.1:8400/v1 即用 CNB swarm 当后端,代码零改动。
- 每条请求 = 一个窗口任务(2 条评论),并发由 lab.swarm 的 48 闸与窗口队列控制;
- prompt 过长的防护:超过 MAX_INSTRUCTION_CHARS 直接报错(评论长度上限未明,快速失败好过挂死);
- 回复剥 @提及 前缀;JSON 场景由调用方(SW generate_json 自带 3 次重试)兜底。
"""
from __future__ import annotations

import json
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from lab import swarm

MAX_INSTRUCTION_CHARS = 60000  # CNB 评论上限未明(GitHub 系通常 65536);p6 实测 46k,压到 60k 内放行
TRAFFIC_LOG = Path("out/shim_traffic.jsonl")  # 逐请求证据(p5 毒化现场复盘靠它)
_JSON_STRICT_TRIES = 2  # 强约束重试轮数(实证:1 轮救不回稳定毒化的场景)


def _log_traffic(rec: dict[str, Any]) -> None:
    try:
        TRAFFIC_LOG.parent.mkdir(parents=True, exist_ok=True)
        with TRAFFIC_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _to_instruction(messages: list[dict[str, Any]]) -> str:
    parts = [str(m.get("content", "")) for m in messages]
    return "\n\n".join(p for p in parts if p)


def _strip_reply(reply: str) -> str:
    body = swarm._MENTION_RE.sub("", reply.strip())
    # JSON 抢救(实证:p0 因 NPC 在 JSON 外包了散文/代码栅栏而解析失败):
    # 优先 ```json 栅栏内容,其次第一个平衡花括号块。
    fence = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", body, re.DOTALL)
    if fence:
        return fence.group(1)
    start = body.find("{")
    if start >= 0:
        depth = 0
        for i, ch in enumerate(body[start:], start):
            depth += 1 if ch == "{" else (-1 if ch == "}" else 0)
            if depth == 0:
                return body[start : i + 1]
    return body


def _has_json(text: str) -> bool:
    return text.lstrip().startswith(("{", "["))


#: 结构省略侦测(实证 ~3% 毒化率:NPC 懒写返回 {"scene_json":"{...}"} /
#: "[{\"line_type\":\"action\",...}, ...]" / "Line[] 的 JSON..."——以 { 开头骗过
#: _has_json,但 SW 侧内层解析必死)。对白合法省略号是中文 ……,ASCII ... 只配占位用。
_ELISION_RE = re.compile(
    r"\{\s*\.\.\.\s*\}"  # {...} 占位
    r"|JSON\s*\.\.\."  # "Line[] 的 JSON..." 模式占位
    r"|[\[,:]\s*\.\.\."  # 结构符后接 ...(如 , ... / [...)
    r"|\.\.\.\s*[,\]\}]"  # ...后接结构符(如 ...] / ...,)
)


def _json_ok(text: str) -> bool:
    """真验证:以 {/[ 开头 + 整体能 json.loads + 无结构省略。三关全过才放行。"""
    if not _has_json(text):
        return False
    try:
        json.loads(text)
    except Exception:  # noqa: BLE001 —— 任何解析失败都走重试通道
        return False
    return not _ELISION_RE.search(text)


class ShimHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if not self.path.rstrip("/").endswith("/v1/chat/completions"):
            self.send_error(404)
            return
        t0 = time.time()
        rec: dict[str, Any] = {"ts": t0}
        try:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            instruction = _to_instruction(body.get("messages", []))
            rec["prompt_len"] = len(instruction)
            rec["json_mode"] = "JSON" in instruction.upper()
            if len(instruction) > MAX_INSTRUCTION_CHARS:
                raise ValueError(f"指令 {len(instruction)} 字符 > 护栏 {MAX_INSTRUCTION_CHARS}")
            reply = _strip_reply(swarm.run_task(instruction, work_mode=False, timeout_s=900,
                                                mention=swarm.WRITER_MENTION))  # 生成任务走写手 NPC(1核降配;判官人格拒答致 p0 解析失败,系统 CodeBuddy 8核计费)
            # JSON 重试(实证:p0 最高频死法是 NPC 回散文;次高频是 ... 占位毒化——
            # 强约束重试把合规彩票前移,占位场景必须明说"禁止省略")
            tries = 0
            while rec["json_mode"] and not _json_ok(reply) and tries < _JSON_STRICT_TRIES:
                tries += 1
                strict = (instruction + f"\n\n【重试要求·第{tries}次】上一次回复无法解析或含有省略/占位内容"
                          "（如 ...、{...}、\"Line[] 的 JSON...\"）。这次请只输出完整合法的 JSON 对象："
                          "所有字段写出完整内容，禁止省略占位、解释、问候、代码栅栏。")
                reply = _strip_reply(swarm.run_task(strict, work_mode=False, timeout_s=900,
                                                    mention=swarm.WRITER_MENTION))
            rec["tries"] = tries
            rec["json_ok"] = _json_ok(reply)
            rec["reply_head"] = reply[:300]
            rec["reply_tail"] = reply[-300:] if len(reply) > 300 else ""
            payload = {
                "id": f"cnb-{int(time.time() * 1000)}",
                "object": "chat.completion",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": reply},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0},
            }
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as exc:  # noqa: BLE001 —— 网关边界,必须把任何异常变成 500 响应
            rec["error"] = str(exc)[:300]
            data = json.dumps({"error": {"message": str(exc)[:300]}},
                              ensure_ascii=False).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        finally:
            rec["dur_s"] = round(time.time() - t0, 1)
            _log_traffic(rec)

    def log_message(self, *args):  # 静默访问日志
        pass


def serve(host: str = "127.0.0.1", port: int = 8400) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), ShimHandler)
    print(f"cnb shim listening on http://{host}:{port}/v1 (backend: CNB swarm)")
    server.serve_forever()
    return server


if __name__ == "__main__":
    serve()
