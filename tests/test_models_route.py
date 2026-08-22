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
