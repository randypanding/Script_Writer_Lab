"""L-06 · 合成偏好对。契约:spec/schemas/pairs.schema.yaml;接口:ADR-0001 §接口。

三类来源(ADR L-D2):corpus_degraded(语料×退化算子)/ corpus_vs_gen(语料 vs 我们生成物)/
gen_degraded(生成物×退化算子)。label 由构造保证(原版按定义优于退化版),禁止任何模型判断写入。

切分纪律:**按 script_id 切分**——同一源脚本的全部对进同一 split,split 间无泄漏。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsonschema
import yaml

SCHEMA_PATH = Path(__file__).parents[2] / "spec" / "schemas" / "pairs.schema.yaml"
_SCHEMA_CACHE: dict | None = None


def _schema() -> dict:
    global _SCHEMA_CACHE
    if _SCHEMA_CACHE is None:
        _SCHEMA_CACHE = yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8"))
    return _SCHEMA_CACHE

AXES = {
    "naturalness", "hook_strength", "placement_integration", "transportation",
    "producibility", "prose_craft", "l0_structure", "l0_fact", "l0_brand", "l0_dialogue",
}
LABELS = {"a_win", "b_win"}
SPLITS = {"exam", "train", "val"}
KINDS = {"corpus_degraded", "corpus_vs_gen", "gen_degraded"}

_PAIR_COUNTER = {"n": 0}


def _ulid(seed_key: str) -> str:
    """确定性 ULID(26 位小写 Crockford base32):同一 seed_key 稳定,便于复跑对齐。"""
    digest = hashlib.sha256(seed_key.encode("utf-8")).digest()
    val = (int.from_bytes(digest[:6], "big") << 80) | int.from_bytes(digest[6:16], "big")
    alpha = "0123456789abcdefghjkmnpqrstvwxyz"
    out = []
    for _ in range(26):
        val, r = divmod(val, 32)
        out.append(alpha[r])
    return "".join(reversed(out))


def build_pair(
    axis: str,
    a_text: str,
    b_text: str,
    label: str,
    construction: dict[str, Any],
    split: str,
) -> dict[str, Any]:
    """构造一条偏好对并按 schema 强校验(非法值抛 ValueError)。"""
    if axis not in AXES:
        raise ValueError(f"非法 axis: {axis}")
    if label not in LABELS:
        raise ValueError(f"非法 label: {label}")
    if split not in SPLITS:
        raise ValueError(f"非法 split: {split}")
    kind = construction.get("kind")
    if kind not in KINDS:
        raise ValueError(f"非法 construction.kind: {kind}")
    if kind in {"corpus_degraded", "gen_degraded"} and not construction.get("op_id"):
        raise ValueError(f"kind={kind} 必须带 op_id")
    if not str(a_text).strip() or not str(b_text).strip():
        raise ValueError("a_text/b_text 不得为空")
    op_id = str(construction.get("op_id", ""))
    digest = hashlib.sha256((a_text + "\0" + b_text).encode("utf-8")).hexdigest()
    pair = {
        "pair_id": f"pair:{_ulid(axis + '|' + digest + '|' + kind + '|' + op_id)}",
        "axis": axis,
        "a_text": a_text,
        "b_text": b_text,
        "label": label,
        "construction": construction,
        "split": split,
        "created_at": datetime.now(UTC).isoformat(),
    }
    jsonschema.validate(pair, _schema())
    return pair


# ---- 语料×退化算子 批量构造(L-06 主管线) ----

def _split_of(script_id: str) -> str:
    """按 script_id 稳定哈希切分:exam 20% / train 60% / val 20%。"""
    h = int(hashlib.sha256(script_id.encode()).hexdigest()[:8], 16) % 100
    return "exam" if h < 20 else ("train" if h < 80 else "val")


_META_LINE = re.compile(
    r"(▲|【[^】]{1,12}】|剧\s*名|书名|类型|梗概|题材|作者|出品|集数|主演|简介|内容简介|文案|备注"
    r"|人物表|人物介绍|人物小传|主要人物|原著|时长|基本信息|故事亮点|故事大纲|分集|目录)"
    r"|^\s*\d+[-—.、]\d+、")   # 人物小传条目(形如 2-1、男主-徐龙)
_SCENE_LINE = re.compile(r"^场景[::]")
_DIALOGUE_LINE = re.compile(r"^[一-龥A-Za-z]{1,8}[::]\S")
_CHAPTER_LINE = re.compile(r"^\s*(第[0-9零一二三四五六七八九十百千]+[集章节回卷部]|序章|楔子|番外|尾声)")
_QUOTED_LINE = re.compile(r"[“「『].{2,}?[”」』]")  # 小说式引号对白


def _narrative_excerpt(text: str, budget: int = 1200, min_chars: int = 100) -> str | None:
    """跳过片头元数据(信息表/梗概/人物表/小传),截取正文片段。

    锚点优先级:场次行/对白行 → 章节行(第N集/章、序章) → 非元数据长叙述句。
    窗口内元数据行一律剔除。有效性(两种文体都要能过):
    含场次/对白/引号对白行,或 ≥2 个 30 字以上叙述段;且全长 ≥ min_chars。
    实证教训:语料头部常是制作信息表,直接取头 1200 字符会让"语料锚"变成
    元数据残片,判官天然偏好生成物(自然度/对白轴灵敏度曾因此为 0)。"""
    lines = text.splitlines()

    def _anchor(pred) -> int | None:
        for i, ln in enumerate(lines):
            s = ln.strip()
            if not s or _META_LINE.search(s):
                continue
            if pred(s):
                return i
        return None

    start = _anchor(lambda s: bool(_SCENE_LINE.match(s) or _DIALOGUE_LINE.match(s)))
    if start is None:
        start = _anchor(lambda s: bool(_CHAPTER_LINE.match(s)))
    if start is None:
        start = _anchor(lambda s: len(s) >= 30)
    if start is None:
        return None
    body = [ln for ln in lines[start:] if ln.strip() and not _META_LINE.search(ln.strip())]
    has_talk = any(
        _SCENE_LINE.match(s) or _DIALOGUE_LINE.match(s) or _QUOTED_LINE.search(s)
        for ln in body if (s := ln.strip()))
    long_paras = sum(1 for ln in body if len(ln.strip()) >= 30)
    if not (has_talk or long_paras >= 2):
        return None
    out = "\n".join(body)[:budget]
    return out if len(out) >= min_chars else None


def build_corpus_degraded(
    store_dir: str | Path,
    *,
    severities: tuple[float, ...] = (0.5, 1.0),
    llm_mid: bool = False,
    llm_mid_scripts: int = 300,
    rng_seed: int = 7,
    checkpoint: str | Path | None = None,
) -> list[dict[str, Any]]:
    """store 全部语料 × deterministic(可选 llm_mid)算子 → 偏好对列表。

    片段截取:_narrative_excerpt(跳过片头元数据,两种文体)。
    llm_mid 算子每个都要一次真实改写,只作用于前 llm_mid_scripts 部有正文的语料
    (默认 300 部 × 5 算子 × 2 强度 ≈ 3000 次改写,swarm 免费路径可承受)。
    checkpoint:llm_mid 对逐条落盘(JSONL),崩溃/中断后重跑自动跳过已完成项
    (实证:423 抖动曾让 531 次改写成果全损)。
    """
    import threading as _th

    from lab.degrade import REGISTRY

    store = Path(store_dir)
    pairs: list[dict[str, Any]] = []
    done_keys: set[tuple[str, str, float]] = set()
    ckpt_path = Path(checkpoint) if checkpoint else None
    ckpt_lock = _th.Lock()
    if ckpt_path and ckpt_path.exists():
        for ln in ckpt_path.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            p = json.loads(ln)
            c = p["construction"]
            done_keys.add((c.get("source_script_id", ""), c.get("op_id", ""),
                           float(c.get("severity", 0))))
            pairs.append(p)
    llm_jobs: list[tuple[str, str, str, float]] = []  # (sid, fragment, op_id, severity)
    llm_mid_used = 0
    for card_file in sorted(store.glob("card_*.json")):
        card = json.loads(card_file.read_text(encoding="utf-8"))
        sid = card["script_id"]
        text_file = store / f"text_{sid.split(':')[1]}.txt"
        if not text_file.exists():
            continue
        text = text_file.read_text(encoding="utf-8")
        fragment = _narrative_excerpt(text)
        if fragment is None:
            continue  # 元数据残片不造对
        use_llm = llm_mid and llm_mid_used < llm_mid_scripts
        llm_mid_used += 1 if use_llm else 0
        for op_id, op in sorted(REGISTRY.items()):
            if op.mechanism == "llm_mid":
                if use_llm:
                    for sev in severities:
                        if (sid, op_id, float(sev)) not in done_keys:
                            llm_jobs.append((sid, fragment, op_id, sev))
                continue
            for sev in severities:
                degraded = op.apply(fragment, sev, rng_seed)
                if degraded == fragment:
                    continue
                pairs.append(build_pair(
                    axis=op.axis, a_text=fragment, b_text=degraded, label="a_win",
                    construction={"kind": "corpus_degraded", "op_id": op_id,
                                  "severity": sev, "source_script_id": sid},
                    split=_split_of(sid),
                ))
    # llm_mid 并行改写(每次一次真实调用;串行 3000 次 × 45s 不可承受)
    def _run_llm(job: tuple[str, str, str, float]) -> dict[str, Any] | None:
        sid, fragment, op_id, sev = job
        op = REGISTRY[op_id]
        try:
            degraded = op.apply(fragment, sev, rng_seed)
        except (TimeoutError, OSError, RuntimeError):
            return None  # 单个改写失败(死窗/超时)跳过,不拖死整场(实证)
        if degraded == fragment:
            return None
        pair = build_pair(axis=op.axis, a_text=fragment, b_text=degraded, label="a_win",
                          construction={"kind": "corpus_degraded", "op_id": op_id,
                                        "severity": sev, "source_script_id": sid},
                          split=_split_of(sid))
        if ckpt_path:
            with ckpt_lock:
                ckpt_path.parent.mkdir(parents=True, exist_ok=True)
                with ckpt_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(pair, ensure_ascii=False) + "\n")
        return pair

    if llm_jobs:
        print(f"[pairs] llm_mid 待改写 {len(llm_jobs)} 项(断点跳过已完成)@ "
              f"{time.strftime('%H:%M:%S')}", flush=True)
        with ThreadPoolExecutor(max_workers=24) as ex:
            done_n = 0
            for res in ex.map(_run_llm, llm_jobs):
                done_n += 1
                if res is not None:
                    pairs.append(res)
                if done_n % 100 == 0:
                    print(f"[pairs] llm_mid 进度 {done_n}/{len(llm_jobs)} @ "
                          f"{time.strftime('%H:%M:%S')}", flush=True)
    return pairs


def build_gen_degraded(
    gen_texts: list[tuple[str, str]],
    *,
    severities: tuple[float, ...] = (0.5, 1.0),
    rng_seed: int = 7,
) -> list[dict[str, Any]]:
    """来源 2:我们生成物 × 退化算子(gen_degraded)。标签由构造保证(原版优于退化版)。

    gen_texts: [(run_id, text)] —— run_id 作为 source_run_id 与切分键(同 run 的对同 split)。
    """
    from lab.degrade import REGISTRY

    pairs: list[dict[str, Any]] = []
    for run_id, text in gen_texts:
        fragment = text[:1200]
        for op_id, op in sorted(REGISTRY.items()):
            if op.mechanism == "llm_mid":
                continue
            for sev in severities:
                degraded = op.apply(fragment, sev, rng_seed)
                if degraded == fragment:
                    continue
                pairs.append(build_pair(
                    axis=op.axis, a_text=fragment, b_text=degraded, label="a_win",
                    construction={"kind": "gen_degraded", "op_id": op_id,
                                  "severity": sev, "source_run_id": run_id},
                    split=_split_of(f"run:{run_id}"),
                ))
    return pairs


# 轴 → 语料锚指标(用于 corpus_vs_gen 的构造性标签;偏离带 = 语料锚意义上的劣,ADR L-D2)
_AXIS_BAND_METRIC = {
    "naturalness": "dialogue_ratio", "l0_dialogue": "dialogue_ratio",
    "prose_craft": "sent_len_cv", "transportation": "sent_len_mean",
}


def build_corpus_vs_gen(
    store_dir: str | Path,
    gen_texts: list[tuple[str, str]],
    *,
    per_gen: int = 20,
    bands_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """来源 3:语料(带内) vs 我们生成物(corpus_vs_gen)。

    标签构造口径(无任何模型判断):语料锚定义"好 = 不偏离带内"(ADR-0001 L-D2)。
    仅当生成物片段在轴对应指标上**确定性偏离正常带**时构造对(标签 a_win = 语料胜);
    带内生成物不构造(无构造性顺序,诚实跳过)。
    """
    import yaml as _yaml

    from lab.corpus import parse_script, stats_card

    bp = Path(bands_path) if bands_path else Path(__file__).parents[2] / "mined" / "bands.yaml"
    bands = _yaml.safe_load(bp.read_text(encoding="utf-8"))
    drama = bands["by_kind"]["drama_script"]["bands"]
    store = Path(store_dir)
    # 抽带内语料片段(drama_script 组,前 per_gen×len(gen) 部)
    corpus_frags: list[tuple[str, str]] = []
    for card_file in sorted(store.glob("card_*.json")):
        card = json.loads(card_file.read_text(encoding="utf-8"))
        if card["kind"] != "drama_script":
            continue
        tf = store / f"text_{card['script_id'].split(':')[1]}.txt"
        if tf.exists():
            frag = _narrative_excerpt(tf.read_text(encoding="utf-8"))
            if frag is not None:
                corpus_frags.append((card["script_id"], frag))
        if len(corpus_frags) >= per_gen * max(1, len(gen_texts)):
            break
    if not corpus_frags:
        return []

    pairs: list[dict[str, Any]] = []
    for run_id, text in gen_texts:
        frag = text[:1200]
        card = stats_card(parse_script(frag))
        for axis, metric in _AXIS_BAND_METRIC.items():
            lo, hi = drama[metric]["p25"], drama[metric]["p75"]
            if lo <= card[metric] <= hi:
                continue  # 带内 → 无构造性顺序,跳过
            for sid, cfrag in corpus_frags[:per_gen]:
                pairs.append(build_pair(
                    axis=axis, a_text=cfrag, b_text=frag, label="a_win",
                    construction={"kind": "corpus_vs_gen",
                                  "source_script_id": sid, "source_run_id": run_id},
                    split=_split_of(sid),  # 切分键=语料 script_id(防同脚本跨 split)
                ))
    return pairs


def write_jsonl(pairs: list[dict[str, Any]], out_dir: str | Path) -> dict[str, int]:
    """按 split 写 out/pairs/{exam,train,val}.jsonl;返回各 split 条数。"""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    counts = {"exam": 0, "train": 0, "val": 0}
    handles = {s: (out / f"{s}.jsonl").open("w", encoding="utf-8") for s in counts}
    try:
        for p in pairs:
            handles[p["split"]].write(json.dumps(p, ensure_ascii=False) + "\n")
            counts[p["split"]] += 1
    finally:
        for h in handles.values():
            h.close()
    return counts


def assert_no_split_leakage(pairs: list[dict[str, Any]]) -> None:
    """同一 source_script_id 不得出现在两个 split(自检)。"""
    seen: dict[str, str] = {}
    for p in pairs:
        sid = p["construction"].get("source_script_id")
        if not sid:
            continue
        if sid in seen and seen[sid] != p["split"]:
            raise AssertionError(f"split 泄漏:{sid} 同时在 {seen[sid]} 与 {p['split']}")
        seen[sid] = p["split"]


def _gen_texts_from_runs(runs_dir: str | Path, limit: int = 20) -> list[tuple[str, str]]:
    """从 lab.runner 产物目录提取生成文本:[(run_id, episode_text)]。"""
    from lab.runner import Artifact, episode_text

    out: list[tuple[str, str]] = []
    for meta_file in sorted(Path(runs_dir).glob("*/meta.json")):
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not meta.get("ir_path"):
            continue
        art = Artifact(meta["run_id"], meta["brief"], meta["profile"], meta["seed"],
                       meta["out_dir"], meta["ir_path"], meta["returncode"])
        text = episode_text(art)
        if text.strip():
            out.append((meta["run_id"], text))
        if len(out) >= limit:
            break
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lab.pairs")
    b = ap.add_subparsers(dest="cmd", required=True)
    gen = b.add_parser("build", help="语料×退化算子 → out/pairs/*.jsonl")
    gen.add_argument("--store", default="corpus/store")
    gen.add_argument("--out", default="out/pairs")
    gen.add_argument("--severities", default="0.5,1.0")
    gen.add_argument("--llm-mid", action="store_true", help="纳入 llm_mid 算子(真实 API)")
    gen.add_argument("--llm-mid-limit", type=int, default=300,
                     help="llm_mid 算子只作用于前 N 部有正文的语料(每次改写都是一次真实调用)")
    gen.add_argument("--gen-dir", default="out/runs",
                     help="SW 运行产物目录(扫 ir.json 提取生成文本;缺省包含全部来源)")
    args = ap.parse_args(argv)
    if args.cmd == "build":
        sevs = tuple(float(x) for x in args.severities.split(",") if x.strip())
        ckpt = (Path(args.out) / "partial_llm.jsonl") if args.llm_mid else None
        print(f"[pairs] 阶段 1/4 corpus_degraded 开始 @ {time.strftime('%H:%M:%S')}", flush=True)
        pairs = build_corpus_degraded(args.store, severities=sevs, llm_mid=args.llm_mid,
                                      llm_mid_scripts=args.llm_mid_limit, checkpoint=ckpt)
        print(f"[pairs] 阶段 2/4 gen_degraded(累计 {len(pairs)})", flush=True)
        gen_texts = _gen_texts_from_runs(args.gen_dir)
        pairs += build_gen_degraded(gen_texts, severities=sevs)
        print(f"[pairs] 阶段 3/4 corpus_vs_gen(累计 {len(pairs)})", flush=True)
        pairs += build_corpus_vs_gen(args.store, gen_texts)
        assert_no_split_leakage(pairs)
        counts = write_jsonl(pairs, args.out)
        kinds = Counter(p["construction"]["kind"] for p in pairs)
        print(f"[pairs] 阶段 4/4 写盘完成 @ {time.strftime('%H:%M:%S')}", flush=True)
        print(json.dumps({"total": len(pairs), **counts, "kinds": dict(kinds)},
                         ensure_ascii=False))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
