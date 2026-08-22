"""L-07/L-08 · 判官工具箱:mock 客户端验证聚合/位置交换/降级/考试。不调真实 API。"""
import json
from types import SimpleNamespace

import pytest

from lab.judgekit import RecordingClient, axis_problem, load_criteria, render_exam_md, run_exam, score_pair

AXIS = "prose_craft"


def _resp(text: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text), logprobs=None)],
        usage=SimpleNamespace(prompt_tokens=5, completion_tokens=5))


class MockVerifierClient:
    """llm_verifier 兼容 mock:打分 token 是字母 A-T(A=20 最佳);按甲/乙顺序吐分。"""

    model_name = "mock-judge"

    def __init__(self, a_wins=True, noise=0.0):
        self.a_wins = a_wins
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        msgs = kw.get("messages", [])
        prompt = msgs[0]["content"]
        first_is_orig = prompt.find("【甲】") < prompt.find("【乙】") if "【甲】" in prompt else None
        if kw.get("max_tokens") == 1 and len(msgs) > 1:
            # vLLM prefill 调用:assistant 前缀以 \n<score_X> 结尾,回单字母。
            # 槽位偏置:槽 A 一律 +2 档(A/C vs E/T),位置交换平均后应互相抵消。
            tag_is_a = msgs[-1]["content"].rstrip().endswith("<score_A>")
            a_wins_slot = (first_is_orig == self.a_wins)
            if tag_is_a:
                letter = "A" if a_wins_slot else "P"
            else:
                letter = "E" if not a_wins_slot else "T"
            self.calls.append(("prefill", tag_is_a))
            return _resp(letter)
        self.calls.append(("analysis",))
        return _resp("这段分析认为两段有明确高下。")


def _cfg(client, k=1):
    return {"client": client, "model": "mock-judge", "k": k}


def test_load_criteria_all_axes():
    for axis in ("naturalness", "hook_strength", "placement_integration", "transportation",
                 "producibility", "prose_craft", "l0_structure", "l0_fact", "l0_brand", "l0_dialogue"):
        crit = load_criteria(axis)
        assert len(crit) >= 3, f"{axis} 至少 3 个信号级子问题"
    assert "口语真实度" in load_criteria("naturalness")


def test_score_pair_position_swap_average():
    a = "……【甲】原版文本……"
    b = "……【乙】退化文本……"
    c = MockVerifierClient(a_wins=True)
    v = score_pair(a, b, AXIS, _cfg(c))
    # mock 自带槽位偏置 +2 档:有向 (a,b) → A 槽=A(20),B 槽=T(1);
    # 有向 (b,a) → 乙在 A 槽=P(5),甲在 B 槽=E(16)。
    # score_a = (a 槽A分 + a 槽B分)/2 = ((20-1)/19 + (16-1)/19)/2 —— 单向的槽位偏置被平均抵消
    assert v.score_a == pytest.approx(((20 - 1) / 19 + (16 - 1) / 19) / 2)
    assert v.score_b == pytest.approx(((1 - 1) / 19 + (5 - 1) / 19) / 2)
    assert v.engine == "llm_verifier.compare"
    assert sum(1 for t in c.calls if t[0] == "analysis") >= 2  # 两次有向调用


def _directional_vote(orig_wins: bool):
    """按 prompt 里谁在第一段来投票,与并发顺序无关(并行投票下的确定性)。"""
    def _vote(slot, prompt, **kw):
        first_is_orig = "第一段:\n原版片段" in prompt
        return "A" if first_is_orig == orig_wins else "B"
    return _vote


def test_k_sample_vote_fallback(monkeypatch):
    class ExplodingClient:
        chat = SimpleNamespace(completions=SimpleNamespace(
            create=lambda **kw: (_ for _ in ()).throw(RuntimeError("logprobs not supported"))))

    from lab import models
    monkeypatch.setattr(models, "route", _directional_vote(orig_wins=True), raising=True)
    import lab.judgekit as jk
    v = jk.score_pair("原版片段", "退化片段", AXIS,
                      {"client": ExplodingClient(), "model": "m", "k": 3,
                       "model_slot": "judge_dev"})
    assert v.engine == "k_sample_vote"
    assert v.fallback_reason
    assert v.score_a == pytest.approx(1.0)  # 原版全票


