#!/usr/bin/env python
"""corpus 泄漏守卫(L-00 落地,L-09 集成 sealed 哈希锁,L-15 升级滚动哈希索引)。

三道防线:
1. 路径防线:corpus/ 与 transcripts/ 下任何文件被 git 跟踪 → 失败。
2. 内容防线(v1,真实语料规模):inbox 语料按文件建立 50 字符窗口的确定性 md5 键集
   (步长 25,含 CJK 过滤,按文件粒度磁盘缓存);对每个待提交文本文件以步长 1 滚动
   全量探查,键命中即判失败(64 位碰撞期望 ~1e-8,不回查原文——误报代价是人工复核,
   漏报代价是语料泄漏)。检出保证:粘贴 ≥ 50+25-1 = 75 字符必中;50–74 字符按对齐
   概率检出。(v0 的逐探针全串搜索在 GB 级语料上为 O(n²),不可用;L-15 再升级。)
3. sealed 防线(L-09):contract/ 存在 .seal.lock.json 时重算哈希比对,不一致 → 失败。
   (LAB_SEAL_KEY 设置时连 HMAC 一起校验;未封印视为通过,封印是显式动作。)

退出码:0 通过(含无语料时仅路径防线生效,打印警告),1 失败。
"""
from __future__ import annotations

import os
import subprocess
import sys
from hashlib import md5
from pathlib import Path

ROOT = Path(__file__).parents[1]
FORBIDDEN = ("corpus/", "transcripts/")
PROBE_LEN = 50
STRIDE = 25
TEXT_SUFFIXES = {".md", ".yaml", ".yml", ".py", ".txt", ".json", ".jsonl", ".toml"}


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout
    return [line for line in out.splitlines() if line]


def _corpus_files() -> list[Path]:
    inbox = ROOT / "corpus" / "inbox"
    if not inbox.exists():
        return []
    return [p for p in sorted(inbox.rglob("*"))
            if p.is_file() and p.suffix.lower() in {".txt", ".md", ".fountain"}]


def _has_cjk(win: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in win)


CACHE_DIR = ROOT / "out" / "guard_cache"
INDEX_VERSION = 4  # 索引算法变更时 +1,作废旧缓存


def _win_key(win: str) -> int:
    """确定性窗口键:md5 前 8 字节。不用内置 hash()——它按进程随机化(PYTHONHASHSEED),
    磁盘缓存的键跨进程不可比,会让守卫静默放行一切。"""
    return int.from_bytes(md5(win.encode("utf-8", "ignore")).digest()[:8], "big")


def _file_keys(text: str) -> set[int]:
    keys: set[int] = set()
    for pos in range(0, max(len(text) - PROBE_LEN, 0) + 1, STRIDE):
        win = text[pos : pos + PROBE_LEN]
        if _has_cjk(win):
            keys.add(_win_key(win))
    return keys


def load_index() -> set[int] | None:
    """语料侧窗口键集,按文件粒度磁盘缓存。

    - 无语料 → None(调用方跳过内容防线);
    - 每个语料文件一个缓存条目(指纹 = size+mtime_ns,算法版本入键);
      下载工具持续新增文件时,未变文件照常秒级载入,只重建新文件;
    - 哈希命中直接判失败:64 位键对百万级探针的碰撞期望 ~1e-8,
      误报的代价是一次人工复核,漏报的代价是语料泄漏,取舍明确。"""
    import pickle

    files = _corpus_files()
    if not files:
        return None
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    all_keys: set[int] = set()
    for p in files:
        rel = p.relative_to(ROOT).as_posix()
        st = p.stat()
        fp = f"v{INDEX_VERSION}|{st.st_size}|{st.st_mtime_ns}|{rel}"
        digest = md5(fp.encode("utf-8")).hexdigest()[:16]
        cache = CACHE_DIR / f"{digest}.pkl"
        keys = None
        if cache.exists():
            try:
                with cache.open("rb") as f:
                    keys = pickle.load(f)
            except (OSError, pickle.UnpicklingError, EOFError):
                keys = None  # 缓存损坏 → 重建该文件
        if keys is None:
            keys = _file_keys(p.read_text(encoding="utf-8", errors="ignore"))
            tmp = cache.with_suffix(".tmp")
            with tmp.open("wb") as f:
                pickle.dump(keys, f, protocol=pickle.HIGHEST_PROTOCOL)
            tmp.replace(cache)
        all_keys |= keys
    return all_keys


def window_hits(text: str, keys: set[int]) -> int:
    """文件侧探查:步长 1 滚动,哈希命中即计(64 位碰撞期望 ~1e-8,不回查原文)。"""
    hits = 0
    for pos in range(max(len(text) - PROBE_LEN, 0) + 1):
        win = text[pos : pos + PROBE_LEN]
        if not _has_cjk(win):
            continue
        if _win_key(win) in keys:
            hits += 1
    return hits


def main() -> int:
    files = tracked_files()
    bad_paths = [f for f in files if f.startswith(FORBIDDEN)]
    # .gitignore 里 force-allow 的占位文件豁免
    bad_paths = [f for f in bad_paths if not f.endswith(".gitkeep")]
    if bad_paths:
        print("路径防线失败:以下禁地文件被 git 跟踪:")
        for f in bad_paths:
            print(f"  {f}")
        return 1

    # sealed 防线(L-09):contract/ 封印后,任何改动必须在此失败
    from lab.contract_guard import verify_committed
    key = os.environ.get("LAB_SEAL_KEY") or None
    if not verify_committed(ROOT / "contract", key):
        print("sealed 防线失败:contract/ 与 .seal.lock.json 不一致")
        return 1

    keys = load_index()
    if keys is None:
        # 无语料 = 无泄漏对象,路径防线已足够;CI 视为通过但打印警告
        print("警告:无语料,内容防线跳过", file=sys.stderr)
        return 0

    for f in files:
        p = ROOT / f
        if p.suffix not in TEXT_SUFFIXES or not p.is_file() or f.startswith("tests/fixtures/"):
            continue
        text = p.read_text(encoding="utf-8", errors="ignore").replace("\r\n", "\n")
        if len(text) < PROBE_LEN:
            continue  # 容不下一个 50 字符窗口;威胁定义即 ≥50 字符粘贴
        if window_hits(text, keys):
            print(f"内容防线失败:{f} 含与语料一致的 ≥{PROBE_LEN} 字符片段")
            return 1
    print(f"泄漏守卫通过({len(files)} 个跟踪文件;索引 {len(keys)} 键)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
