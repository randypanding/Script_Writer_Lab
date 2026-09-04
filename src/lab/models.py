"""LLM 路由(唯一入口)。AGENTS.md 硬约束:每个 LLM 调用必须经本模块并写 transcript,禁止直接调 SDK。

槽位与密钥环境变量名来自 lab.toml [models];transcript 落 SQLite(表结构 ADR-0001 §接口):
(ts, caller, model, prompt, response, tokens_in, tokens_out, cost_usd, experiment_id)
"""

from __future__ import annotations

import os
import random
import sqlite3
import threading
import time
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[2]
LAB_TOML = ROOT / "lab.toml"

# .env 是密钥的唯一存放点(gitignored)。模块导入即加载;
# load_dotenv 默认不覆盖已存在的环境变量——显式 export 优先。
from dotenv import load_dotenv
from openai import APIStatusError, RateLimitError

load_dotenv(ROOT / ".env")


def _load_lab_toml() -> dict[str, Any]:
    with LAB_TOML.open("rb") as f:
        return tomllib.load(f)


def _db_path(override: str | Path | None = None) -> Path:
    if override:
        return Path(override)
    cfg = _load_lab_toml()
    p = ROOT / cfg["paths"]["transcripts"]
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


_SCHEMA = """
CREATE TABLE IF NOT EXISTS transcripts (
    ts REAL, caller TEXT, model TEXT, prompt TEXT, response TEXT,
    tokens_in INTEGER, tokens_out INTEGER, cost_usd REAL, experiment_id TEXT
)
"""

_CONCURRENCY_SEM = threading.Semaphore(12)  # 全局并发上限(stepfun 20 留余量)


def _write_transcript(db: Path, row: tuple) -> None:
    con = sqlite3.connect(db)
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA busy_timeout=10000")
        con.execute(_SCHEMA)
        con.execute("INSERT INTO transcripts VALUES (?,?,?,?,?,?,?,?,?)", row)
        con.commit()
    finally:
        con.close()


def _resolve_client(slot: str) -> tuple[str, Any]:
    """槽位 → (model, openai client)。缺 key 时抛 RuntimeError(不静默降级)。"""
    cfg = _load_lab_toml()["models"][slot]
    key = os.environ.get(cfg["api_key_env"], "")
    base = os.environ.get(cfg["api_base_env"], "") or None
    if not key:
        raise RuntimeError(f"槽位 {slot} 缺少环境变量 {cfg['api_key_env']}(真实调用需 --run-llm 场景)")
    from openai import OpenAI

    return cfg["model"], OpenAI(api_key=key, base_url=base)


class ContentBlockedError(RuntimeError):
    """451 censorship: provider refused to generate."""


def route(
    slot: str,
    prompt: str,
    *,
    system: str | None = None,
    caller: str = "",
    experiment_id: str = "",
    temperature: float | None = None,
    db_path: str | Path | None = None,
    client: Any | None = None,
) -> str:
    """一次 LLM 调用:路由槽位 + transcript 落库。client 参数供测试注入 mock。

    槽位 cfg 带 backend = "cnb" 时走 CNB 免费沙箱集群(lab.swarm),不调 OpenAI 兼容端点。
    """
    cfg = _load_lab_toml()["models"][slot]
    if client is None and cfg.get("backend") == "cnb":
        from lab.swarm import _MENTION_RE, run_task  # 延迟导入:swarm 反向 import 本模块

        text = run_task(
            (f"{system}\n\n" if system else "") + prompt,
            work_mode=False,
            mention=cfg.get("mention"),  # 槽位可指定 NPC 人格(判官/写手)
            timeout_s=float(cfg.get("timeout_s", 600)),
        )  # 死窗等待上限(默认 600 太久)
        text = _MENTION_RE.sub("", text.strip())  # 剥 NPC 回复的 @提及 前缀(实证:曾混入生成物)
        _write_transcript(
            _db_path(db_path),
            (time.time(), caller, str(cfg.get("model", "codebuddy")), prompt, text, 0, 0, 0.0, experiment_id),
        )
        return text
    if client is None:
        model, real_client = _resolve_client(slot)
        cl = real_client
    else:
        model = getattr(client, "model_name", slot)
        cl = client
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": prompt}
    ]
    kwargs: dict[str, Any] = {"model": model, "messages": messages, "max_tokens": 4096}
    if temperature is not None:
        kwargs["temperature"] = temperature
    # 有界指数退避 + jitter 重试 RateLimitError(429);总并发由 _CONCURRENCY_SEM 钳制
    max_retries = 6
    for attempt in range(max_retries + 1):
        try:
            with _CONCURRENCY_SEM:
                resp = cl.chat.completions.create(**kwargs)
            break
        except RateLimitError:
            if attempt == max_retries:
                raise
            delay = min(1.0 * (2**attempt), 60.0)
            jitter = random.uniform(delay * 0.75, delay * 1.25)
            time.sleep(jitter)
        except APIStatusError as exc:
            if getattr(exc, "status_code", None) == 451:
                raise ContentBlockedError(str(exc)[:200]) from exc
            raise
    text = resp.choices[0].message.content or ""
    if not text:
        text = getattr(resp.choices[0].message, "reasoning_content", "") or ""
    usage = getattr(resp, "usage", None)
    t_in = getattr(usage, "prompt_tokens", 0) or 0
    t_out = getattr(usage, "completion_tokens", 0) or 0
    _write_transcript(
        _db_path(db_path),
        (time.time(), caller, str(model), prompt, text, t_in, t_out, 0.0, experiment_id),
    )
    return text


def read_transcripts(db_path: str | Path | None = None) -> list[dict[str, Any]]:
    con = sqlite3.connect(_db_path(db_path))
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute("SELECT * FROM transcripts ORDER BY ts").fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


__all__ = ["ROOT", "ContentBlockedError", "read_transcripts", "route"]