def test_openai_api_error_also_falls_back(monkeypatch):
    """回归:真实端点抛的是 openai.APIStatusError 子类(如 BadRequestError),
    不是 RuntimeError——之前漏捕导致探针直接崩。"""
    import httpx
    import openai

    def _raise(**kw):
        req = httpx.Request("POST", "http://test/v1/chat/completions")
        raise openai.BadRequestError("logprobs not supported",
                                     response=httpx.Response(400, request=req), body=None)

    class RealishClient:
        chat = SimpleNamespace(completions=SimpleNamespace(create=_raise))

    from lab import models
    monkeypatch.setattr(models, "route", _directional_vote(orig_wins=False), raising=True)
    import lab.judgekit as jk
    v = jk.score_pair("原版片段", "退化片段", AXIS,
                      {"client": RealishClient(), "model": "m", "k": 3,
                       "model_slot": "judge_dev"})
    assert v.engine == "k_sample_vote"
    assert "logprobs" in v.fallback_reason
    assert v.score_a == pytest.approx(0.0)  # 退化版全票


def test_swarm_slot_goes_straight_to_vote(monkeypatch):
    """backend=cnb 的槽位不得触碰 llm_verifier(无端点),直连投票降级路径。"""
    from lab import models
    monkeypatch.setattr(models, "_load_lab_toml", lambda: {
        "models": {"judge_dev_swarm": {"backend": "cnb", "model": "codebuddy-random"}},
        "paths": {"transcripts": ":memory:"},
    })
    monkeypatch.setattr(models, "route", _directional_vote(orig_wins=True), raising=True)
    import lab.judgekit as jk
    v = jk.score_pair("原版片段", "退化片段", AXIS,
                      {"model_slot": "judge_dev_swarm", "k": 2})
    assert v.engine == "k_sample_vote"
    assert "cnb" in v.fallback_reason
    assert v.score_a == pytest.approx(1.0)


def test_run_exam_packed_aggregates(monkeypatch):
    """打包考试:跨对打包投票的聚合正确性(灵敏度/位置偏差/样本量门限)。"""
    import re as _re

    import lab.judgekit as jk
    from lab import swarm
    from lab.pairs import build_pair

    pairs = [
        build_pair(axis="prose_craft", a_text=f"……【甲】原版文本{i}……", b_text=f"……【乙】退化文本{i}……",
                   label="a_win", construction={"kind": "corpus_degraded", "op_id": "D05_inject_slop",
                                                "severity": 1,
                                                "source_script_id": f"scr:pk{i:024d}"},
                   split="exam")
        for i in range(4)
    ]

    def fake_batch(instructions, **kw):
        replies = []
        for ins in instructions:
            letters = []
            for gi, g in enumerate(_re.split(r"第\d+组:", ins)[1:], 1):
                first_seg = g.split("第二段:")[0]
                letters.append(f"{gi}:" + ("A" if "【甲】" in first_seg else "B"))
            replies.append(" ".join(letters))
        return replies

    monkeypatch.setattr(swarm, "run_batch", fake_batch)
    report = jk.run_exam_packed({"model_slot": "judge_dev_swarm", "k": 2}, pairs, pack_size=3)
    ax = report["axes"]["prose_craft"]
    assert ax["sensitivity"] == 1.0      # 所有投票判对(原版胜)
    assert ax["position_bias"] == 0.0    # 两方向结论一致
    assert ax["pass"] is False           # n=4 < min_exam_pairs_per_axis=100
    assert report["engine"] == "k_sample_vote_packed"


def test_run_exam_packed_excludes_corpus_vs_gen(monkeypatch):
    """考试只用退化锚:corpus_vs_gen 标签与判官真实偏好系统性相反(实证),不进考场。"""
    import re as _re

    import lab.judgekit as jk
    from lab import swarm
    from lab.pairs import build_pair

    def _mk(kind, i):
        return build_pair(axis="prose_craft", a_text=f"……【甲】原版{i}……", b_text=f"……【乙】退化{i}……",
                          label="a_win", construction={"kind": kind, "op_id": "D05_inject_slop",
                                                       "severity": 1,
                                                       "source_script_id": f"scr:ex{i:024d}"},
                          split="exam")

    pairs = [_mk("corpus_degraded", i) for i in range(2)] + \
            [_mk("corpus_vs_gen", i) for i in range(2, 5)]

    def fake_batch(instructions, **kw):
        replies = []
        for ins in instructions:
            letters = []
            for gi, g in enumerate(_re.split(r"第\d+组:", ins)[1:], 1):
                first_seg = g.split("第二段:")[0]
                letters.append(f"{gi}:" + ("A" if "【甲】" in first_seg else "B"))
            replies.append(" ".join(letters))
        return replies

    monkeypatch.setattr(swarm, "run_batch", fake_batch)
    report = jk.run_exam_packed({"model_slot": "judge_dev_swarm", "k": 1}, pairs, pack_size=5)
    assert report["corpus_vs_gen_excluded"] == 3
    assert report["axes"]["prose_craft"]["n_pairs"] == 2  # 只有退化锚进了考场


