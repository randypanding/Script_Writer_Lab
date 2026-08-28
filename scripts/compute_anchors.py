"""分题材锚计算(W1.3,可复现):标注卡 + genre_map → mined/craft_anchors_v2.json。

口径(2026-08-28 round27 固化,取代此前内联手算):
- 分桶:标注文件 stem ↔ genre_map 键的文件名 stem;卡全量合并(池化)后计频。
- 五维:hook_attack=(threat+promise+inversion)/n;conflict_person=person/n;
  info_gap=1-none/n;cliffhanger_rd=(reveal+danger)/n;scene_turn=true/n。
- 张力曲线:池化卡序等分三段(1/3,1/3,余量)的张力均值,记 [前,中,后]。
- provisional:n_works<3(薄料锚,只作方向参考)。
用法: uv run python scripts/compute_anchors.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ANCHORS_PATH = ROOT / "mined" / "craft_anchors_v2.json"
GENRE_MAP_PATH = ROOT / "mined" / "genre_map.json"

WEIGHTS = {"hook_attack": 0.25, "conflict_person": 0.25, "info_gap": 0.20,
           "cliffhanger_rd": 0.15, "scene_turn": 0.15}
DEFAULT_ANCHOR = "都市日常"
PROVISIONAL_WORKS = 3
#: "其他"=信息不足兜底桶(genre_classify.GENRES), heterogeneous,不作锚(v2.0 冻结口径即 7 桶)
NON_ANCHOR_BUCKETS = {"其他"}

#: 与 genre_classify.GENRE_DEFS 同源的桶→关键词(Lab craft_bench.detect_genre 消费)
GENRE_KEYWORDS = {
    "治愈成长": ["治愈", "松弛", "温暖", "陪伴", "自在"],
    "复仇爽文": ["复仇", "打脸", "逆袭", "翻身", "虐渣"],
    "甜宠言情": ["甜宠", "恋爱", "霸总", "娇妻", "心动"],
    "都市日常": ["都市", "职场", "日常", "家庭"],
    "悬疑探秘": ["悬疑", "谜团", "真相", "案件"],
    "玄幻仙侠": ["修仙", "玄幻", "仙侠", "异能"],
    "历史穿越": ["穿越", "重生", "古代", "朝代"],
}


def bucket_dims(cards: list[dict]) -> dict | None:
    n = len(cards)
    if n == 0:
        return None
    hk = Counter(str(c.get("hook_type", "")).lower() for c in cards)
    cf = Counter(str(c.get("conflict_type", "")).lower() for c in cards)
    ig = Counter(str(c.get("info_gap", "")).lower() for c in cards)
    ch = Counter(str(c.get("cliffhanger_rd", c.get("cliffhanger", ""))).lower() for c in cards)
    t = [int(c.get("tension", 0) or 0) for c in cards]
    k = max(1, n // 3)
    seg = t[:k], t[k:2 * k], t[2 * k:]
    return {
        "hook_attack": round(sum(hk[x] for x in ("threat", "promise", "inversion")) / n, 2),
        "conflict_person": round(cf["person"] / n, 2),
        "info_gap": round(1 - ig["none"] / n, 2),
        "cliffhanger_rd": round((ch["reveal"] + ch["danger"]) / n, 2),
        "scene_turn": round(sum(1 for c in cards if str(c.get("scene_turn")).lower() == "true") / n, 2),
        "tension_curve": [round(sum(s) / len(s), 2) for s in seg],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    gm = json.loads(GENRE_MAP_PATH.read_text(encoding="utf-8"))
    stem2genre = {Path(p).stem: g for p, g in gm.items()}
    buckets: dict[str, list[dict]] = {}
    works_of: dict[str, set[str]] = {}
    for f in sorted((ROOT / "out" / "annotate").glob("*.jsonl")):
        g = stem2genre.get(f.stem)
        if not g:
            continue
        cards = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines()]
        if cards:
            buckets.setdefault(g, []).extend(cards)
            works_of.setdefault(g, set()).add(f.stem)

    anchors = {}
    for g in sorted(buckets):
        if g in NON_ANCHOR_BUCKETS:
            continue
        d = bucket_dims(buckets[g])
        if d is None:
            continue
        d["n_works"] = len(works_of[g])
        d["n_cards"] = len(buckets[g])
        if d["n_works"] < PROVISIONAL_WORKS:
            d["provisional"] = True
        anchors[g] = d

    out = {
        "version": "2.1",
        "date": "2026-08-28",
        "source": f"{sum(d['n_cards'] for d in anchors.values())} 卡"
                  f"({sum(d['n_works'] for d in anchors.values())} 部,"
                  "annotate k=3 多数票,标注器一致率 0.73);聚合口径见 scripts/compute_anchors.py",
        "note": "round27:金榜题名之寒门状元经分类器 k=2 复核由治愈成长改判复仇爽文"
                "(双标一致;其六维形状亦离治愈桶最远),复仇桶随之重算;"
                "治愈成长桶语料内仅 1 部,补料需 owner 投放治愈系语料至 corpus/inbox;"
                "张力曲线自本轮起按池化等分三段口径复算(五维与 v2.0 一致,曲线有 ≤0.15 手算偏差)",
        "weights": WEIGHTS,
        "anchors": anchors,
        "genre_keywords": GENRE_KEYWORDS,
        "default_anchor": DEFAULT_ANCHOR,
    }
    if args.dry_run:
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0
    ANCHORS_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[anchors] {len(anchors)} 桶 → {ANCHORS_PATH}")
    for g, d in sorted(anchors.items()):
        print(f"  {g}: {d['n_works']} 部 {d['n_cards']} 卡 "
              f"{'(provisional)' if d.get('provisional') else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
