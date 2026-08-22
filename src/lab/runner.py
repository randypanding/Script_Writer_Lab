"""L-10/L-11/L-12 · 运行器。接口:ADR-0001 §接口(run/ab/sealed_submit)。

- run:subprocess 调 pinned SW checkout 的 `uv run nsc run/check`(AGENTS.md:禁止 import SW);
- 产物与 trace 落 out/runs/<run_id>/(stdout.log + meta.json);LLM 走 SW 侧自身的路由;
- NSC_NO_CACHE=1 开关透传(内容寻址缓存旁路);
- ab:同 brief 同种子 champion vs candidate 配对,胜率差 bootstrap CI95;
- sealed_submit:配额账本(SQLite,默认每轮 20 次,contract/objective.yaml),只回标量。
"""
from __future__ import annotations

import json
import os
import random
import sqlite3
import subprocess
import time
import tomllib
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from lab.corpus import _ulid  # 复用 ULID 生成(内容无关 ID 纪律)

ROOT = Path(__file__).parents[2]


def _lab_cfg() -> dict[str, Any]:
    with (ROOT / "lab.toml").open("rb") as f:
        return tomllib.load(f)


def sw_checkout() -> Path:
    p = Path(_lab_cfg()["paths"]["script_writer_checkout"])
    return p if p.is_absolute() else (ROOT / p).resolve()


@dataclass
class Artifact:
    run_id: str
    brief: str
    profile: str
    seed: int
    out_dir: str
    ir_path: str | None
    returncode: int
    cmd: list[str] = field(default_factory=list)


def _which_nsc(cwd: Path) -> list[str]:
    return ["uv", "run", "nsc"]


def run(brief: str | Path, config: dict[str, Any] | None = None, seed: int = 0,
        *, runner_root: str | Path | None = None, _spawn: Callable[..., subprocess.CompletedProcess] | None = None,
        sw_dir: Path | None = None) -> Artifact:
    """一个 brief 一次 run。config: {profile, rerank, no_retrieval, no_cache, env, check}。"""
    config = config or {}
    cwd = Path(config.get("sw_dir")) if config.get("sw_dir") else (sw_dir or sw_checkout())
    run_id = _ulid()  # 时间+随机 ULID:run 记录天然时序可查
    out_root = Path(runner_root) if runner_root else (ROOT / "out" / "runs")
    out_dir = out_root / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    brief_path = Path(brief)
    if not brief_path.is_absolute():
        brief_path = (ROOT / brief).resolve()
    cmd = [*_which_nsc(cwd), "run", str(brief_path), "--out", str(out_dir / "sw")]
    if config.get("profile"):
        cmd += ["--profile", str(config["profile"])]
    if config.get("rerank"):
        cmd.append("--rerank")
    if config.get("no_retrieval"):
        cmd.append("--no-retrieval")

    env = {**os.environ, "NSC_SEED": str(seed)}
    if config.get("no_cache") or os.environ.get("NSC_NO_CACHE") == "1":
        env["NSC_NO_CACHE"] = "1"
    for k, v in (config.get("env") or {}).items():
        env[k] = str(v)

    spawn = _spawn or subprocess.run
    proc = spawn(cmd, cwd=str(cwd), env=env, capture_output=True, text=True,
                 timeout=config.get("timeout", 1800))
    (out_dir / "stdout.log").write_text(
        f"$ {' '.join(cmd)}\n--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}",
        encoding="utf-8")

    ir_path = None
    sw_out = out_dir / "sw"
    if sw_out.exists():
        cands = sorted(sw_out.rglob("ir.json"))
        if cands:
            ir_path = str(cands[-1])
            if config.get("check", True):
                chk = spawn([*_which_nsc(cwd), "check", ir_path, "--fmt", "json"],
                            cwd=str(cwd), env=env, capture_output=True, text=True, timeout=300)
                (out_dir / "check.json").write_text(
                    chk.stdout + ("\n--stderr--\n" + chk.stderr if chk.stderr else ""),
                    encoding="utf-8")

    art = Artifact(run_id=run_id, brief=str(brief_path), profile=str(config.get("profile", "")),
                   seed=seed, out_dir=str(out_dir), ir_path=ir_path, returncode=proc.returncode,
                   cmd=cmd)
    (out_dir / "meta.json").write_text(json.dumps(asdict(art), ensure_ascii=False, indent=1),
                                       encoding="utf-8")
    return art


def episode_text(artifact: Artifact) -> str:
    """从产物抽可比文本(剧本正文)。SW IR 是扁平结构(lines 顶层数组按 parent_id
    关联),按 order 取全部台词行;兼容嵌套形态。"""
    if not artifact.ir_path:
        return ""
    ir = json.loads(Path(artifact.ir_path).read_text(encoding="utf-8"))
    if ir.get("lines"):
        return "\n".join(str(ln.get("text", "")).strip() for ln in
                         sorted(ir["lines"], key=lambda l: l.get("order", 0))
                         if str(ln.get("text", "")).strip())
    parts: list[str] = []
    for ep in ir.get("episodes", []):
        for sc in ep.get("scenes", []):
            parts.extend(str(x) for x in sc.get("lines", sc.get("beats", [])))
    return "\n".join(p for p in parts if p)


# ---- L-11 · 配对 A/B ----

@dataclass
class ABReport:
    n_pairs: int
    wins: int
    losses: int
    ties: int
    winrate: float
    ci95: tuple[float, float]
    per_pair: list[dict[str, Any]] = field(default_factory=list)


