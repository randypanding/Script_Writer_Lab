#!/usr/bin/env python
"""进场就绪自检(boot check)——优化/训练 agent 进场后运行的第一条命令。

用法:
    cd Script_Writer_Lab && uv run python scripts/boot_check.py [--full]

四层检查,任何一层缺失都会给出"缺什么、影响什么、找谁要"的明确指引:
  1. 环境:Python/uv 版本、SW checkout 路径解析(默认 ../Script_Writer,可被
     LAB_SW_PATH 环境变量或 --sw 参数覆盖;找不到按候选路径探测)
  2. 凭证:LLM key(SW 用 OPENAI_API_KEY;Lab 用 GEN/JUDGE_DEV/JUDGE_SEALED/CNB_TOKEN)
  3. 数据:corpus 语料本体、out/pairs 偏好对(判官考试燃料)
  4. 契约:contract/ 封印完整性(LAB_SEAL_KEY)

退出码:0 = 就绪;1 = 有阻断项(可开工的工作仍会列出)。
--full 额外跑 SW 快测与 Lab 全测(约数分钟,验证依赖装齐)。

设计约束:本脚本必须在任意环境可跑而不崩溃——SW checkout 缺失时是"阻断项"
(退出码 1),不是 traceback(退出码 0 假成功)。所有 subprocess 调用均捕获异常。
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
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


def _candidate_sw_paths() -> list[Path]:
    """SW checkout 候选路径,按优先级:
    1) --sw / 环境变量 LAB_SW_PATH(显式指定)
    2) lab.toml 的 paths.script_writer_checkout(相对 ROOT 解析)
    3) 常见邻居目录探测(../Script_Writer、../Script_Writer_dev、../sw)
    """
    explicit = os.environ.get("LAB_SW_PATH", "").strip()
    cands: list[Path] = []
    if explicit:
        cands.append(Path(explicit).expanduser())
    cfg_path = ROOT / "lab.toml"
    if cfg_path.exists():
        try:
            cfg = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
            rel = cfg.get("paths", {}).get("script_writer_checkout")
            if rel:
                cands.append((ROOT / str(rel)).resolve())
        except (tomllib.TOMLDecodeError, KeyError, OSError):
            pass
    for name in ("Script_Writer", "Script_Writer_dev", "sw"):
        cands.append((ROOT.parent / name).resolve())
    # 去重(保持顺序)
    seen: set[str] = set()
    out: list[Path] = []
    for c in cands:
        if str(c) not in seen:
            seen.add(str(c))
            out.append(c)
    return out


def _is_sw(p: Path) -> bool:
    return (p / "pyproject.toml").exists() and (p / "src" / "nsc").exists()


def _run(cmd: list[str], cwd: Path, timeout: int = 300) -> subprocess.CompletedProcess | None:
    """subprocess 包装:任何启动失败(路径不存在/SW 缺依赖)返回 None,不抛异常。"""
    try:
        return subprocess.run(
            cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout, check=False,
        )
    except FileNotFoundError:
        return None
    except subprocess.TimeoutExpired:
        print("          (超时,已跳过)")
        return None


def _find_sw() -> tuple[Path | None, list[tuple[str, Path]]]:
    """返回 (找到的 SW 路径 | None, 探测过的候选列表)。"""
    found: Path | None = None
    tried: list[tuple[str, Path]] = []
    for c in _candidate_sw_paths():
        tried.append(("nsc" if _is_sw(c) else "no-nsc", c))
        if found is None and _is_sw(c):
            found = c
    return found, tried


def check_env() -> None:
    section("1/4 环境")
    sw, tried = _find_sw()
    if sw is not None:
        ok(f"SW checkout 解析: {sw}")
        git = _run(["git", "-C", str(sw), "rev-parse", "--short", "HEAD"], sw, 30)
        if git is not None and git.returncode == 0:
            ok(f"SW pinned commit: {git.stdout.strip()}")
    else:
        cand_desc = "; ".join(f"{tag}:{p}" for tag, p in tried)
        blocker(
            "SW checkout 未找到(探测过: " + cand_desc + ")",
            "克隆 randypanding/Script_Writer 的 Developing 分支,并用 LAB_SW_PATH 指定,"
            "或放在 ../Script_Writer(软链亦可)",
        )
        return
    # SW 侧依赖探测:优先直用 .venv(避免 uv run 触发 sync 卡住);失败再回退 uv run
    venv_py = sw / ".venv" / "bin" / "python"
    if venv_py.exists():
        imp = _run([str(venv_py), "-c", "import nsc"], sw, 60)
        if imp is not None and imp.returncode == 0:
            ok("SW 依赖可导入(nsc,.venv)")
            return
        warn(
            "SW .venv 存在但 import 失败",
            f"在 {sw} 执行: uv sync --all-extras 后重试",
        )
        return
    imp = _run(["uv", "run", "--no-sync", "python", "-c", "import nsc"], sw, 120)
    if imp is not None and imp.returncode == 0:
        ok("SW 依赖可导入(nsc)")
    else:
        warn("SW 依赖未装齐或 import 失败", f"在 {sw} 执行: uv sync --all-extras")


def check_credentials() -> None:
    section("2/4 凭证(LLM key)")
    env_keys = [
        ("OPENAI_API_KEY", "SW 生成管线", True),
        ("GEN_API_KEY", "Lab 生成槽位", True),
        ("JUDGE_DEV_API_KEY", "dev 判官(可暂走 CNB swarm)", False),
        ("JUDGE_SEALED_API_KEY", "sealed 判官——W2 卡点", True),
        ("CNB_TOKEN", "免费 swarm 集群", False),
        ("LAB_SEAL_KEY", "封印 HMAC(无则只做哈希校验)", False),
    ]
    for k, desc, is_blocker in env_keys:
        if os.environ.get(k):
            ok(f"{k} 已设置({desc})")
        elif is_blocker:
            blocker(f"{k} 未设置", f"向 owner 要 {desc} 的 key;写入 .env(见 .env.example)")
        else:
            warn(f"{k} 未设置", f"{desc} 当前不可用;可接受(非阻塞)")
    if os.path.exists(ROOT / ".env"):
        ok(".env 存在")
    else:
        warn(".env 不存在", "cp .env.example .env 并填入 key")


def check_data() -> None:
    section("3/4 数据(语料与偏好对)")
    inbox = ROOT / "corpus" / "inbox"
    store = ROOT / "corpus" / "store"
    inbox_n = (
        sum(1 for p in inbox.rglob("*") if p.is_file() and not p.name.startswith("."))
        if inbox.exists() else 0
    )
    store_n = (
        sum(1 for p in store.rglob("card_*.json") if p.is_file()) if store.exists() else 0
    )
    if store_n > 0:
        ok(f"语料库: corpus/store {store_n} 张统计卡")
    elif inbox_n > 0:
        warn(
            f"corpus/inbox 有 {inbox_n} 个文件但未入库",
            "跑 uv run python -m lab.corpus ingest corpus/inbox",
        )
    else:
        blocker(
            "语料库为空(原机 1665 部未迁移到本机)",
            "向 owner 要语料迁移:corpus/store/(card_*.json+text_*.txt) 打包拷贝;"
            "或先投放少量作品至 corpus/inbox/",
        )
    pairs = ROOT / "out" / "pairs"
    if pairs.exists() and any(pairs.glob("*.jsonl")):
        n = sum(sum(1 for _ in p.open(encoding="utf-8")) for p in pairs.glob("*.jsonl"))
        ok(f"偏好对: out/pairs 共 {n} 条(判官考试燃料)")
    else:
        blocker(
            "偏好对缺失(out/pairs/*.jsonl 不存在)",
            "语料到位后跑 uv run python -m lab.pairs build;或向 owner 要原机 out/pairs 打包",
        )
    if (ROOT / "mined" / "craft_anchors_v2.json").exists():
        ok("语料锚资产: mined/craft_anchors_v2.json(v2.1)在库")
    if (ROOT / "spec" / "training").exists() and any((ROOT / "spec" / "training").glob("*.md")):
        ok("训练路线规格: spec/training/ 在库")
    if (ROOT / "spec" / "gates_layers.yaml").exists():
        ok("门禁分层清单: spec/gates_layers.yaml 在库")
    if (ROOT / "spec" / "genre_shapes" / "shapes.yaml").exists():
        ok("套路注册表: spec/genre_shapes/shapes.yaml 在库")


def check_contract() -> None:
    section("4/4 契约(封印)")
    r = _run([sys.executable, "-m", "lab.contract_guard", "verify", "contract"], ROOT, 60)
    if r is not None and r.returncode == 0:
        ok("contract/ 封印校验通过")
    else:
        blocker(
            "contract/ 封印失配",
            "owner 执行: LAB_SEAL_KEY=<key> uv run python -m lab.contract_guard seal contract",
        )
    g = _run([sys.executable, "scripts/corpus_leak_guard.py"], ROOT, 120)
    if g is not None and g.returncode == 0:
        ok("corpus 泄漏守卫通过")
    else:
        blocker("泄漏守卫失败", f"输出: {(g.stdout + g.stderr).strip() if g else '<无>'}")


def check_full() -> None:
    section("全量验证(--full)")
    sw, _ = _find_sw()
    if sw is None:
        blocker("SW checkout 未找到,跳过 SW 快测", "见 1/4 环境 指引")
        return
    print("  跑 SW 快测(约 2-4 分钟)...")
    t1 = _run(["uv", "run", "pytest", "-m", "not llm", "-n", "auto", "-q", "--tb=no"], sw, 2400)
    tail = (t1.stdout.strip().splitlines() or ["<无输出>"])[-1] if t1 else "<失败>"
    if t1 is not None and t1.returncode == 0:
        ok(f"SW 快测全绿({tail})")
    else:
        blocker(f"SW 快测失败({tail})", f"在 {sw} 复跑 uv run pytest -m 'not llm' -n auto 看详情")
    print("  跑 Lab 全测...")
    t2 = _run(["uv", "run", "pytest", "-q"], ROOT, 900)
    tail2 = (t2.stdout.strip().splitlines() or ["<无输出>"])[-1] if t2 else "<失败>"
    if t2 is not None and t2.returncode == 0:
        ok(f"Lab 全测全绿({tail2})")
    else:
        blocker(f"Lab 测试失败({tail2})", "cd Script_Writer_Lab && uv run pytest -q 复跑看详情")


def main() -> int:
    ap = argparse.ArgumentParser(description="Lab 进场就绪自检")
    ap.add_argument("--full", action="store_true", help="额外跑两仓测试套件")
    ap.add_argument("--sw", type=str, default="", help="显式指定 SW checkout 路径(覆盖 LAB_SW_PATH)")
    args = ap.parse_args()
    if args.sw:
        os.environ["LAB_SW_PATH"] = args.sw
    print("== Lab 进场自检 ==")
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
        "\n指引:阻断项多为 owner 待注入资源(见 docs/PM_ONBOARDING.md §资源清单)。"
        "\n注意:key 从环境/.env 继承;本脚本不打印任何 key 值。"
    )
    return 1 if BLOCKERS else 0


if __name__ == "__main__":
    sys.exit(main())
