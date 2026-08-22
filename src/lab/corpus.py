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

from lab.readers import READABLE_SUFFIXES, extract_text, is_scriptlike

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
    """64 位 simhash(字符 3-gram 特征,md5 前 8 字节),16 位十六进制。同文同值。

    性能口径:gram 数上限约 8 千,超出按确定性等距步长抽样(全量对长剧本为
    数十万次哈希×64 位累加,不可用;抽样不破坏"同文同值",近重判定精度略降)。
    <50 字符的短文本 3-gram 过少,近重判定基本失效,适用下限约为一段完整对白。"""
    v = [0] * 64
    normalized = "".join(text.split())
    n = len(normalized)
    if n < 3:
        grams = [normalized]
    else:
        stride = max(1, (n - 2) // 8192)
        grams = [normalized[i : i + 3] for i in range(0, n - 2, stride)]
    for gram in grams:
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
    """接受路径(str|Path,是文件则读)或直接文本(不是文件则按文本解析)。

    注意双重语义:拼错的路径不会报错,会被当成正文解析成一张卡(spec 规定)。"""
    p = Path(path)
    try:
        is_file = p.is_file()
    except OSError:
        # POSIX 对超长"路径"(其实是被当路径的正文)抛 ENAMETOOLONG:按文本处理
        is_file = False
    if is_file:
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


_SENT_RE = re.compile(r"(?<=[。!?…?!])")


def _sentences(text: str) -> list[str]:
    parts = _SENT_RE.split(text)
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
    if len(paras) <= 1:  # 无空行文本(格式化提取常态):按非空行计段落(parsing_conventions §段落口径)
        paras = lines
    para_lens = [len("".join(p.split())) for p in paras]
    para_len_cv = (statistics.pstdev(para_lens) / statistics.fmean(para_lens)) if len(para_lens) > 1 and statistics.fmean(para_lens) else 0.0

    ep_char_counts = _ep_char_counts(lines)
    # kind 判定(parsing_conventions §真实语料修正):场次行,或 集标题+高密度对白行
    dialogue_line_ratio = (n_lines / n) if n else 0.0
    kind = "drama_script" if scene_idx or (n_episodes and dialogue_line_ratio >= 0.3) else "novel"

    return {
        "script_id": f"scr:{_ulid()}",
        "kind": kind,
        "n_episodes": n_episodes,
        "n_scenes": len(scene_idx),
        "n_lines": n_lines,
        "total_chars": total_chars,
        "dialogue_ratio": round(dialogue_ratio, 6),
        "sent_len_mean": round(sent_len_mean, 4),
        "sent_len_cv": round(sent_len_cv, 6),
        "para_len_cv": round(para_len_cv, 6),
        "hook_positions": hook_positions,
        "ep_char_counts": ep_char_counts,
        "meta": {"claimed_genre": "未声明", "claimed_platform": "未声明", **card.meta,
                 "source_file": card.source_file},
        "simhash": simhash64(card.text),
    }


def _ep_char_counts(lines: list[str]) -> list[int]:
    """分集字数(非空白字符;小说=分章)。首个集/章标题之前的前导正文并入第一
    个单位(口径:spec 未定义,本实现选择并入,见 PR 偏差记录)。无标题 → 全文 1 单位。"""
    starts = [i for i, ln in enumerate(lines) if EP_TITLE.match(ln)]
    if not starts:
        return [sum(len("".join(ln.split())) for ln in lines)] if lines else []
    bounds = ([0] if starts[0] > 0 else []) + starts + [len(lines)]
    return [sum(len("".join(ln.split())) for ln in lines[a:b])
            for a, b in itertools.pairwise(bounds)]


# ---- 入库与 simhash 去重 ----

BAND_METRICS = ("dialogue_ratio", "sent_len_mean", "sent_len_cv", "para_len_cv",
                "hook_density", "ep_char_median", "episodes_per_script")


def _quantiles(values: list[float]) -> dict[str, float]:
    """P25/P50/P75(statistics.quantiles 线性插值,n=4);样本不足时退化重复边界。"""
    if not values:
        return {"p25": 0.0, "p50": 0.0, "p75": 0.0}
    if len(values) < 4:
        s = sorted(values)
        return {"p25": round(s[0], 6), "p50": round(statistics.median(s), 6),
                "p75": round(s[-1], 6)}
    q1, q2, q3 = statistics.quantiles(values, n=4)
    return {"p25": round(q1, 6), "p50": round(q2, 6), "p75": round(q3, 6)}


def _card_scalars(card: dict[str, Any]) -> dict[str, float]:
    eps = card.get("ep_char_counts") or []
    return {
        "dialogue_ratio": float(card.get("dialogue_ratio", 0)),
        "sent_len_mean": float(card.get("sent_len_mean", 0)),
        "sent_len_cv": float(card.get("sent_len_cv", 0)),
        "para_len_cv": float(card.get("para_len_cv", 0)),
        "hook_density": len(card.get("hook_positions", [])) / card["n_episodes"]
        if card.get("n_episodes") else 0.0,
        "ep_char_median": float(statistics.median(eps)) if eps else 0.0,
        "episodes_per_script": float(card.get("n_episodes", 0)),
    }


def bands(store_dir: str | Path, mined_dir: str | Path) -> dict[str, Any]:
    """L-02:全 store 卡片 → mined/bands.yaml(各指标 P25/P50/P75 正常带)+ corpus_stats.md 画像。

    bands 按 kind 分组(drama_script / novel 各自的正常带):混合分组的"正常带"
    两头都不是(剧本与小说的对白占比/句长分布天然不同),会把锚拉平到无意义。
    顶层 bands = 全体(向后兼容),by_kind = 分组(L-14 消费 drama_script 组)。
    """
    store, mined = Path(store_dir), Path(mined_dir)
    mined.mkdir(parents=True, exist_ok=True)
    cards = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(store.glob("card_*.json"))]
    if not cards:
        raise ValueError(f"store 为空:{store} —— 拒绝产出全零'正常带'(空画像会污染下游锚)")

    def _group(cs: list[dict[str, Any]]) -> dict[str, Any]:
        scalars = [_card_scalars(c) for c in cs]
        return {"n": len(cs), "bands": {m: _quantiles([s[m] for s in scalars]) for m in BAND_METRICS}}

    by_kind = {k: _group([c for c in cards if c["kind"] == k])
               for k in sorted({c["kind"] for c in cards})}
    out_bands = _group(cards)["bands"]
    payload = {"version": 2, "n_scripts": len(cards), "metrics": BAND_METRICS,
               "data_source": store.resolve().as_posix(),
               "status": "corpus" if len(cards) >= 50 else "placeholder",
               "bands": out_bands, "by_kind": by_kind,
               "note": "语料群体统计正常带(ADR-0001 L-D2 语料锚);聚合产物,无原文;"
                       "n_scripts<50 时 status=placeholder,L-14 应拒绝以此为分布锚;"
                       "by_kind.drama_script 是 brief 生成的分布锚(剧本≠小说)"}
    (mined / "bands.yaml").write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")

    kinds: dict[str, int] = {k: g["n"] for k, g in by_kind.items()}
    genres: dict[str, int] = {}
    for c in cards:
        genres[c["meta"].get("claimed_genre", "未声明")] = genres.get(c["meta"].get("claimed_genre", "未声明"), 0) + 1
    lines = [
        "# 语料画像(corpus_stats)", "",
        f"- 脚本数:**{len(cards)}**" + "".join(f", {k}={v}" for k, v in sorted(kinds.items())),
        f"- 声称题材分布:{'、'.join(f'{k}×{v}' for k, v in sorted(genres.items())) or '—'}",
        f"- 总字数(非空白):{sum(c.get('total_chars', 0) for c in cards)}",
        f"- 集数范围:{min((c['n_episodes'] for c in cards), default=0)}–{max((c['n_episodes'] for c in cards), default=0)}",
    ]
    for kind, g in sorted(by_kind.items()):
        lines += ["", f"## {kind} 正常带(n={g['n']})", "",
                  "| 指标 | P25 | P50 | P75 |", "|---|---|---|---|"]
        lines += [f"| {m} | {b['p25']} | {b['p50']} | {b['p75']} |" for m, b in g["bands"].items()]
    lines += ["", "> 依据 ADR-0001 L-D2 语料锚:'好'=不偏离带内。本文件为聚合产物,不含任何语料原文。"]
    (mined / "corpus_stats.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return payload


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
        if not p.is_file() or p.name == ".gitkeep" or p.suffix.lower() == ".yaml":
            continue  # .meta.yaml 侧车由 _load_meta 读取,不当正文
        if p.suffix.lower() not in READABLE_SUFFIXES:
            report["skipped"].append({"file": p.name, "reason": "nontext"})
            continue
        text = extract_text(p)
        if text is None:
            report["skipped"].append({"file": p.name, "reason": "unextractable"})
            continue
        if not is_scriptlike(text):
            report["skipped"].append({"file": p.name, "reason": "not_scriptlike"})
            continue
        card = ScriptCard(text=text, source_file=p.name, meta=_load_meta(p))
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


def restat(store_dir: str | Path) -> int:
    """按当前统计口径重算 store 内全部卡片(保留 script_id 与文件名,防断链)。

    stats_card 每次生成新 ULID;重算时用旧卡的 script_id 覆盖,保证
    script_id 稳定 —— 下游(偏好对/分层抽样)以它为主键。
    """
    store = Path(store_dir)
    n = 0
    for text_file in sorted(store.glob("text_*.txt")):
        sid_tail = text_file.stem.removeprefix("text_")
        card_file = store / f"card_{sid_tail}.json"
        old = json.loads(card_file.read_text(encoding="utf-8")) if card_file.exists() else {}
        card = parse_script(text_file)
        stats = stats_card(card)
        stats["script_id"] = old.get("script_id", stats["script_id"])
        stats["meta"] = {**stats["meta"], **{k: v for k, v in old.get("meta", {}).items()
                                             if k in ("claimed_genre", "claimed_platform")}}
        card_file.write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")
        n += 1
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lab.corpus")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ing = sub.add_parser("ingest", help="inbox → store,simhash 去重")
    ing.add_argument("inbox", nargs="?", default="corpus/inbox")
    ing.add_argument("--store", default="corpus/store")
    st = sub.add_parser("stats", help="store 卡片 → mined/bands.yaml + corpus_stats.md")
    st.add_argument("--store", default="corpus/store")
    st.add_argument("--mined", default="mined")
    rs = sub.add_parser("restat", help="按当前口径重算卡片(保留 script_id)")
    rs.add_argument("--store", default="corpus/store")
    args = ap.parse_args(argv)
    if args.cmd == "ingest":
        report = ingest(args.inbox, args.store)
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return 0
    if args.cmd == "restat":
        n = restat(args.store)
        print(json.dumps({"restat": n}, ensure_ascii=False))
        return 0
    if args.cmd == "stats":
        payload = bands(args.store, args.mined)
        print(json.dumps({"n_scripts": payload["n_scripts"], "metrics": list(payload["bands"])},
                         ensure_ascii=False))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
