"""L-SWARM v2 · CNB CodeBuddy NPC 免费沙箱集群客户端。

机制(docs/cnb-swarm-usage-guide.md):仓库 Cloudbird-Software/talk 的 issue 是并行窗口;
评论以 @CodeBuddy 开头即拉起一次性沙箱异步执行,结果以 NPC 评论回写。

v2 纪律(实证教训:并发超限导致 35 个窗口锁死):
- 全局并发上限 48(沙箱硬上限 64,留余量),进程内信号量强制;
- 窗口健康度:评论数 ≥80 退役(100 封顶);最后被人类指令占住的窗口跳过;
- 窗口择优:空闲且评论最少者优先,均匀摊烧;健康空闲池 <20 时自动补开新 issue;
- 评论经济:支持打包投票(一条指令带多组对比,一条回复带回多个判定),
  因为评论会进入 NPC 上下文,评论越少质量越好、窗口越耐用。

定位:免费的后端算力,不是判官质量的保证——随机后端模型,质量由 k 采样聚合 +
判官考试门限兜底(ADR-0001 L-D4)。单编排进程使用。
"""
from __future__ import annotations

import json
import os
import queue
import re
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import lab.models  # noqa: F401  导入即加载 .env(load_dotenv 副作用)

BASE = "https://api.cnb.cool"
REPO = "Cloudbird-Software/talk"
ISSUE_POOL = range(1, 101)  # 初始窗口池(列表接口异常时的兜底)

MAX_HEALTHY_COMMENTS = 80   # 100 评论封顶,留余量退役
MIN_FREE_POOL = 20          # 健康空闲窗口低于此数自动补开
MAX_INFLIGHT = int(os.environ.get("CNB_MAX_INFLIGHT", "48"))  # 沙箱并发硬上限 64
_inflight = threading.BoundedSemaphore(MAX_INFLIGHT)


def _token() -> str:
    tok = os.environ.get("CNB_TOKEN", "").strip()
    if not tok:
        raise RuntimeError("缺 CNB_TOKEN(写进 .env;见 .env.example 与 docs/cnb-swarm-usage-guide.md)")
    return tok


def _http(method: str, path: str, body: dict | None = None, timeout: int = 30) -> Any:
    req = urllib.request.Request(f"{BASE}/{REPO}{path}", method=method)
    req.add_header("Authorization", f"Bearer {_token()}")
    req.add_header("Content-Type", "application/vnd.cnb.api+json")
    req.add_header("Accept", "application/vnd.cnb.api+json")
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    with urllib.request.urlopen(req, data=data, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw.strip() else {}


def list_issues(page_size: int = 200) -> list[dict]:
    return _http("GET", f"/-/issues?page_size={page_size}")


def list_comments(number: int, page_size: int = 100) -> list[dict]:
    return _http("GET", f"/-/issues/{number}/comments?page_size={page_size}")


def create_window(title: str | None = None) -> int:
    """补开新窗口(新 issue)。返回 issue number。"""
    resp = _http("POST", "/-/issues", {
        "title": title or f"调度窗口(swarm v2 自动补开 {int(time.time())})",
        "body": "自动调度窗口。空闲 = 最后一条评论来自 NPC。",
    })
    return int(resp["number"])


def close_window(number: int) -> bool:
    """关闭窗口。CNB 要求 state 与 state_reason 同时给(实证:单给 state 报 2000054)。"""
    try:
        _http("PATCH", f"/-/issues/{number}", {"state": "closed", "state_reason": "completed"})
        return True
    except (OSError, ValueError):
        return False


def cleanup_pool() -> dict:
    """关闭锁死窗口(最后评论是人类指令)与退役窗口(≥80 评论),返回统计。

    警告:会无差别关闭"人类指令收尾"的窗口——在飞任务的窗口也长这样。
    只能在无战役运行时调用。"""
    status = pool_status()
    closed = []
    for s in status:
        if (not s["free"]) or s["comments"] >= MAX_HEALTHY_COMMENTS:
            if close_window(s["number"]):
                closed.append(s["number"])
    return {"closed": closed, "remaining_healthy_free": len(healthy_free_windows(status))}


def pool_status(workers: int = 16) -> list[dict]:
    """全池体检:[{number, comments, free}]。free = 最后评论来自 NPC 或无评论。"""
    try:
        numbers = [i["number"] for i in list_issues()]
    except (OSError, ValueError, KeyError):
        numbers = list(ISSUE_POOL)

    def _one(n: int) -> dict:
        try:
            cs = list_comments(n)
        except (OSError, ValueError):
            return {"number": n, "comments": -1, "free": False}
        free = (not cs) or (cs[-1].get("author", {}).get("is_npc") is True)
        return {"number": n, "comments": len(cs), "free": free}

    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(_one, numbers))


def healthy_free_windows(status: list[dict] | None = None) -> list[int]:
    """空闲且未退役的窗口,按评论数升序(少烧优先)。"""
    status = pool_status() if status is None else status
    ok = [s for s in status if s["free"] and 0 <= s["comments"] < MAX_HEALTHY_COMMENTS]
    return [s["number"] for s in sorted(ok, key=lambda s: s["comments"])]


def ensure_pool(min_free: int = MIN_FREE_POOL) -> int:
    """健康空闲窗口不足时补开新 issue。返回当前健康空闲窗口数。"""
    wins = healthy_free_windows()
    while len(wins) < min_free:
        wins.append(create_window())
    return len(wins)


