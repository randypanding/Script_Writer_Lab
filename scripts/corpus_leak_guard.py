#!/usr/bin/env python
"""corpus 泄漏守卫(L-00 落地,L-09 集成 sealed 哈希锁,L-15 升级滚动哈希索引)。

三道防线:
1. 路径防线:corpus/ 与 transcripts/ 下任何文件被 git 跟踪 → 失败。
2. 内容防线(v1,真实语料规模):语料拼接串按步长 25 建立 50 字符窗口的 md5 键集;
   对每个待提交文本文件以步长 1 滚动全量探查,哈希命中即回查原文确认。
   检出保证:粘贴 ≥ 50+25-1 = 75 字符必中;50–74 字符按对齐概率检出。
   (v0 的逐探针全串搜索在百 MB 语料上为 O(n²),不可用;L-15 再升级滚动哈希索引。)
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


def load_corpus_blob() -> str | None:
    corpus = ROOT / "corpus"
    if not corpus.exists():
        return None
    parts = []
    for p in sorted(corpus.rglob("*")):
        if p.is_file() and p.suffix in {".txt", ".md", ".fountain"}:
            parts.append(p.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(parts) if parts else None


def _has_cjk(win: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in win)


def index_keys(blob: str) -> set[int]:
    """语料侧索引:步长 STRIDE 的 50 字符窗口 md5 键(int);只索引含 CJK 的窗口。

    语料是中文剧本文本,无 CJK 的窗口(空白/代码)无区分度,只会带来假阳性命中
    与昂贵的全串回查;索引与探查两侧一致跳过,检出保证只针对中文原文粘贴。"""
    keys: set[int] = set()
    for pos in range(0, max(len(blob) - PROBE_LEN, 0) + 1, STRIDE):
        win = blob[pos : pos + PROBE_LEN]
        if _has_cjk(win):
            keys.add(int(md5(win.encode("utf-8", "ignore")).hexdigest()[:16], 16))
    return keys


def window_hits(text: str, keys: set[int], blob: str) -> int:
    """文件侧探查:步长 1 滚动,哈希命中并回查原文确认的窗口数。"""
    hits = 0
    for pos in range(max(len(text) - PROBE_LEN, 0) + 1):
        win = text[pos : pos + PROBE_LEN]
        if not _has_cjk(win):
            continue
        h = int(md5(win.encode("utf-8", "ignore")).hexdigest()[:16], 16)
        if h in keys and win in blob:
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

    blob = load_corpus_blob()
    if blob is None:
        # 无语料 = 无泄漏对象,路径防线已足够;CI 视为通过但打印警告
        print("警告:无语料,内容防线跳过", file=sys.stderr)
        return 0

    keys = index_keys(blob)
    for f in files:
        p = ROOT / f
        if p.suffix not in TEXT_SUFFIXES or not p.is_file() or f.startswith("tests/fixtures/"):
            continue
        text = p.read_text(encoding="utf-8", errors="ignore").replace("\r\n", "\n")
        if not text.strip():
            continue
        if len(text) <= PROBE_LEN:
            if text.strip() and text in blob:
                print(f"内容防线失败:{f} 含与语料一致的 ≥{PROBE_LEN} 字符片段")
                return 1
            continue
        if window_hits(text, keys, blob):
            print(f"内容防线失败:{f} 含与语料一致的 ≥{PROBE_LEN} 字符片段")
            return 1
    print(f"泄漏守卫通过({len(files)} 个跟踪文件;语料 {len(blob)//1024} KB 索引 {len(keys)} 键)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
