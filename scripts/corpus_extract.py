"""语料抽取与切分(R1a,纯 stdlib,无第三方依赖):

- docx(短剧剧本):zip+document.xml 正则剥壳;
- txt(q点作者小说):gb18030 解码;
- 切分:短剧按「第N集」,小说按「第N章/回/卷」;
用法: uv run python scripts/corpus_extract.py <文件路径> [--max-units 15]
输出: stdout JSONL,每行一个单元 {"unit_id","title","text"}
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import zipfile
from pathlib import Path

EP_RE = re.compile(r"^\s*#*\s*第\s*[0-9０-９一二三四五六七八九十百零]{1,5}\s*集", re.MULTILINE)
CH_RE = re.compile(r"^\s*#*\s*第\s*[0-9０-９一二三四五六七八九十百千万零]{1,7}\s*[章回卷节]", re.MULTILINE)
#: 剧本"场号"式分集兜底(如 1-1/2-1/10-1:每集从 x-1 场开始,集号后可紧跟汉字)
SCENE_EP_RE = re.compile(r"^\s*\d+\s*-\s*1(?!\d)", re.MULTILINE)


def docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    # <w:p> 可能带属性(w14:paraId 等)或自闭合;只剥开标签留换行,残属性会被下一行通配剥壳吃掉
    text = re.sub(r"<w:p(?:\s[^>]*)?/?>", "\n", xml)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text)


def txt_text(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("gb18030", "utf-8", "utf-16"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return raw.decode("gb18030", errors="replace")


def _cut(text: str, rex) -> list[tuple[str, str]]:
    marks = list(rex.finditer(text))
    units = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        body = text[m.end():end].strip()
        if len(body) >= 200:  # 过短单元(扉页/目录)丢弃
            units.append((m.group(0).strip(), body))
    return units


def split_units(text: str) -> list[tuple[str, str]]:
    """按集/章切分;返回 [(标题行, 正文)]。集/章/场号三种标记都试,取切出最多单元的方案
    (同数时 集>章>场号;一卡集剧本只有 x-1 场号式集首标记,靠场号兜底)。"""
    best: list[tuple[str, str]] = []
    for rex in (EP_RE, CH_RE):
        units = _cut(text, rex)
        if len(units) > len(best):
            best = units
    scene = _cut(text, SCENE_EP_RE)
    if len(scene) >= 5 and len(scene) > len(best):  # 场号切分须成串(≥5)才候选,防零星时间戳误切
        best = scene
    return best


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--max-units", type=int, default=15)
    args = ap.parse_args()
    p = Path(args.path)
    text = docx_text(p) if p.suffix.lower() == ".docx" else txt_text(p)
    units = split_units(text)
    if len(units) > args.max_units:  # 首部 60% + 中部 20% + 尾部 20%,张力曲线要覆盖全弧
        n = args.max_units
        head = units[: int(n * 0.6)]
        mid = units[len(units) // 2 : len(units) // 2 + max(1, int(n * 0.2))]
        tail = units[-max(1, n - len(head) - len(mid)):]
        units = head + mid + tail
    for i, (title, body) in enumerate(units):
        print(json.dumps({"unit_id": f"{p.stem}#u{i:02d}", "title": title, "text": body},
                         ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
