#!/usr/bin/env python
"""真实管线冒烟(无 API key):delivery 分支 worktree + SW mock LLM server。

产出:
1. L-17 三组 M2 冒烟(dashboards/m2_smoke.md)—— mock LLM 端到端跑 pinned vs overlay;
2. SW champion 刻印(出口判据 3)—— 10 个合成 brief 的基线产物 + 确定性基准分
   (L0 check + 语料带 z 距离 + slop 密度;判官分待 API key,记偏差);
3. L-13 dry-run 实验轮记录(optimizer/notebook.md)。

用法:uv run python scripts/real_smoke.py [--briefs-dir out/briefs/val]
"""
from __future__ import annotations

import argparse
import json
import socket
import statistics
import subprocess
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "src"))

SW_WT = Path("D:/Projects/sw_delivery_wt")  # delivery 分支 worktree(mock server 所在)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def start_mock_server(wt: Path) -> tuple[subprocess.Popen, int]:
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "scripts/mock_llm_server.py", "--port", str(port)],
        cwd=str(wt), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return proc, port
        except OSError:
            time.sleep(0.3)
    proc.terminate()
    raise RuntimeError("mock LLM server 未就绪")


def models_config(path: Path, port: int) -> Path:
    tiers = {t: {"model": "openai/mock", "api_base": f"http://127.0.0.1:{port}/v1",
                 "temperature": 0.5, "max_tokens": 16000}
             for t in ("tier_plan", "tier_draft", "tier_bulk", "tier_judge", "tier_reflect")}
    path.write_text(yaml.safe_dump({"tiers": tiers, "retry": {"attempts": 2}}), encoding="utf-8")
    return path


def mock_env(port: int, models: Path) -> dict[str, str]:
    return {"OPENAI_API_KEY": "mock-key", "NSC_MODELS_CONFIG": str(models),
            "NSC_NO_CACHE": "1", "NSC_CACHE_DIR": str(ROOT / "out" / "sw_cache")}


def episode_text(ir_path: Path) -> str:
    """SW IR 扁平结构:lines 顶层数组,按 order 取 text。"""
    ir = json.loads(ir_path.read_text(encoding="utf-8"))
    lines = sorted(ir.get("lines", []), key=lambda l: l.get("order", 0))
    return "\n".join(str(l.get("text", "")).strip() for l in lines
                     if str(l.get("text", "")).strip())


