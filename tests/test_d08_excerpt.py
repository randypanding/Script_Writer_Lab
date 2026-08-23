"""D08 语义与语料片段选择的回归(判官考试首考失败的两个根因)。"""
import re

from lab.degrade import REGISTRY
from lab.pairs import _narrative_excerpt


def test_d08_contradiction_after_fact_line():
    src = "林舟今年32岁,是茶馆的老板。\n他在柜台后坐下。\n窗外的雨没有停。"
    out = REGISTRY["D08_inject_contradiction"].apply(src, severity=1, rng_seed=3)
    assert "32岁" in out
    lines = out.splitlines()
    fact_i = next(i for i, ln in enumerate(lines) if "32岁" in ln)
    contra_i = next(i for i, ln in enumerate(lines)
                    if ln != lines[fact_i] and re.search(r"岁|记错|并非|不在", ln))
    assert contra_i > fact_i, "矛盾句必须出现在被反驳事实之后(同窗可见)"
    ages = set(re.findall(r"(\d+)\s*岁", out))
    assert len(ages) >= 2
    # 裸矛盾:不得带自我洗白从句(实证:"瞒着说的"式矛盾被读成伏笔,判官不报)
    assert "瞒" not in out and "记错" not in out and "说辞" not in out


def test_d08_no_fact_returns_unchanged():
    src = "雨下了一夜。\n小满坐在柜台后面。\n门被推开了。"
    assert REGISTRY["D08_inject_contradiction"].apply(src, severity=1, rng_seed=1) == src


def test_llm_rewrite_length_guard(monkeypatch):
    """改写回复过短(人格污染/截断)→ 重试一次后原样返回,不造垃圾对(实证:判官人格回 3 字符)。"""
    import lab.models as m
    from lab.degrade import _llm_rewrite

    monkeypatch.setattr(m, "route", lambda *a, **k: "A")
    src = "原文" * 100
    assert _llm_rewrite("拍平节奏", src, 1.0, 7) == src
    monkeypatch.setattr(m, "route", lambda *a, **k: "改写后" + "文" * 200)
    assert _llm_rewrite("拍平节奏", src, 1.0, 7) != src


_META_HEAD = (
    "穿到之我的老婆是女皇 恬作品\n1、基本信息 ▲类型】 古装竖屏微短剧\n"
    "▲故事亮点】 穿越经营\n▲一句话梗概】 金融天才穿越\n人物表:林茵 封肆\n"
)


def test_excerpt_skips_metadata_head():
    text = _META_HEAD + "场景:酒吧·夜·内景\n林茵:你到底瞒了我什么?\n" + "灯光暗下来。" * 40
    frag = _narrative_excerpt(text)
    assert frag is not None
    assert frag.startswith("场景:酒吧")
    assert "类型" not in frag and "梗概" not in frag


def test_excerpt_prefers_scene_over_long_synopsis():
    """长梗概句不得抢锚点;窗口内的 ▲ 元数据行也要剔除。"""
    text = (_META_HEAD
            + "二十一世界经融天才意外车祸穿越架空古代世界,从新经营自己的经融帝国,成为古代首富。\n"
            + "▲一句话梗概】 同上\n场景:酒吧·夜·内景\n林茵:你到底瞒了我什么?\n" + "灯光暗下来。" * 40)
    frag = _narrative_excerpt(text)
    assert frag is not None
    assert frag.startswith("场景:酒吧")
    assert "梗概" not in frag and "▲" not in frag


def test_excerpt_novel_format_chapter_anchor():
    """小说文体:书名/作者/简介头 + 第N章锚点 + 引号对白。"""
    text = ("《宋成祖》作者:青史尽成灰\n文案:\n宋太祖起介胄之中,践九五之位。\n\n"
            "第1章 靖康天子\n" + "　　开封,皇宫,夜半。一位年老的宦官仓皇冲入,脚步急促,神情慌张。\n"
            "　　“官家,出事了。”他喊道。\n" + "　　烛火摇晃。" * 30)
    frag = _narrative_excerpt(text)
    assert frag is not None
    assert frag.startswith("第1章")
    assert "文案" not in frag and "作者" not in frag


def test_excerpt_pure_metadata_returns_none():
    assert _narrative_excerpt("▲类型】 古装\n▲梗概】 穿越\n人物表:甲 乙") is None
