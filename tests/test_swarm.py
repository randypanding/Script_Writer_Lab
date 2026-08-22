"""L-SWARM · CNB 免费沙箱集群客户端。实现目标: src/lab/swarm.py
机制依据: docs/cnb-swarm-usage-guide.md(抢占/投递/轮询三拍;窗口=issue,空闲=最后评论来自 NPC)。
测试用内存 FakeCNB  mock _http 层,不打真实 API、不需要令牌。"""
import pytest

from lab import swarm


class FakeCNB:
    """内存版 CNB:窗口 1 无评论(空闲),窗口 2 最后为 NPC 回复(空闲),窗口 3 占用中。
    dispatch 追加人类指令后立即追加 NPC 回复(同步模拟异步)。"""

    def __init__(self, auto_reply: str | None = "A"):
        self.comments = {
            1: [],
            2: [{"author": {"is_npc": True}, "body": "旧回复"}],
            3: [{"author": {"is_npc": False}, "body": "占用中的指令"}],
        }
        self.posts: list[tuple[int, dict]] = []
        self.auto_reply = auto_reply

    def http(self, method, path, body=None, timeout=30):
        if "/comments" in path:
            n = int(path.split("/issues/")[1].split("/")[0])
            if method == "POST":
                self.posts.append((n, body))
                self.comments[n].append({"author": {"is_npc": False}, "body": body["body"]})
                if self.auto_reply is not None:
                    self.comments[n].append({"author": {"is_npc": True}, "body": self.auto_reply})
                return {}
            return self.comments[n]
        if "/issues" in path:
            return [{"number": k} for k in sorted(self.comments)]
        raise AssertionError(path)


@pytest.fixture
def fake(monkeypatch):
    f = FakeCNB()
    monkeypatch.setattr(swarm, "_http", f.http)
    monkeypatch.setattr(swarm.time, "sleep", lambda s: None)
    return f


def test_is_free_rules(fake):
    assert swarm.is_free(1) is True   # 无评论
    assert swarm.is_free(2) is True   # 最后是 NPC 回复
    assert swarm.is_free(3) is False  # 最后是人类指令 = 占用中


def test_find_free_window_skips_occupied(fake):
    n = swarm.find_free_window()
    assert n in (1, 2)
    assert n != 3


def test_dispatch_prefix_and_work_mode(fake):
    swarm.dispatch(1, "比较两段文本,只答 A 或 B", work_mode=True)
    n, body = fake.posts[-1]
    assert n == 1
    assert body["body"].startswith("@CodeBuddy")
    assert body["work_mode"] is True


def test_run_task_full_loop_and_window_recycles(fake):
    reply = swarm.run_task("评个分", timeout_s=10)
    assert reply == "A"
    used = fake.posts[-1][0]
    # 任务收尾后最后一条是 NPC 回复 → 窗口回到空闲,可被复用
    assert swarm.is_free(used) is True


def test_poll_timeout_raises(monkeypatch):
    f = FakeCNB(auto_reply=None)  # NPC 永不回复
    monkeypatch.setattr(swarm, "_http", f.http)
    monkeypatch.setattr(swarm.time, "sleep", lambda s: None)
    with pytest.raises(TimeoutError):
        swarm.run_task("不会回的任务", timeout_s=0.05)


def test_parse_vote():
    assert swarm.parse_vote("A") == "A"
    assert swarm.parse_vote("更好的是 B,因为…") == "B"
    assert swarm.parse_vote("无法判断") == ""
    # NPC 回复的 @提及 前缀含 A/B 字母("AGA"),不剥会永远误判 A
    assert swarm.parse_vote("@cnb.dQQ3yYJOAGA(潘鼎) B") == "B"
    assert swarm.parse_vote("@cnb.dQQ3yYJOAGA(潘鼎) 答案是 A") == "A"


def test_run_batch(fake):
    outs = swarm.run_batch(["任务一", "任务二", "任务三"], workers=2, timeout_s=10)
    assert outs == ["A", "A", "A"]
    assert len(fake.posts) == 3


def test_route_swarm_backend(monkeypatch, tmp_path):
    """lab.models.route 对 backend=cnb 的槽位走 swarm,并写 transcript。"""
    from lab import models

    monkeypatch.setattr(models, "_load_lab_toml", lambda: {
        "models": {"judge_dev_swarm": {"backend": "cnb", "model": "codebuddy-random"}},
        "paths": {"transcripts": str(tmp_path / "t.db")},
    })
    monkeypatch.setattr(swarm, "run_task", lambda *a, **k: "B")
    out = models.route("judge_dev_swarm", "投个票", caller="test")
    assert out == "B"
    rows = models.read_transcripts(tmp_path / "t.db")
    assert len(rows) == 1 and rows[0]["model"] == "codebuddy-random"
