"""产物三轴判分(champion 基线刻印用):产物文本 vs 同轴语料锚,双向 k=5 打包投票。

判分面 = 考试验证过的三轴(transportation/placement_integration/l0_dialogue)。
语料侧文本取自 out/pairs/exam.jsonl 同轴对的 a_text(语料锚);
产物侧按轴取切片:transportation→小说段落,l0_dialogue→剧本场对白,
placement_integration→含品牌名的剧本场。
用法: uv run python scripts/judge_artifact.py out/<标题> <tag> [--pairs 20] [--k 5]
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from lab import swarm
from lab.judgekit import _axis_hint, load_criteria

AXES = ("transportation", "placement_integration", "l0_dialogue")
BRAND_RE = re.compile(r"清野|轻乳茶")  # 默认 demo_tea;其他品牌用 --brand-re 覆盖


def _novel_excerpts(novel_md: str, n: int, rng: random.Random, chars: int = 700) -> list[str]:
    paras = [p.strip() for p in novel_md.split("\n") if p.strip() and not p.startswith("#")]
    out, cur = [], ""
    for p in paras:
        cur += p + "\n"
        if len(cur) >= chars:
            out.append(cur.strip())
            cur = ""
    if len(cur) >= chars // 2:
        out.append(cur.strip())
    rng.shuffle(out)
    return out[:n]


def _script_scenes(script_md: str, brand_only: bool) -> list[str]:
    blocks = re.split(r"\n(?=### 场 )", script_md)
    scenes = [b.strip() for b in blocks if b.startswith("### 场")]
    if brand_only:
        scenes = [s for s in scenes if BRAND_RE.search(s)]
    return scenes


def _dialogue_excerpts(script_md: str, n: int, rng: random.Random, chars: int = 700) -> list[str]:
    scenes = _script_scenes(script_md, brand_only=False)
    out = []
    for s in scenes:
        lines = [ln for ln in s.split("\n") if "：" in ln and not ln.startswith(("#", "[", "△"))]
        text = "\n".join(lines).strip()
        if len(text) >= chars // 3:
            out.append(text[:chars])
    rng.shuffle(out)
    return out[:n]


def _brand_excerpts(script_md: str, n: int, rng: random.Random, chars: int = 900) -> list[str]:
    scenes = _script_scenes(script_md, brand_only=True)
    out = [s[:chars] for s in scenes]
    rng.shuffle(out)
    return out[:n]


def _corpus_pool(axis: str, pairs_path: Path, min_len: int = 300) -> list[str]:
    """语料锚池：同轴 a_text 优先;不足时用其他轴的 a_text 补足
    (exam 各轴 a_text 全是原生剧本语料,轴归属只是构造时的退化目标)。"""
    same, other, seen = [], [], set()
    for line in pairs_path.open(encoding="utf-8"):
        r = json.loads(line)
        t = r["a_text"]
        if t in seen or len(t) < min_len:
            continue
        seen.add(t)
        (same if r["axis"] == axis else other).append(t)
    return same + other


def judge_axis(axis: str, product: list[str], corpus: list[str], n: int, k: int,
               workers: int) -> dict:
    pairs = list(zip(product[:n], corpus[:n], strict=True))
    items: list[tuple[int, int, str, str]] = []
    for i, (prod, corp) in enumerate(pairs):
        for d in (0, 1):
            a, b = (corp, prod) if d == 0 else (prod, corp)  # 方向0: A=语料 B=产物
            for _ in range(k):
                items.append((i, d, a, b))
    chunks = [items[i:i + 5] for i in range(0, len(items), 5)]
    signals = list(load_criteria(axis).keys())
    instructions = [
        swarm.pack_vote_instruction(axis, _axis_hint(axis), [(a, b) for _, _, a, b in c],
                                    signals=signals)
        for c in chunks
    ]
    replies = swarm.run_batch(instructions, workers=workers, timeout_s=300)
    votes: dict[tuple[int, int], list[str]] = {}
    abstain = 0
    for chunk, reply in zip(chunks, replies, strict=True):
        if reply is None:
            abstain += 1
            letters = [""] * len(chunk)
        else:
            letters = swarm.parse_packed_votes(reply, len(chunk))
        for (i, d, _, _), letter in zip(chunk, letters, strict=True):
            votes.setdefault((i, d), []).append(letter)
    pair_scores = []
    for i in range(len(pairs)):
        v0 = votes.get((i, 0), [])
        v1 = votes.get((i, 1), [])
        r0 = sum(x == "B" for x in v0) / len(v0) if v0 else 0.5  # 产物在 B
        r1 = sum(x == "A" for x in v1) / len(v1) if v1 else 0.5  # 产物在 A
        pair_scores.append((r0 + r1) / 2)
    score = sum(pair_scores) / len(pair_scores) if pair_scores else 0.0
    winrate = sum(s > 0.5 for s in pair_scores) / len(pair_scores) if pair_scores else 0.0
    return {"axis": axis, "n_pairs": len(pairs), "k": k, "score": round(score, 4),
            "winrate": round(winrate, 4), "abstain_chunks": abstain,
            "pair_scores": [round(s, 3) for s in pair_scores]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact_dir")
    ap.add_argument("tag")
    ap.add_argument("--pairs", type=int, default=20)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--brand-re", default=None,
                    help="含品牌元素的场过滤正则(placement_integration 切片用),默认清野|轻乳茶")
    args = ap.parse_args()
    if args.brand_re:
        global BRAND_RE
        BRAND_RE = re.compile(args.brand_re)
    ad = Path(args.artifact_dir)
    novel = (ad / "novel.md").read_text("utf-8")
    script = (ad / "script.md").read_text("utf-8")
    pairs_path = Path("out/pairs/exam.jsonl")
    rng = random.Random(7)
    extractors = {
        "transportation": lambda n: _novel_excerpts(novel, n, rng),
        "placement_integration": lambda n: _brand_excerpts(script, n, rng),
        "l0_dialogue": lambda n: _dialogue_excerpts(script, n, rng),
    }
    report = {"artifact": str(ad), "tag": args.tag, "axes": {}}
    for axis in AXES:
        corpus = _corpus_pool(axis, pairs_path)
        rng.shuffle(corpus)
        product = extractors[axis](args.pairs)
        take = min(args.pairs, len(product), len(corpus))
        if take < 6:  # 6 对 ×2 方向 ×k5 = 60 票,仍成读数(实证:南浪仔对白场仅 7 切片)
            report["axes"][axis] = {"error": f"切片不足 product={len(product)} corpus={len(corpus)}"}
            continue
        print(f"[judge] 轴 {axis}: {take} 对 ×2 方向 ×k{args.k} @ {time.strftime('%H:%M:%S')}",
              flush=True)
        res = judge_axis(axis, product, corpus, take, args.k, args.workers)
        report["axes"][axis] = res
        print(f"[judge] 完成 {axis}: score={res['score']} winrate={res['winrate']} "
              f"弃票={res['abstain_chunks']} @ {time.strftime('%H:%M:%S')}", flush=True)
    out_path = Path(f"out/artifact_judge_{args.tag}.json")
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    print(f"[judge] 报告写入 {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
