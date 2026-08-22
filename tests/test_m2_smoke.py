"""L-17 · M2 冒烟:假 SW 仓 + 注入 run/judge,验证三组对照管线活。"""
import json
import subprocess
from pathlib import Path

from lab.m2_smoke import CANDIDATES, smoke


def _make_fake_sw(tmp_path: Path) -> Path:
    sw = tmp_path / "sw"
    (sw / "profiles").mkdir(parents=True)
    (sw / "config").mkdir()
    (sw / "prompts").mkdir()
    (sw / "profiles" / "short_drama_v1.yaml").write_text("context:\n  budget: 100\n", encoding="utf-8")
    for args in (["init", "-q"], ["add", "-A"],
                 ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"]):
        subprocess.run(["git", *args], cwd=sw, capture_output=True, check=True)
    return sw


def test_smoke_three_groups(tmp_path):
    sw = _make_fake_sw(tmp_path)

    def fake_run(brief, cfg, seed, **kw):
        from lab.runner import Artifact
        d = tmp_path / f"run-{cfg.get('env', {}).get('tag', 'pinned')}-{seed}"
        d.mkdir(parents=True, exist_ok=True)
        return Artifact(f"{d.name}", str(brief), "p", seed, str(d), None, 0)

    def fake_art(artifact):
        # 无 ir 产物 → episode_text 为空 → ab 记 invalid。给 fake_run 塞 ir 更实际:
        return artifact

    # 让 ab 有可比文本:给每个 run 目录补 ir.json(内容按目录名区分)
    orig_run = fake_run

    seen_sw_dirs = []

    def fake_run_with_ir(brief, cfg, seed, **kw):
        art = orig_run(brief, cfg, seed, **kw)
        seen_sw_dirs.append(cfg.get("sw_dir"))
        cand = cfg.get("sw_dir") is not None  # candidate 带 worktree 路径
        d = Path(art.out_dir) / "sw" / "剧"
        d.mkdir(parents=True, exist_ok=True)
        (d / "ir.json").write_text(json.dumps(
            {"episodes": [{"scenes": [{"lines": ["候选台词" if cand else "冠军台词"]}]}]},
            ensure_ascii=False), encoding="utf-8")
        art.ir_path = str(d / "ir.json")
        return art

    rep = smoke(["b.yaml"], seeds=[1], judge=lambda a, b: (0.4, 0.6),  # candidate 恒胜
                _run_fn=fake_run_with_ir, sw_dir=sw, out_md=tmp_path / "m2_smoke.md")
    assert len(rep["groups"]) == 3 == len(CANDIDATES)
    # candidate 侧跑在 overlay worktree(champion 侧 None=pinned)
    assert any(d and "m2_" in str(d) for d in seen_sw_dirs)
    assert any(d is None for d in seen_sw_dirs)
    assert all(g["n_pairs"] == 1 for g in rep["groups"])
    md = (tmp_path / "m2_smoke.md").read_text(encoding="utf-8")
    assert "m2_assembler_p234_on" in md and "M2 面是活的" in md
    # worktree 用完即清理
    assert not list((tmp_path).glob("m2_wt_*"))


def test_candidates_touch_only_m2_surface():
    from lab.overlay import _validate
    for c in CANDIDATES:
        _validate(c)  # 不抛 = 全部在 M2 面内
