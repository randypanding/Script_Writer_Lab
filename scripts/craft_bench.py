"""craft_bench:craft 标注卡 → 加权达标率评分(爆款频率为锚的客观戏剧工艺分)。

动机(round24):判官轴与 craft 基准正面冲突——placement/l0_dialogue 判官偏爱
"广告式顺滑"(v3),而爆款实证频率说 R3 最好。判官可能在奖励平淡。
craft_bench 把"离爆款工艺形状有多远"算成一个可复现的数,作为 promotion 的主攻轴
(三轴判官降为防崩地板)。维度/权重/锚值全部来自 315 卡实证(docs/craft_taxonomy_v1.md)。
用法: uv run python scripts/craft_bench.py out/annotate/<作品>.jsonl
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

#: (维度, 爆款锚值, 权重) —— 锚值=315 卡爆款频率(docs/craft_taxonomy_v1.md §0-5)
DIMS = (
    ("hook_attack", 0.75, 0.25),
    ("conflict_person", 0.83, 0.25),
    ("info_gap", 0.72, 0.20),
    ("cliffhanger_rd", 0.70, 0.15),
    ("scene_turn", 0.66, 0.15),
)


def score(cards: list[dict]) -> dict:
    n = len(cards)
    hk = Counter(str(c.get("hook_type", "")).lower() for c in cards)
    cf = Counter(str(c.get("conflict_type", "")).lower() for c in cards)
    ig = Counter(str(c.get("info_gap", "")).lower() for c in cards)
    ch = Counter(str(c.get("cliffhanger", "")).lower() for c in cards)
    rates = {
        "hook_attack": sum(hk[k] for k in ("threat", "promise", "inversion")) / n,
        "conflict_person": cf["person"] / n,
        "info_gap": 1 - ig["none"] / n,
        "cliffhanger_rd": (ch["reveal"] + ch["danger"]) / n,
        "scene_turn": sum(1 for c in cards if str(c.get("scene_turn")).lower() == "true") / n,
    }
    per_dim = {k: min(1.0, rates[k] / anchor) for k, anchor, _w in DIMS}
    total = sum(per_dim[k] * w for k, _a, w in DIMS)
    return {"craft_bench": round(total, 4), "n": n,
            "rates": {k: round(v, 3) for k, v in rates.items()},
            "per_dim_attainment": {k: round(v, 3) for k, v in per_dim.items()}}


def main() -> int:
    cards = [json.loads(l) for l in Path(sys.argv[1]).read_text("utf-8").splitlines()]
    print(json.dumps(score(cards), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
