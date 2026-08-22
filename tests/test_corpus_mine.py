"""L-03 · LLM 深提取(mock 路由,不调真实 API)。"""
import json
from pathlib import Path

import yaml

import lab.corpus_mine as cm

MINI = (Path(__file__).parent / "fixtures" / "corpus" / "mini_drama.txt").read_text(encoding="utf-8")


def _make_store(tmp_path: Path, n: int = 8) -> Path:
    from lab.corpus import parse_script, stats_card
    store = tmp_path / "store"
    store.mkdir()
    for i in range(n):
        stats = stats_card(parse_script(MINI))
        stats["n_episodes"] = [0, 5, 30, 80, 150][i % 5]  # 覆盖多个分层桶
        stats["kind"] = ["drama_script", "novel"][i % 2]
        sid = stats["script_id"].split(":")[1]
        (store / f"card_{sid}.json").write_text(json.dumps(stats, ensure_ascii=False), encoding="utf-8")
        (store / f"text_{sid}.txt").write_text(MINI, encoding="utf-8")
    return store


def test_stratified_sample_covers_strata(tmp_path):
    store = _make_store(tmp_path, 8)
    cards = cm.stratified_sample(store, n=4)
    strata = {(c["kind"], cm._bucket(c["n_episodes"])) for c in cards}
    assert len(cards) == 4
    assert len(strata) == 4  # 保底:每层至少 1 部
    again = cm.stratified_sample(store, n=4)
    assert [c["script_id"] for c in cards] == [c["script_id"] for c in again]  # 确定性


def test_mine_one_parses_yaml_and_truncates(tmp_path, monkeypatch):
    long_beat = "超长beat" * 10
    raw = yaml.safe_dump({"beats": [long_beat, "误会开局"], "hooks": ["结尾断崖"],
                          "reversals": ["身份反转"], "stats": {"episodes": 2}})
    monkeypatch.setattr(cm, "route",
                        lambda *a, **k: raw, raising=True)
    out = cm.mine_one({"script_id": "scr:x" * 8, "kind": "drama_script", "n_episodes": 2}, MINI)
    assert out["beats"][0] == long_beat[:20]  # 截断防线
    assert out["beats"][1] == "误会开局"


def test_run_resume_skips_existing(tmp_path, monkeypatch):
    store = _make_store(tmp_path, 4)
    calls = {"n": 0}

    def fake_route(slot, prompt, **kw):
        calls["n"] += 1
        return yaml.safe_dump({"beats": ["b"], "hooks": ["h"], "reversals": ["r"]})

    monkeypatch.setattr(cm, "route", fake_route, raising=True)
    r1 = cm.run(store, tmp_path / "mined", sample=4, db_path=tmp_path / "t.db")
    assert r1["mined"] == 4 and calls["n"] == 4
    r2 = cm.run(store, tmp_path / "mined", sample=4, db_path=tmp_path / "t.db")
    assert r2["skipped_existing"] == 4 and calls["n"] == 4  # 断点续跑不重复扣费
    assert (tmp_path / "mined" / "patterns_digest.md").exists()
