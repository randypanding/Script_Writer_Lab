"""L-04 · AI 味词典(mock 数据,不依赖真实语料)。"""

import yaml

from lab.slop import build_lexicon, detect, load_brand_exclusions, write_outputs


def test_lexicon_meets_quota_with_pmi():
    # 语料侧每个短语跨 ≥2 部出现(df 约束),否则按专名滤除
    our = ["他的眼中闪过一丝不易察觉的复杂情绪,她说。", "命运的齿轮开始转动,他握紧了拳头。"] * 10
    drama = ["阿婆把茶叶摔在柜台上说这茶谁敢喝。小满说真的。",
             "小满说我只做头采茶叶。阿婆你先尝一口。",
             "阿婆愣住了,小满把茶叶递过去。"] * 10
    novel = ["山间的雾气漫过竹林,他想起多年前的事。", "船行千里,岸上的灯火渐次熄灭。"] * 20
    entries = build_lexicon(our, drama, novel, top=150)
    assert len(entries) >= 12  # 种子 + 差异信号
    seeds = [e for e in entries if e["source"] == "seed"]
    assert len(seeds) >= 10  # D05 内置种子全量在册
    with_pmi = [e for e in entries if e["pmi"] is not None]
    assert with_pmi, "差异信号必须产出带 PMI 的条目"
    # 专名防线:≤3 字专名不收(小满在语料不跨部出现 → 不应作为 our_vs_drama 条目)
    assert all(not (e["source"] == "our_vs_drama" and len(e["phrase"]) < 4) for e in entries)
    # 配额:种子守恒 + our 信号在场
    sources = {e["source"] for e in entries}
    assert sources >= {"seed", "our_vs_drama"}


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


def test_build_lexicon_applies_exclusions():
    # 小林在生成物高频、语料跨部出现(df=2)→ 本会作为 our_vs_drama 条目入围;排除集应剔除它
    our = ["小林把茶叶递到她面前,小林说。", "小林走进门店吧台,小林转身。"] * 6
    drama = ["小林在柜台前把茶叶递过去。", "小林说这茶谁敢喝。", "阿婆愣住了。"] * 6
    novel = ["山间的雾气漫过竹林,他想起多年前的事。", "船行千里,岸上的灯火渐次熄灭。"] * 20
    entries = build_lexicon(our, drama, novel, top=150, exclusions={"小林"})
    phrases = {e["phrase"] for e in entries}
    assert "小林" not in phrases, "排除集内的品牌专名必须从词典剔除"
    # 排除集机制是通用集合差,不影响非排除条目
    assert any(e["source"] == "our_vs_drama" for e in entries)


def test_slop_lexicon_free_of_known_brand_fp():
    # 回归守卫:落盘的品牌专名假阳性(T3 前置清洗对象)必须已清除
    from lab.models import ROOT
    data = yaml.safe_load((ROOT / "mined" / "slop_lexicon.yaml").read_text(encoding="utf-8"))
    phrases = {e["phrase"] for e in data.get("entries", [])}
    assert "小林" not in phrases, "小林系品牌角色专名假阳性,必须清洗"
    assert "门店吧台" not in phrases, "门店吧台系品牌场景专名假阳性,必须清洗"


def test_load_brand_exclusions():
    from lab.models import ROOT
    exclusions = load_brand_exclusions(ROOT / "mined" / "brand_proper_nouns.yaml")
    assert isinstance(exclusions, set)
    # 已知假阳性必须在排除表中(T3 前置)
    assert {"小林", "门店吧台"}.issubset(exclusions), "排除表必须收录已知的品牌专名假阳性"
