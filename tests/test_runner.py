"""L-10/L-11/L-12 · 运行器:mock subprocess,不依赖真实 SW checkout。"""
import json
from pathlib import Path

import pytest

from lab.runner import ABReport, Artifact, ab, bootstrap_ci95, episode_text, ledger_usage, run, sealed_submit


def _fake_ir(out_dir: Path, text: str) -> None:
    sw = out_dir / "sw" / "剧名"
    sw.mkdir(parents=True, exist_ok=True)
    (sw / "ir.json").write_text(json.dumps(
        {"episodes": [{"scenes": [{"lines": [text]}]}]}, ensure_ascii=False), encoding="utf-8")


class FakeSpawn:
    """记录调用并伪造成功:对 `nsc run` 产出 ir.json。"""

    def __init__(self, texts: dict[str, str] | None = None):
        self.calls: list[dict] = []
        self.texts = texts or {}

    def __call__(self, cmd, **kw):
        self.calls.append({"cmd": cmd, "cwd": kw.get("cwd"), "env": kw.get("env")})
        if len(cmd) > 3 and cmd[3] == "run":  # uv run nsc run ...
            out_dir = Path(cmd[cmd.index("--out") + 1])
            marker = " ".join(cmd[cmd.index("--profile") + 1:])
            _fake_ir(out_dir.parent, self.texts.get(marker, f"文本[{marker}]"))
        from types import SimpleNamespace
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")


def test_run_invokes_pinned_sw_and_records_trace(tmp_path, monkeypatch):
    monkeypatch.chdir(Path(__file__).parents[1])
    spawn = FakeSpawn()
    art = run("examples/brief.yaml", {"profile": "pA", "no_cache": True, "check": False},
              seed=7, runner_root=tmp_path, _spawn=spawn, sw_dir=Path("D:/fake/sw"))
    c = spawn.calls[0]
    assert c["cwd"] == str(Path("D:/fake/sw"))
    assert c["cmd"][:3] == ["uv", "run", "nsc"]
    assert "--profile" in c["cmd"] and "pA" in c["cmd"]
    assert c["env"]["NSC_NO_CACHE"] == "1" and c["env"]["NSC_SEED"] == "7"
    meta = json.loads((Path(art.out_dir) / "meta.json").read_text(encoding="utf-8"))
    assert meta["run_id"] == art.run_id and art.returncode == 0
    assert (Path(art.out_dir) / "stdout.log").exists()


def test_run_no_cache_not_set_by_default(tmp_path, monkeypatch):
    monkeypatch.chdir(Path(__file__).parents[1])
    spawn = FakeSpawn()
    run("b.yaml", {"profile": "p"}, 0, runner_root=tmp_path, _spawn=spawn, sw_dir=Path("."))
    assert "NSC_NO_CACHE" not in spawn.calls[0]["env"]


def test_run_ids_isolated_per_seed(tmp_path, monkeypatch):
    monkeypatch.chdir(Path(__file__).parents[1])
    spawn = FakeSpawn()
    a = run("b.yaml", {"profile": "p", "check": False}, 1, runner_root=tmp_path,
            _spawn=spawn, sw_dir=Path("."))
    b = run("b.yaml", {"profile": "p", "check": False}, 2, runner_root=tmp_path,
            _spawn=spawn, sw_dir=Path("."))
    assert a.run_id != b.run_id and a.out_dir != b.out_dir  # 种子隔离


def test_episode_text_extraction(tmp_path):
    art = Artifact("r", "b", "p", 0, str(tmp_path), None, 0)
    assert episode_text(art) == ""
    _fake_ir(tmp_path, "台词一")
    art.ir_path = str(next(tmp_path.rglob("ir.json")))
    assert episode_text(art) == "台词一"


def test_ab_paired_seeds_and_ci(tmp_path, monkeypatch):
    monkeypatch.chdir(Path(__file__).parents[1])
    texts = {"cand p": "候选文本", "cham p": "冠军文本"}

    def spawn(cmd, **kw):
        " ".join(cmd[cmd.index("--profile") + 1:cmd.index("--profile") + 2])
        return FakeSpawn(texts)(cmd, **kw)

    def fake_run(brief, cfg, seed, **kw):
        marker = cfg["profile"]
        root = kw.get("runner_root") or tmp_path
        art_dir = Path(root) / f"fake-{marker}-{seed}"
        art_dir.mkdir(parents=True, exist_ok=True)
        _fake_ir(art_dir, texts.get(marker, "?"))
        return Artifact(f"{marker}-{seed}", str(brief), marker, seed, str(art_dir),
                        str(next(art_dir.rglob("ir.json"))), 0)

    # 判官:candidate 恒优 → winrate 1.0, CI 收窄
    rep = ab({"profile": "cand p"}, {"profile": "cham p"}, ["b.yaml"], [1, 2, 3],
             judge=lambda a, b: (0.2, 0.8), _run_fn=fake_run)
    assert isinstance(rep, ABReport) and rep.n_pairs == 3 and rep.wins == 3
    assert rep.winrate == 1.0
    assert rep.ci95[0] > 0.9  # 全胜时 CI 下界接近 1
    # 种子配对:每个 seed 都有一对 cham/cand
    seeds_seen = {p["seed"] for p in rep.per_pair}
    assert seeds_seen == {1, 2, 3}


def test_bootstrap_ci_covers_truth():
    scores = [1.0] * 7 + [0.0] * 3
    lo, hi = bootstrap_ci95(scores, n_boot=2000)
    assert 0.3 < lo <= 0.7 <= hi <= 1.0


def test_sealed_submit_quota_and_persistence(tmp_path):
    db = tmp_path / "ledger.db"
    for i in range(3):
        s = sealed_submit({"experiment_id": f"e{i}", "sha": f"s{i}"}, ledger=db,
                          score_fn=lambda c: 0.9)
        assert isinstance(s, float)
    assert ledger_usage(db) == {next(iter(ledger_usage(db))): 3}
    with pytest.raises(RuntimeError, match="配额"):
        # 配额上限从 contract 读;这里临时用小配额验证拒绝路径
        import lab.runner as R
        orig = R._quota
        R._quota = lambda: 3
        try:
            sealed_submit({"experiment_id": "over"}, ledger=db, score_fn=lambda c: 1.0)
        finally:
            R._quota = orig
    # 账本持久化:重开连接仍在
    assert sum(ledger_usage(db).values()) == 3
