"""L-05 · 退化算子库。契约:spec/degradation/operators.yaml(一一对应,导入时校验);
补充约定:spec/parsing_conventions.md §退化算子的补充约定。

机制二分:deterministic = 纯规则、同 rng_seed 可复现;llm_mid = 中档模型按指令改写
(缺陷由指令注入,标签仍由构造保证),调用一律经 lab.models 路由写 transcript。

通用约定(本文件实现层,PR 偏差记录):
- severity ∈ [0,1],1 = 最大退化强度;算子在各自 spec severity 带内按 rng 插值。
- 删除型算子不得删除输入非空白字符的 30% 以上(D14 整行删【回收】除外)。
- 目标结构缺失时,删除型算子降级为"删除最长非标记行",注入型算子按注入语义继续——
  保证确定性算子对任何非空输入都产生可见变化(测试契约:退化必须真的改变文本)。
"""
from __future__ import annotations

import itertools
import random
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import yaml

SPEC_PATH = Path(__file__).parents[2] / "spec" / "degradation" / "operators.yaml"
MAX_DELETE_RATIO = 0.30
HOOK_MARKERS = ("【钩子】", "【悬念】", "【反转】")

# D05 内置种子词表(≥10 常见 AI 套话);mined/slop_lexicon.yaml 存在时合并(L-04 产物)
SLOP_SEEDS = [
    "他的眼中闪过一丝不易察觉的复杂情绪",
    "空气仿佛凝固了一般",
    "嘴角勾起一抹意味深长的弧度",
    "她的心跳漏了一拍",
    "一股无名火从心底窜起",
    "时间仿佛静止了",
    "他的声音里带着一丝颤抖",
    "让人不寒而栗",
    "所有的努力都化为了泡影",
    "命运的齿轮开始转动",
    "仿佛抓住了最后一根救命稻草",
    "夜色如墨,压得人喘不过气",
]


def _slop_lexicon() -> list[str]:
    lex = list(SLOP_SEEDS)
    mined = Path(__file__).parents[2] / "mined" / "slop_lexicon.yaml"
    if mined.exists():
        try:
            data = yaml.safe_load(mined.read_text(encoding="utf-8")) or {}
            entries = data.get("entries") if isinstance(data, dict) else data
            if isinstance(entries, list):
                for e in entries:
                    phrase = e.get("phrase") if isinstance(e, dict) else e
                    if isinstance(phrase, str) and phrase.strip():
                        lex.append(phrase.strip())
        except yaml.YAMLError:
            pass
    seen: set[str] = set()
    return [x for x in lex if not (x in seen or seen.add(x))]


# ---- 文本结构工具 ----

def _lines(text: str) -> list[str]:
    return text.splitlines()


def _nonspace_len(text: str) -> int:
    return len("".join(text.split()))


def _ep_bounds(lines: list[str]) -> list[tuple[int, int]]:
    """集/章边界 [(start,end_exclusive)];无标题 → 整体一段。"""
    marks = [i for i, ln in enumerate(lines) if re.match(r"^第[0-9零一二三四五六七八九十百千]+[集章]", ln.strip())]
    if not marks:
        return [(0, len(lines))] if lines else []
    bounds = [(a, b) for a, b in zip([0, *marks], [*marks, len(lines)]) if b > a]
    return bounds or [(0, len(lines))]


def _cap_delete(text: str, out: str) -> str:
    """删除超 30% 时退回原文(算子放弃而非过度删除)。"""
    if _nonspace_len(text) == 0:
        return text
    deleted = _nonspace_len(text) - _nonspace_len(out)
    return out if deleted <= _nonspace_len(text) * MAX_DELETE_RATIO else text


def _greedy_delete(text: str, lines: list[str], victims: list[int]) -> str:
    """按 victims 顺序逐行删,累计不超过 30% 上限(至少尝试 1 行;单行超限则原样返回)。"""
    total = _nonspace_len(text)
    out: list[str] = []
    victim_set: set[int] = set()
    deleted = 0
    for i in victims:
        cost = _nonspace_len(lines[i])
        if deleted + cost > total * MAX_DELETE_RATIO:
            continue
        victim_set.add(i)
        deleted += cost
    if not victim_set:
        return text
    out = [ln for i, ln in enumerate(lines) if i not in victim_set]
    return _join(out)


def _fallback_delete_longest(lines: list[str]) -> list[str]:
    """目标结构缺失时的通用降级:删掉最长非标记行(可复现)。"""
    idx = max((i for i, ln in enumerate(lines) if ln.strip()), key=lambda i: len(lines[i]), default=-1)
    return [ln for i, ln in enumerate(lines) if i != idx] if idx >= 0 else lines


