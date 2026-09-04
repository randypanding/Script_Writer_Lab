"""infra · lab.models 路由:LLM 调用唯一入口 + transcript 落库(AGENTS.md 硬约束)。"""

from types import SimpleNamespace

from lab.models import read_transcripts, route


class MockClient:
    model_name = "mock-model"

    def __init__(self, reply="你好"):
        self.reply = reply
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        msg = SimpleNamespace(content=self.reply)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=msg)],
            usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7),
        )


def test_route_writes_transcript(tmp_path):
    db = tmp_path / "t.db"
    c = MockClient("回复内容")
    out = route("generation", "问题", caller="test", db_path=db, client=c)
    assert out == "回复内容"
    assert c.calls[0]["messages"][-1]["content"] == "问题"
    rows = read_transcripts(db)
    assert len(rows) == 1
    r = rows[0]
    assert r["caller"] == "test" and r["prompt"] == "问题" and r["response"] == "回复内容"
    assert r["tokens_in"] == 11 and r["tokens_out"] == 7


def test_route_without_key_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("GEN_API_KEY", raising=False)
    import pytest

    with pytest.raises(RuntimeError, match="GEN_API_KEY"):
        route("generation", "问题", db_path=tmp_path / "t.db")


def test_system_prompt_prepended(tmp_path):
    db = tmp_path / "t.db"
    c = MockClient()
    route("generation", "q", system="s1", db_path=db, client=c)
    assert c.calls[0]["messages"][0] == {"role": "system", "content": "s1"}


def test_route_reasoning_content_fallback(tmp_path):
    """content=None/empty 时回退 reasoning_content。"""
    db = tmp_path / "t.db"

    class EmptyContentClient:
        model_name = "mock-model"

        def __init__(self):
            self.calls = []
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

        def _create(self, **kw):
            self.calls.append(kw)
            msg = SimpleNamespace(content=None)
            msg.reasoning_content = "推理回退内容"
            return SimpleNamespace(
                choices=[SimpleNamespace(message=msg)],
                usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7),
            )

    c = EmptyContentClient()
    out = route("generation", "问题", caller="test", db_path=db, client=c)
    assert out == "推理回退内容"
    rows = read_transcripts(db)
    assert len(rows) == 1
    assert rows[0]["response"] == "推理回退内容"


def test_route_max_tokens_sent(tmp_path):
    """route 默认带 max_tokens=4096。"""
    db = tmp_path / "t.db"
    c = MockClient("回复")
    route("generation", "问题", db_path=db, client=c)
    assert c.calls[0]["max_tokens"] == 4096


def test_route_censors_451_blocked(tmp_path):
    """451 censorship 应抛 ContentBlockedError,不落 transcript。"""
    import sqlite3

    import httpx
    import openai

    from lab.models import ContentBlockedError, route

    def _block(**kw):
        req = httpx.Request("POST", "http://test/v1/chat/completions")
        raise openai.APIStatusError(
            "content blocked",
            response=httpx.Response(451, request=req),
            body=None,
        )

    class BlockClient:
        model_name = "block-model"
        chat = SimpleNamespace(completions=SimpleNamespace(create=_block))

    db = tmp_path / "t.db"
    with pytest.raises(ContentBlockedError, match="content blocked"):
        route("generation", "问题", caller="test", db_path=db, client=BlockClient())
    try:
        rows = read_transcripts(db)
    except sqlite3.OperationalError:
        rows = []
    assert len(rows) == 0


import threading
import time

import pytest
from openai import RateLimitError


def test_route_rate_limit_retry(tmp_path):
    """429 时 route() 应带 jitter 退避重试,最多 6 次,其他异常不吞。"""
    db = tmp_path / "t.db"
    calls = []

    class FlakyClient:
        model_name = "mock-model"

        def __init__(self, fail_times=2):
            self.fail_times = fail_times
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

        def _create(self, **kw):
            calls.append(time.time())
            if len(calls) <= self.fail_times:
                raise RateLimitError(
                    "429 concurrency reached",
                    response=SimpleNamespace(
                        status_code=429,
                        headers={},
                        request=SimpleNamespace(method="POST", url="http://test/v1/chat/completions"),
                    ),
                    body=None,
                )
            msg = SimpleNamespace(content="success", reasoning_content=None)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=msg)],
                usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
            )

    c = FlakyClient(fail_times=2)
    start = time.time()
    out = route("generation", "prompt", caller="test", db_path=db, client=c)
    elapsed = time.time() - start
    assert out == "success"
    assert len(calls) == 3
    # 两次失败后第三次成功:退避导致耗时至少 ~1s(首退避 1s 左右)
    assert elapsed >= 0.8


def test_route_other_errors_not_swallowed(tmp_path):
    """非 RateLimitError 异常应直接传播,不重试。"""
    db = tmp_path / "t.db"
    calls = []

    class BadClient:
        model_name = "mock-model"

        def __init__(self):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

        def _create(self, **kw):
            calls.append(kw)
            raise ValueError("real error")

    c = BadClient()
    with pytest.raises(ValueError, match="real error"):
        route("generation", "prompt", caller="test", db_path=db, client=c)
    assert len(calls) == 1


def test_route_concurrency_limited(tmp_path):
    """route() 全局并发应被 semaphore 钳制在 <=12。"""
    db = tmp_path / "t.db"
    call_times = []

    class SlowClient:
        model_name = "mock-model"

        def __init__(self):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

        def _create(self, **kw):
            call_times.append(time.time())
            time.sleep(0.2)
            msg = SimpleNamespace(content="ok", reasoning_content=None)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=msg)],
                usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
            )

    c = SlowClient()
    threads = [
        threading.Thread(target=lambda: route("generation", "p", caller="test", db_path=db, client=c))
        for _ in range(20)
    ]
    start = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.time() - start
    # 20 次调用,每次 0.2s,semaphore(12) 下至少需要两波: ceil(20/12)*0.2 = 0.4s
    assert elapsed >= 0.35
    # 验证 transcript 写了 20 条
    rows = read_transcripts(db)
    assert len(rows) == 20
