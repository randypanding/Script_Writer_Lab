"""L-04 · AI 味词典(mock 数据,不依赖真实语料)。"""

import yaml

from lab.slop import build_lexicon, detect, write_outputs


def test_lexicon_meets_quota_with_pmi():
    our = ["他的眼中闪过一丝不易察觉的复杂情绪,她说。", "命运的齿轮开始转动,他握紧了拳头。"] * 10
    drama = ["阿婆把茶叶摔在柜台上说这茶谁敢喝。", "小满说我只做头采茶叶。"] * 20
    novel = ["山间的雾气漫过竹林,他想起多年前的事。", "船行千里,岸上的灯火渐次熄灭。"] * 20
    entries = build_lexicon(our, drama, novel, top=150)
    assert len(entries) >= 12  # 种子 + 差异信号
    seeds = [e for e in entries if e["source"] == "seed"]
    assert len(seeds) >= 10  # D05 内置种子全量在册
    with_pmi = [e for e in entries if e["pmi"] is not None]
    assert with_pmi, "差异信号必须产出带 PMI 的条目"
    # our_vs_drama:我们的模型腔短语 lift>0
    assert any(e["source"] == "our_vs_drama" and e["pmi"] > 0 for e in entries)


def test_lexicon_entries_short_and_clean():
    our = ["短词高频出现短词高频出现短词高频出现"] * 5
    entries = build_lexicon(our, ["无关对照文本" * 10], ["另一组无关文本" * 10])
    assert all(len(e["phrase"]) <= 20 for e in entries)  # 无 >50 字符原文,泄漏守卫可过


def test_write_outputs_and_detect(tmp_path):
    entries = build_lexicon(["他的眼中闪过一丝复杂情绪" * 3], ["对照" * 30], ["他组" * 30])
    write_outputs(entries, tmp_path)
    lex = yaml.safe_load((tmp_path / "slop_lexicon.yaml").read_text(encoding="utf-8"))
    assert lex["n_entries"] == len(lex["entries"])
    reg = yaml.safe_load((tmp_path / "metrics_registry" / "slop_density.yaml").read_text(encoding="utf-8"))
    for k in ("what", "detector", "cost", "anti_gaming", "delivery_pitch"):  # 五要素
        assert reg.get(k)
    d = detect("他的眼中闪过一丝不易察觉的复杂情绪。", tmp_path / "slop_lexicon.yaml")
    assert d > 0  # 命中至少一次
