"""L-15 · 观测面板。ADR-0001 L-D6 五面板固定结构,`lab report` 生成 dashboards/latest.md。

数据源:实验台账(SQLite,lab.record_experiment 写入)+ sealed 账本 + 判官考试报告。
没有数据的面板渲染为"无数据"占位——空面板也是信息(哪一层断供一眼可见)。
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Any

from lab.models import ROOT

PANELS = ("sealed_winrate", "dev_sealed_divergence", "corpus_blind_winrate",
          "degradation_detection", "accept_reject_ratio")

LEDGER_SCHEMA = """
CREATE TABLE IF NOT EXISTS experiments (
    round INTEGER, ts REAL, kind TEXT, surface TEXT, hypothesis TEXT,
    decision TEXT, winrate REAL, ci_lo REAL, ci_hi REAL, sealed_score REAL,
    notes TEXT
)
"""


def record_experiment(db_path: str | Path, row: dict[str, Any]) -> None:
    db = Path(db_path)
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    try:
        con.execute(LEDGER_SCHEMA)
        con.execute("INSERT INTO experiments VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
            row.get("round"), row.get("ts"), row.get("kind", "ab"), row.get("surface"),
            row.get("hypothesis"), row.get("decision"), row.get("winrate"),
            row.get("ci_lo"), row.get("ci_hi"), row.get("sealed_score"), row.get("notes")))
        con.commit()
    finally:
        con.close()


def _rows(db_path: str | Path) -> list[dict[str, Any]]:
    p = Path(db_path)
    if not p.exists():
        return []
    con = sqlite3.connect(p)
    con.row_factory = sqlite3.Row
    try:
        con.execute(LEDGER_SCHEMA)
        return [dict(r) for r in con.execute("SELECT * FROM experiments ORDER BY round, ts")]
    finally:
        con.close()


def render(db_path: str | Path, out_path: str | Path | None = None,
           exam_report: str | Path | None = None) -> Path:
    """五面板 dashboard → dashboards/latest.md。返回产物路径。"""
    out = Path(out_path) if out_path else ROOT / "dashboards" / "latest.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = _rows(db_path)

    def by(kind: str) -> list[dict[str, Any]]:
        return [r for r in rows if r.get("kind") == kind]

    lines = ["# Lab 观测面板(latest)", ""]

    # 面板 1:sealed 对 champion 胜率轨迹(唯一主指标)
    lines += ["## 1. sealed 胜率轨迹(主指标)", ""]
    sealed_rows = [r for r in by("ab") if r.get("sealed_score") is not None]
    if sealed_rows:
        lines += ["| 轮 | 胜率 | CI95 | sealed |", "|---|---|---|---|"]
        lines += [f"| {r['round']} | {r['winrate']} | [{r['ci_lo']}, {r['ci_hi']}] | {r['sealed_score']} |"
                  for r in sealed_rows]
        latest = sealed_rows[-1]
        verdict = "✅ CI 下界 > 0" if (latest["ci_lo"] or 0) > 0 else "❌ CI 下界 ≤ 0(回滚)"
        lines += ["", f"**最新轮 {latest['round']}:{verdict}**"]
    else:
        lines += ["_无数据(sealed 确认尚未发生;bootstrap 带需 ≥ 12 briefs,见 promotion.yaml)_"]

    # 面板 2:dev 与 sealed 趋势背离警报
    lines += ["", "## 2. dev/sealed 背离警报", ""]
    div = [r for r in by("ab") if r.get("sealed_score") is not None
           and r.get("winrate") is not None]
    alarms = [r for r in div if abs((r["sealed_score"] or 0) - (r["winrate"] or 0)) > 0.15]
    if div:
        lines += [f"- 有 sealed 对比的轮次:{len(div)};背离(|sealed-dev|>0.15):**{len(alarms)}**"]
        for r in alarms:
            lines += [(f"  - 轮 {r['round']}:dev={r['winrate']} sealed={r['sealed_score']}"
                      "(dev 疑似被过拟合,降权 dev 反馈)")]
        if not alarms:
            lines += ["- 无背离,dev 反馈可信"]
    else:
        lines += ["_无数据_"]

    # 面板 3:语料盲测胜率趋势
    lines += ["", "## 3. 语料盲测胜率", ""]
    blind = by("blind_corpus")
    if blind:
        lines += ["| 轮 | 盲测胜率 |", "|---|---|"]
        lines += [f"| {r['round']} | {r['winrate']} |" for r in blind if r.get("winrate") is not None]
        rising = [r["winrate"] for r in blind if r.get("winrate") is not None]
        if len(rising) >= 2 and rising[-1] <= rising[0]:
            lines += ["", "**⚠️ 内部指标涨而盲测不涨 = 指标腐坏嫌疑(L-D6 面板 3 定义)**"]
    else:
        lines += ["_无数据(语料盲测 = select PPT 对打语料样本;判官闸门 ON 后开始)_"]

    # 面板 4:退化检出率(判官健康度)
    lines += ["", "## 4. 退化检出率(判官健康度)", ""]
    exam_path = Path(exam_report) if exam_report else ROOT / "dashboards" / "judge_exam.md"
    if exam_path.exists():
        text = exam_path.read_text(encoding="utf-8")
        # 从判官考试报告抽灵敏度列
        import re
        rowsmd = re.findall(r"^\| (\S+) \| \d+ \| ([\d.]+) \|", text, flags=re.MULTILINE)
        if rowsmd:
            worst = min(float(v) for _, v in rowsmd)
            lines += [f"- 考试报告:{exam_path.name};最差轴灵敏度:**{worst}**"
                      + ("(低于 0.85 = 判官被绕过,关闸)" if worst < 0.85 else " ✅")]
        else:
            lines += [f"- 考试报告存在但未解析出灵敏度表:{exam_path.name}"]
    else:
        lines += ["_无数据(判官考试未跑;闸门 OFF 期间一切分数仅报告不生效)_"]

    # 面板 5:实验接受/拒绝比
    lines += ["", "## 5. 接受/拒绝比(健康带 30–70% 接受)", ""]
    decisions = [r["decision"] for r in by("ab") if r.get("decision")]
    if decisions:
        acc = sum(d and d.startswith("accepted") or d == "promoted" for d in decisions)
        ratio = acc / len(decisions)
        flag = ("✅ 带内" if 0.3 <= ratio <= 0.7 else
                ("⚠️ 100% 接受=作弊或噪声" if ratio == 1.0 else "⚠️ 接受率过低(过度保守或判官太严)"))
        lines += [f"- 总轮次 {len(decisions)},接受 {acc},比例 {ratio:.0%} {flag}"]
    else:
        lines += ["_无数据_"]

    # 附:实验台账 SQL
    lines += ["", "## 附:实验台账(最近 20 行)", ""]
    if rows:
        lines += ["```sql"]
        con = sqlite3.connect(Path(db_path))
        try:
            for r in con.execute("SELECT round, ts, kind, surface, decision, winrate, ci_lo, ci_hi, "
                                 "sealed_score FROM experiments ORDER BY ts DESC LIMIT 20"):
                lines.append(str(r))
        finally:
            con.close()
        lines += ["```"]
    else:
        lines += ["_台账为空_"]

    lines += ["", "> 面板结构是契约(ADR-0001 L-D6);本文件由 `lab report` 生成,勿手改。"]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lab.report")
    ap.add_argument("--db", default=str(ROOT / "out" / "lab.db"))
    ap.add_argument("--out", default=None)
    ap.add_argument("--exam", default=None)
    args = ap.parse_args(argv)
    p = render(args.db, args.out, args.exam)
    print(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
