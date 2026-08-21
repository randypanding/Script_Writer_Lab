"""L-01 · 语料入库:格式归一解析、统计卡、simhash 去重。

口径唯一依据:spec/parsing_conventions.md;schema 契约:spec/schemas/corpus_card.schema.yaml。
接口签名依据:adr/0001-lab-constitution.md §接口。
"""
from __future__ import annotations

import argparse
import itertools
import json
import re
import secrets
import statistics
import sys
import time
from dataclasses import dataclass, field
from hashlib import md5
from pathlib import Path
from typing import Any

import yaml

# ---- 行分类正则(spec/parsing_conventions.md §行分类) ----
EP_TITLE = re.compile(r"^第[0-9零一二三四五六七八九十百千]+[集章]")
SCENE_LINE = re.compile(r"^场景[:：]")
DIALOGUE_LINE = re.compile(r"^([一-龥A-Za-z]{1,8})[:：](.+)")
HOOK_MARKERS = ("【钩子】", "【悬念】", "【反转】")  # 【伏笔】【回收】只服务 D14,不入 hook
SENT_SPLIT = "。!?…?!"
HAMMING_SAME = 3  # 判同阈值:hamming ≤ 3


@dataclass(frozen=True)
class ScriptCard:
    """parse_script 的产物:原文 + 元数据。统计字段由 stats_card 派生(不落盘原文以外的地方)。"""

    text: str
    source_file: str = ""
    meta: dict[str, str] = field(default_factory=dict)


def _ulid() -> str:
    """26 字符小写 ULID(48bit 毫秒时间戳 + 80bit 随机,内容无关)。"""
    val = (int(time.time() * 1000) << 80) | int.from_bytes(secrets.token_bytes(10), "big")
    return _to_base32(val, 26)


_ULID_ALPHA = "0123456789abcdefghjkmnpqrstvwxyz"


def _to_base32(val: int, width: int) -> str:
    out = []
    for _ in range(width):
        val, r = divmod(val, 32)
        out.append(_ULID_ALPHA[r])
    return "".join(reversed(out))


def simhash64(text: str) -> str:
    """64 位 simhash(字符 3-gram 特征,md5 前 8 字节),16 位十六进制。同文同值。"""
    v = [0] * 64
    normalized = "".join(text.split())  # 空白不参与
    for i in range(max(len(normalized) - 2, 1)):
        gram = normalized[i : i + 3] if len(normalized) >= 3 else normalized
        h = int.from_bytes(md5(gram.encode("utf-8")).digest()[:8], "big")
        for b in range(64):
            v[b] += 1 if (h >> b) & 1 else -1
    fp = sum(1 << b for b in range(64) if v[b] > 0)
    return f"{fp:016x}"


def hamming(a_hex: str, b_hex: str) -> int:
    return (int(a_hex, 16) ^ int(b_hex, 16)).bit_count()


def _load_meta(path: Path) -> dict[str, str]:
    """元数据卡:同名 .meta.yaml 侧车;缺省值'未声明'(提供者声称,未经核实)。"""
    meta = {"claimed_genre": "未声明", "claimed_platform": "未声明"}
    sidecar = path.with_suffix(".meta.yaml")
    if sidecar.exists():
        loaded = yaml.safe_load(sidecar.read_text(encoding="utf-8")) or {}
        for k in meta:
            if isinstance(loaded.get(k), str):
                meta[k] = loaded[k]
    return meta


def parse_script(path: str | Path) -> ScriptCard:
    """接受路径(str|Path,存在则读)或直接文本(不存在该路径则按文本解析)。"""
    p = Path(path)
    if p.exists():
        return ScriptCard(text=p.read_text(encoding="utf-8", errors="ignore"),
                          source_file=p.name, meta=_load_meta(p))
    return ScriptCard(text=str(path), source_file="", meta={})


# ---- 统计口径(spec/parsing_conventions.md §统计口径) ----

