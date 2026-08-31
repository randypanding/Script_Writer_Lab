#!/usr/bin/env python
"""PM 进场自检(boot check)——项目经理 agent 进场后运行的第一条命令。

用法:
    cd Script_Writer_Lab && uv run python scripts/boot_check.py [--full]

四层检查,任何一层缺失都会给出"缺什么、影响什么、找谁要"的明确指引:
  1. 环境:Python/uv 版本、SW checkout 路径解析(pinned ../Script_Writer)
  2. 凭证:LLM key(SW 用 OPENAI_API_KEY;Lab 用 GEN/JUDGE_DEV/JUDGE_SEALED/CNB_TOKEN)
  3. 数据:corpus 语料本体、out/pairs 偏好对(判官考试燃料)
  4. 契约:contract/ 封印完整性(LAB_SEAL_KEY)

退出码:0 = 就绪;1 = 有阻断项(可开工的工作仍会列出)。
--full 额外跑 SW 快测与 Lab 全测(约数分钟,验证依赖装齐)。
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[1]

BLOCKERS: list[str] = []
WARNINGS: list[str] = []
READY: list[str] = []


def ok(msg: str) -> None:
    READY.append(msg)
    print(f"  [OK]    {msg}")


def blocker(msg: str, action: str) -> None:
    BLOCKERS.append(f"{msg} → {action}")
    print(f"  [BLOCK] {msg}")
    print(f"          需要: {action}")


def warn(msg: str, action: str) -> None:
    WARNINGS.append(f"{msg} → {action}")
    print(f"  [WARN]  {msg}")
    print(f"          建议: {action}")


def section(title: str) -> None:
    print(f"\n== {title} ==")


def _sw_checkout() -> Path:
    cfg = tomllib.loads((ROOT / "lab.toml").read_text(encoding="utf-8"))
    return (ROOT / cfg["paths"]["script_writer_checkout"]).resolve()


def check_env() -> None:
    section("1/4 环境")
    try:
        sw = _sw_checkout()
        if (sw / "pyproject.toml").exists() and (sw / "src" / "nsc").exists():
            ok(f"SW checkout 解析: {sw}")
            git = subprocess.run(
                ["git", "-C", str(sw), "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, check=False,
            )
            if git.returncode == 0:
                ok(f"SW pinned commit: {git.stdout.strip()}")
        else:
            blocker(
                f"SW checkout 不存在或不含 nsc: {sw}",
                "clone randypanding/Script_Writer 的 Developing 分支,目录名/软链需为 ../Script_Writer",
            )
    except Exception as e:  # noqa: BLE001 - 自检脚本要枚举一切启动失败
        blocker(f"lab.toml 或 SW 解析失败: {e}", "检查 lab.toml [paths] 与仓库布局")
        return
    # SW 侧依赖是否装齐(快速 import 探测,不跑测试;须用 SW 自己的 venv,故 uv run)
    imp = subprocess.run(
        ["uv", "run", "python", "-c", "import nsc, dspy, litellm"], cwd=str(_sw_checkout()),
        capture_output=True, text=True, timeout=300, check=False,
    )
    if imp.returncode == 0:
        ok("SW 依赖已装齐(nsc/dspy/litellm 可导入)")
    else:
        blocker("SW 依赖缺失", f"在 {_sw_checkout()} 执行: uv sync --all-extras")


def check_credentials() -> None:
    section("2/4 凭证(LLM key)")
    if os.environ.get("OPENAI_API_KEY"):
        ok("OPENAI_API_KEY 已设置(SW 生成管线)")
    else:
        blocker(
            "OPENAI_API_KEY 未设置",
            "向 owner 要 LongCat(或任意 OpenAI 兼容)key;SW 端点在 config/models.yaml",
        )
    if os.environ.get("GEN_API_KEY"):
        ok("GEN_API_KEY 已设置(Lab 生成槽位)")
    else:
        blocker("GEN_API_KEY 未设置", "向 owner 要百炼/兼容端点 key(.env)")
    if os.environ.get("JUDGE_DEV_API_KEY"):
        ok("JUDGE_DEV_API_KEY 已设置(dev 判官)")
    else:
        warn(
            "JUDGE_DEV_API_KEY 未设置",
            "dev 判官可暂时走 CNB swarm 免费通道;付费 key 到位后写入 .env",
        )
    if os.environ.get("JUDGE_SEALED_API_KEY"):
        ok("JUDGE_SEALED_API_KEY 已设置(sealed 判官——W2 卡点)")
    else:
        blocker(
            "JUDGE_SEALED_API_KEY 未设置",
            "W2 sealed 判官(跨家族校验/champion 仲裁)整卡等它;向 owner 要任一付费异家族 key",
        )
    if os.environ.get("CNB_TOKEN"):
        ok("CNB_TOKEN 已设置(免费 swarm 集群)")
    else:
        warn(
            "CNB_TOKEN 未设置",
            "免费算力通道关闭;判官投票/合成改写将全走付费 key(成本↑)",
        )
    if os.environ.get("LAB_SEAL_KEY"):
        ok("LAB_SEAL_KEY 已设置(封印 HMAC 校验启用)")
    else:
        warn(
            "LAB_SEAL_KEY 未设置",
            "guard 只做清单哈希校验(防线2),HMAC(防线1)跳过——可接受,key 由 owner 保管",
        )


def check_data() -> None:
    section("3/4 数据(语料与偏好对)")
    inbox = ROOT / "corpus" / "inbox"
    store = ROOT / "corpus" / "store"
    inbox_n = sum(
        1 for p in inbox.rglob("*")
        if p.is_file() and not p.name.startswith(".")
    ) if inbox.exists() else 0
    store_n = sum(1 for p in store.rglob("card_*.json") if p.is_file()) if store.exists() else 0
    if store_n > 0:
        ok(f"语料库: corpus/store {store_n} 张统计卡")
    elif inbox_n > 0:
        warn(
            f"corpus/inbox 有 {inbox_n} 个文件但未入库",
            "跑 uv run python -m lab.corpus ingest 解析归一",
        )
    else:
        blocker(
            "语料库为空(原机 1665 部未迁移)",
            "向 owner 要语料迁移:corpus/store/(card_*.json+text_*.txt)打包,或至少先投放治愈系作品(W3 卡点)",
        )
    pairs = ROOT / "out" / "pairs"
    if pairs.exists() and any(pairs.glob("*.jsonl")):
        n = sum(sum(1 for _ in p.open(encoding="utf-8")) for p in pairs.glob("*.jsonl"))
        ok(f"偏好对: out/pairs 共 {n} 条(判官考试燃料)")
    else:
        blocker(
            "偏好对缺失(out/pairs/*.jsonl 不存在)",
            "语料到位后跑 uv run python -m lab.pairs build [--llm-mid];或向 owner 要原机 out/pairs 打包",
        )
    if (ROOT / "mined" / "craft_anchors_v2.json").exists():
        ok("语料锚资产: mined/craft_anchors_v2.json(v2.1)在库")


def check_contract() -> None:
    section("4/4 契约(封印)")
    r = subprocess.run(
        [sys.executable, "-m", "lab.contract_guard", "verify", "contract"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    if r.returncode == 0:
        ok("contract/ 封印校验通过")
    else:
        blocker(
            "contract/ 封印失配",
            "owner 执行: LAB_SEAL_KEY=<key> uv run python -m lab.contract_guard seal contract",
        )
    g = subprocess.run(
        [sys.executable, "scripts/corpus_leak_guard.py"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    if g.returncode == 0:
        ok("corpus 泄漏守卫通过")
    else:
        blocker("泄漏守卫失败", f"输出: {g.stdout.strip()} {g.stderr.strip()}")


def check_full() -> None:
    section("全量验证(--full)")
    sw = _sw_checkout()
    print("  跑 SW 快测(约 2-4 分钟)...")
    t1 = subprocess.run(
        ["uv", "run", "pytest", "-m", "not llm", "-n", "auto", "-q", "--tb=no"],
        cwd=str(sw), capture_output=True, text=True, timeout=2400, check=False,
    )
    tail = (t1.stdout.strip().splitlines() or ["<无输出>"])[-1]
    if t1.returncode == 0:
        ok(f"SW 快测全绿({tail})")
    else:
        blocker(f"SW 快测失败({tail})", f"在 {sw} 复跑 uv run pytest -m 'not llm' -n auto 看详情")
    print("  跑 Lab 全测...")
    t2 = subprocess.run(
        ["uv", "run", "pytest", "-q"], cwd=str(ROOT), capture_output=True, text=True, timeout=900, check=False,
    )
    tail = (t2.stdout.strip().splitlines() or ["<无输出>"])[-1]
    if t2.returncode == 0:
        ok(f"Lab 全测全绿({tail})")
    else:
        blocker(f"Lab 测试失败({tail})", "cd Script_Writer_Lab && uv run pytest -q 复跑看详情")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="额外跑两仓测试套件")
    args = ap.parse_args()
    print("== PM 进场自检 ==")
    check_env()
    check_credentials()
    check_data()
    check_contract()
    if args.full:
        check_full()

    print("\n== 自检结论 ==")
    print(f"  就绪项 {len(READY)} | 警告 {len(WARNINGS)} | 阻断 {len(BLOCKERS)}")
    if BLOCKERS:
        print("\n阻断项(进场后无法开始的工作):")
        for b in BLOCKERS:
            print(f"  - {b}")
    print(
        "\n指引:阻断项需要 owner 注入资源(见 docs/PM_ONBOARDING.md §资源清单)。"
        "\n注意:key 从环境/.env 继承;本脚本不打印任何 key 值。"
    )
    return 1 if BLOCKERS else 0


if __name__ == "__main__":
    sys.exit(main())
