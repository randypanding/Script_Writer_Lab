"""L-05 · 退化算子库。实现目标: src/lab/degrade.py
契约: spec/degradation/operators.yaml(本文件在实现前必须为红)"""
from pathlib import Path

import pytest
import yaml

from lab.degrade import REGISTRY

SPEC = yaml.safe_load(
    (Path(__file__).parents[1] / "spec/degradation/operators.yaml").read_text(encoding="utf-8")
)
OP_IDS = [op["id"] for op in SPEC["operators"]]
KNOWN_AXES = {
    "naturalness", "hook_strength", "placement_integration", "transportation",
    "producibility", "prose_craft", "l0_structure", "l0_fact", "l0_brand", "l0_dialogue",
}
FIXTURE_TEXT = (Path(__file__).parent / "fixtures" / "corpus" / "mini_drama.txt").read_text(encoding="utf-8")


def test_registry_matches_spec_exactly():
    assert sorted(REGISTRY) == sorted(OP_IDS), "注册表必须与 operators.yaml 一一对应"


@pytest.mark.parametrize("op_id", OP_IDS)
def test_axis_is_known(op_id):
    assert REGISTRY[op_id].axis in KNOWN_AXES


@pytest.mark.parametrize("op_id", OP_IDS)
def test_deterministic_ops_reproducible(op_id):
    op = REGISTRY[op_id]
    if op.mechanism == "llm_mid":
        pytest.skip("llm_mid 算子走 --run-llm 冒烟")
    a = op.apply(FIXTURE_TEXT, severity=1, rng_seed=7)
    b = op.apply(FIXTURE_TEXT, severity=1, rng_seed=7)
    assert a == b, "同种子必须可复现"
    if op_id in ("D08_inject_contradiction", "D14_setup_cut"):
        # D08:无窗内可反驳事实时原样返回;D14:无【回收】标记时原样返回(降级删除=假缺陷,验真实证 0/682)。
        # 该 fixture 无 D08 事实、无 D14 标记。有靶向时的行为见 test_d08_excerpt.py / test_verify.py
        return
    assert a != FIXTURE_TEXT, "退化必须真的改变文本"


@pytest.mark.llm
@pytest.mark.parametrize("op_id", [op["id"] for op in SPEC["operators"] if op["mechanism"] == "llm_mid"])
def test_llm_ops_actually_degrade(op_id):
    out = REGISTRY[op_id].apply(FIXTURE_TEXT, severity=1, rng_seed=7)
    assert out != FIXTURE_TEXT
    assert len(out) > len(FIXTURE_TEXT) * 0.5, "改写不得把文本改没"