def is_free(number: int, comments: list[dict] | None = None) -> bool:
    comments = list_comments(number) if comments is None else comments
    if not comments:
        return True
    return comments[-1].get("author", {}).get("is_npc") is True


def dispatch(number: int, instruction: str, work_mode: bool = False) -> None:
    """投递即锁定窗口。纯问答(投票/改写)用 work_mode=False,沙箱执行才开 True。"""
    body = instruction if instruction.lstrip().startswith("@CodeBuddy") else f"@CodeBuddy {instruction}"
    _http("POST", f"/-/issues/{number}/comments", {"body": body, "work_mode": bool(work_mode)})


def poll_reply(number: int, timeout_s: float = 600, interval_s: float = 20) -> str:
    """轮询到"最后一条评论来自 NPC"即取回正文(与空闲判定同一条规则)。"""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        comments = list_comments(number)
        if comments and comments[-1].get("author", {}).get("is_npc") is True:
            return comments[-1].get("body", "")
        time.sleep(interval_s)
    raise TimeoutError(f"窗口 #{number} {timeout_s}s 内无 NPC 回复")


def run_task(instruction: str, work_mode: bool = False, timeout_s: float = 600) -> str:
    """单任务闭环:全局并发闸内 抢占 → 投递 → 轮询 → 返回 NPC 回复正文。"""
    with _inflight:
        wins = healthy_free_windows()
        if not wins:
            ensure_pool()
            wins = healthy_free_windows()
        if not wins:
            raise RuntimeError("无健康空闲窗口且补开失败")
        n = wins[0]
        dispatch(n, instruction, work_mode=work_mode)
        return poll_reply(n, timeout_s=timeout_s)


def run_batch(instructions: list[str], work_mode: bool = False, timeout_s: float = 900,
              workers: int = 16) -> list[str]:
    """多任务并行:窗口队列复用(NPC 回复后即空闲归还),全局并发闸兜底。

    任务间必须相互独立(指南 §6)。窗口数即天然并发上限,workers 再大也不会超池。
    """
    wins = healthy_free_windows()
    if len(wins) < min(len(instructions), MIN_FREE_POOL):
        ensure_pool()
        wins = healthy_free_windows()
    if not wins:
        raise RuntimeError("无健康空闲窗口且补开失败")
    win_q: queue.Queue[int] = queue.Queue()
    for w in wins:
        win_q.put(w)

    def _one(ins: str) -> str:
        with _inflight:
            n = win_q.get()
            try:
                dispatch(n, ins, work_mode=work_mode)
                return poll_reply(n, timeout_s=timeout_s)
            finally:
                win_q.put(n)  # NPC 回复后窗口即空闲,归还复用

    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(_one, instructions))


# ---- 打包投票(评论经济:一条指令带多组独立对比) ----

_VOTE_RE = re.compile(r"[AB]")
_MENTION_RE = re.compile(r"^(@\S+\s*)+")
_PACKED_RE = re.compile(r"(\d{1,3})\s*[:：.、]?\s*([AB])")


def parse_vote(reply: str) -> str:
    """单个判定:剥 @提及 前缀后取第一个 A/B;取不到返回 ''。"""
    body = _MENTION_RE.sub("", reply.strip())
    m = _VOTE_RE.search(body.upper())
    return m.group(0) if m else ""


def pack_vote_instruction(axis: str, axis_hint: str, items: list[tuple[str, str]],
                          text_budget: int = 1200,
                          signals: list[str] | None = None) -> str:
    """items = [(text_a, text_b), ...] 同轴的多组独立对比 → 一条指令。

    严格输出格式要求 + 文本截断,控制评论长度与上下文污染。
    signals = 该轴的信号级子问题(criteria/<axis>.md),分解判据可显著提升
    弱后端灵敏度(LLM-as-a-Verifier 的 criteria decomposition 结论)。"""
    parts = [
        f"你是短剧质量判官。下面有 {len(items)} 组互不相关的文本对比,评判轴:「{axis}」({axis_hint})。",
    ]
    if signals:
        parts.append("评判时逐条关注以下信号:" + ";".join(s[:60] for s in signals[:6]))
    parts += [
        "对每组独立判断哪一段在该轴上更好;逐组只回一个大写字母,格式严格为 1:A 2:B 3:A …,",
        "不要解释,不要输出任何其他内容。",
    ]
    for i, (a, b) in enumerate(items, 1):
        parts.append(f"第{i}组:\n第一段:\n{a[:text_budget]}\n第二段:\n{b[:text_budget]}")
    return "\n\n".join(parts)


def parse_packed_votes(reply: str, n: int) -> list[str]:
    """解析打包回复 → 长度为 n 的字母列表(缺失组为 '')。

    优先按编号对位(1:A 2:B …);编号缺失时退回取回复中的字母序列前 n 个。"""
    body = _MENTION_RE.sub("", reply.strip()).upper()
    out = [""] * n
    hits = {int(g): letter for g, letter in _PACKED_RE.findall(body) if 1 <= int(g) <= n}
    if hits:
        for g, letter in hits.items():
            out[g - 1] = letter
        return out
    letters = _VOTE_RE.findall(body)
    for i in range(min(n, len(letters))):
        out[i] = letters[i]
    return out
