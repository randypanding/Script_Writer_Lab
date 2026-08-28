"""craft_bench:craft 标注卡 → 加权达标率评分(分题材锚 v2,锚=522 卡实证频率)。

动机(round24):判官轴与 craft 基准正面冲突——判官可能在奖励平淡。
v2(ADR-0003 后续 W1):锚按题材分带(round25 实证:复仇系与治愈系工艺形状完全不同,
混题材锚对治愈系失真)。锚值表 mined/craft_anchors_v2.json。
用法: uv run python scripts/craft_bench.py out/annotate/<作品>.jsonl [--genre 治愈成长]
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

_ANCHORS_PATH = Path(__file__).resolve().parent.parent / "mined" / "craft_anchors_v2.json"

#: v1 混题材锚(315 卡),无 --genre 时的向后兼容默认
_V1_DIMS = (
    ("hook_attack", 0.75, 0.25),
    ("conflict_person", 0.83, 0.25),
    ("info_gap", 0.72, 0.20),
    ("cliffhanger_rd", 0.70, 0.15),
    ("scene_turn", 0.66, 0.15),
)


def _load_anchors() -> dict:
    return json.loads(_ANCHORS_PATH.read_text("utf-8"))


def detect_genre(text: str, anchors: dict | None = None) -> str:
    """按关键词把 brief/tone 文本映射到题材桶(证据不足落 default_anchor)。"""
    data = anchors or _load_anchors()
    best, best_hits = data.get("default_anchor", "都市日常"), 0
    for genre, keywords in data.get("genre_keywords", {}).items():
        hits = sum(1 for kw in keywords if kw in text)
        if hits > best_hits:
            best, best_hits = genre, hits
    return best


def score(cards: list[dict], genre: str | None = None) -> dict:
    n = len(cards)
    hk = Counter(str(c.get("hook_type", "")).lower() for c in cards)
    cf = Counter(str(c.get("conflict_type", "")).lower() for c in cards)
    ig = Counter(str(c.get("info_gap", "")).lower() for c in cards)
    ch = Counter(str(c.get("cliffhanger_rd", c.get("cliffhanger", ""))).lower() for c in cards)
    rates = {
        "hook_attack": sum(hk[k] for k in ("threat", "promise", "inversion")) / n,
        "conflict_person": cf["person"] / n,
        "info_gap": 1 - ig["none"] / n,
        "cliffhanger_rd": (ch["reveal"] + ch["danger"]) / n,
        "scene_turn": sum(1 for c in cards if str(c.get("scene_turn")).lower() == "true") / n,
    }
    if genre:  # v2 分题材锚
        data = _load_anchors()
        anchor = data["anchors"][genre]
        weights = data["weights"]
        per_dim = {k: min(1.0, rates[k] / anchor[k]) for k in weights}
        total = sum(per_dim[k] * weights[k] for k in weights)
        return {"craft_bench": round(total, 4), "genre": genre, "anchor_version": "v2",
                "provisional": bool(anchor.get("provisional")), "n": n,
                "rates": {k: round(v, 3) for k, v in rates.items()},
                "per_dim_attainment": {k: round(v, 3) for k, v in per_dim.items()}}
    per_dim = {k: min(1.0, rates[k] / a) for k, a, _w in _V1_DIMS}
    total = sum(per_dim[k] * w for k, _a, w in _V1_DIMS)
    return {"craft_bench": round(total, 4), "anchor_version": "v1", "n": n,
            "rates": {k: round(v, 3) for k, v in rates.items()},
            "per_dim_attainment": {k: round(v, 3) for k, v in per_dim.items()}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cards")
    ap.add_argument("--genre", default=None, help="题材桶(如 治愈成长);缺省=v1 混题材锚")
    args = ap.parse_args()
    cards = [json.loads(l) for l in Path(args.cards).read_text("utf-8").splitlines()]
    print(json.dumps(score(cards, args.genre), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
