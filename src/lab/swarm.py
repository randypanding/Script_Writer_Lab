"""L-SWARM · CNB CodeBuddy NPC 免费沙箱集群客户端。

机制(docs/cnb-swarm-usage-guide.md):仓库 Cloudbird-Software/talk 的 issue #1-#100 是并行窗口;
评论以 @CodeBuddy 开头即拉起一次性沙箱异步执行,结果以 NPC 评论回写。
- 空闲判定:窗口无评论,或最后一条评论 author.is_npc == true;
- 纪律:一个窗口同一时刻只承载一个任务;dispatch 后最后评论必是人类指令,
  轮询到"最后一条是 NPC 回复"即为结果到达(与空闲判定同一条规则,天然闭环);
- 令牌只从 CNB_TOKEN 环境变量读(.env 经 lab.models 导入时加载),永不入仓。

定位:这是**免费的后端算力**,不是判官质量的保证——随机后端模型,质量由
k 采样投票聚合 + 判官考试门限兜底(ADR-0001 L-D4:弱验证器+重复采样)。
注意:单编排进程使用;多进程并发抢占同一窗口会有竞态(抢占-投递非原子)。
"""
from __future__ import annotations

import json
import os
import random
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import lab.models  # noqa: F401  导入即加载 .env(load_dotenv 副作用)

BASE = "https://api.cnb.cool"
REPO = "Cloudbird-Software/talk"
ISSUE_POOL = range(1, 101)  # 预置窗口 #1-#100


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


def list_comments(number: int, page_size: int = 50) -> list[dict]:
    return _http("GET", f"/-/issues/{number}/comments?page_size={page_size}")


def is_free(number: int, comments: list[dict] | None = None) -> bool:
    comments = list_comments(number) if comments is None else comments
    if not comments:
        return True
    return comments[-1].get("author", {}).get("is_npc") is True


def find_free_window(rng: random.Random | None = None, sample: int = 20) -> int | None:
    rng = rng or random.Random()
    try:
        candidates = [i["number"] for i in list_issues()]
    except (OSError, ValueError, KeyError):
        candidates = list(ISSUE_POOL)  # 列表接口异常时退回固定池
    rng.shuffle(candidates)
    for n in candidates[:sample]:
        if is_free(n):
            return n
    return None


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


def run_task(instruction: str, work_mode: bool = False, timeout_s: float = 600,
             rng: random.Random | None = None) -> str:
    """完整闭环:抢占 → 投递 → 轮询 → 返回 NPC 回复正文。"""
    n = find_free_window(rng=rng)
    if n is None:
        raise RuntimeError("100 个窗口全占用,稍后再试")
    dispatch(n, instruction, work_mode=work_mode)
    return poll_reply(n, timeout_s=timeout_s)


def run_batch(instructions: list[str], work_mode: bool = False, timeout_s: float = 900,
              workers: int = 8) -> list[str]:
    """多任务并行(各占一个窗口)。任务间必须相互独立(指南 §6 纪律)。"""
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(lambda ins: run_task(ins, work_mode=work_mode, timeout_s=timeout_s),
                           instructions))


_VOTE_RE = re.compile(r"[AB]")
_MENTION_RE = re.compile(r"^(@\S+\s*)+")


def parse_vote(reply: str) -> str:
    """从 NPC 回复取第一个 A/B 字母;取不到返回 ''(调用方按弃票处理)。

    必须先剥 @提及 前缀——NPC 回复形如 "@cnb.dQQ3yYJOAGA(潘鼎) ...",
    提及本身含 A/B 字母,不剥会永远误判。"""
    body = _MENTION_RE.sub("", reply.strip())
    m = _VOTE_RE.search(body.upper())
    return m.group(0) if m else ""
