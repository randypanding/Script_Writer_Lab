"""L-13 · OPTIMIZER 纪律:notebook 台账格式校验(CI 会查,不合规的轮次视为未发生)。"""
from pathlib import Path

import yaml

NOTEBOOK = Path(__file__).parents[1] / "optimizer" / "notebook.md"
REQUIRED = {"round", "date", "hypothesis", "surface", "change", "ab", "decision"}
ALLOWED_SURFACE_PREFIX = ("op.",)  # surface.yaml 的动作 id 必须以 op. 开头
ALLOWED_DECISION = {"rejected", "accepted_pending_sealed", "promoted"}


def _blocks() -> list[dict]:
    text = NOTEBOOK.read_text(encoding="utf-8")
    inside = False
    buf: list[str] = []
    out: list[dict] = []
    for line in text.splitlines():
        if line.strip().startswith("```yaml"):
            inside = True
            buf = []
            continue
        if line.strip() == "```" and inside:
            inside = False
            try:
                data = yaml.safe_load("\n".join(buf))
            except yaml.YAMLError:
                continue
            if isinstance(data, dict):
                out.append(data)
            continue
        if inside:
            buf.append(line)
    return out


def test_notebook_records_are_wellformed():
    records = [b for b in _blocks() if isinstance(b.get("round"), int)]
    assert records, "notebook 至少一条轮次记录"
    for r in records:
        missing = REQUIRED - set(r)
        assert not missing, f"轮次 {r.get('round')} 缺字段:{missing}"
        assert str(r["surface"]).startswith(ALLOWED_SURFACE_PREFIX), r["surface"]
        assert r["decision"] in ALLOWED_DECISION, r["decision"]
        assert isinstance(r["ab"], dict) and {"briefs", "winrate", "ci95"} <= set(r["ab"])
    rounds = [r["round"] for r in records]
    assert len(rounds) == len(set(rounds)), "round 不得重复"


def test_notebook_template_itself_complies():
    # 模板占位记录就是首条合规记录(README 声明"非真实实验",字段仍须齐全)
    records = [b for b in _blocks() if "round" in b]
    assert any(r.get("notes", "").startswith("这是模板占位") for r in records)
