"""L-SWARM v2 · CNB 免费沙箱集群客户端。实现目标: src/lab/swarm.py
机制依据: docs/cnb-swarm-usage-guide.md + v2 纪律(并发闸/窗口退役/补开/打包投票)。
测试用内存 FakeCNB mock _http 层,不打真实 API、不需要令牌。"""
import pytest

from lab import swarm


class FakeCNB:
    """内存版 CNB:窗口 1 无评论(空闲),窗口 2 最后为 NPC 回复(空闲),
    窗口 3 占用中,窗口 4 评论 85 条(退役)。dispatch 同步追加 NPC 回复。"""

    def __init__(self, auto_reply: str | None = "A"):
        self.comments = {
            1: [],
            2: [{"author": {"is_npc": True}, "body": "旧回复"}],
            3: [{"author": {"is_npc": False}, "body": "占用中的指令"}],
            4: [{"author": {"is_npc": True}, "body": "x"} for _ in range(85)],
        }
        self.posts: list[tuple[int, dict]] = []
        self.created: list[dict] = []
        self.auto_reply = auto_reply
        self._next_number = 5

    def http(self, method, path, body=None, timeout=30):
        if path.startswith("/-/issues") and method == "POST" and "comments" not in path:
            n = self._next_number
            self._next_number += 1
            self.comments[n] = []
            self.created.append(body)
            return {"number": n}
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


def test_healthy_free_skips_locked_and_retired(fake):
    wins = swarm.healthy_free_windows()
    assert 1 in wins and 2 in wins
    assert 3 not in wins  # 锁死
    assert 4 not in wins  # 退役(评论 ≥80)
    assert wins[0] == 1   # 评论最少者优先


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
    assert swarm.is_free(used) is True  # 收尾后窗口回空闲


def test_ensure_pool_creates_windows(fake, monkeypatch):
    monkeypatch.setattr(swarm, "MIN_FREE_POOL", 6)  # 现有健康空闲 2 个 → 需补 4
    n = swarm.ensure_pool()
    assert n >= 6
    assert len(fake.created) >= 4


def test_poll_timeout_raises(monkeypatch):
    f = FakeCNB(auto_reply=None)
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


def test_pack_and_parse_roundtrip():
    ins = swarm.pack_vote_instruction("prose_craft", "文笔", [("甲文", "乙文")] * 3)
    assert "第1组" in ins and "第3组" in ins and "1:A" in ins  # 含格式要求
    votes = swarm.parse_packed_votes("@cnb.dQQ3yYJOAGA(潘鼎) 1:A 2:B 3:A", 3)
    assert votes == ["A", "B", "A"]
    # 编号缺失时退回字母序列
    assert swarm.parse_packed_votes("A B", 3) == ["A", "B", ""]
    # 缺组为 ''
    assert swarm.parse_packed_votes("1:B 3:A", 3) == ["B", "", "A"]


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
    monkeypatch.setattr(swarm, "healthy_free_windows", lambda *a, **k: [1])
    monkeypatch.setattr(swarm, "dispatch", lambda *a, **k: None)
    monkeypatch.setattr(swarm, "poll_reply", lambda *a, **k: "B")
    out = models.route("judge_dev_swarm", "投个票", caller="test")
    assert out == "B"
    rows = models.read_transcripts(tmp_path / "t.db")
    assert len(rows) == 1 and rows[0]["model"] == "codebuddy-random"
