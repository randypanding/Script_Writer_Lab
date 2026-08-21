#!/usr/bin/env python
"""CI 本地等价入口(make ci 的无 make 版,Windows Git Bash 无 make 时用)。

与 .github/workflows/ci.yml 及 Makefile::ci 完全同构:
lint → test → corpus leak guard。任一步失败即非零退出。
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]

STEPS = [
    ["uv", "run", "ruff", "check", "src", "tests", "scripts"],
    ["uv", "run", "pytest", "-q"],
    ["uv", "run", "python", "scripts/corpus_leak_guard.py"],
]


def main() -> int:
    for cmd in STEPS:
        print(f"\n$ {' '.join(cmd)}", flush=True)
        r = subprocess.run(cmd, cwd=ROOT)
        if r.returncode != 0:
            print(f"FAILED: {' '.join(cmd)}", file=sys.stderr)
            return r.returncode
    print("\nci: all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
