"""L-17 · M2 冒烟实验。三组对照:assembler P2-P4 开/关、compress ratio 0.1/0.3、Thread 注入开/关。

流程(每组):overlay 应用 candidate → 与 pinned 副本各跑同 brief 同种子 → lab ab 出报告
→ dashboards/m2_smoke.md。判官闸门未 ON 时用注入的 mock 判官跑通管线(明示 status)。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from lab.models import ROOT
from lab.overlay import apply_overlay, cleanup, diff_report
from lab.runner import ab, run

CANDIDATES: list[dict[str, Any]] = [
    {
        "name": "m2_assembler_p234_on",
        "profile": "short_drama_v1",
        "profile_patch": {"context": {"assembler": {"p2": True, "p3": True, "p4": True}}},
    },
    {
        "name": "m2_compress_ratio_03",
        "profile": "short_drama_v1",
        "profile_patch": {"context": {"compress": {"ratio": 0.3, "keep_recent": 3}}},
    },
    {
        "name": "m2_thread_inject_on",
        "profile": "short_drama_v1",
        "profile_patch": {"context": {"thread_inject": True}},
    },
]


def smoke(briefs: list[str], seeds: list[int] = (1, 2), *,
          judge: Callable[[str, str], tuple[float, float]] | None = None,
          _run_fn: Callable = run, sw_dir: Path | None = None,
          out_md: str | Path | None = None) -> dict[str, Any]:
    """跑三组对照,返回报告结构并落 dashboards/m2_smoke.md。"""
    results: dict[str, Any] = {"groups": [], "judge": "mock" if judge else "dev(需 API key)"}
    for cand in CANDIDATES:
        wt = apply_overlay(cand, sw_dir=sw_dir)
        try:
            diff = diff_report(wt)
            rep = ab({"profile": cand["profile"], "sw_dir": str(wt)},
                     {"profile": cand["profile"]},
                     briefs, seeds, judge=judge, _run_fn=_run_fn)
            results["groups"].append({
                "candidate": cand["name"], "diff": diff,
                "winrate": rep.winrate, "ci95": list(rep.ci95),
                "wins": rep.wins, "losses": rep.losses, "ties": rep.ties,
                "n_pairs": rep.n_pairs,
            })
        finally:
            cleanup(wt, sw_dir=sw_dir)
    _render_md(results, out_md or ROOT / "dashboards" / "m2_smoke.md")
    return results


def _render_md(results: dict[str, Any], path: Path) -> None:
    lines = [
        "# M2 冒烟实验(m2_smoke)", "",
        f"- 判官:{results['judge']}",
        "- 结论:**M2 面是活的** —— 变更可应用(worktree)、可打分(lab ab)、可归因(diff)",
        "", "| 对照 | diff 摘要 | n | 胜率 | CI95 |", "|---|---|---|---|---|",
    ]
    for g in results["groups"]:
        diff_short = "; ".join(ln.strip() for ln in g["diff"].splitlines() if "|" in ln)[:80]
        lines.append(f"| {g['candidate']} | {diff_short} | {g['n_pairs']} | "
                     f"{g['winrate']} | {g['ci95']} |")
    lines += ["", "> L-17 验收产物;生成物,勿手改。真实判官分数需闸门 ON + API key。"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lab.m2_smoke")
    ap.add_argument("--briefs", nargs="+", required=True)
    ap.add_argument("--seeds", nargs="+", type=int, default=[1, 2])
    args = ap.parse_args(argv)
    rep = smoke(args.briefs, args.seeds)
    print(json.dumps(rep, ensure_ascii=False, default=str)[:2000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