def _nonempty(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def _is_dialogue(line: str) -> tuple[bool, str]:
    m = DIALOGUE_LINE.match(line)
    if m and m.group(1) != "场景" and not line.startswith("【"):
        return True, m.group(2)
    return False, ""


def _sentences(text: str) -> list[str]:
    parts, buf = [], []
    for ch in text:
        buf.append(ch)
        if ch in SENT_SPLIT:
            parts.append("".join(buf))
            buf = []
    if buf:
        parts.append("".join(buf))
    return [s for s in (p.strip() for p in parts) if s]


def stats_card(card: ScriptCard) -> dict[str, Any]:
    lines = _nonempty(card.text)
    n = len(lines)

    n_episodes = sum(1 for ln in lines if EP_TITLE.match(ln))
    scene_idx = [i for i, ln in enumerate(lines) if SCENE_LINE.match(ln)]
    dialogue_chars = 0
    n_lines = 0
    for ln in lines:
        ok, speech = _is_dialogue(ln)
        if ok:
            n_lines += 1
            dialogue_chars += len("".join(speech.split()))
    hook_positions = [(i + 1) / n for i, ln in enumerate(lines)
                      if any(m in ln for m in HOOK_MARKERS)]

    nonws = "".join(card.text.split())
    total_chars = len(nonws)
    dialogue_ratio = (dialogue_chars / total_chars) if total_chars else 0.0

    sent_lens = [len("".join(s.split())) for s in _sentences(card.text)]
    sent_len_mean = statistics.fmean(sent_lens) if sent_lens else 0.0
    sent_len_cv = (statistics.pstdev(sent_lens) / sent_len_mean) if sent_len_mean else 0.0

    paras = [p for p in (blk.strip() for blk in card.text.split("\n\n")) if p]
    para_lens = [len("".join(p.split())) for p in paras]
    para_len_cv = (statistics.pstdev(para_lens) / statistics.fmean(para_lens)) if len(para_lens) > 1 and statistics.fmean(para_lens) else 0.0

    ep_char_counts = _ep_char_counts(lines)

    return {
        "script_id": f"scr:{_ulid()}",
        "kind": "drama_script" if scene_idx else "novel",
        "n_episodes": n_episodes,
        "n_scenes": len(scene_idx),
        "n_lines": n_lines,
        "total_chars": total_chars,
        "dialogue_ratio": round(dialogue_ratio, 6),
        "sent_len_mean": round(sent_len_mean, 4),
        "sent_len_cv": round(sent_len_cv, 6),
        "para_len_cv": round(para_len_cv, 6),
        "hook_positions": [round(p, 6) for p in hook_positions],
        "ep_char_counts": ep_char_counts,
        "meta": {"claimed_genre": "未声明", "claimed_platform": "未声明", **card.meta,
                 "source_file": card.source_file},
        "simhash": simhash64(card.text),
    }


def _ep_char_counts(lines: list[str]) -> list[int]:
    """分集字数(非空白字符;小说=分章)。无任何集/章标题 → 全文记 1 个单位。"""
    bounds = [i for i, ln in enumerate(lines) if EP_TITLE.match(ln)] + [len(lines)]
    if len(bounds) == 1:
        return [sum(len("".join(ln.split())) for ln in lines)] if lines else []
    return [sum(len("".join(ln.split())) for ln in lines[a:b])
            for a, b in itertools.pairwise(bounds)]


# ---- 入库与 simhash 去重 ----

def ingest(inbox_dir: str | Path, store_dir: str | Path) -> dict[str, Any]:
    """inbox → store:解析 → 统计卡 JSON + 原文副本;simhash hamming≤3 判重。

    store 落在 corpus/ 禁地内(gitignored),原文不出禁地。
    """
    inbox, store = Path(inbox_dir), Path(store_dir)
    store.mkdir(parents=True, exist_ok=True)
    seen: list[tuple[str, str]] = []  # (simhash, script_id) 已入库(含本次批次)
    for card_file in sorted(store.glob("card_*.json")):  # 断点续跑:先载已有
        data = json.loads(card_file.read_text(encoding="utf-8"))
        seen.append((data["simhash"], data["script_id"]))

    report: dict[str, Any] = {"ingested": 0, "duplicates": 0, "skipped": [], "accepted": []}
    for p in sorted(inbox.rglob("*")):
        if not p.is_file() or p.suffix not in {".txt", ".md", ".fountain", ".meta.yaml"}:
            continue
        if p.suffix == ".meta.yaml":
            continue
        card = parse_script(p)
        stats = stats_card(card)
        dup = next((sid for sh, sid in seen if hamming(sh, stats["simhash"]) <= HAMMING_SAME), None)
        if dup:
            report["duplicates"] += 1
            report["skipped"].append({"file": p.name, "duplicate_of": dup})
            continue
        sid = stats["script_id"]
        (store / f"card_{sid.split(':')[1]}.json").write_text(
            json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")
        (store / f"text_{sid.split(':')[1]}.txt").write_text(card.text, encoding="utf-8")
        seen.append((stats["simhash"], sid))
        report["ingested"] += 1
        report["accepted"].append({"file": p.name, "script_id": sid})
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lab.corpus")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ing = sub.add_parser("ingest", help="inbox → store,simhash 去重")
    ing.add_argument("inbox", nargs="?", default="corpus/inbox")
    ing.add_argument("--store", default="corpus/store")
    args = ap.parse_args(argv)
    if args.cmd == "ingest":
        report = ingest(args.inbox, args.store)
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
