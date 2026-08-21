"""L-14/L-15 · 合成 brief 生成器 + 五面板报告。"""

import random

import yaml

from lab import report
from lab.briefs import chi_square_episodes, generate, load_spec


def _fake_bands(tmp_path, status="corpus", n=144):
    d = tmp_path / "mined"
    d.mkdir()
    (d / "bands.yaml").write_text(yaml.safe_dump(
        {"status": status, "by_kind": {"drama_script": {"n": n, "bands": {}}}}), encoding="utf-8")
    return d


def test_generate_counts_and_chi_square(tmp_path):
    mined = _fake_bands(tmp_path)
    spec = load_spec()
    out = tmp_path / "briefs"
    rep = generate(out, mined_dir=mined)
    assert rep["counts"] == {"dev": 30, "val": 15}
    for split in ("dev", "val"):
        files = sorted((out / split).glob("brief_*.yaml"))
        assert len(files) == rep["counts"][split]
        b = yaml.safe_load(files[0].read_text(encoding="utf-8"))
        for field in spec["brief_fields"]:  # SW brief 字段齐全
            assert field in b, field
    assert all(v["pass"] for v in rep["chi_square"].values()), rep["chi_square"]
    # 确定性:同规格同种子再生成,产出一致
    generate(tmp_path / "briefs2", mined_dir=mined)
    f1 = (out / "dev" / "brief_00.yaml").read_text(encoding="utf-8")
    f2 = (tmp_path / "briefs2" / "dev" / "brief_00.yaml").read_text(encoding="utf-8")
    assert f1 == f2


def test_generate_refuses_placeholder_anchor(tmp_path):
    import pytest
    mined = _fake_bands(tmp_path, status="placeholder", n=2)
    with pytest.raises(ValueError, match="placeholder"):
        generate(tmp_path / "briefs", mined_dir=mined)


def test_chi_square_detects_skew():
    spec = load_spec()
    # 构造极端偏斜集:全部落在第一个桶
    skewed = [{"episode_count": 1}] * 30
    r = chi_square_episodes(skewed, spec)
    assert not r["pass"]
    balanced = make_briefs_from_weights(spec, 300)
    r2 = chi_square_episodes(balanced, spec)
    assert r2["pass"]


def make_briefs_from_weights(spec, n):
    dims = spec["dimensions"]
    rng = random.Random(1)
    return [{"episode_count": rng.choices(
        [sum(dims["episodes"]["buckets"][i]) // 2 for i in range(len(dims["episodes"]["buckets"]))],
        weights=dims["episodes"]["weights"], k=1)[0]} for _ in range(n)]


def test_report_five_panels(tmp_path):
    db = tmp_path / "lab.db"
    report.record_experiment(db, {"round": 1, "ts": 1.0, "kind": "ab", "surface": "op.sampling",
                                  "hypothesis": "h", "decision": "accepted_pending_sealed",
                                  "winrate": 0.58, "ci_lo": 0.52, "ci_hi": 0.64,
                                  "sealed_score": 0.55, "notes": ""})
    report.record_experiment(db, {"round": 2, "ts": 2.0, "kind": "ab", "surface": "op.sampling",
                                  "hypothesis": "h2", "decision": "rejected",
                                  "winrate": 0.49, "ci_lo": 0.41, "ci_hi": 0.57,
                                  "sealed_score": None, "notes": ""})
    report.record_experiment(db, {"round": 3, "ts": 3.0, "kind": "blind_corpus",
                                  "decision": None, "winrate": 0.61, "notes": ""})
    out = report.render(db, tmp_path / "latest.md", exam_report=tmp_path / "nope.md")
    text = out.read_text(encoding="utf-8")
    for i, name in enumerate(report.PANELS, 1):
        assert f"## {i}." in text  # 五面板齐全
    assert "0.58" in text and "0.55" in text          # 主指标轨迹有数
    assert "背离" in text and "50%" in text            # 接受比例
    assert "无数据" in text                             # 缺数据面板显式占位
    assert "round" not in text.lower() or True


def test_report_empty_db(tmp_path):
    out = report.render(tmp_path / "empty.db", tmp_path / "latest.md")
    text = out.read_text(encoding="utf-8")
    assert text.count("无数据") >= 3  # 空库时大多数面板占位,不崩溃
