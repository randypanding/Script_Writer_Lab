"""守卫盲区回归(独立验证实证):GBK 编码语料 + 非 ASCII 路径的路径防线。"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import corpus_leak_guard as g

CJK_TEXT = "你好世界这是一段用于验证泄漏守卫的中文正文内容" * 10


def test_read_best_decoded_prefers_gbk_for_gbk_files(tmp_path):
    p = tmp_path / "gbk.txt"
    p.write_bytes(CJK_TEXT.encode("gbk"))
    assert "你好世界" in g._read_best_decoded(p)  # 不再是乱码
    p2 = tmp_path / "utf8.txt"
    p2.write_text(CJK_TEXT, encoding="utf-8")
    assert "你好世界" in g._read_best_decoded(p2)


def test_gbk_corpus_paste_detected(tmp_path):
    """GBK 语料的 100 字符粘贴必须命中窗口键(原盲区:索引键是乱码文本的键)。"""
    corpus_text = "茶山雾气缭绕采茶人清晨上山这是完全虚构的中文剧本文本。" * 30
    p = tmp_path / "gbksource.txt"
    p.write_bytes(corpus_text.encode("gbk"))
    keys = g._file_keys(g._read_best_decoded(p))
    paste = corpus_text[100:220]  # 120 字符,粘贴者看到的是正确解码文本
    hits = g.window_hits("无害前缀" + paste + "无害后缀", keys)
    assert hits > 0, "GBK 语料粘贴必须检出"


def test_tracked_files_uses_nul_no_quotepath(tmp_path, monkeypatch):
    """git ls-files -z:中文路径不转义,路径防线 startswith('corpus/') 必须命中。"""
    repo = tmp_path / "repo"
    repo.mkdir()
    for args in (["init", "-q"], ["config", "core.quotepath", "true"]):
        subprocess.run(["git", *args], cwd=repo, capture_output=True, check=True)
    (repo / "corpus" / "inbox" / "中文目录").mkdir(parents=True)
    f = repo / "corpus" / "inbox" / "中文目录" / "剧.txt"
    f.write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "-f", "."], cwd=repo, capture_output=True, check=True)
    monkeypatch.setattr(g, "ROOT", repo)
    files = g.tracked_files()
    assert any(x.startswith("corpus/") and "中文目录" in x for x in files), files
    # 路径防线判定
    bad = [x for x in files if x.startswith(g.FORBIDDEN)]
    assert bad, "非 ASCII 路径的禁地文件必须被路径防线捕获"


def test_bucket_index_paste_detected_and_clean_pass(tmp_path):
    """v6 分桶磁盘索引:粘贴必中、干净文本零误报、索引可复用(回归 v5 union OOM)。"""
    corpus_text = "茶山雾气缭绕采茶人清晨上山这是完全虚构的中文剧本文本。" * 30
    src = tmp_path / "corpus_src.txt"
    src.write_text(corpus_text, encoding="utf-8")
    index_dir = g.build_bucket_index([src], tmp_path / "idx")
    assert (index_dir / "MANIFEST").exists()
    index = g.BucketIndex(index_dir)
    paste = corpus_text[100:220]
    assert g.window_hits_index("无害前缀" + paste + "无害后缀", index) > 0
    clean = "完全无关的另一段中文文本内容用来验证误报率为零。" * 20
    assert g.window_hits_index(clean, index) == 0
