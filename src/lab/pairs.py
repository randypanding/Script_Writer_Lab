"""L-06 · 合成偏好对。契约:spec/schemas/pairs.schema.yaml;接口:ADR-0001 §接口。

三类来源(ADR L-D2):corpus_degraded(语料×退化算子)/ corpus_vs_gen(语料 vs 我们生成物)/
gen_degraded(生成物×退化算子)。label 由构造保证(原版按定义优于退化版),禁止任何模型判断写入。

切分纪律:**按 script_id 切分**——同一源脚本的全部对进同一 split,split 间无泄漏。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
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


def build_corpus_degraded(
    store_dir: str | Path,
    *,
    severities: tuple[float, ...] = (0.5, 1.0),
    llm_mid: bool = False,
    rng_seed: int = 7,
) -> list[dict[str, Any]]:
    """store 全部语料 × deterministic(可选 llm_mid)算子 → 偏好对列表。

    片段截取:每部取正文前 1200 字符(对判官足够、原文不出 out/ 以外 tracked 面)。
    """
    from lab.degrade import REGISTRY

    store = Path(store_dir)
    pairs: list[dict[str, Any]] = []
    for card_file in sorted(store.glob("card_*.json")):
        card = json.loads(card_file.read_text(encoding="utf-8"))
        sid = card["script_id"]
        text_file = store / f"text_{sid.split(':')[1]}.txt"
        if not text_file.exists():
            continue
        text = text_file.read_text(encoding="utf-8")
        fragment = text[:1200]
        for op_id, op in sorted(REGISTRY.items()):
            if op.mechanism == "llm_mid" and not llm_mid:
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lab.pairs")
    b = ap.add_subparsers(dest="cmd", required=True)
    gen = b.add_parser("build", help="语料×退化算子 → out/pairs/*.jsonl")
    gen.add_argument("--store", default="corpus/store")
    gen.add_argument("--out", default="out/pairs")
    gen.add_argument("--severities", default="0.5,1.0")
    gen.add_argument("--llm-mid", action="store_true", help="纳入 llm_mid 算子(真实 API)")
    args = ap.parse_args(argv)
    if args.cmd == "build":
        sevs = tuple(float(x) for x in args.severities.split(",") if x.strip())
        pairs = build_corpus_degraded(args.store, severities=sevs, llm_mid=args.llm_mid)
        assert_no_split_leakage(pairs)
        counts = write_jsonl(pairs, args.out)
        print(json.dumps({"total": len(pairs), **counts}, ensure_ascii=False))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