def _band(rng: random.Random, lo_hi: tuple[float, float], severity: float) -> float:
    lo, hi = lo_hi
    return lo + (hi - lo) * max(0.0, min(1.0, severity))


# ---- deterministic 算子 ----

def _d01_shuffle_beats(text: str, severity: float, seed: int) -> str:
    rng = random.Random(seed)
    lines = _lines(text)
    swaps = max(1, round(_band(rng, (1, 3), severity)))
    out = list(lines)
    for a, b in _ep_bounds(lines):
        # beat = 场次块;无场次行时 = 非空段块
        seg = out[a:b]
        scene_idx = [i for i, ln in enumerate(seg) if ln.strip().startswith("场景")]
        if len(scene_idx) >= 2:
            # anchor the head (e.g. episode title) before the first scene;
            # shuffle only the scene-delimited blocks so no content is dropped
            head, blocks = seg[:scene_idx[0]], _split_by(seg, scene_idx)
        else:
            head, blocks = [], _split_paragraphs(seg)
        if len(blocks) < 2:
            continue
        for _ in range(min(swaps, len(blocks) - 1)):
            i, j = sorted(rng.sample(range(len(blocks)), 2))
            blocks[i], blocks[j] = blocks[j], blocks[i]
        out[a:b] = head + [ln for blk in blocks for ln in blk]
    return "\n".join(out) if out != lines else _join(_fallback_delete_longest(lines))


def _split_by(seg: list[str], idx: list[int]) -> list[list[str]]:
    bounds = idx + [len(seg)]
    return [seg[a:b] for a, b in itertools.pairwise(bounds)]


def _split_paragraphs(seg: list[str]) -> list[list[str]]:
    blocks: list[list[str]] = []
    cur: list[str] = []
    for ln in seg:
        if ln.strip():
            cur.append(ln)
        else:
            if cur:
                blocks.append(cur)
                cur = []
    if cur:
        blocks.append(cur)
    return blocks or [seg]


def _join(lines: list[str]) -> str:
    return "\n".join(lines)


def _d02_remove_hook(text: str, severity: float, seed: int) -> str:
    rng = random.Random(seed)
    lines = _lines(text)
    hooks = [i for i, ln in enumerate(lines) if any(m in ln for m in HOOK_MARKERS)]
    if not hooks:
        return _join(_fallback_delete_longest(lines))
    k = max(1, round(len(hooks) * max(0.2, severity)))
    victims = rng.sample(hooks, min(k, len(hooks)))
    return _greedy_delete(text, lines, victims)


def _d05_inject_slop(text: str, severity: float, seed: int) -> str:
    rng = random.Random(seed)
    lex = _slop_lexicon()
    per_1k = _band(rng, (2, 8), severity)
    n = max(1, round(per_1k * _nonspace_len(text) / 1000))
    lines = _lines(text)
    insert_at = sorted(rng.sample(range(len(lines) + 1), min(n, len(lines) + 1)))
    out: list[str] = []
    pos = 0
    for i in insert_at:
        out.extend(lines[pos:i])
        out.append(rng.choice(lex))
        pos = i
    out.extend(lines[pos:])
    return _join(out)


def _d07_pov_break(text: str, severity: float, seed: int) -> str:
    rng = random.Random(seed)
    lines = _lines(text)
    speakers = _speakers(lines)
    if len(speakers) < 2:
        # 无人名可换:他/她 对调(视角指称越界)
        return text.replace("他", "她", 1) + ("" if "他" in text else "\n(他把这一切看在眼里。)")
    src, dst = rng.sample(speakers, 2)
    n = max(1, round(_band(rng, (1, 5), severity)))
    out, replaced = [], 0
    for ln in lines:
        if replaced < n and src in ln and not _is_dialogue_line(ln):
            ln = ln.replace(src, dst, 1)
            replaced += 1
        out.append(ln)
    if replaced == 0:  # 全是对白行:退而对白行内替换
        for i, ln in enumerate(out):
            if replaced >= n:
                break
            if src in ln:
                out[i] = ln.replace(src, dst, 1)
                replaced += 1
    return _join(out) if replaced else _join(_fallback_delete_longest(lines))


