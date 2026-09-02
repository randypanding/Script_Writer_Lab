"""L-06 补充 · 偏好对管线:批量构造/落盘/按 script_id 切分无泄漏。"""
import json
from pathlib import Path

from lab.pairs import (
    assert_no_split_leakage,
    build_corpus_degraded,
    build_gen_degraded,
    build_pair,
    write_jsonl,
)

MINI = (Path(__file__).parent / "fixtures" / "corpus" / "mini_drama.txt").read_text(encoding="utf-8")


def _make_store(tmp_path: Path, n: int = 3) -> Path:
    from lab.corpus import parse_script, stats_card
    store = tmp_path / "store"
    store.mkdir()
    for i in range(n):
        card = parse_script(MINI)
        stats = stats_card(card)
        sid = stats["script_id"].split(":")[1]
        stats["script_id"] = f"scr:{sid[:-2]}{i:02d}"  # 造出不同的 script_id
        (store / f"card_{sid[:-2]}{i:02d}.json").write_text(json.dumps(stats, ensure_ascii=False), encoding="utf-8")
        (store / f"text_{sid[:-2]}{i:02d}.txt").write_text(MINI + f"\n第{i}集", encoding="utf-8")
    return store


def test_build_corpus_degraded_and_no_leak(tmp_path):
    store = _make_store(tmp_path, 3)
    pairs, _ = build_corpus_degraded(store, severities=(1.0,))
    assert len(pairs) >= 3 * 5  # 3 部 × ≥5 个 deterministic 算子
    assert all(p["label"] == "a_win" for p in pairs)  # 标签由构造保证
    assert_no_split_leakage(pairs)  # 同 script_id 同 split


def test_llm_mid_parallel_build(tmp_path, monkeypatch):
    """llm_mid 算子:并行执行 + llm_mid_scripts 限量生效。"""
    from collections import Counter
    from types import SimpleNamespace

    import lab.degrade as deg

    fake_det = SimpleNamespace(mechanism="deterministic", axis="prose_craft",
                               apply=lambda t, s, seed: t + " [DET]")
    fake_llm = SimpleNamespace(mechanism="llm_mid", axis="naturalness",
                               apply=lambda t, s, seed: t + " [LLM]")
    monkeypatch.setattr(deg, "REGISTRY", {"D99_det": fake_det, "D98_llm": fake_llm})
    store = _make_store(tmp_path, 2)
    pairs, _ = build_corpus_degraded(store, severities=(1.0,), llm_mid=True, llm_mid_scripts=10)
    kinds = Counter(p["construction"]["op_id"] for p in pairs)
    assert kinds["D99_det"] == 2 and kinds["D98_llm"] == 2
    limited, _ = build_corpus_degraded(store, severities=(1.0,), llm_mid=True, llm_mid_scripts=1)
    assert Counter(p["construction"]["op_id"] for p in limited)["D98_llm"] == 1


def test_llm_checkpoint_resume(tmp_path, monkeypatch):
    """断点续跑:已完成项零重复调用(实证:423 曾让 531 次改写成果全损)。"""
    from types import SimpleNamespace

    import lab.degrade as deg

    fake_llm = SimpleNamespace(mechanism="llm_mid", axis="naturalness",
                               apply=lambda t, s, seed: t + " [LLM]")
    monkeypatch.setattr(deg, "REGISTRY", {"D98_llm": fake_llm})
    store = _make_store(tmp_path, 2)
    ckpt = tmp_path / "partial.jsonl"
    p1, _ = build_corpus_degraded(store, severities=(1.0,), llm_mid=True,
                               llm_mid_scripts=10, checkpoint=ckpt)
    assert ckpt.exists() and len(p1) == 2
    calls = []
    monkeypatch.setattr(fake_llm, "apply",
                        lambda *a, **k: (calls.append(1), "x")[1])
    p2, _ = build_corpus_degraded(store, severities=(1.0,), llm_mid=True,
                               llm_mid_scripts=10, checkpoint=ckpt)
    assert calls == []          # 全部命中断点
    assert len(p2) == len(p1)   # 结果一致(断点载入 + 无重复)


def test_llm_job_timeout_skips_not_crashes(tmp_path, monkeypatch):
    """单个改写超时/死窗 → 跳过该对,不拖死整场(实证:run_task 超时曾崩掉整个 build)。"""
    from types import SimpleNamespace

    import lab.degrade as deg

    fake_llm = SimpleNamespace(mechanism="llm_mid", axis="naturalness",
                               apply=lambda *a, **k: (_ for _ in ()).throw(TimeoutError("死窗")))
    monkeypatch.setattr(deg, "REGISTRY", {"D98_llm": fake_llm})
    store = _make_store(tmp_path, 2)
    pairs, _ = build_corpus_degraded(store, severities=(1.0,), llm_mid=True, llm_mid_scripts=10)
    assert pairs == []  # 全部跳过,无崩溃


