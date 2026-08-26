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
    'tension(1-5 整数,5=非看不可), hook_type(见下定义),'
    ' cliffhanger(见下定义),'
    ' conflict_type(person/self/society/nature/fate/none),'
    ' stakes(一句话:失败会失去什么),'
    ' reversals([{"legal":true/false,"note":"铺垫依据或null"}]),'
    ' info_gap(见下定义),'
    ' scene_turn(true/false:本单元核心目标的结果是否发生反转),'
    ' summary(一句话剧情)'
)

TAXONOMY_DEFS = """类别定义(判定时严格遵守,有多个候选时取最先出现的):
- hook_type: threat=开篇即有具体危险或损失逼近; curiosity=抛出未解之谜或反常信息;
  promise=明示即将兑现的好处/爽点; inversion=既有预期被立即颠覆; none=无明显钩子。
- cliffhanger: question=以未回答的问题收束; danger=收束于逼近的危险;
  reveal=收束于新信息被揭露的瞬间; choice=收束于两难抉择; none=平收。取本单元最末一拍的状态。
- info_gap: reader_more=读者知道而关键角色不知道; reader_less=关键角色知道而读者不知道;
  characters_between=角色甲知道而角色乙不知道; none=无信息差。"""


def build_instruction(units: list[dict]) -> str:
    parts = [
        f"你是戏剧结构分析员。下面有 {len(units)} 个互不相关的短剧集/小说章。"
        "对每个单元做戏剧机制标注,只输出一个合法 JSON 数组,不要任何解释、问候、代码栅栏。",
        TAXONOMY_DEFS,
        f"数组长度必须={len(units)},每个元素字段:unit_id(照抄输入的 u1/u2 编号), {CARD_FIELDS}",
    ]
    for i, u in enumerate(units, 1):
        # chunk 内局部编号(实证:全长 unit_id 会被 NPC 缩写回显,按 id 映射全场错位零产出)
        parts.append(f"单元 u{i}（{u['title']}）:\n{u['text'][:6000]}")
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


def _majority(cards: list[dict | None]) -> dict | None:
    """k 次独立标注的多数票合成(实证:单次类别字段一致率仅 0.5-0.6,噪声必须投票消化):
    tension 取中位数;类别字段取众数(平票取先见);文本字段取自张力为中位的那张卡。"""
    valid = [c for c in cards if c]
    if not valid:
        return None
    tensions = sorted(int(c.get("tension", 0) or 0) for c in valid)
    med = tensions[len(tensions) // 2]
    out: dict = {"tension": med}
    for f in ("hook_type", "cliffhanger", "conflict_type", "info_gap", "scene_turn"):
        votes: dict[str, int] = {}
        for c in valid:
            v = str(c.get(f, "")).strip().lower()
            if v:
                votes[v] = votes.get(v, 0) + 1
        out[f] = max(votes, key=votes.get) if votes else ""
    anchor = next(c for c in valid if int(c.get("tension", 0) or 0) == med)
    for f in ("stakes", "reversals", "summary"):
        out[f] = anchor.get(f)
    return out


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
    replies = swarm.run_batch(instructions, workers=workers, timeout_s=600,
                              mention="@CodeBuddy")  # 生成类任务(实证:默认判官人格会回字母票)
    out: list[dict | None] = []
    for chunk, reply in zip(chunks, replies, strict=True):
        cards = parse_cards(reply, len(chunk)) if reply else None
        if cards is None:
            out.extend([None] * len(chunk))
        else:
            # 位置对齐 + 局部编号兜底(卡序通常随输入序;NPC 回显 u1/u2 时按号核对)
            by_local = {str(c.get("unit_id", "")).strip().lower(): c for c in cards}
            for i, u in enumerate(chunk, 1):
                card = by_local.get(f"u{i}") or (cards[i - 1] if i <= len(cards) else None)
                if card:
                    card = {**card, "unit_id": u["unit_id"], "title": u["title"]}
                out.append(card)
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

    if args.exam:  # 考的是"数据产品"(k=3 多数卡)的稳定性:两组独立 k=3 各合成一张,再比一致率
        runs_a = [annotate(units, args.workers) for _ in range(3)]
        runs_b = [annotate(units, args.workers) for _ in range(3)]
        maj_a = [_majority([r[i] for r in runs_a]) for i in range(len(units))]
        maj_b = [_majority([r[i] for r in runs_b]) for i in range(len(units))]
        pairs = [(x, y) for x, y in zip(maj_a, maj_b, strict=True) if x and y]
        rate = _agreement([p[0] for p in pairs], [p[1] for p in pairs])
        report = {"units": len(units), "valid_pairs": len(pairs), "agreement": round(rate, 4),
                  "engine": "k3_majority_vs_k3_majority",
                  "pass": rate >= 0.7 and len(pairs) >= len(units) * 0.7}
        Path("out/annotate").mkdir(parents=True, exist_ok=True)
        Path("out/annotate/exam.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
        print(f"[exam] 有效对 {len(pairs)}/{len(units)} 一致率 {rate:.2f} "
              f"{'PASS' if report['pass'] else 'FAIL'}", flush=True)
        return 0 if report["pass"] else 1

    runs = [annotate(units, args.workers) for _ in range(3)]  # k=3 多数票(考试验证的数据产品形态)
    cards = [_majority([r[i] for r in runs]) for i in range(len(units))]
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
