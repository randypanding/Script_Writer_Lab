"""L-04 · AI 味词典 + 语料相对指标。产物:mined/slop_lexicon.yaml(≥100 条,每条带 PMI 值)
与 mined/metrics_registry/slop_density.yaml(五要素指标卡,ADR-0001 L-D3)。

信号定义(偏差记录,PR 内裁决):
- 我们生成物(SW out/ 的 script.md 等)与语料(剧本组)的 n-gram 频率差:
  PMI = log( (f_our + α) / (f_corpus + α) ),α=平滑;> 0 = 生成物侧过 represented = 模型腔候选;
- 语料内对照组(短剧剧本 vs 小说)的过 represented 短语:模板化"短剧腔",同入词典;
- 内置种子(SLOP_SEEDS,degrade D05 同源)以 source=seed 入册(PMI=null)。
生成物样本不足时(SW 刚起步)以对照组信号为主;runner transcripts 落地后由 --refresh 重算。
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

import yaml

from lab.degrade import SLOP_SEEDS

CJK = re.compile(r"[一-龥]{2,6}")
SMOOTH = 0.5
MIN_LEN = 2

def ngram_freqs(texts: Iterable[str]) -> Counter:
    """CJK 连续串的整串计数(2–6 字):短语级,不做滑窗(滑窗会指数放大常见字组合)。"""
    c: Counter = Counter()
    for t in texts:
        c.update(m.group(0) for m in CJK.finditer(t))
    return c

def _rate(counter: Counter, total: int) -> dict[str, float]:
    return {k: v / total for k, v in counter.items()} if total else {}

def _pmi(p_our: float, p_ref: float) -> float:
    return math.log((p_our + SMOOTH / 1e6) / (p_ref + SMOOTH / 1e6))

def load_our_texts(script_writer_out: str | Path | None = None) -> list[str]:
    """我们生成物:优先 lab.toml 指向的 SW checkout 的 out/ 下 script.md。"""
    from lab.models import ROOT
    base = Path(script_writer_out) if script_writer_out else ROOT.parent / "Script_Writer" / "out"
    texts: list[str] = []
    for p in sorted(base.rglob("script.md")):
        texts.append(p.read_text(encoding="utf-8", errors="ignore"))
    return texts

def build_lexicon(
    our_texts: list[str],
    drama_texts: list[str],
    novel_texts: list[str],
    top: int = 150,
) -> list[dict]:
    """词典条目:phrase / pmi / source(our_vs_drama | drama_vs_novel | seed)。"""
    entries: dict[str, dict] = {}

    def add(phrase: str, pmi: float, source: str, extra: dict | None = None):
        e = entries.setdefault(phrase, {"phrase": phrase, "pmi": round(pmi, 4), "source": source})
        e.update(extra or {})

    # 信号 1:我们生成物 vs 语料剧本组
    our_c = ngram_freqs(our_texts)
    our_total = sum(our_c.values())
    drama_c = ngram_freqs(drama_texts)
    drama_total = sum(drama_c.values())
    if our_total and drama_total:
        r_our, r_drama = _rate(our_c, our_total), _rate(drama_c, drama_total)
        for phrase, cnt in our_c.items():
            if cnt < 2 or len(phrase) < MIN_LEN:
                continue
            lift = _pmi(r_our[phrase], r_drama.get(phrase, 0.0))
            if lift > 0.5:
                add(phrase, lift, "our_vs_drama",
                    {"freq_our": cnt, "freq_corpus": drama_c.get(phrase, 0)})

    # 信号 2:语料内对照组(剧本 vs 小说)——模板化短剧腔
    novel_c = ngram_freqs(novel_texts)
    novel_total = sum(novel_c.values())
    if drama_total and novel_total:
        r_drama2, r_novel = _rate(drama_c, drama_total), _rate(novel_c, novel_total)
        for phrase, cnt in drama_c.items():
            if cnt < max(5, drama_total // 2_000_000):
                continue
            lift = _pmi(r_drama2[phrase], r_novel.get(phrase, 0.0))
            if lift > 1.0:
                add(phrase, lift, "drama_vs_novel",
                    {"freq_drama": cnt, "freq_novel": novel_c.get(phrase, 0)})

    # 信号 3:内置种子(D05 同源)
    for s in SLOP_SEEDS:
        entries.setdefault(s, {"phrase": s, "pmi": None, "source": "seed"})

    ranked = sorted(entries.values(),
                    key=lambda e: -(e["pmi"] if e["pmi"] is not None else 99))[:top]
    return ranked

def write_outputs(entries: list[dict], mined_dir: str | Path, n_drama: int = 0, n_novel: int = 0) -> None:
    mined = Path(mined_dir)
    (mined / "metrics_registry").mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "n_entries": len(entries),
        "entries": entries,
        "note": "AI 味词典(聚合产物,无 >50 字符原文);pmi=log((f_our+α)/(f_ref+α));"
                "source: our_vs_drama=生成物模型腔 / drama_vs_novel=模板化短剧腔 / seed=内置先验;"
                "D05_inject_slop 注入时按 per_1k_chars 带内取样合并本词典。",
    }
    (mined / "slop_lexicon.yaml").write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    # 五要素指标卡(L-D3)
    card = {
        "metric_id": "slop_density",
        "what": "每千字命中 AI 味词典的次数(生成物的'模型腔'密度)",
        "detector": "lab.slop.detect(text) -> 每 1000 非空白字符的词典命中数;词典=mined/slop_lexicon.yaml",
        "cost": "零成本(纯字符串匹配,无模型调用)",
        "anti_gaming": "词典由语料+生成物差异驱动,优化器无法靠背词典过检(语料锚随语料更新);"
                       "词典文件本身受泄漏守卫约束,不得含语料原文",
        "delivery_pitch": "'机器腔密度'——客户可感知的'AI 味'代名词,用于解释为什么这稿更像人写的",
        "baseline": None,  # L-02 bands 跑完后回填语料基线
    }
    (mined / "metrics_registry" / "slop_density.yaml").write_text(
        yaml.safe_dump(card, allow_unicode=True, sort_keys=False), encoding="utf-8")

def detect(text: str, lexicon_path: str | Path | None = None) -> float:
    """指标检测器:每千非空白字符的词典命中数。"""
    from lab.models import ROOT
    path = Path(lexicon_path) if lexicon_path else ROOT / "mined" / "slop_lexicon.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    phrases = [e["phrase"] for e in data.get("entries", []) if e.get("phrase")]
    nonws = len("".join(text.split()))
    if not nonws:
        return 0.0
    hits = sum(text.count(p) for p in phrases if len(p) >= 2)
    return round(hits * 1000 / nonws, 4)

def run(mined_dir: str | Path = "mined", store_dir: str | Path = "corpus/store",
        script_writer_out: str | Path | None = None, top: int = 150) -> dict:
    """主入口:store 语料 + SW 生成物 → 词典落盘。返回摘要。"""
    store = Path(store_dir)
    drama_texts, novel_texts = [], []
    for card_file in sorted(store.glob("card_*.json")):
        card = json.loads(card_file.read_text(encoding="utf-8"))
        tf = store / f"text_{card['script_id'].split(':')[1]}.txt"
        if not tf.exists():
            continue
        # 超长文本抽样头部即可代表短语分布(全量对 4B 字符语料不可行)
        text = tf.read_text(encoding="utf-8", errors="ignore")[:200_000]
        (drama_texts if card["kind"] == "drama_script" else novel_texts).append(text)
    our_texts = load_our_texts(script_writer_out)
    entries = build_lexicon(our_texts, drama_texts, novel_texts, top=top)
    write_outputs(entries, mined_dir, n_drama=len(drama_texts), n_novel=len(novel_texts))
    return {"entries": len(entries), "our_texts": len(our_texts),
            "drama": len(drama_texts), "novel": len(novel_texts)}

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lab.slop")
    ap.add_argument("--store", default="corpus/store")
    ap.add_argument("--mined", default="mined")
    ap.add_argument("--top", type=int, default=150)
    ap.add_argument("--sw-out", default=None, help="SW out/ 目录(缺省用 lab.toml checkout)")
    args = ap.parse_args(argv)
    report = run(args.mined, args.store, args.sw_out, args.top)
    print(json.dumps(report, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
