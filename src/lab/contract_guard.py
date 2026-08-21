"""L-09 · sealed 哈希锁。约定:锁文件 = <dir>/.seal.lock.json,内容 = 文件清单 +
每文件哈希 + 整体 HMAC(key);verify 重算比对。篡改/新增/重命名/删除任一 sealed 文件均判失败。

哈希口径:文本读入后统一 \\r\\n → \\n 再 sha256(跨平台行尾稳定,CI 与本地一致)。
verify(dir, lock) 只带 lock:若 LockFile 内存中持有 key(刚 seal 完)则连 HMAC 一起校验;
从磁盘加载的锁(如 CI 守卫)做清单哈希一致性校验 —— 改动仍必然失败,只差"重造锁文件"
这一层防护,该层由 git diff 可见性 + 人类 re-seal 私钥承担(威胁模型见 PR)。
"""
from __future__ import annotations

import argparse
import hashlib
import hmac as hmac_mod
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LOCK_NAME = ".seal.lock.json"


def _file_hash(p: Path) -> str:
    data = p.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def _manifest(dir_: Path) -> list[dict[str, Any]]:
    files = []
    for p in sorted(dir_.rglob("*")):
        if not p.is_file() or p.name == LOCK_NAME:
            continue
        files.append({"path": p.relative_to(dir_).as_posix(), "sha256": _file_hash(p)})
    return files


def _canonical(manifest: list[dict[str, Any]]) -> bytes:
    return json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass
class LockFile:
    dir: Path
    manifest: list[dict[str, Any]]
    hmac: str
    key: str | None = None  # 仅内存;不落盘

    @classmethod
    def load(cls, dir_: str | Path) -> LockFile:
        d = Path(dir_)
        data = json.loads((d / LOCK_NAME).read_text(encoding="utf-8"))
        return cls(dir=d, manifest=data["files"], hmac=data["hmac"])

    def to_json(self) -> str:
        return json.dumps({"version": 1, "algo": "sha256", "files": self.manifest,
                           "hmac": self.hmac}, ensure_ascii=False, indent=1)


def seal_dir(dir_: str | Path, key: str) -> LockFile:
    d = Path(dir_)
    manifest = _manifest(d)
    mac = hmac_mod.new(key.encode("utf-8"), _canonical(manifest), hashlib.sha256).hexdigest()
    lock = LockFile(dir=d, manifest=manifest, hmac=mac, key=key)
    (d / LOCK_NAME).write_text(lock.to_json() + "\n", encoding="utf-8", newline="\n")
    return lock


def verify(dir_: str | Path, lock: LockFile) -> bool:
    d = Path(dir_)
    if not (d / LOCK_NAME).exists():
        return False
    current = _manifest(d)
    if current != lock.manifest:
        return False
    if lock.key is not None:
        expect = hmac_mod.new(lock.key.encode("utf-8"), _canonical(current), hashlib.sha256).hexdigest()
        if not hmac_mod.compare_digest(expect, lock.hmac):
            return False
    return True


def verify_committed(dir_: str | Path, key: str | None = None) -> bool:
    """对已提交的锁文件做校验(guard/CLI 入口);带 key 时连 HMAC 一起验。"""
    d = Path(dir_)
    if not (d / LOCK_NAME).exists():
        return True  # 未封印 = 无对象;guard 视为通过(封印是显式动作)
    lock = LockFile.load(d)
    lock.key = key
    return verify(d, lock)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lab.contract_guard")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("seal", help="封印目录(写 <dir>/.seal.lock.json)")
    sp.add_argument("dir")
    sp.add_argument("--key-env", default="LAB_SEAL_KEY")
    vp = sub.add_parser("verify", help="校验目录(不改文件,只读)")
    vp.add_argument("dir")
    vp.add_argument("--key-env", default="LAB_SEAL_KEY")
    args = ap.parse_args(argv)
    key = os.environ.get(args.key_env, "")
    if args.cmd == "seal":
        if not key:
            print(f"缺少 {args.key_env}", file=sys.stderr)
            return 2
        lock = seal_dir(args.dir, key)
        print(f"sealed {args.dir}: {len(lock.manifest)} files, hmac={lock.hmac[:12]}…")
        return 0
    if args.cmd == "verify":
        ok = verify_committed(args.dir, key or None)
        print("verify: OK" if ok else "verify: FAILED(目录与锁文件不一致)")
        return 0 if ok else 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
