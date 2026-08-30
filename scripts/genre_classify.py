"""题材分类器(W1.1):标题+作者+前 1500 字 → 题材桶,CNB swarm 打包分类。

桶(定稿冻结前可调):复仇爽文/甜宠言情/都市日常/悬疑探秘/玄幻仙侠/历史穿越/治愈成长/其他
产出 mined/genre_map.json(只含 路径→题材,无原文——corpus 红线)。
用法:
  一致性考试: uv run python scripts/genre_classify.py --exam --workers 16
  全量分类:   uv run python scripts/genre_classify.py --workers 24
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from corpus_extract import docx_text, txt_text

from lab import swarm

GENRES = ["复仇爽文", "甜宠言情", "都市日常", "悬疑探秘", "玄幻仙侠", "历史穿越", "治愈成长", "其他"]

GENRE_DEFS = """题材桶定义(判定时选最主要的一个):
- 复仇爽文:主角受欺压后反击/翻身/打脸,冲突驱动,节奏快张力高;
- 甜宠言情:恋爱关系为主线,甜/宠/误会-和解循环;
- 都市日常:现代都市生活流,职场/家庭/日常冲突,无强复仇线;
- 悬疑探秘:谜团/案件/真相追查为主线;
- 玄幻仙侠:架空修炼/仙侠/异能体系;
- 历史穿越:穿越/重生到历史或架空的过去时代;
- 治愈成长:温暖治愈、陪伴、成长,冲突温和,气质松弛;
- 其他:不属于以上任何一类或信息不足。"""


def _works() -> list[dict]:
    root = Path("corpus/inbox")
    works = [{"id": p.stem, "path": p} for p in sorted(root.glob("48.短剧脚本/竖屏短剧/**/*.docx"))]
    for d in sorted(root.glob("q点作者/*")):
        txts = sorted(d.rglob("*.txt"))
        if txts:
            works.append({"id": txts[0].stem, "path": txts[0]})
    return works


def _snippet(path: Path) -> str:
    try:
        text = docx_text(path) if path.suffix.lower() == ".docx" else txt_text(path)
    except Exception:  # noqa: BLE001 —— 单文件失败不拖死全批,标"其他"
        return ""
    return text[:1500]


def _build_instruction(items: list[dict]) -> str:
    parts = [
        (
            f"你是小说类型分类员。下面有 {len(items)} 部作品,请把每部归入一个题材桶。"
            "只输出合法 JSON 数组,不要任何解释、问候、代码栅栏。"
        ),
        GENRE_DEFS,
        f'数组长度必须={len(items)},每个元素 {{"work": "w1/w2/... 编号照抄", "genre": "桶名照抄"}}。',
    ]
    for i, w in enumerate(items, 1):
        parts.append(f"w{i}《{w['id']}》开头:\n{w['snippet']}")
    return "\n\n".join(parts)


_JSON_RE = re.compile(r"\[.*\]", re.DOTALL)


def _parse(reply: str, n: int) -> list[str | None]:
    body = swarm._MENTION_RE.sub("", reply.strip())
    m = _JSON_RE.search(body)
    if not m:
        return [None] * n
    try:
        arr = json.loads(m.group(0))
    except json.JSONDecodeError:
        return [None] * n
    if not isinstance(arr, list) or len(arr) != n:
        return [None] * n
    out = []
    for x in arr:
        g = str(x.get("genre", "")).strip() if isinstance(x, dict) else ""
        out.append(g if g in GENRES else None)
    return out


def _classify(items: list[dict], workers: int, pack: int = 5) -> list[str | None]:
    chunks = [items[i:i + pack] for i in range(0, len(items), pack)]
    instrs = [_build_instruction(c) for c in chunks]
    replies = swarm.run_batch(instrs, workers=workers, timeout_s=600, mention=swarm.WRITER_MENTION)
    out: list[str | None] = []
    for chunk, reply in zip(chunks, replies, strict=True):
        out.extend(_parse(reply, len(chunk)) if reply else [None] * len(chunk))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--exam", action="store_true")
    args = ap.parse_args()
    works = _works()
    for w in works:
        w["snippet"] = _snippet(w["path"])
    works = [w for w in works if w["snippet"]]
    print(f"[genre] 作品数 {len(works)} @ {time.strftime('%H:%M:%S')}", flush=True)

    if args.exam:  # 抽 30 部双标,一致率 ≥0.7 才放量(W1.1 验收线)
        sample = works[:30]
        a = _classify(sample, args.workers)
        b = _classify(sample, args.workers)
        pairs = [(x, y) for x, y in zip(a, b, strict=True) if x and y]
        rate = sum(x == y for x, y in pairs) / len(pairs) if pairs else 0.0
        print(f"[exam] 有效对 {len(pairs)}/30 一致率 {rate:.2f} "
              f"{'PASS' if rate >= 0.7 else 'FAIL'}", flush=True)
        return 0 if rate >= 0.7 else 1

    labels = _classify(works, args.workers)
    Path("mined").mkdir(exist_ok=True)
    mapping = {}
    fallback = 0
    for w, g in zip(works, labels, strict=True):
        if g is None:
            fallback += 1
            g = "其他"
        mapping[w["path"].as_posix()] = g
    Path("mined/genre_map.json").write_text(
        json.dumps(mapping, ensure_ascii=False, indent=1, sort_keys=True), "utf-8")
    from collections import Counter

    dist = Counter(mapping.values())
    print(f"[genre] 完成 {len(mapping)} 部(解析失败兜底 '其他' {fallback} 部) 分布: "
          f"{dict(dist.most_common())} @ {time.strftime('%H:%M:%S')}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
