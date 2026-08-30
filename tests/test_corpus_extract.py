"""corpus_extract 切分器回归(round27):docx 带属性 <w:p> 剥壳 + 场号 x-1 分集兜底。

实证:金榜题名之寒门状元1-10集.docx 上旧实现产出 0 单元(标注 0 卡)——
①<w:p w14:paraId="..."> 带属性标签剥壳后残渣混入正文;②只有"1-1/2-1"场号式集首
标记,第N集/第N章正则全空。修复后 10 集全出,六维标注恢复。
"""
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from corpus_extract import SCENE_EP_RE, docx_text, split_units


def _make_docx(tmp_path: Path, name: str, text: str, attrs: bool = False) -> Path:
    if attrs:
        paras = "".join(
            f'<w:p w14:paraId="{i:08X}" w14:textId="{i:08X}" w:rsidR="00000000">'
            f"<w:r><w:t>{p}</w:t></w:r></w:p>"
            for i, p in enumerate(text.splitlines())
        )
    else:
        paras = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in text.splitlines())
    doc = (
        '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/'
        f'wordprocessingml/2006/main"><w:body>{paras}</w:body></w:document>'
    )
    p = tmp_path / name
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("word/document.xml", doc)
    return p


def test_docx_text_strips_attributed_paragraph_tags(tmp_path):
    """带属性 <w:p>(w14:paraId)剥壳后不得残留 XML 属性进正文(round27 缺陷①)。"""
    p = _make_docx(tmp_path, "a.docx", "第一集\n开场白内容足够长" * 20, attrs=True)
    text = docx_text(p)
    assert "w14" not in text and "paraId" not in text and "rsidR" not in text
    assert "开场白内容足够长" in text


def test_scene_number_fallback_split():
    """纯场号式剧本(x-1 = 每集首场)按场号兜底切分(round27 缺陷②)。"""
    lines = ["片头信息行"] * 3
    for ep in range(1, 9):
        lines.append(f"{ep}-1  陈家祠堂日外")
        lines += [f"本集第{ep}场拍在陈家祠堂,正文内容足以超过二百字的门槛线。" * 10]
        if ep == 3:  # 集内第二场,不该成为新单元起点
            lines.append("3-2  医院日内")
            lines.append("本场是本集第二场,转场去医院,正文同样凑足最小长度门槛线。" * 10)
    units = split_units("\n".join(lines))
    assert len(units) == 8
    assert units[0][0] == "1-1" and units[7][0] == "8-1"


def test_episode_marker_beats_scene_when_richer():
    """第N集标记切出更多单元时优先(场号只在更优时候选)。"""
    lines = []
    for ep in range(1, 7):
        lines.append(f"第{ep}集")
        lines.append("正文内容足够长,超过二百字的最小门槛线。" * 10)
        lines.append(f"{ep}-1  某地日外")  # 场号标记也在场,但单元数更少
    units = split_units("\n".join(lines))
    assert len(units) == 6
    assert units[0][0] == "第1集"


def test_standard_episode_split_unaffected():
    """既有行为回归:常规 第N集 文档切分与修复前一致。"""
    text = "\n".join(
        f"第{i}集\n" + "正文内容。" * 60 for i in range(1, 4)
    )
    units = split_units(text)
    assert [u[0] for u in units] == ["第1集", "第2集", "第3集"]


def test_scene_regex_requires_hyphen_one():
    """SCENE_EP_RE 只认 x-1 形态(x-2 是集内场次不是集首)。"""
    assert SCENE_EP_RE.match("1-1  医院日")
    assert SCENE_EP_RE.match("10 - 1考场日内")
    assert SCENE_EP_RE.match("3-2  医院日内") is None
    assert SCENE_EP_RE.match("12-11 宫内") is None
