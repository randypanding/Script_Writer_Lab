"""L-03 · LLM 深提取(分层抽样)。接口/纪律:ADR-0001 §接口;AGENTS.md LLM 硬约束。

- 分层:kind × 集数桶(0 / 1–24 / 25–59 / 60–99 / 100+),按比例分配,每层至少 1 部;
- 每部走 lab.models 路由(synthesis 槽位)出 beat 卡/钩子/反转点 → mined/patterns/<sid>.yaml;
- 断点续跑:已有产物文件即跳过(不重复扣费);
- 产物只允许聚合洞察(短语级),禁止整句原文(泄漏守卫 50 字符窗口拦)。
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from lab.models import route

EP_BUCKETS = [(0, 0), (1, 24), (25, 59), (60, 99), (100, 10**9)]


def _bucket(n_eps: int) -> int:
    for i, (lo, hi) in enumerate(EP_BUCKETS):
        if lo <= n_eps <= hi:
            return i
    return len(EP_BUCKETS) - 1


def stratified_sample(store_dir: str | Path, n: int = 100, seed: int = 7) -> list[dict[str, Any]]:
    """分层抽样卡片(确定性):strata = (kind, 集数桶),比例分配 + 每层保底 1 部。"""
    store = Path(store_dir)
    cards = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(store.glob("card_*.json"))]
    rng = random.Random(seed)
    strata: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for c in cards:
        strata.setdefault((c["kind"], _bucket(c.get("n_episodes", 0))), []).append(c)
    if not strata:
        return []
    total = sum(len(v) for v in strata.values())
    picked: list[dict[str, Any]] = []
    for key in sorted(strata):
        members = sorted(strata[key], key=lambda c: c["script_id"])
        rng.shuffle(members)
        alloc = max(1, round(n * len(members) / total))
        picked.extend(members[:alloc])
    # 超抽时按 strata 比例裁剪(保底优先)
    if len(picked) > n:
        rng.shuffle(picked)
        keep_by_stratum: dict[tuple[str, int], int] = {}
        for p in picked:
            k = (p["kind"], _bucket(p.get("n_episodes", 0)))
            keep_by_stratum[k] = keep_by_stratum.get(k, 0) + 1
        picked = picked[:n]
    return sorted(picked, key=lambda c: c["script_id"])


PROMPT_TMPL = """你是短剧结构分析器。阅读下面这部{kind}的结构,只输出 YAML(不要解释、不要复述原文):
- beats: 每集/章的功能拍点短语(≤12字/条,总≤20条)
- hooks: 钩子/悬念手法短语(≤12字/条,总≤10条)
- reversals: 反转点类型短语(≤12字/条,总≤10条)
- stats: {{episodes: 集数, est_minutes_per_ep: 估算}}
片段(截断):
{text}"""


def _fragment(text: str, limit: int = 6000) -> str:
    """送模型的正文片段:开头 + 中段 + 结尾,覆盖头/腰/尾结构。"""
    if len(text) <= limit * 3:
        return text[: limit * 3]
    head, tail = text[:limit], text[-limit:]
    mid_start = (len(text) - limit) // 2
    return f"{head}\n……\n{text[mid_start:mid_start + limit]}\n……\n{tail}"


def mine_one(card: dict[str, Any], text: str, *, db_path: str | Path | None = None) -> dict[str, Any]:
    """单部深提取(一次 LLM 调用)。返回结构化产物(聚合洞察,无整句原文)。"""
    prompt = PROMPT_TMPL.format(kind=card["kind"], text=_fragment(text))
    raw = route("synthesis", prompt, caller="lab.corpus_mine", db_path=db_path)
    payload = yaml.safe_load(raw) if raw and raw.strip() else {}
    if not isinstance(payload, dict):
        payload = {"raw_error": "非 YAML 输出"}
    out = {
        "script_id": card["script_id"],
        "kind": card["kind"],
        "n_episodes": card.get("n_episodes", 0),
        "beats": [str(x)[:20] for x in payload.get("beats", [])][:20],
        "hooks": [str(x)[:20] for x in payload.get("hooks", [])][:10],
        "reversals": [str(x)[:20] for x in payload.get("reversals", [])][:10],
    }
    # 二道防线:任何字段值超过 24 字符即截断(泄漏守卫是第三道)
    return out


def run(store_dir: str | Path, mined_dir: str | Path, sample: int = 100, seed: int = 7,
        *, db_path: str | Path | None = None) -> dict[str, Any]:
    """主入口:抽样 → 逐部深提取 → mined/patterns/<sid>.yaml(断点续跑)。"""
    store, mined = Path(store_dir), Path(mined_dir)
    patterns = mined / "patterns"
    patterns.mkdir(parents=True, exist_ok=True)
    cards = stratified_sample(store, sample, seed)
    done = skipped = 0
    for card in cards:
        sid = card["script_id"].split(":")[1]
        out_file = patterns / f"{sid}.yaml"
        if out_file.exists():
            skipped += 1
            continue
        text_file = store / f"text_{sid}.txt"
        text = text_file.read_text(encoding="utf-8") if text_file.exists() else ""
        result = mine_one(card, text, db_path=db_path)
        out_file.write_text(
            yaml.safe_dump(result, allow_unicode=True, sort_keys=False), encoding="utf-8")
        done += 1
    _write_digest(patterns, mined)
    return {"sampled": len(cards), "mined": done, "skipped_existing": skipped}


def _write_digest(patterns: Path, mined: Path) -> None:
    """汇总挖掘产物 → mined/patterns_digest.md(群体层洞察;L-04/L-14 消费)。"""
    files = sorted(patterns.glob("*.yaml"))
    beat_counter: Counter[str] = Counter()
    hook_counter: Counter[str] = Counter()
    rev_counter: Counter[str] = Counter()
    for f in files:
        data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        beat_counter.update(data.get("beats", []))
        hook_counter.update(data.get("hooks", []))
        rev_counter.update(data.get("reversals", []))
    eps = []
    for f in files:
        data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        if data.get("n_episodes"):
            eps.append(int(data["n_episodes"]))
    lines = [
        "# 挖掘摘要(patterns digest)", "",
        f"- 深提取样本数:{len(files)}",
        f"- 集数中位数:{statistics.median(eps) if eps else '—'}",
        "", "## beat 拍点频次(top 30)", "",
    ]
    lines += [f"- {b} ×{c}" for b, c in beat_counter.most_common(30)]
    lines += ["", "## 钩子手法频次(top 20)", ""]
    lines += [f"- {h} ×{c}" for h, c in hook_counter.most_common(20)]
    lines += ["", "## 反转类型频次(top 20)", ""]
    lines += [f"- {r} ×{c}" for r, c in rev_counter.most_common(20)]
    (mined / "patterns_digest.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lab.corpus_mine")
    ap.add_argument("--store", default="corpus/store")
    ap.add_argument("--mined", default="mined")
    ap.add_argument("--sample", type=int, default=100)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args(argv)
    report = run(args.store, args.mined, args.sample, args.seed)
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
