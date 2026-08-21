"""L-06 补充 · 偏好对管线:批量构造/落盘/按 script_id 切分无泄漏。"""
import json
from pathlib import Path

from lab.pairs import assert_no_split_leakage, build_corpus_degraded, build_pair, write_jsonl

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
    pairs = build_corpus_degraded(store, severities=(1.0,))
    assert len(pairs) >= 3 * 5  # 3 部 × ≥5 个 deterministic 算子
    assert all(p["label"] == "a_win" for p in pairs)  # 标签由构造保证
    assert_no_split_leakage(pairs)  # 同 script_id 同 split


def test_write_jsonl_roundtrip(tmp_path):
    store = _make_store(tmp_path, 3)
    pairs = build_corpus_degraded(store, severities=(1.0,))
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