def ab(candidate_cfg: dict[str, Any], champion_cfg: dict[str, Any],
       briefs: list[str | Path], seeds: list[int],
       *, judge: Callable[[str, str], tuple[float, float]] | None = None,
       _run_fn: Callable = run, runner_root: str | Path | None = None) -> ABReport:
    """同 brief 同种子配对;judge(a_text, b_text) -> (score_a, score_b),缺省 dev 判官。"""
    if judge is None:
        from lab.judgekit import make_client, score_pair
        model, client = make_client("judge_dev")
        locked = {"client": client, "model": model, "k": 5}

        def judge(a: str, b: str) -> tuple[float, float]:
            v = score_pair(a, b, "prose_craft", locked)
            return v.score_a, v.score_b
    results: list[dict[str, Any]] = []
    for brief in briefs:
        for seed in seeds:
            cham = _run_fn(brief, champion_cfg, seed, runner_root=runner_root)
            cand = _run_fn(brief, candidate_cfg, seed, runner_root=runner_root)
            ta, tb = episode_text(cham), episode_text(cand)
            if not ta or not tb:
                results.append({"brief": str(brief), "seed": seed, "outcome": "invalid",
                                "reason": "产物无可比文本", "cham_run": cham.run_id,
                                "cand_run": cand.run_id})
                continue
            sa, sb = judge(ta, tb)
            outcome = "win" if sb > sa else ("loss" if sb < sa else "tie")
            results.append({"brief": str(brief), "seed": seed, "outcome": outcome,
                            "score_champion": sa, "score_candidate": sb,
                            "cham_run": cham.run_id, "cand_run": cand.run_id})
    valid = [r for r in results if r["outcome"] in {"win", "loss", "tie"}]
    wins = sum(r["outcome"] == "win" for r in valid)
    losses = sum(r["outcome"] == "loss" for r in valid)
    ties = sum(r["outcome"] == "tie" for r in valid)
    n = len(valid)
    # 胜率 = (wins + 0.5*ties)/n;tie 记半胜(标准惯例,report 里注明)
    scores = [1.0 if r["outcome"] == "win" else (0.5 if r["outcome"] == "tie" else 0.0)
              for r in valid]
    winrate = (wins + 0.5 * ties) / n if n else 0.0
    lo, hi = bootstrap_ci95(scores)
    return ABReport(n, wins, losses, ties, round(winrate, 4), (round(lo, 4), round(hi, 4)), results)


def bootstrap_ci95(scores: list[float], n_boot: int = 10_000, seed: int = 7) -> tuple[float, float]:
    """胜率的 bootstrap 95% 置信区间(percentile 法)。"""
    if not scores:
        return (0.0, 0.0)
    rng = random.Random(seed)
    n = len(scores)
    means = sorted(sum(rng.choice(scores) for _ in range(n)) / n for _ in range(n_boot))
    return means[int(0.025 * n_boot)], means[int(0.975 * n_boot) - 1]


# ---- L-12 · sealed 提交(配额账本,只回标量) ----

def _ledger_path(override: str | Path | None = None) -> Path:
    return Path(override) if override else ROOT / "out" / "sealed_ledger.db"


def _quota() -> int:
    cfg = yaml.safe_load((ROOT / "contract" / "objective.yaml").read_text(encoding="utf-8"))
    return int(cfg["resources"]["sealed_quota_per_round"])


def _round_key(ts: float | None = None) -> str:
    """实验轮 = ISO 周(周一起始);一周内配额 20。"""
    import datetime
    return (datetime.datetime.fromtimestamp(ts or time.time(), datetime.UTC)).strftime("%G-W%V")


def sealed_submit(candidate: dict[str, Any], *, ledger: str | Path | None = None,
                  score_fn: Callable[[dict[str, Any]], float] | None = None) -> float:
    """提交候选给 sealed 判官;只回标量分。超配额抛 RuntimeError。

    score_fn 注入点:缺省走真实 sealed 判官(需要 key);测试/演练注入 mock。
    """
    db = _ledger_path(ledger)
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    try:
        con.execute("""CREATE TABLE IF NOT EXISTS submits
                       (ts REAL, round TEXT, experiment_id TEXT, candidate_sha TEXT, score REAL)""")
        rk = _round_key()
        used = con.execute("SELECT COUNT(*) FROM submits WHERE round=?", (rk,)).fetchone()[0]
        quota = _quota()
        if used >= quota:
            raise RuntimeError(f"sealed 配额已用尽:{used}/{quota}(本轮 {rk});等下一轮或人类提额")
        if score_fn is None:
            from lab.judgekit import make_client, run_exam  # noqa: F401  真实路径:sealed 判官
            raise RuntimeError("sealed 真实打分需要 judge_sealed API key;演练请注入 score_fn")
        score = float(score_fn(candidate))
        con.execute("INSERT INTO submits VALUES (?,?,?,?,?)",
                    (time.time(), rk, str(candidate.get("experiment_id", "")),
                     str(candidate.get("sha", "")), score))
        con.commit()
    finally:
        con.close()
    return score


def ledger_usage(ledger: str | Path | None = None) -> dict[str, int]:
    con = sqlite3.connect(_ledger_path(ledger))
    try:
        rows = con.execute("SELECT round, COUNT(*) FROM submits GROUP BY round").fetchall()
        return {r: c for r, c in rows}
    finally:
        con.close()


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "usage":
        print(json.dumps(ledger_usage(), ensure_ascii=False))
