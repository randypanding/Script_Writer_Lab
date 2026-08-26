"""语料戏剧机制标注器(R1b):CNB swarm 批量标注,先考一致性再放量。

标注卡(每个 集/章 一张):张力分/钩子类型/悬念类型/冲突类型/赌注/反转合法性/
信息差/场景转折/一句话剧情。输出 out/annotate/<作品>.jsonl。
用法:
  一致性考试: uv run python scripts/annotate_corpus.py --exam --units 10 --workers 16
  正式标注:   uv run python scripts/annotate_corpus.py <文件路径> [--units 15] [--workers 16]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from lab import swarm  # noqa: E402

CARD_FIELDS = (
    'tension(1-5 整数,5=非看不可), hook_type(threat/curiosity/promise/inversion/none),'
    ' cliffhanger(question/danger/reveal/choice/none),'
    ' conflict_type(person/self/society/nature/fate/none),'
    ' stakes(一句话:失败会失去什么),'
    ' reversals([{"legal":true/false,"note":"铺垫依据或null"}]),'
    ' info_gap(reader_more/reader_less/characters_between/none),'
    ' scene_turn(true/false:本单元核心目标的结果是否发生反转),'
    ' summary(一句话剧情)'
)


def build_instruction(units: list[dict]) -> str:
    parts = [
        f"你是戏剧结构分析员。下面有 {len(units)} 个互不相关的短剧集/小说章。"
        "对每个单元做戏剧机制标注,只输出一个合法 JSON 数组,不要任何解释、问候、代码栅栏。",
        f"数组长度必须={len(units)},每个元素字段:unit_id, {CARD_FIELDS}",
    ]
    for u in units:
        parts.append(f"单元 {u['unit_id']}（{u['title']}）:\n{u['text'][:6000]}")
    return "\n\n".join(parts)


_JSON_RE = re.compile(r"\[.*\]", re.DOTALL)


def parse_cards(reply: str, n: int) -> list[dict] | None:
    body = swarm._MENTION_RE.sub("", reply.strip())
    m = _JSON_RE.search(body)
    if not m:
        return None
    try:
        cards = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(cards, list) or len(cards) != n:
        return None
    return [c for c in cards if isinstance(c, dict)]


def _load_units(path: str, max_units: int) -> list[dict]:
    out = subprocess.run(
        ["uv", "run", "python", "scripts/corpus_extract.py", path, "--max-units", str(max_units)],
        capture_output=True, text=True, cwd=Path(__file__).resolve().parent.parent,
    )
    return [json.loads(l) for l in out.stdout.splitlines() if l.strip()]


def _agreement(a: list[dict], b: list[dict]) -> float:
    """一致性:张力 |Δ|≤1 记 1 分;类别字段精确匹配;逐字段平均。"""
    cat_fields = ("hook_type", "cliffhanger", "conflict_type", "info_gap", "scene_turn")
    scores = []
    for ca, cb in zip(a, b, strict=True):
        try:
            scores.append(1.0 if abs(int(ca.get("tension", 0)) - int(cb.get("tension", 0))) <= 1 else 0.0)
        except (TypeError, ValueError):
            scores.append(0.0)
        scores += [1.0 if str(ca.get(f, "")).lower() == str(cb.get(f, "")).lower() else 0.0
                   for f in cat_fields]
    return sum(scores) / len(scores) if scores else 0.0


def annotate(units: list[dict], workers: int, pack: int = 2) -> list[dict | None]:
    chunks = [units[i:i + pack] for i in range(0, len(units), pack)]
    instructions = [build_instruction(c) for c in chunks]
    replies = swarm.run_batch(instructions, workers=workers, timeout_s=600)
    out: list[dict | None] = []
    for chunk, reply in zip(chunks, replies, strict=True):
        cards = parse_cards(reply, len(chunk)) if reply else None
        if cards is None:
            out.extend([None] * len(chunk))
        else:
            by_id = {str(c.get("unit_id")): c for c in cards}
            out.extend([by_id.get(u["unit_id"]) for u in chunk])
    return out


EXAM_WORK = "corpus/inbox/48.短剧脚本/竖屏短剧/爆款短剧剧本（完整本）/《云总你的小心肝重生了》1-100.docx"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?")
    ap.add_argument("--units", type=int, default=15)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--exam", action="store_true")
    args = ap.parse_args()
    path = args.path or EXAM_WORK
    units = _load_units(path, args.units)
    print(f"[annotate] {Path(path).stem}: {len(units)} 单元 @ {time.strftime('%H:%M:%S')}", flush=True)

    if args.exam:  # 同一批单元标注两次(独立任务流),测标注器一致性,≥0.7 才允许放量
        cards_a = annotate(units, args.workers)
        cards_b = annotate(units, args.workers)
        pairs = [(a, b) for a, b in zip(cards_a, cards_b, strict=True) if a and b]
        rate = _agreement([p[0] for p in pairs], [p[1] for p in pairs])
        report = {"units": len(units), "valid_pairs": len(pairs), "agreement": round(rate, 4),
                  "pass": rate >= 0.7 and len(pairs) >= len(units) * 0.7}
        Path("out/annotate").mkdir(parents=True, exist_ok=True)
        Path("out/annotate/exam.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
        print(f"[exam] 有效对 {len(pairs)}/{len(units)} 一致率 {rate:.2f} "
              f"{'PASS' if report['pass'] else 'FAIL'}", flush=True)
        return 0 if report["pass"] else 1

    cards = annotate(units, args.workers)
    ok = [c for c in cards if c]
    Path("out/annotate").mkdir(parents=True, exist_ok=True)
    out_path = Path(f"out/annotate/{Path(path).stem}.jsonl")
    with out_path.open("w", encoding="utf-8") as f:
        for c in ok:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"[annotate] 完成 {len(ok)}/{len(units)} 张卡 → {out_path} @ {time.strftime('%H:%M:%S')}",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
