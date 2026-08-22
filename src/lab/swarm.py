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
REPO = os.environ.get("CNB_SWARM_REPO", "Cloudbird-Software/swarm-pool")  # 专用池(1 核降配+判官人格)
ISSUE_POOL = range(1, 101)  # 初始窗口池(列表接口异常时的兜底)
# 自定义 NPC 角色(定义于 swarm-pool 仓 .cnb/settings.yml);异常时退回系统 @CodeBuddy
MENTION = os.environ.get("CNB_NPC_MENTION", f"@{REPO}(判官)")

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


def list_issues(page_size: int = 100, max_pages: int = 20) -> list[dict]:
    """分页拉全(实证:page_size 上限 100,窗口池已超 100 个,单页会漏掉新窗口)。"""
    out: list[dict] = []
    for page in range(1, max_pages + 1):
        batch = _http("GET", f"/-/issues?page_size={page_size}&page={page}")
        if not batch:
            break
        out.extend(batch)
        if len(batch) < page_size:
            break
    return out


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
        if ((not s["free"]) or s["comments"] >= MAX_HEALTHY_COMMENTS) and close_window(s["number"]):
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
    body = instruction if instruction.lstrip().startswith("@") else f"{MENTION} {instruction}"
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
              workers: int = 16, max_retries: int = 2,
              circuit_breaker: int = 10) -> list[str | None]:
    """多任务并行:窗口队列复用(NPC 回复后即空闲归还),全局并发闸兜底。

    韧性(实证:单个死窗口曾杀死整场考试):
    - 窗口超时 → 本地拉黑该窗口,换窗重试,最多 max_retries 次;
    - 重试耗尽 → 该任务弃票返回 None(调用方按缺失票处理),不拖死全场;
    - 连续 circuit_breaker 次失败 → 熔断 raise(平台额度/服务异常,继续跑只会产垃圾)。
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
    total_windows = len(wins)
    blacklist: set[int] = set()
    lock = threading.Lock()
    consecutive_fail = 0

    def _take() -> int | None:
        while True:
            try:
                n = win_q.get(timeout=1)
            except queue.Empty:
                with lock:
                    if len(blacklist) >= total_windows:
                        return None  # 窗口全灭
                continue  # 窗口都在飞,继续等
            if n not in blacklist:
                return n
            with lock:  # 拉黑窗口不归还(本地退役)
                if len(blacklist) >= total_windows:
                    return None

    def _one(ins: str) -> str | None:
        nonlocal consecutive_fail
        for _attempt in range(max_retries + 1):
            with _inflight:
                with lock:
                    if consecutive_fail >= circuit_breaker:
                        raise RuntimeError("熔断:连续失败超阈(疑似平台额度/服务异常)")
                n = _take()
                if n is None:
                    return None
                try:
                    dispatch(n, ins, work_mode=work_mode)
                    reply = poll_reply(n, timeout_s=timeout_s)
                except TimeoutError:
                    with lock:
                        blacklist.add(n)
                        consecutive_fail += 1
                    continue  # 死窗口不归还
                with lock:
                    consecutive_fail = 0
                win_q.put(n)  # NPC 回复后窗口即空闲,归还复用
                return reply
        return None  # 弃票

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
