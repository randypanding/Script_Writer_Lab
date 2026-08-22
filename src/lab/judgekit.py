"""L-07 · 判官工具箱。**打分内核一律复用官方包 llm_verifier,禁止自造**(ADR-0001 L-D4;
docs/VERIFIER_IMPLEMENTATION.md)。本模块只做:封装/路由/transcript/考试。

- score_pair = 两次有向 compare 取平均(去槽位偏差,对应 SW position_swap 纪律);
- best-of-n / 语料盲测排名 = llm_verifier.select(PPT);
- criteria = criteria/<axis>.md 每轴一份信号级子问题(拆解后再聚合,L-D4 子信号分解);
- ground_truth_note 永远不用(考试时喂 GT 等于泄题);
- 端点不支持 logprobs 时降级 k_sample_vote(contract/judges.yaml::scoring_fallback),
  降级路径有单测;
- 所有调用经 lab.models 的客户端工厂 + RecordingClient 写 transcript。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from lab.models import ROOT, _db_path, _resolve_client, _write_transcript

CRITERIA_DIR = ROOT / "criteria"
AXES = ("naturalness", "hook_strength", "placement_integration", "transportation",
        "producibility", "prose_craft", "l0_structure", "l0_fact", "l0_brand", "l0_dialogue")
BLOCK_OPS = ("D07_pov_break", "D08_inject_contradiction", "D09_brand_cut", "D14_setup_cut")


class _RecordingCompletions:
    def __init__(self, inner: Any, model: str, db_path: Path | None, caller: str):
        self._inner, self._model, self._db, self._caller = inner, model, db_path, caller

    def create(self, **kw):
        resp = self._inner.create(**kw)
        prompt = json.dumps(kw.get("messages", []), ensure_ascii=False)
        text = resp.choices[0].message.content or ""
        usage = getattr(resp, "usage", None)
        _write_transcript(self._db, (
            time.time(), self._caller, str(kw.get("model", self._model)), prompt, text,
            getattr(usage, "prompt_tokens", 0) or 0,
            getattr(usage, "completion_tokens", 0) or 0, 0.0, ""))
        return resp


class _RecordingChat:
    def __init__(self, inner: Any, model: str, db_path: Path | None, caller: str):
        self.completions = _RecordingCompletions(inner.completions, model, db_path, caller)


class RecordingClient:
    """把 llm_verifier 内部的每笔调用落 transcript(AGENTS.md 硬约束)。"""

    def __init__(self, inner: Any, model: str, db_path: Path | None = None, caller="lab.judgekit"):
        self.chat = _RecordingChat(inner.chat, model, db_path or _db_path(), caller)


def make_client(model_slot: str, db_path: str | Path | None = None) -> tuple[str, Any]:
    """槽位 → (model, RecordingClient)。缺 key 时抛 RuntimeError(与 lab.models 一致)。"""
    model, client = _resolve_client(model_slot)
    return model, RecordingClient(client, model, _db_path(db_path) if db_path else None)


def load_criteria(axis: str) -> dict[str, str]:
    """criteria/<axis>.md → {信号名: 信号级子问题}。"""
    path = CRITERIA_DIR / f"{axis}.md"
    if not path.exists():
        raise FileNotFoundError(f"缺 criteria/{axis}.md(判官考试与打分都以它为准)")
    text = path.read_text(encoding="utf-8")
    out: dict[str, str] = {}
    for block in re.split(r"\n(?=## )", text):
        m = re.match(r"^## (.+)$", block.strip(), flags=re.MULTILINE)
        if not m:
            continue
        name = m.group(1).strip()
        desc = re.sub(r"^## .+?\n", "", block.strip()).strip()
        if desc:
            out[name] = desc
    if not out:
        raise ValueError(f"criteria/{axis}.md 无信号段(需要 '## 信号名' 小节)")
    return out


def axis_problem(axis: str) -> str:
    """compare 的 problem 槽:轴定义 + 判分对象说明(不含任何答案信息)。"""
    header = {
        "naturalness": "自然度:对白像真人说话吗", "hook_strength": "钩子强度:开头抓人/结尾留钩吗",
        "placement_integration": "植入融合:商业信息融进剧情吗", "transportation": "代入感:信息给送顺畅吗",
        "producibility": "可拍性:制作元素在预算内吗", "prose_craft": "文笔:句法节奏与用词质量",
        "l0_structure": "结构合规:视角/伏笔承接/beat 顺序", "l0_fact": "事实一致性:无硬矛盾",
        "l0_brand": "品牌合规:必覆盖卖点齐全", "l0_dialogue": "对白占比:对白驱动叙事",
    }
    return (f"你是短剧质量判官。比较两段短剧文本,轴:「{axis}」({header.get(axis, axis)})。"
            "按信号级子问题分别评估两段,再给 1-20 刻度的细粒度分。")


@dataclass
class Verdict:
    axis: str
    score_a: float
    score_b: float
    k: int
    engine: str          # llm_verifier.compare | k_sample_vote
    n_api_calls: int
    fallback_reason: str = ""


def score_pair(a_text: str, b_text: str, axis: str, judge_cfg: dict[str, Any]) -> Verdict:
    """(A,B)+(B,A) 两次有向 compare 取平均。logprobs 不可用 → k_sample_vote 降级。"""
    import llm_verifier as lv

    k = int(judge_cfg.get("k", 5))
    if "client" in judge_cfg:
        client = judge_cfg["client"]
        model = judge_cfg.get("model") or "judge"
    else:
        model, client = make_client(judge_cfg["model_slot"], judge_cfg.get("db_path"))
    criteria = judge_cfg.get("criteria") or load_criteria(axis)
    problem = judge_cfg.get("problem") or axis_problem(axis)
    try:
        ra1, rb1 = lv.compare(problem, a_text, b_text, criteria=criteria,
                              n_evaluations=k, model=model, client=client)
        ra2, rb2 = lv.compare(problem, b_text, a_text, criteria=criteria,
                              n_evaluations=k, model=model, client=client)
        if (ra1, rb1) == (0.5, 0.5) and (ra2, rb2) == (0.5, 0.5):
            # OpenAI 兼容端点不支持 vLLM prefill 也不吐可解析标签时,内核静默返回
            # 全 0.5(dashscope 实测风险,VERIFIER_IMPLEMENTATION §后端要求)→ 视同失败
            raise RuntimeError("degenerate scores: endpoint returns unparseable 0.5 everywhere")
        score_a = (ra1 + rb2) / 2
        score_b = (rb1 + ra2) / 2
        return Verdict(axis, score_a, score_b, k, "llm_verifier.compare",
                       n_api_calls=2 * k * max(1, len(criteria)))
    except (RuntimeError, OSError, ValueError, KeyError, TypeError) as exc:
        # 端点不支持 logprobs / 客户端报错 → 降级路径(contract/judges.yaml::scoring_fallback)
        return _k_sample_vote(a_text, b_text, axis, judge_cfg, reason=str(exc)[:200])


def _k_sample_vote(a_text: str, b_text: str, axis: str, judge_cfg: dict[str, Any],
                   reason: str) -> Verdict:
    """降级打分:k 次多数投票(双向),无 logprobs 也能出 [0,1] 相对分。"""
    from lab.models import route

    k = int(judge_cfg.get("k", 5))
    db = judge_cfg.get("db_path")
    votes_a = 0
    n = 0
    for i in range(k):
        for first, second, first_is_a in ((a_text, b_text, True), (b_text, a_text, False)):
            prompt = (f"比较两段短剧文本在轴「{axis}」上的质量。只回答一个字母:更好的是第一段(A)"
                      f"还是第二段(B)?\n\n第一段:\n{first[:2000]}\n\n第二段:\n{second[:2000]}\n\n只答 A 或 B。")
            ans = route(judge_cfg["model_slot"], prompt, caller="lab.judgekit.vote",
                        db_path=db, temperature=1.0)
            n += 1
            pick_first = ans.strip().upper().startswith("A")
            if pick_first == first_is_a:
                votes_a += 1
    total = 2 * k
    return Verdict(axis, votes_a / total, 1 - votes_a / total, k, "k_sample_vote",
                   n_api_calls=n, fallback_reason=reason)


def select_best(problem: str, candidates: list[str], axis: str, judge_cfg: dict[str, Any],
                cache_dir: str | Path | None = None) -> Any:
    """best-of-n / 语料盲测排名:llm_verifier.select(PPT,O(Nk) 成对 + Bradley-Terry)。"""
    import llm_verifier as lv

    if "client" in judge_cfg:
        client, model = judge_cfg["client"], judge_cfg.get("model") or "judge"
    else:
        model, client = make_client(judge_cfg["model_slot"], judge_cfg.get("db_path"))
    cache = str(Path(cache_dir)) if cache_dir else None
    if cache:
        Path(cache).parent.mkdir(parents=True, exist_ok=True)
    return lv.select(problem, candidates, criteria=load_criteria(axis),
                     n_evaluations=int(judge_cfg.get("k", 4)),
                     pivots=int(judge_cfg.get("pivots", 2)),
                     seed=int(judge_cfg.get("seed", 0)),
                     model=model, client=client, cache=cache)


# ---- L-08 · 判官考试(contract/judges.yaml §exam) ----

def _gate_cfg() -> dict[str, Any]:
    path = ROOT / "contract" / "judges.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def run_exam(judge_cfg: dict[str, Any], exam_pairs: list[dict[str, Any]],
             other_judge_cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """对照 contract/judges.yaml::exam 五门限出 pass/fail。

    exam_pairs 来自 lab.pairs(split=exam,label 由构造保证)。
    每轴:灵敏度(原版>退化版)/ block 类灵敏度 / 位置偏差(交换后判罚翻转率)/
    传递性(同脚本同算子两档强度的三元组)/ 样本量;双判官时算跨族一致率。
    """
    gates = _gate_cfg()["exam"]
    by_axis: dict[str, list[dict[str, Any]]] = {}
    for p in exam_pairs:
        by_axis.setdefault(p["axis"], []).append(p)

    report: dict[str, Any] = {"axes": {}, "gates": gates, "judge": judge_cfg.get("model_slot")}
    for axis, pairs in sorted(by_axis.items()):
        n = len(pairs)
        correct = flips = 0
        block_pairs = [p for p in pairs if p["construction"].get("op_id", "").startswith(
            tuple(op.split("_")[0] for op in BLOCK_OPS))]
        block_correct = 0
        verdicts: list[tuple[float, float]] = []
        for p in pairs:
            a, b = p["a_text"], p["b_text"]
            v1 = score_pair(a, b, axis, judge_cfg)
            verdicts.append((v1.score_a, v1.score_b))
            ok = v1.score_a > v1.score_b
            correct += ok
            if p["construction"].get("op_id") in BLOCK_OPS:
                block_correct += ok
            v2 = score_pair(b, a, axis, judge_cfg)  # 位置交换
            flips += (v2.score_a > v2.score_b)  # 交换后退化版胜 = 位置偏差事件
        sensitivity = correct / n if n else 0.0
        block_sensitivity = (block_correct / len(block_pairs)) if block_pairs else None
        position_bias = flips / n if n else 1.0
        transitivity = _transitivity(pairs, axis, judge_cfg)
        axis_report = {
            "n_pairs": n,
            "sensitivity": round(sensitivity, 4),
            "block_sensitivity": round(block_sensitivity, 4) if block_sensitivity is not None else None,
            "position_bias": round(position_bias, 4),
            "transitivity": transitivity,
            "pass": (
                n >= gates["min_exam_pairs_per_axis"]
                and sensitivity >= gates["degradation_sensitivity"]
                and (block_sensitivity is None or block_sensitivity >= gates["block_defect_sensitivity"])
                and position_bias <= gates["position_bias"]
                and (transitivity is None or transitivity >= gates["transitivity"])
            ),
        }
        report["axes"][axis] = axis_report

    if other_judge_cfg is not None:
        agree = total = 0
        for axis, pairs in sorted(by_axis.items()):
            for p in pairs:
                v1 = score_pair(p["a_text"], p["b_text"], axis, judge_cfg)
                v2 = score_pair(p["a_text"], p["b_text"], axis, other_judge_cfg)
                total += 1
                agree += ((v1.score_a > v1.score_b) == (v2.score_a > v2.score_b))
        report["cross_family_agreement"] = round(agree / total, 4) if total else None
        report["pass"] = (all(a["pass"] for a in report["axes"].values())
                          and report["cross_family_agreement"] is not None
                          and report["cross_family_agreement"] >= gates["cross_family_agreement"])
    else:
        report["pass"] = bool(report["axes"]) and all(a["pass"] for a in report["axes"].values())
    return report


def _transitivity(pairs: list[dict[str, Any]], axis: str, judge_cfg: dict[str, Any]) -> float | None:
    """同源同算子两档强度的三元组:orig>mid 与 mid>strong 都成立时 orig>strong 必须成立。"""
    from collections import defaultdict

    groups: dict[tuple[str, str], dict[float, dict[str, Any]]] = defaultdict(dict)
    for p in pairs:
        c = p["construction"]
        if c.get("kind") != "corpus_degraded":
            continue
        groups[(c.get("source_script_id", ""), c.get("op_id", ""))][c.get("severity", 0)] = p
    checked = consistent = 0
    for by_sev in groups.values():
        sevs = sorted(by_sev)
        if len(sevs) < 2:
            continue
        mid_p, strong_p = by_sev[sevs[0]], by_sev[sevs[-1]]
        # 链:orig > mid(弱退化)且 mid > strong(强退化)⇒ 检查 orig > strong
        vm = score_pair(mid_p["a_text"], mid_p["b_text"], axis, judge_cfg)
        vms = score_pair(mid_p["b_text"], strong_p["b_text"], axis, judge_cfg)
        if not (vm.score_a > vm.score_b and vms.score_a > vms.score_b):
            continue  # 前提不成立,不计入
        vo = score_pair(strong_p["a_text"], strong_p["b_text"], axis, judge_cfg)
        checked += 1
        consistent += vo.score_a > vo.score_b
    return round(consistent / checked, 4) if checked else None


def render_exam_md(report: dict[str, Any], out_path: str | Path) -> None:
    lines = [
        "# 判官考试报告(judge_exam)", "",
        f"- 判官槽位:{report.get('judge')}",
        f"- **结论:{'PASS ✅(判官闸门 ON)' if report.get('pass') else 'FAIL ❌(闸门保持 OFF,该轴降级仅报告)'}**",
        "", "| 轴 | n | 灵敏度 | block 灵敏度 | 位置偏差 | 传递性 | pass |",
        "|---|---|---|---|---|---|---|",
    ]
    for axis, a in sorted(report.get("axes", {}).items()):
        lines.append(
            f"| {axis} | {a['n_pairs']} | {a['sensitivity']} | "
            f"{a['block_sensitivity'] if a['block_sensitivity'] is not None else '—'} | "
            f"{a['position_bias']} | {a['transitivity'] if a['transitivity'] is not None else '—'} | "
            f"{'✅' if a['pass'] else '❌'} |")
    if report.get("cross_family_agreement") is not None:
        lines += ["", f"- 跨族一致率:{report['cross_family_agreement']}"]
    lines += ["", "> 门限:contract/judges.yaml §exam;全部通过才准出分(ADR-0001 L-D4)。"]
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lab.judgekit")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("exam", help="判官考试(exam split 偏好对 → 报告)")
    ex.add_argument("--pairs", default="out/pairs/exam.jsonl")
    ex.add_argument("--slot", default="judge_dev")
    ex.add_argument("--sealed-slot", default=None, help="同时跑 sealed 判官算跨族一致率")
    ex.add_argument("--k", type=int, default=5)
    ex.add_argument("--out", default="dashboards/judge_exam.md")
    ex.add_argument("--limit", type=int, default=0, help="每轴截断(冒烟用;正式考试须 0)")
    args = ap.parse_args(argv)
    pairs = [json.loads(ln) for ln in Path(args.pairs).read_text(encoding="utf-8").splitlines() if ln]
    if args.limit:
        by_axis: dict[str, list] = {}
        for p in pairs:
            by_axis.setdefault(p["axis"], []).append(p)
        pairs = [p for ax, ps in by_axis.items() for p in ps[: args.limit]]
    cfg = {"model_slot": args.slot, "k": args.k}
    other = {"model_slot": args.sealed_slot, "k": args.k} if args.sealed_slot else None
    report = run_exam(cfg, pairs, other)
    render_exam_md(report, args.out)
    print(json.dumps(report, ensure_ascii=False)[:2000])
    return 0 if report.get("pass") else 1


if __name__ == "__main__":
    sys.exit(main())
