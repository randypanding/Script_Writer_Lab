"""验真器(ADR-0002)与 D16 公文化算子的回归。"""
from lab.degrade import REGISTRY, verify_pair


def test_d16_strips_modal_particles():
    src = "小满:你尝一口嘛!\n阿婆:这茶好香啊。\n旁白没有语气词改动目标。"
    out = REGISTRY["D16_formalize_tone"].apply(src, severity=1, rng_seed=1)
    assert "嘛" not in out and "啊。" not in out
    assert verify_pair("D16_formalize_tone", src, out)


def test_d17_decolloquialize():
    src = "小满:你这是啥意思?\n阿婆:咱不管他咋想的。\n旁白行不含对白。"
    out = REGISTRY["D17_decolloquialize"].apply(src, severity=1, rng_seed=1)
    assert "什么" in out or "我们" in out or "怎么" in out
    assert out != src
    assert verify_pair("D17_decolloquialize", src, out)
    src2 = "小满:正常对白,没有口语标记。"
    assert REGISTRY["D17_decolloquialize"].apply(src2, severity=1, rng_seed=1) == src2


def test_verify_pair_semantics():
    # 通过:缺陷真的落地
    assert verify_pair("D12_info_stuffing", "短" * 100, "短" * 100 + "注水" * 40)
    # 不通过:缺陷未落地(长度没变)
    assert not verify_pair("D12_info_stuffing", "短" * 100, "短" * 100)
    # 无算子 / 无验真器 → 不进考场
    assert not verify_pair(None, "a", "b")
    assert not verify_pair("D06_voice_homogenize", "a", "b")
    assert not verify_pair("D11_pacing_flatten", "a", "b")


def test_every_verifiable_op_has_consistent_direction():
    """所有确定性算子:apply 后的产物必须通过自己的验真器(fixture 文本上)。"""
    from pathlib import Path
    src = (Path(__file__).parent / "fixtures" / "corpus" / "mini_drama.txt").read_text(encoding="utf-8")
    # D08 在无事实文本上原样返回(不验真),D14 需要标记对,单独豁免并另有专测
    exempt = {"D08_inject_contradiction", "D14_setup_cut", "D02_remove_hook", "D09_brand_cut"}
    for op_id, op in REGISTRY.items():
        if op.mechanism != "deterministic" or op_id in exempt:
            continue
        out = op.apply(src, 1, 7)
        if out.strip() == src.strip():
            continue  # 无靶向内容,诚实未变(splitlines/join 会丢文件尾换行,按 strip 比较)
        assert verify_pair(op_id, src, out), f"{op_id} 的产物未通过自身验真器"
