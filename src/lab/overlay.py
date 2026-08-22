"""L-16 · M2 变更面应用器。把 candidate 的 profile/config/prompts 变更映射到 SW 的
**git worktree 临时副本**(不污染 pinned checkout),供 lab.runner 指向该副本运行。

candidate 形状(spec/operators/surface.yaml M2 项的可执行投影):
    {
      "name": "m2_assembler_on",
      "profile": "short_drama_v1",          # 目标 profile 名
      "profile_patch": {context: {...}},    # 合并进 profiles/<name>.yaml 的 dict 补丁
      "models_patch": {tier_x: {...}},      # 合并进 config/models.yaml
      "prompts": {"p3.json": {...}},        # 整文件写入 prompts/
    }
只允许 M1/M2 面字段;评测器/规则/阈值类字段在 _FORBIDDEN_KEYS 里硬拒。
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

from lab.runner import sw_checkout

_FORBIDDEN_KEYS = {"checks", "eval", "thresholds", "rubric", "promotion", "brief_distribution"}
_ALLOWED_TOP = {"name", "profile", "profile_patch", "models_patch", "prompts"}


def _validate(candidate: dict[str, Any]) -> None:
    if _FORBIDDEN_KEYS & set(candidate):
        raise ValueError(f"candidate 触碰 M3 禁区:{_FORBIDDEN_KEYS & set(candidate)}")
    extra = set(candidate) - _ALLOWED_TOP
    if extra:
        raise ValueError(f"candidate 含未知字段:{extra}")
    if not candidate.get("name"):
        raise ValueError("candidate 需要 name")
    for fname in (candidate.get("prompts") or {}):
        if "/" in fname or ".." in fname:
            raise ValueError(f"prompts 文件名不合法:{fname}")


def _git(sw: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(sw), *args], capture_output=True, text=True,
                        encoding="utf-8", check=False)
    if r.returncode != 0:
        raise RuntimeError(f"git {args} 失败:{r.stderr[:300]}")
    return r.stdout


def _deep_merge(base: dict, patch: dict) -> dict:
    out = dict(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def apply_overlay(candidate: dict[str, Any], worktree_root: str | Path | None = None,
                  sw_dir: Path | None = None) -> Path:
    """创建 SW 的 git worktree 副本并应用变更;返回副本路径(调用方用完调 cleanup)。"""
    _validate(candidate)
    sw = sw_dir or sw_checkout()
    root = Path(worktree_root) if worktree_root else Path(tempfile.mkdtemp(prefix="m2_wt_"))
    root.mkdir(parents=True, exist_ok=True)
    wt = root / candidate["name"]
    if wt.exists():
        raise FileExistsError(f"worktree 已存在:{wt}(先 cleanup)")
    _git(sw, "worktree", "add", "--detach", str(wt), "HEAD")

    changed: list[str] = []

    if candidate.get("profile_patch"):
        profile = candidate.get("profile") or "short_drama_v1"
        pf = wt / "profiles" / f"{profile}.yaml"
        base = yaml.safe_load(pf.read_text(encoding="utf-8")) if pf.exists() else {}
        pf.parent.mkdir(parents=True, exist_ok=True)
        pf.write_text(yaml.safe_dump(_deep_merge(base, candidate["profile_patch"]),
                                     allow_unicode=True, sort_keys=False), encoding="utf-8")
        changed.append(f"profiles/{profile}.yaml")

    if candidate.get("models_patch"):
        mf = wt / "config" / "models.yaml"
        base = yaml.safe_load(mf.read_text(encoding="utf-8")) if mf.exists() else {}
        mf.parent.mkdir(parents=True, exist_ok=True)
        mf.write_text(yaml.safe_dump(_deep_merge(base, candidate["models_patch"]),
                                     allow_unicode=True, sort_keys=False), encoding="utf-8")
        changed.append("config/models.yaml")

    for fname, content in (candidate.get("prompts") or {}).items():
        pf = wt / "prompts" / fname
        pf.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(content, ensure_ascii=False, indent=1) if isinstance(content, dict) else str(content)
        pf.write_text(text, encoding="utf-8")
        changed.append(f"prompts/{fname}")

    (wt / ".m2_overlay.json").write_text(
        json.dumps({"name": candidate["name"], "changed": changed}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    return wt


def cleanup(wt: str | Path, sw_dir: Path | None = None) -> None:
    """worktree 用完即清理(丢弃未提交变更,不留悬挂元数据)。"""
    sw = sw_dir or sw_checkout()
    wt = Path(wt)
    if wt.exists():
        try:
            _git(sw, "worktree", "remove", "--force", str(wt))
        except RuntimeError:
            shutil.rmtree(wt, ignore_errors=True)
            _git(sw, "worktree", "prune")


def diff_report(wt: str | Path) -> str:
    """副本 vs pinned HEAD 的 diff 摘要(变更可归因的依据,L-17 冒烟消费)。"""
    return _git(Path(wt), "diff", "--stat", "HEAD")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lab.overlay")
    ap.add_argument("candidate_json")
    ap.add_argument("--root", default=None)
    args = ap.parse_args(argv)
    candidate = json.loads(Path(args.candidate_json).read_text(encoding="utf-8"))
    wt = apply_overlay(candidate, args.root)
    print(json.dumps({"worktree": str(wt), "diff": diff_report(wt)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