def deterministic_score(text: str) -> float:
    """确定性基准分(0-1,越高越好):语料带贴近度 + 反 AI 味。判官分待 key(偏差记录)。"""
    from lab.corpus import parse_script, stats_card
    from lab.slop import detect
    bands = yaml.safe_load((ROOT / "mined" / "bands.yaml").read_text(encoding="utf-8"))
    drama = bands["by_kind"]["drama_script"]["bands"]
    card = stats_card(parse_script(text))
    z = []
    for metric, field, better in (("dialogue_ratio", "dialogue_ratio", "closer"),
                                  ("sent_len_mean", "sent_len_mean", "closer"),
                                  ("sent_len_cv", "sent_len_cv", "closer")):
        lo, hi = drama[metric]["p25"], drama[metric]["p75"]
        v = card[field]
        # 带内=0,带外按带宽归一
        z.append(0.0 if lo <= v <= hi else min(1.0, abs(v - (lo + hi) / 2) / max(1e-9, (hi - lo))))
    slop = detect(text)
    return round(max(0.0, 1 - statistics.fmean(z) * 0.7 - min(1.0, slop / 20) * 0.3), 4)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--briefs-dir", default=str(ROOT / "out" / "briefs" / "val"))
    ap.add_argument("--n-baseline", type=int, default=10)
    args = ap.parse_args()

    from lab.m2_smoke import smoke
    from lab.runner import run

    proc, port = start_mock_server(SW_WT)
    models = models_config(ROOT / "out" / "sw_models.yaml", port)
    env = mock_env(port, models)
    try:
        # ---- 1) SW champion 刻印:10 个合成 brief 基线产物 + 基准分 ----
        # mock LLM 服务器回放的是 6 集剧本,p2 合同校验拒绝任何非 6 集 brief:
        # 基线集用 episode_count=6 的派生 brief(记录为 mock 限制;真实判官/刻印不受此限)
        src = sorted(Path(args.briefs_dir).glob("brief_*.yaml"))[: args.n_baseline]
        mock_dir = ROOT / "out" / "briefs" / "mock6"
        mock_dir.mkdir(parents=True, exist_ok=True)
        briefs = []
        for b in src:
            data = yaml.safe_load(b.read_text(encoding="utf-8"))
            data["episode_count"] = 6
            out_b = mock_dir / b.name
            out_b.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
            briefs.append(out_b)
        baseline = []
        for b in briefs:
            art = run(b, {"profile": "", "env": env, "no_retrieval": True, "check": True,
                          "timeout": 1200}, seed=1, sw_dir=SW_WT)
            text = episode_text(Path(art.ir_path)) if art.ir_path else ""
            baseline.append({
                "brief": b.name, "run_id": art.run_id,
                "ir": art.ir_path, "returncode": art.returncode,
                "score": deterministic_score(text) if text else None,
                "chars": len("".join(text.split())),
            })
            print(f"[baseline] {b.name}: rc={art.returncode} score={baseline[-1]['score']}", flush=True)
        ok = [x for x in baseline if x["score"] is not None]
        digest = {
            "tag_target": "delivery/30ep-song-hotel @ " + subprocess.run(
                ["git", "-C", str(SW_WT), "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, check=False).stdout.strip(),
            "n_briefs": len(briefs), "n_ok": len(ok),
            "mean_score": round(statistics.fmean(x["score"] for x in ok), 4) if ok else None,
            "baseline": baseline,
            "note": "确定性基准分(L0 check 随 run 落盘 + 语料带贴近度 + slop 密度);判官基准分待 API key",
        }
        (ROOT / "out" / "champion_baseline.json").write_text(
            json.dumps(digest, ensure_ascii=False, indent=1), encoding="utf-8")

        # ---- 2) L-17 冒烟:mock 管线 + 确定性打分 ----
        def det_judge(a: str, b: str) -> tuple[float, float]:
            return (1 - deterministic_score(a), 1 - deterministic_score(b))

        orig_run = run

        def run_with_env(brief, cfg, seed, **kw):
            cfg = {**cfg, "env": {**env, **cfg.get("env", {})}, "no_retrieval": True,
                   "check": False, "timeout": 1200}
            return orig_run(brief, cfg, seed, sw_dir=SW_WT, **kw)

        rep = smoke([str(briefs[0])], seeds=[1], judge=det_judge, _run_fn=run_with_env,
                    sw_dir=SW_WT)
        print(json.dumps({"m2_groups": len(rep["groups"]),
                          "winrates": [g["winrate"] for g in rep["groups"]]}, ensure_ascii=False))

        # ---- 3) L-13 dry-run 轮次记录 ----
        round_md = (
            f"\n```yaml\nround: 1\ndate: \"{time.strftime('%Y-%m-%d')}\"\n"
            "hypothesis: \"dry-run:mock LLM 管线下验证 M2 面接线(变更可应用/可打分/可归因),"
            "不产生真实优化结论\"\n"
            "surface: op.memory_assembler\n"
            "change: \"lab.overlay 应用 assembler/compress/thread 三组 profile 补丁到 worktree\"\n"
            f"ab: {{briefs: {len(briefs[:1])}, seeds: [1], "
            f"winrate: {rep['groups'][0]['winrate'] if rep['groups'] else 'null'}, "
            f"ci95: {list(rep['groups'][0]['ci95']) if rep['groups'] else '[null, null]'}, "
            "per_axis_floor: null}\n"
            "decision: rejected\nsealed_score: null\n"
            "notes: \"dry-run(mock LLM):管线活性验证通过;判官闸门 OFF,分数仅报告。\"\n```\n")
        with (ROOT / "optimizer" / "notebook.md").open("a", encoding="utf-8") as f:
            f.write(round_md)
        print("done: out/champion_baseline.json + dashboards/m2_smoke.md + notebook round 1")
        return 0 if ok else 1
    finally:
        proc.terminate()
        proc.wait(timeout=10)


if __name__ == "__main__":
    sys.exit(main())