def test_run_exam_mock_report(tmp_path):
    from lab.degrade import REGISTRY
    from lab.pairs import build_pair
    pairs = []
    for i in range(6):
        op = list(REGISTRY.values())[i % len(REGISTRY)]
        pairs.append(build_pair(
            axis=op.axis, a_text=f"……【甲】原版文本{i}……", b_text=f"……【乙】退化文本{i}……",
            label="a_win", construction={"kind": "corpus_degraded", "op_id": op.id,
                                         "severity": 0.5, "source_script_id": f"scr:{i:025d}"},
            split="exam"))
    c = MockVerifierClient(a_wins=True)
    report = run_exam(_cfg(c), pairs)
    assert set(report["axes"]) == {p["axis"] for p in pairs}
    a = next(iter(report["axes"].values()))
    assert a["sensitivity"] == pytest.approx(1.0)   # mock 判官永远判对
    assert a["position_bias"] == pytest.approx(0.0)  # 交换后仍判原版胜
    render_exam_md(report, tmp_path / "judge_exam.md")
    md = (tmp_path / "judge_exam.md").read_text(encoding="utf-8")
    assert "判官考试报告" in md and "灵敏度" in md


def test_recording_client_writes_transcript(tmp_path):
    inner = MockVerifierClient(a_wins=True)
    db = tmp_path / "t.db"
    rc = RecordingClient(inner, "mock-judge", db_path=db)
    rc.chat.completions.create(messages=[{"role": "user", "content": "p"}], model="m")
    rows = json.loads(json.dumps(_read(db)))
    assert len(rows) == 1 and rows[0]["caller"] == "lab.judgekit"


def _read(db):
    import sqlite3
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute("SELECT * FROM transcripts")]


def test_axis_problem_has_no_answer_leak():
    p = axis_problem("l0_fact")
    assert "l0_fact" in p and "退化" not in p and "答案" not in p



def test_transitivity_chain_semantics():
    """传递性链 = orig>mid、mid>strong ⇒ orig>strong。
    断言判官实际收到的比较对:必须含 (mid,strong),且 (orig,mid) 只出现一次
    (旧实现把 orig>mid 比较了两遍、从不比 mid vs strong —— 本测试锁死新语义)。"""
    from lab.judgekit import _transitivity
    from lab.pairs import build_pair

    pairs = [build_pair(
        axis="prose_craft", a_text="【甲】原版", b_text=f"【乙】退化强度{sev}",
        label="a_win", construction={"kind": "corpus_degraded", "op_id": "D05_inject_slop",
                                     "severity": sev, "source_script_id": "scr:" + "0" * 25},
        split="exam") for sev in (0.5, 1.0)]

    compared: list[tuple[str, str]] = []

    class RecordMock(MockVerifierClient):
        def _create(self, **kw):
            msgs = kw.get("messages", [])
            prompt = msgs[0]["content"]
            pa = prompt.split("Trajectory A:")[-1].split("Trajectory B:")[0]
            pb = prompt.split("Trajectory B:")[-1]
            def mark(t):
                return "orig" if "原版" in t else ("mid" if "强度0.5" in t else "strong")

            if len(msgs) > 1:  # prefill:按被问的槽位给字母(质量 orig>mid>strong → A/B/C)
                is_tag_a = msgs[-1]["content"].rstrip().endswith("<score_A>")
                target = mark(pa) if is_tag_a else mark(pb)
                q = {"orig": 3, "mid": 2, "strong": 1}[target]
                return _resp("ABC"[3 - q])
            compared.append((mark(pa), mark(pb)))
            return _resp("分析")

    cfg = {"client": RecordMock(), "model": "m", "k": 1}
    t = _transitivity(pairs, "prose_craft", cfg)
    assert t == 1.0
    distinct = set(compared)
    assert ("mid", "strong") in distinct     # 链的中段必须被比较(旧实现从不比它)
    assert ("strong", "mid") in distinct
    assert ("orig", "strong") in distinct and ("strong", "orig") in distinct
    assert distinct == {("orig", "mid"), ("mid", "orig"), ("mid", "strong"),
                        ("strong", "mid"), ("orig", "strong"), ("strong", "orig")}
