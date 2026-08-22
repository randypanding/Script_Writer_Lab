"""L-16 · M2 overlay 应用器:真实 git worktree(临时假 SW 仓)。"""
import json
import subprocess
from pathlib import Path

import yaml

from lab.overlay import apply_overlay, cleanup, diff_report


def _make_fake_sw(tmp_path: Path) -> Path:
    sw = tmp_path / "sw"
    (sw / "profiles").mkdir(parents=True)
    (sw / "config").mkdir()
    (sw / "prompts").mkdir()
    (sw / "profiles" / "short_drama_v1.yaml").write_text(
        "novel:\n  styles: [plain]\ncontext:\n  budget: 100\n", encoding="utf-8")
    (sw / "config" / "models.yaml").write_text("tier_w: {model: m1}\n", encoding="utf-8")
    (sw / "prompts" / "p3.json").write_text('{"instructions": "x"}', encoding="utf-8")
    for args in (["init", "-q"], ["add", "-A"], ["-c", "user.email=t@t", "-c", "user.name=t",
                                                "commit", "-qm", "init"]):
        subprocess.run(["git", *args], cwd=sw, capture_output=True, check=True)
    return sw


CAND = {
    "name": "m2_assembler_on",
    "profile": "short_drama_v1",
    "profile_patch": {"context": {"assembler": {"p2": True, "p3": True, "p4": True}}},
    "models_patch": {"tier_w": {"model": "m2"}},
    "prompts": {"p3.json": {"instructions": "y"}},
}


def test_overlay_applies_to_worktree_and_pinned_untouched(tmp_path):
    sw = _make_fake_sw(tmp_path)
    before = (sw / "profiles" / "short_drama_v1.yaml").read_text(encoding="utf-8")
    wt = apply_overlay(CAND, tmp_path / "wts", sw_dir=sw)
    assert wt.exists() and wt.is_dir()
    # 1) pinned 副本未污染
    assert (sw / "profiles" / "short_drama_v1.yaml").read_text(encoding="utf-8") == before
    # 2) overlay 副本变更生效且深合并保留未动键
    prof = yaml.safe_load((wt / "profiles" / "short_drama_v1.yaml").read_text(encoding="utf-8"))
    assert prof["context"]["assembler"]["p2"] is True   # 补丁进入
    assert prof["context"]["budget"] == 100             # 原键保留
    assert prof["novel"]["styles"] == ["plain"]
    models = yaml.safe_load((wt / "config" / "models.yaml").read_text(encoding="utf-8"))
    assert models["tier_w"]["model"] == "m2"
    assert json.loads((wt / "prompts" / "p3.json").read_text(encoding="utf-8"))["instructions"] == "y"
    meta = json.loads((wt / ".m2_overlay.json").read_text(encoding="utf-8"))
    assert set(meta["changed"]) == {"profiles/short_drama_v1.yaml", "config/models.yaml", "prompts/p3.json"}
    # 3) diff 可归因
    stat = diff_report(wt)
    assert "short_drama_v1.yaml" in stat
    cleanup(wt, sw_dir=sw)
    assert not wt.exists()


def test_overlay_rejects_m3_surface(tmp_path):
    import pytest
    sw = _make_fake_sw(tmp_path)
    with pytest.raises(ValueError, match="M3"):
        apply_overlay({**CAND, "name": "bad", "eval": {"thresholds": 0.9}}, tmp_path / "wts", sw_dir=sw)
    with pytest.raises(ValueError, match="未知字段"):
        apply_overlay({**CAND, "name": "bad", "unknown_key": 1}, tmp_path / "wts", sw_dir=sw)


def test_overlay_same_name_twice_rejected(tmp_path):
    import pytest
    sw = _make_fake_sw(tmp_path)
    apply_overlay(CAND, tmp_path / "wts", sw_dir=sw)
    with pytest.raises(FileExistsError):
        apply_overlay(CAND, tmp_path / "wts", sw_dir=sw)