def _speakers(lines: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    for ln in lines:
        m = re.match(r"^([一-龥A-Za-z]{1,8})[:：]", ln.strip())
        if m and m.group(1) != "场景":
            seen[m.group(1)] = seen.get(m.group(1), 0) + 1
    return [s for s, _ in sorted(seen.items(), key=lambda kv: -kv[1])]


def _is_dialogue_line(ln: str) -> bool:
    m = re.match(r"^([一-龥A-Za-z]{1,8})[:：]", ln.strip())
    return bool(m) and m.group(1) != "场景" and not ln.strip().startswith("【")


_AGE = re.compile(r"(\d{1,3})\s*岁")
_TIME = re.compile(r"(三|两|几|十|[0-9一二三四五六七八九十]+)\s*(天|日|年|月|小时)后")
_PLACE = re.compile(r"在([一-龥]{2,6})(市|城|镇|村|山|岛)")


def _d08_inject_contradiction(text: str, severity: float, seed: int) -> str:
    rng = random.Random(seed)
    lines = _lines(text)
    contradictions: list[str] = []
    m = _AGE.search(text)
    if m:
        contradictions.append(f"(其实他今年分明是{int(m.group(1)) + 20}岁,刚才不过是瞒着说的。)")
    m2 = _TIME.search(text)
    if m2:
        contradictions.append(f"(实际上才过了半个{m2.group(2)},所谓{m2.group(0)}根本是记错了。)")
    m3 = _PLACE.search(text)
    if m3:
        contradictions.append(f"(他们其实身在千里之外,所谓{m3.group(1)}只是说辞。)")
    if not contradictions:
        contradictions.append("(而这一切,其实发生在整整十年前的同一个地方。)")
    stmt = rng.choice(contradictions)
    idx = rng.randrange(len(lines) + 1)
    out = lines[:idx] + [stmt] + lines[idx:]
    return _join(out)


def _d09_brand_cut(text: str, severity: float, seed: int) -> str:
    # 卖点/产品名特征:量化承诺句(数字+量词)、品牌标记行
    rng = random.Random(seed)
    lines = _lines(text)
    target = [
        i for i, ln in enumerate(lines)
        if re.search(r"[\d一二两三四五六七八九十百千]+[折%％%]|[\d一二两三四五六七八九十百千]+\s*(斤|克|毫升|包|盒|件|年|天|次)", ln)
        or "品牌" in ln or "广告" in ln or "植入" in ln
    ]
    if not target:
        return _join(_fallback_delete_longest(lines))
    k = max(1, round(len(target) * max(0.3, severity)))
    victims = rng.sample(target, min(k, len(target)))
    return _greedy_delete(text, lines, victims)


def _d10_brand_overstuff(text: str, severity: float, seed: int) -> str:
    rng = random.Random(seed)
    per_ep = _band(rng, (5, 12), severity)
    lines = _lines(text)
    token = _most_frequent_token(text) or "本品牌"
    out: list[str] = []
    for a, b in _ep_bounds(lines):
        n = max(1, round(per_ep))
        seg = lines[a:b]
        for _ in range(n):
            pos = rng.randrange(len(seg) + 1)
            seg = seg[:pos] + [f"{token},{token},还是{token}。"] + seg[pos:]
        out.extend(seg)
    return _join(out) if out else f"{token},{token},{token}。"


def _most_frequent_token(text: str) -> str:
    words = re.findall(r"[一-龥]{2,3}", text)
    if not words:
        return ""
    seen: dict[str, int] = {}
    for w in words:
        seen[w] = seen.get(w, 0) + 1
    return max(seen, key=lambda w: seen[w])


def _d12_info_stuffing(text: str, severity: float, seed: int) -> str:
    rng = random.Random(seed)
    pad_ratio = _band(rng, (0.15, 0.4), severity)
    total = _nonspace_len(text)
    budget = max(1, round(total * pad_ratio))
    sents = [s.strip() for s in re.split(r"(?<=[。!?…?!])", text) if s.strip()]
    lines = _lines(text)
    pads: list[str] = []
    acc = 0
    rng.shuffle(sents)
    for s in sents:
        if acc >= budget or not sents:
            break
        pad = f"要知道,{s}"
        pads.append(pad)
        acc += _nonspace_len(pad)
    if not pads:
        pads = ["要知道,事情就是这样。"]
    out = list(lines)
    for pad in pads:
        idx = rng.randrange(len(out) + 1)
        out = out[:idx] + [pad] + out[idx:]
    return _join(out)


def _d14_setup_cut(text: str, severity: float, seed: int) -> str:
    # 语义约定(parsing_conventions §D14):删除【回收】标记行(整行),不受 30% 上限约束
    lines = _lines(text)
    has = [ln for ln in lines if "【回收】" in ln]
    out = [ln for ln in lines if "【回收】" not in ln]
    if not has:
        # 无标记可删时降级:删掉最长的对白行(等效于拆掉一次承接),仍整行删
        idx = max((i for i, ln in enumerate(lines) if _is_dialogue_line(ln)), key=lambda i: len(lines[i]), default=-1)
        if idx < 0:
            return _join(_fallback_delete_longest(lines))
        out = [ln for i, ln in enumerate(lines) if i != idx]
    return _join(out)


_PROD_BREAKS = [
    "【制作】千人群演涌上街头,鼓声震天。",
    "【制作】全息特效包裹整条街道,雨滴悬浮在半空。",
    "【制作】实景航拍雪山之巅,剧组转场三次。",
    "【制作】爆破场面连炸七辆真车。",
    "【制作】水下长镜头,演员闭气三分钟。",
]


def _d15_producibility_break(text: str, severity: float, seed: int) -> str:
    rng = random.Random(seed)
    n = max(1, round(_band(rng, (1, 4), severity)))
    lines = _lines(text)
    for _ in range(n):
        idx = rng.randrange(len(lines) + 1)
        lines = lines[:idx] + [rng.choice(_PROD_BREAKS)] + lines[idx:]
    return _join(lines)


# ---- llm_mid 算子(经 lab.models 路由;真实调用仅 --run-llm) ----

_LLM_PRELUDE = "你是短剧文本退化器。对下面的剧本片段执行指定的退化改写。只输出改写后的全文,不要解释。\n"


def _llm_rewrite(instruction: str, text: str, severity: float, seed: int) -> str:
    from lab.models import route
    prompt = (_LLM_PRELUDE + f"退化指令:{instruction}(强度 {severity:.2f},随机种子 {seed})\n---\n{text}")
    return route("generation", prompt, caller="lab.degrade", temperature=0.7)


def _d03_flatten_cliffhanger(text: str, severity: float, seed: int) -> str:
    return _llm_rewrite(
        "把结尾的悬念/钩子改写为平铺直叙的收尾:事件内容全部保留,删去紧张感与留白,像总结陈词一样把结局说完", text, severity, seed)


def _d04_flatten_rhythm(text: str, severity: float, seed: int) -> str:
    return _llm_rewrite(
        "把所有句子改写成长度接近的中等长度句,消除长短句交错与节奏变化,内容不变", text, severity, seed)


def _d06_voice_homogenize(text: str, severity: float, seed: int) -> str:
    return _llm_rewrite(
        "把所有角色的台词改写成同一种腔调(平铺、书面、无个性),称呼与称呼语统一,信息不变", text, severity, seed)


def _d11_pacing_flatten(text: str, severity: float, seed: int) -> str:
    return _llm_rewrite(
        "删除所有反转与张力峰,事件按时间顺序平铺直叙,冲突改为顺理成章地解决", text, severity, seed)


def _d13_dialogue_to_narration(text: str, severity: float, seed: int) -> str:
    return _llm_rewrite(
        "把大部分对白改写成旁白叙述(保留说话人身份信息但不再用对白格式),信息不变", text, severity, seed)


# ---- 注册表(与 spec 一一对应,导入时强制) ----

_IMPL: dict[str, Callable[[str, float, int], str]] = {
    "D01_shuffle_beats": _d01_shuffle_beats,
    "D02_remove_hook": _d02_remove_hook,
    "D03_flatten_cliffhanger": _d03_flatten_cliffhanger,
    "D04_flatten_rhythm": _d04_flatten_rhythm,
    "D05_inject_slop": _d05_inject_slop,
    "D06_voice_homogenize": _d06_voice_homogenize,
    "D07_pov_break": _d07_pov_break,
    "D08_inject_contradiction": _d08_inject_contradiction,
    "D09_brand_cut": _d09_brand_cut,
    "D10_brand_overstuff": _d10_brand_overstuff,
    "D11_pacing_flatten": _d11_pacing_flatten,
    "D12_info_stuffing": _d12_info_stuffing,
    "D13_dialogue_to_narration": _d13_dialogue_to_narration,
    "D14_setup_cut": _d14_setup_cut,
    "D15_producibility_break": _d15_producibility_break,
}


@dataclass(frozen=True)
class Operator:
    id: str
    axis: str
    mechanism: str
    desc: str
    fn: Callable[[str, float, int], str]
    lexicon: list[str] = field(default_factory=list)

    def apply(self, text: str, severity: float, rng_seed: int) -> str:
        return self.fn(text, severity, rng_seed)


def _build_registry() -> dict[str, Operator]:
    spec = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))
    reg: dict[str, Operator] = {}
    for op in spec["operators"]:
        impl = _IMPL.get(op["id"])
        if impl is None:
            raise KeyError(f"spec 算子 {op['id']} 缺实现")
        lex = _slop_lexicon() if op["id"] == "D05_inject_slop" else []
        reg[op["id"]] = Operator(op["id"], op["axis"], op["mechanism"], op.get("desc", ""), impl, lex)
    missing = set(_IMPL) - set(reg)
    if missing:
        raise KeyError(f"实现多余的算子:{missing}")
    return reg


REGISTRY: dict[str, Operator] = _build_registry()
