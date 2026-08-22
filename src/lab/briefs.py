"""L-14 · 合成 brief 生成器。分布规格:spec/brief_distribution.yaml(contract 引用,优化器不可改)。

- 按 episodes 分桶权重 × 题材混合生成 dev 30 / val 15 briefs → out/briefs/{split}/;
- 卡方检验:生成集的集数分桶频数不得偏离规格(alpha=0.05,临界值表内置于规格);
- 分布锚是 drama_script 组(剧本≠小说),bands status=placeholder 时拒绝生成。
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any

import yaml

from lab.models import ROOT

SPEC_PATH = ROOT / "spec" / "brief_distribution.yaml"


def load_spec() -> dict[str, Any]:
    return yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))


def _assert_anchor_ok(mined_dir: str | Path | None = None) -> None:
    bands_path = Path(mined_dir) / "bands.yaml" if mined_dir else ROOT / "mined" / "bands.yaml"
    bands = yaml.safe_load(bands_path.read_text(encoding="utf-8"))
    drama = (bands.get("by_kind") or {}).get("drama_script") or {}
    if bands.get("status") != "corpus" or drama.get("n", 0) < 50:
        raise ValueError("bands.yaml 不是 corpus 级真实语料锚(placeholder/样本不足),拒绝生成 brief")


def make_brief(spec: dict[str, Any], split: str, idx: int, rng: random.Random) -> dict[str, Any]:
    dims = spec["dimensions"]
    w = dims["episodes"]["weights"]
    bucket = rng.choices(dims["episodes"]["buckets"], weights=w, k=1)[0]
    episodes = rng.randint(bucket[0], bucket[1])
    genre = rng.choices(list(dims["genre_mix"]), weights=list(dims["genre_mix"].values()), k=1)[0]
    anchor = rng.choice(dims["scene_anchors"])
    minutes = dims["ep_minutes"]["point"] + rng.uniform(-dims["ep_minutes"]["jitter"],
                                                        dims["ep_minutes"]["jitter"])
    lo, hi = dims["placement"]["brand_mentions_per_ep"]
    mentions = rng.randint(lo, hi)
    sp = dims["placement"]["selling_points"]
    return {
        "project_title": f"合成-{split}-{idx:02d}-{genre}",
        "profile": "short_drama_v1",
        "brand": "demo_tea",  # SW 既有 demo 品牌(合成 brief 必须指向存在的品牌)
        "raw_request": (
            f"我们想拍一个 {episodes} 集的{genre}竖屏短剧,每集约 {minutes:.1f} 分钟。"
            f"主要场景在{anchor}附近,演员控制在三个左右。"
            f"希望自然带出产品,每集提及不超过 {mentions} 次,覆盖 {sp} 个核心卖点。"
            "前几秒要抓人,不要硬广。"),
        "episode_count": episodes,
        "notes": [
            f"题材:{genre}",
            f"场景锚点:{anchor}",
            f"品牌提及每集 {mentions} 次,卖点 {sp} 个",
        ],
    }


def generate(out_dir: str | Path = "out/briefs", mined_dir: str | Path | None = None,
             spec: dict[str, Any] | None = None) -> dict[str, Any]:
    """dev 30 / val 15 briefs 落盘;返回各 split 数量与卡方检验结果。"""
    spec = spec or load_spec()
    _assert_anchor_ok(mined_dir)
    out = Path(out_dir)
    counts: dict[str, int] = {}
    chi2_results: dict[str, Any] = {}
    for split, n_total in spec["target_counts"].items():
        rng = random.Random(spec["seed"] + {"dev": 1, "val": 2}.get(split, 0))
        d = out / split
        d.mkdir(parents=True, exist_ok=True)
        briefs = [make_brief(spec, split, i, rng) for i in range(n_total)]
        for i, b in enumerate(briefs):
            (d / f"brief_{i:02d}.yaml").write_text(
                yaml.safe_dump(b, allow_unicode=True, sort_keys=False), encoding="utf-8")
        counts[split] = len(briefs)
        chi2_results[split] = chi_square_episodes(briefs, spec)
    return {"counts": counts, "chi_square": chi2_results}


def chi_square_episodes(briefs: list[dict[str, Any]], spec: dict[str, Any]) -> dict[str, Any]:
    """集数分桶频数 vs 规格期望的卡方检验(dof=桶数-1;临界值表在规格里)。"""
    dims = spec["dimensions"]
    buckets = dims["episodes"]["buckets"]
    weights = dims["episodes"]["weights"]
    n = len(briefs)
    observed = [0] * len(buckets)
    for b in briefs:
        for i, (lo, hi) in enumerate(buckets):
            if lo <= b["episode_count"] <= hi:
                observed[i] += 1
                break
    expected = [n * w for w in weights]
    stat = sum((o - e) ** 2 / e for o, e in zip(observed, expected) if e > 0)
    dof = len([e for e in expected if e > 0]) - 1
    crit = spec["chi_square"]["critical_values"].get(dof)
    return {"statistic": round(stat, 4), "dof": dof, "critical": crit,
            "observed": observed, "expected": [round(e, 2) for e in expected],
            "pass": crit is not None and stat <= crit}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lab.briefs")
    ap.add_argument("--out", default="out/briefs")
    ap.add_argument("--mined", default=None)
    args = ap.parse_args(argv)
    report = generate(args.out, args.mined)
    print(json.dumps(report, ensure_ascii=False))
    ok = all(v["pass"] for v in report["chi_square"].values())
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
