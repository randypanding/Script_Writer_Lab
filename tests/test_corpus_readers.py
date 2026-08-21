"""L-01 补全 · 真实语料格式入库(docx/doc/pdf)。实现目标: src/lab/readers.py + corpus.ingest 集成。
真实 inbox 为 docx/doc/pdf(698 文件,无 txt);无此卡则 L-02 的 bands 建立在 2 个 fixture 上。"""
import zipfile
from pathlib import Path

from lab.corpus import ingest
from lab.readers import extract_text, is_scriptlike

MINI = (Path(__file__).parent / "fixtures" / "corpus" / "mini_drama.txt").read_text(encoding="utf-8")


def _make_docx(tmp_path: Path, name: str, text: str) -> Path:
    """构造最小合法 docx(word/document.xml 的 w:p/w:t)。"""
    paras = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in text.splitlines())
    doc = f'<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>{paras}</w:body></w:document>'
    p = tmp_path / name
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("word/document.xml", doc)
    return p


def _make_doc(tmp_path: Path, name: str, text: str) -> Path:
    """伪 OLE .doc:二进制噪声中夹 UTF-16LE 正文(真实 Word 文档的文本段即如此存储)。"""
    noise = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + bytes(range(256)) * 4
    return tmp_path / name if (tmp_path / name).write_bytes(
        noise + text.encode("utf-16-le") + noise) else None


def test_docx_extraction(tmp_path):
    p = _make_docx(tmp_path, "样本.docx", MINI)
    out = extract_text(p)
    assert out is not None and "第1集" in out and "场景:茶园·清晨·外景" in out


def test_doc_extraction_utf16_runs(tmp_path):
    p = _make_doc(tmp_path, "样本.doc", MINI)
    out = extract_text(p)
    assert out is not None
    assert "场景:茶园" in out.replace("\n", "")


def test_plain_txt_still_works(tmp_path):
    p = tmp_path / "plain.txt"
    p.write_text(MINI, encoding="utf-8")
    assert "第1集" in extract_text(p)


def test_nontext_returns_none(tmp_path):
    p = tmp_path / "video.mp4"
    p.write_bytes(b"\x00\x01\x02")
    assert extract_text(p) is None


def test_garbage_docx_returns_none_or_short(tmp_path):
    p = tmp_path / "broken.docx"
    p.write_bytes(b"not a zip")
    assert extract_text(p) is None


def test_scriptlike_gate():
    assert is_scriptlike(MINI) is True
    assert is_scriptlike("太短") is False
    assert is_scriptlike("plain english text " * 100) is False  # 无 CJK


def test_ingest_accepts_docx_and_blocks_duplicate(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    _make_docx(inbox, "剧1.docx", MINI)
    store = tmp_path / "store"
    r1 = ingest(inbox, store)
    assert r1["ingested"] == 1
    _make_docx(inbox, "剧1副本.docx", MINI)  # 同文重跑 → 两个文件都撞已入库 simhash,拦
    r2 = ingest(inbox, store)
    assert r2["ingested"] == 0 and r2["duplicates"] == 2


def test_ingest_skips_unextractable_with_reason(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "坏.docx").write_bytes(b"not a zip")
    r = ingest(inbox, tmp_path / "store")
    assert r["ingested"] == 0
    assert any(s["file"] == "坏.docx" and s.get("reason") for s in r["skipped"])
