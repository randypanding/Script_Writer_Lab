#!/usr/bin/env python
"""corpus 泄漏守卫(L-00 落地,L-09 集成 sealed 哈希锁,L-15 升级滚动哈希索引)。

三道防线:
1. 路径防线:corpus/ 与 transcripts/ 下任何文件被 git 跟踪 → 失败。
2. 内容防线(v2,真实语料规模·分桶磁盘索引):inbox 语料按 50 字符窗口生成确定性
   md5 键(步长 25,含 CJK 过滤),按键高 16 位分桶落盘(桶内排序 uint64,整库按
   语料清单指纹缓存);对每个待提交文本文件以步长 1 滚动探查,桶内二分命中即判失败
   (64 位碰撞期望 ~1e-8,不回查原文——误报代价是人工复核,漏报代价是语料泄漏)。
   检出保证:粘贴 ≥ 50+25-1 = 75 字符必中;50–74 字符按对齐概率检出。
   (v1 的全量 set union 在 1609 部真实语料上需 GB 级内存,实测 OOM-kill/exit 137;
   v0 逐探针全串搜索为 O(n²);均不可用。)
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
    """-z:NUL 分隔、不做 quotepath 转义。否则中文路径被引号包裹
    ("\"corpus/inbox/\\346\\224\\267...\""),startswith("corpus/") 失配 → 路径防线
    对真实语料(全在中文目录下)完全失效(独立验证实证的盲区)。"""
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
    ).stdout
    return [p.decode("utf-8", "surrogateescape") for p in out.split(b"\0") if p]


def _read_best_decoded(path: Path) -> str:
    """语料文件按最佳解码读取:utf-8 与 GBK 中取 CJK 占比高者。

    真实语料存在大量 GBK 编码文件(验证实证:GBK 源 100 字符粘贴曾漏检)——
    utf-8/ignore 会把 GBK 中文解码成乱码,索引键随之全错,内容防线对这类
    语料失效;泄漏者粘贴的是正确解码文本,必须用同一解码建索引。"""
    raw = path.read_bytes()
    best, best_ratio = "", -1.0
    for enc in ("utf-8", "gbk"):
        try:
            text = raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
        body = "".join(text.split())
        if not body:
            ratio = 0.0
        else:
            ratio = sum(1 for ch in body if "\u4e00" <= ch <= "\u9fff") / len(body)
        if ratio > best_ratio:
            best, best_ratio = text, ratio
    return best or raw.decode("utf-8", errors="ignore")


def _corpus_files() -> list[Path]:
    inbox = ROOT / "corpus" / "inbox"
    if not inbox.exists():
        return []
    return [p for p in sorted(inbox.rglob("*"))
            if p.is_file() and p.suffix.lower() in {".txt", ".md", ".fountain"}]


def _has_cjk(win: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in win)


CACHE_DIR = ROOT / "out" / "guard_cache"
INDEX_VERSION = 6  # 索引算法变更时 +1,作废旧缓存(v6:分桶磁盘索引,修全量 union 的 OOM)
BUCKET_BITS = 16  # 按窗口键高 16 位分桶;桶内排序 uint64,查询走桶内二分


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


def _corpus_manifest(files: list[Path]) -> str:
    """语料清单指纹(path+size+mtime_ns),作整库索引的缓存键。"""
    h = md5()
    for p in files:
        st = p.stat()
        h.update(f"{p.relative_to(ROOT).as_posix()}|{st.st_size}|{st.st_mtime_ns}\n".encode())
    return h.hexdigest()[:16]


def build_bucket_index(files: list[Path], index_dir: Path) -> Path:
    """语料窗口键 → 分桶排序 uint64 磁盘索引(bucket_XXXX.bin + MANIFEST)。

    内存上界 = 单语料文件的窗口键集 + 单桶缓冲;不做全库 union
    (v5 的 all_keys |= keys 在 1609 部真实语料上实测 OOM-kill/exit 137)。"""
    import array
    import shutil

    if index_dir.exists():
        shutil.rmtree(index_dir)
    index_dir.mkdir(parents=True)
    buckets: dict[int, array.array] = {}
    for p in files:
        for k in _file_keys(_read_best_decoded(p)):
            buckets.setdefault(k >> (64 - BUCKET_BITS), array.array("Q")).append(k)
    n_total = 0
    for b, arr in buckets.items():
        array.array("Q", sorted(set(arr))).tofile(
            open(index_dir / f"bucket_{b:04x}.bin", "wb"))
        n_total += len(set(arr))
    (index_dir / "MANIFEST").write_text(
        f"v{INDEX_VERSION}\nfiles={len(files)}\nkeys={n_total}\n", encoding="utf-8")
    return index_dir


def load_index() -> Path | None:
    """语料侧分桶索引目录,按语料清单指纹整库缓存。

    - 无语料 → None(调用方跳过内容防线);
    - 清单指纹命中 → 秒级复用;语料增删改 → 全量重建(内存有界);
    - 哈希命中直接判失败:64 位键对百万级探针的碰撞期望 ~1e-8,
      误报的代价是一次人工复核,漏报的代价是语料泄漏,取舍明确。"""
    files = _corpus_files()
    if not files:
        return None
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    index_dir = CACHE_DIR / f"index_v{INDEX_VERSION}_{_corpus_manifest(files)}"
    if (index_dir / "MANIFEST").exists():
        return index_dir
    return build_bucket_index(files, index_dir)


class BucketIndex:
    """分桶索引查询:桶文件按需加载(LRU),桶内 C 级二分。"""

    def __init__(self, index_dir: Path, max_cached: int = 512) -> None:
        import array

        self._dir = index_dir
        self._cache: dict[int, array.array] = {}
        self._order: list[int] = []
        self._max = max_cached
        self._array = array

    def _bucket(self, b: int):
        arr = self._cache.get(b)
        if arr is not None:
            return arr
        arr = self._array.array("Q")
        f = self._dir / f"bucket_{b:04x}.bin"
        if f.exists():
            with f.open("rb") as fp:
                arr.fromfile(fp, f.stat().st_size // 8)
        if len(self._order) >= self._max:
            self._cache.pop(self._order.pop(0), None)
        self._cache[b] = arr
        self._order.append(b)
        return arr

    def __contains__(self, key: int) -> bool:
        import bisect

        arr = self._bucket(key >> (64 - BUCKET_BITS))
        i = bisect.bisect_left(arr, key)
        return i < len(arr) and arr[i] == key


def window_hits_index(text: str, index: BucketIndex) -> int:
    """文件侧探查(分桶索引版):步长 1 滚动,桶内二分命中即计。"""
    hits = 0
    for pos in range(max(len(text) - PROBE_LEN, 0) + 1):
        win = text[pos : pos + PROBE_LEN]
        if not _has_cjk(win):
            continue
        if _win_key(win) in index:
            hits += 1
    return hits


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

    index_dir = load_index()
    if index_dir is None:
        # 无语料 = 无泄漏对象,路径防线已足够;CI 视为通过但打印警告
        print("警告:无语料,内容防线跳过", file=sys.stderr)
        return 0

    index = BucketIndex(index_dir)
    n_buckets = len(list(index_dir.glob("bucket_*.bin")))
    for f in files:
        p = ROOT / f
        if p.suffix not in TEXT_SUFFIXES or not p.is_file() or f.startswith("tests/fixtures/"):
            continue
        text = p.read_text(encoding="utf-8", errors="ignore").replace("\r\n", "\n")
        if len(text) < PROBE_LEN:
            continue  # 容不下一个 50 字符窗口;威胁定义即 ≥50 字符粘贴
        if window_hits_index(text, index):
            print(f"内容防线失败:{f} 含与语料一致的 ≥{PROBE_LEN} 字符片段")
            return 1
    print(f"泄漏守卫通过({len(files)} 个跟踪文件;索引 {n_buckets} 桶)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
