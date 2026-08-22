"""L-01 补全 · 真实语料格式提取(docx/doc/pdf → 纯文本)。

真实 inbox 构成:362 docx + 84 OLE .doc + 46 pdf + 少量非文本(mp4/jpg/xlsx)。
- docx:zip + word/document.xml 的 w:t(标准 OOXML,stdlib 可靠解析);
- doc(OLE2 二进制):无外部依赖的启发式——正文在现代 Word 中以 UTF-16LE 存储,
  整文件按 utf-16-le 容错解码后滤出 CJK 连续段(段落边界有损,统计口径可接受,见 PR 偏差记录);
- pdf:pypdf(纯文本提取质量随制作工具浮动,靠 is_scriptlike 质量门兜底)。
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path

PLAIN_SUFFIXES = {".txt", ".md", ".fountain"}
DOCX_SUFFIXES = {".docx"}
OLE_DOC_SUFFIXES = {".doc", ".wps"}
PDF_SUFFIXES = {".pdf"}
# 提取器认识的全部后缀;其余(mp4/jpg/xlsx/qkdownloading 等)按"非文本"跳过
READABLE_SUFFIXES = PLAIN_SUFFIXES | DOCX_SUFFIXES | OLE_DOC_SUFFIXES | PDF_SUFFIXES

_CJK_RUN = re.compile(
    r"[\u4e00-\u9fff][\u4e00-\u9fff0-9A-Za-z，。！？：；“”‘’、…—·:;,.!?()\[\]（）【】《》\"'\s-]{9,}")
MIN_CHARS = 200      # 质量门:非空白字符下限(过滤残缺提取/碎片)
MIN_CJK_RATIO = 0.4  # 质量门:CJK 占比(过滤乱码提取与纯外文)


def _read_plain(p: Path) -> str | None:
    raw = p.read_bytes()
    for enc in ("utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def _read_docx(p: Path) -> str | None:
    if not zipfile.is_zipfile(p):
        return None
    with zipfile.ZipFile(p) as z:
        if "word/document.xml" not in z.namelist():
            return None
        xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
    paras: list[str] = []
    for para in re.findall(r"<w:p[ >].*?</w:p>", xml, flags=re.DOTALL):
        runs = re.findall(r"<w:t[^>]*>([^<]*)</w:t>", para)
        if runs:
            paras.append("".join(runs))
    return "\n".join(paras) if paras else None


def _read_ole_doc(p: Path) -> str | None:
    raw = p.read_bytes()
    text = raw.decode("utf-16-le", errors="ignore")
    runs = _CJK_RUN.findall(text)
    body = "\n".join(r.strip() for r in runs if r.strip())
    if len(body) * 2 < len(raw) * 0.01:  # utf16 提不出东西 → 试 gbk(旧版 Word)
        gbk_runs = _CJK_RUN.findall(raw.decode("gbk", errors="ignore"))
        alt = "\n".join(r.strip() for r in gbk_runs if r.strip())
        if len(alt) > len(body):
            body = alt
    return body or None


def _read_pdf(p: Path) -> str | None:
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError:
        return None
    try:
        pages = [pg.extract_text() or "" for pg in PdfReader(str(p)).pages]
    except (OSError, ValueError, RuntimeError, PdfReadError):  # 损坏/加密 pdf 统一按不可提取
        return None
    return "\n".join(pages) or None


def extract_text(p: Path) -> str | None:
    """按后缀分派;None = 无法提取(损坏/非文本类型)。"""
    s = p.suffix.lower()
    if s in PLAIN_SUFFIXES:
        return _read_plain(p)
    if s in DOCX_SUFFIXES:
        return _read_docx(p)
    if s in OLE_DOC_SUFFIXES:
        return _read_ole_doc(p)
    if s in PDF_SUFFIXES:
        return _read_pdf(p)
    return None


def is_scriptlike(text: str | None) -> bool:
    """质量门:够长且以中文为主。过滤课程笔记/乱码/图片说明等非剧本文本。"""
    if not text:
        return False
    body = "".join(text.split())
    if len(body) < MIN_CHARS:
        return False
    cjk = sum(1 for ch in body if "\u4e00" <= ch <= "\u9fff")
    return cjk / len(body) >= MIN_CJK_RATIO