def test_write_jsonl_roundtrip(tmp_path):
    store = _make_store(tmp_path, 3)
    pairs, _ = build_corpus_degraded(store, severities=(1.0,))
    counts = write_jsonl(pairs, tmp_path / "out")
    assert sum(counts.values()) == len(pairs)
    for split, n in counts.items():
        lines = (tmp_path / "out" / f"{split}.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(lines) == n
        for ln in lines:
            assert json.loads(ln)["split"] == split


def test_pair_id_deterministic():
    a = build_pair("prose_craft", "甲", "乙", "a_win",
                   {"kind": "corpus_degraded", "op_id": "D05_inject_slop"}, "exam")
    b = build_pair("prose_craft", "甲", "乙", "a_win",
                   {"kind": "corpus_degraded", "op_id": "D05_inject_slop"}, "train")
    assert a["pair_id"] == b["pair_id"]  # 与 split 无关,内容寻址
    c = build_pair("prose_craft", "甲", "丙", "a_win",
                   {"kind": "corpus_degraded", "op_id": "D05_inject_slop"}, "exam")
    assert a["pair_id"] != c["pair_id"]


def test_gen_degraded_pairs(tmp_path):
    from lab.pairs import assert_no_split_leakage, build_gen_degraded
    gen = [("run-abc", MINI)]
    pairs, _ = build_gen_degraded(gen, severities=(1.0,))
    assert len(pairs) >= 5
    assert all(p["construction"]["kind"] == "gen_degraded" and
               p["construction"]["source_run_id"] == "run-abc" for p in pairs)
    assert all(p["label"] == "a_win" for p in pairs)
    assert_no_split_leakage(pairs)


def test_corpus_vs_gen_skips_in_band_and_labels_by_band_rule(tmp_path, monkeypatch):
    """带内生成物不构造;带外生成物按语料锚规则 a_win。"""
    import yaml as _yaml


    store = _make_store(tmp_path, 2)
    # 卡片标记为 drama_script(构造带内语料源)
    import json as _json
    for p in store.glob("card_*.json"):
        c = _json.loads(p.read_text(encoding="utf-8")); c["kind"] = "drama_script"
        p.write_text(_json.dumps(c, ensure_ascii=False), encoding="utf-8")
    mined = tmp_path / "mined"; mined.mkdir()
    (mined / "bands.yaml").write_text(_yaml.safe_dump(
        {"by_kind": {"drama_script": {"n": 50, "bands": {
            "dialogue_ratio": {"p25": 0.1, "p50": 0.2, "p75": 0.3},
            "sent_len_cv": {"p25": 0.5, "p50": 0.6, "p75": 0.7},
            "sent_len_mean": {"p25": 10, "p50": 15, "p75": 20}}}}}), encoding="utf-8")
    import lab.pairs as P
    bands_file = mined / "bands.yaml"
    pairs = P.build_corpus_vs_gen(store, [("run-x", MINI)], per_gen=2, bands_path=bands_file)
    # MINI 的 dialogue_ratio≈0.21 在 [0.1,0.3] 带内;但 sent_len_cv 可能带外 → 只检构造合法性
    for p in pairs:
        assert p["construction"]["kind"] == "corpus_vs_gen"
        assert p["label"] == "a_win" and p["construction"]["source_run_id"] == "run-x"
    # 全带内文本(构造一个假 bands 使所有指标带内覆盖)→ 0 对
    (mined / "bands.yaml").write_text(_yaml.safe_dump(
        {"by_kind": {"drama_script": {"n": 50, "bands": {
            "dialogue_ratio": {"p25": 0.0, "p50": 0.2, "p75": 1.0},
            "sent_len_cv": {"p25": 0.0, "p50": 0.6, "p75": 5.0},
            "sent_len_mean": {"p25": 0.0, "p50": 15, "p75": 999}}}}}), encoding="utf-8")
    pairs2 = P.build_corpus_vs_gen(store, [("run-x", MINI)], per_gen=2, bands_path=bands_file)
    assert pairs2 == []


def test_single_line_fragment_skips_empty_degraded(tmp_path, monkeypatch):
    """单行片段喂给会删成空白的算子 → 跳过不崩(实证:长段落小说触发的空产出)。"""
    import json as _json

    import lab.degrade as deg

    # 造一个 store:两行文本,首行 >=1200 字符,使 _narrative_excerpt 预算截断为单行片段
    store = tmp_path / "store"
    store.mkdir()
    sid = "scr:singleline01"
    long_line = "冷月如霜一、玉树琼枝作烟罗四更时分，如霜冻得醒来，外头飒飒的一片轻响，窗棂泛起白光，原来是下雪了。如霜脚上原本就生了冻疮，又痛又痒，忍不住轻轻的在被子里摩挲，这"
    text = long_line * 20 + "\n" + "第二行足够长以满足 narrative_excerpt 的 long_paras>=2 条件。" * 5
    assert len(text.splitlines()) == 2
    assert len(text.splitlines()[0]) >= 1200
    card = {"script_id": sid, "kind": "novel", "title": "单行测试"}
    (store / f"card_{sid.split(':')[1]}.json").write_text(
        _json.dumps(card, ensure_ascii=False), encoding="utf-8"
    )
    (store / f"text_{sid.split(':')[1]}.txt").write_text(text, encoding="utf-8")

    # 只保留会在单行上产空的算子 + 一个不会产空的 D05 作对照
    real_registry = deg.REGISTRY
    monkeypatch.setattr(deg, "REGISTRY", {
        k: v for k, v in real_registry.items()
        if k in {"D01_shuffle_beats", "D02_remove_hook", "D09_brand_cut", "D05_inject_slop"}
    })
    pairs, _ = build_corpus_degraded(store, severities=(1.0,))
    # D05 应正常产出;D01/D02/D09 的单行空产出应被跳过
    assert len(pairs) >= 1  # D05 × 1 severity
    assert all(p["construction"]["op_id"] == "D05_inject_slop" for p in pairs)


def test_build_gen_degraded_skips_empty(tmp_path, monkeypatch):
    """生成物单行片段 × 退化算子产空 → 跳过不崩。"""
    from types import SimpleNamespace

    import lab.degrade as deg

    single_line = "生成物单行文本。" * 200
    assert len(single_line.splitlines()) == 1
    fake_det = SimpleNamespace(mechanism="deterministic", axis="prose_craft",
                               apply=lambda t, s, seed: "")  # 故意返回空
    monkeypatch.setattr(deg, "REGISTRY", {"D99_empty": fake_det})
    pairs, _ = build_gen_degraded([("run-1", single_line)], severities=(1.0,))
    assert pairs == []
