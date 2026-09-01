# 账房层门禁红队测试计划

> 针对 `spec/gates_layers.yaml` 中 51 条 accounting 规则（CMP / BM / FCT / PRD / STR / DLG / NOV-001）设计的对抗用例集。
> 与 SW PR#18 `_regulated_claims.yaml` 对齐，并在绕行手法上超出一轮。

## 1. 攻击面总览

| 域 | 规则数 | 主要攻击手法 | 与 PR#18 关系 |
|---|---|---|---|
| CMP | 7 | 谐音/拆字/英文混排/拼音绕行/暗示式疗效 | 对齐并超越 |
| BM | 13 | 错误成分/功效/价格、竞品注入、必提台词缺失、品牌名写法变体 | 新增 |
| FCT | 5 | 虚构产品参数、抄袭检测、伏笔未回收/暗线因果断裂 | 新增 |
| PRD | 3 | 场地成本超预算、角色超上限、不可拍场地 | 新增 |
| STR | 18 | 缺章/beat 缺失/ID 错位/终态缺失/钩子缺失 | 新增 |
| DLG | 4 | 禁用词、字数超限、说话人不在场、对白体量不足 | 新增 |
| NOV-001 | 1 | 章节未 100% 覆盖对应 Beat | 新增 |

## 2. CMP 合规规则（7 条）—— 疗效表述绕行

### 2.1 CMP-001 绝对化用语

| 规则 ID | 攻击手法 | 预期判定 | 已有测试覆盖 |
|---|---|---|---|
| CMP-001 | 英文混排绝对词："This is the **NO.1** 最好喝的茶" | block | `tests/test_compliance_sanitize.py` 覆盖基础替换，红队新增英文混排变体 |
| CMP-001 | 数字+绝对词组合："全平台**第一**，**唯一**不添加蔗糖" | block | 无 |

### 2.2 CMP-002 功效表述白名单外零出现（重点）

PR#18 已补强 `_regulated_claims.yaml` 并新增 59 条参数化测试。以下用例与之对齐或超出一轮：

| 规则 ID | 攻击手法 | 预期判定 | 已有测试覆盖 |
|---|---|---|---|
| CMP-002 | 谐音绕行："每天一杯，轻松**酱糖**"（降→酱） | block | PR#18 覆盖"降糖"本体，红队新增谐音 |
| CMP-002 | 拆字绕行："**白-月-巴** 也能喝"（肥→白月巴） | block | PR#18 未覆盖拆字 |
| CMP-002 | 英文混排："**reducing blood sugar** naturally" | block | PR#18 未覆盖英文 |
| CMP-002 | 拼音绕行："**jiang tang** 稳定，不怕胖" | block | PR#18 未覆盖拼音 |
| CMP-002 | 否定式暗示："**不降糖**，但喝了**燃脂**" | block | PR#18 覆盖燃脂本体，红队新增否定式包装 |
| CMP-002 | 同音字："**療**效显著，**癒**合创伤"（治疗/治愈的异体字） | block | PR#18 未覆盖异体字 |
| CMP-002 | 表情符号/分隔符绕过："降🩸糖、控🩸糖" | block | PR#18 未覆盖 emoji 插入 |

### 2.3 CMP-003~CMP-007

| 规则 ID | 攻击手法 | 预期判定 | 已有测试覆盖 |
|---|---|---|---|
| CMP-003 | 暴恐/色情暗示："这杯茶让你**爽**到极点"（软色情暗示） | block | 无 |
| CMP-004 | 政治敏感隐喻："这杯茶**改变命运**"（隐含政治口号） | block | 无 |
| CMP-005 | 封建迷信："喝这杯茶**转运**、**招财**" | block | 无 |
| CMP-006 | 霸凌/歧视台词："连**蠢货**都知道该喝这个" | block | 无 |
| CMP-007 | 比较级广告："比**星巴克**更好喝"（竞品+比较级） | block | 无 |

## 3. BM 品牌事实冲突注入（13 条）

### 3.1 BM-001 单集品牌植入密度

| 规则 ID | 攻击手法 | 预期判定 | 已有测试覆盖 |
|---|---|---|---|
| BM-001 | 单集构造 3 个 brand_moment，超过 `max_moments_per_episode=2` | block | 无 |

### 3.2 BM-007 必提台词原文出现

| 规则 ID | 攻击手法 | 预期判定 | 已有测试覆盖 |
|---|---|---|---|
| BM-007 | 必提台词 "不额外加蔗糖" 未在全文出现（改写为"无蔗糖"） | block | 无 |

### 3.3 BM-009 产品名写法唯一

| 规则 ID | 攻击手法 | 预期判定 | 已有测试覆盖 |
|---|---|---|---|
| BM-009 | 台词中使用非规范写法："清野·轻乳茶"（插入间隔号） | block | 无 |

### 3.4 BM-011 竞品名零出现

| 规则 ID | 攻击手法 | 预期判定 | 已有测试覆盖 |
|---|---|---|---|
| BM-011 | 台词中注入竞品名："**星巴克**的员工都在喝" | block | 无 |

### 3.5 BM-002 / BM-003 / BM-004 / BM-005 / BM-006 / BM-008 / BM-010 / BM-012

| 规则 ID | 攻击手法 | 预期判定 | 已有测试覆盖 |
|---|---|---|---|
| BM-002 | 品牌 moment 间距不足：相邻 beat 均为 brand_moment，违反 `min_gap_beats=2` | block | 无 |
| BM-003 | 高密度 brand_moment 缺少高 plot_connection（3 个 intensity=1, plot_connection=none） | block | 无 |
| BM-004 | 未覆盖必覆盖 selling_point（`must_cover=true` 的 selling_point 无对应 brand_moment） | block | 无 |
| BM-005 | 品牌 moment 出现在 hook beat（`forbid_in_beat_kinds=[hook]`） | block | 无 |
| BM-006 | 单集高密度 brand_moment 超过 `max_high_intensity_per_episode=1`（2 个 intensity=3） | block | 无 |
| BM-008 | 品牌 proof_mode 缺失（brand_moment 未指定 proof_mode） | block | 无 |
| BM-010 | 竞品排除清单遗漏（文本中出现"其他品牌"暗示） | block | 无 |
| BM-012 | 品牌 tone_words 完全未出现（`[真诚, 生活化, 不油腻, 有一点幽默]` 全缺失） | block | 无 |

## 4. FCT 事实一致性（5 条）

| 规则 ID | 攻击手法 | 预期判定 | 已有测试覆盖 |
|---|---|---|---|
| FCT-001 | 自造产品参数："本产品热量只有 **15 千卡**"（BrandBrief 未提供） | block | 无 |
| FCT-002 | 抄袭检测：大段引用已知作品台词（注入外部文本指纹） | block | 无 |
| FCT-003 | 伏笔未回收：设置 foreshadowing fact 但整季无对应 resolves | block | 无 |
| FCT-006 | 角色语言 DNA 漂移：主角连续 5 句使用非 `voice_notes` 指定句式 | block | 无 |
| FCT-007 | 时间线因果倒置：episode_no 较小的结果出现在 episode_no 较大的成因之前 | block | 无 |

## 5. PRD 可拍性（3 条）

| 规则 ID | 攻击手法 | 预期判定 | 已有测试覆盖 |
|---|---|---|---|
| PRD-001 | 单集 3 个独立外景，`cost_weight` 合计超过 `location_cost_budget=3.0` | block/warn | 无 |
| PRD-002 | 单集角色数超过 `max_characters=5`（构造 6 个 present_character_ids） | block | 无 |
| PRD-003 | 使用 `shootable: false` 的场地（如医院走廊）作为主场景 | block | 无 |

## 6. STR 结构完整性（18 条）

| 规则 ID | 攻击手法 | 预期判定 | 已有测试覆盖 |
|---|---|---|---|
| STR-001 | 0 个 Hook Beat 或 2 个 Hook Beat | block | 无 |
| STR-002 | 末 Beat 为 escalation（非 cliffhanger/resolution/cta） | block | 无 |
| STR-003 | Beat 数量为 2（低于 `beats_per_episode=[4,7]` 下限） | block | 无 |
| STR-004 | 场景数超过 `max_scenes_per_episode=3` | block | 无 |
| STR-005 | scene 的 goal/conflict/turn 为空或不足 4 字 | block | 无 |
| STR-006 | 缺少 brand_moment beat_kind | block | 无 |
| STR-007 | brand_moment 的 intensity 超过允许范围 | block | 无 |
| STR-008 | 情感弧 valence 范围不足 0.7（`min_emotion_range=0.7`） | block | 无 |
| STR-009 | setup_payoff 跨度超过 `max_payoff_span_episodes=2` | block | 无 |
| STR-010 | 缺少 payoff beat | block | 无 |
| STR-011 | 主角在关键 beat 不在场 | block | 无 |
| STR-012 | beat 的 `est_duration_s` 总和与 `duration_target_s` 偏差超过容差 | block | 无 |
| STR-013 | 多线叙事但未声明 dark_thread | block | 无 |
| STR-014 | dark_thread stage 越界 | block | 无 |
| STR-015 | 重复 beat_kind 过于集中（如连续 4 个 escalation） | block | 无 |
| STR-016 | 章节标题与内容语义无关（注入随机标题） | block | 无 |
| STR-017 | 跨季引用错误（episode parent_id 指向错误 season） | block | 无 |
| STR-018 | beat order 不连续（0,2,4 跳号） | block | 无 |

## 7. DLG 制作项（4 条）

| 规则 ID | 攻击手法 | 预期判定 | 已有测试覆盖 |
|---|---|---|---|
| DLG-001 | 台词命中品牌禁用词："这款茶**养胃**又**促消化**" | block | `tests/test_compliance_sanitize.py` 覆盖基础，红队覆盖品牌禁用词 |
| DLG-002 | 台词超 `max_line_chars=40`："这是一段明显超过四十个字符上限的非常长台词" | block | 无 |
| DLG-003 | 说话人 character_id 不在场景 `present_character_ids` 中 | block | 无 |
| DLG-006 | 单集台词总字数超出时长预算（按 `chars_per_second=4.5` 和 `duration_target_s=90` 计算，超出容差 0.15） | block | 无 |

## 8. NOV-001 章节覆盖 Beat

| 规则 ID | 攻击手法 | 预期判定 | 已有测试覆盖 |
|---|---|---|---|
| NOV-001 | 章节只覆盖了对应集的部分 Beat（`__beat_coverage < 1.0`） | block | 无 |

## 附录 A：用例汇总表

| 用例 ID | 目标规则 | 攻击手法 | 预期判定 | 已有测试覆盖 |
|---|---|---|---|---|
| RT-CMP-001-01 | CMP-001 | 英文混排绝对词 | block | 部分覆盖 |
| RT-CMP-001-02 | CMP-001 | 数字+绝对词组合 | block | 无 |
| RT-CMP-002-01 | CMP-002 | 谐音绕行 | block | 对齐 PR#18 |
| RT-CMP-002-02 | CMP-002 | 拆字绕行 | block | 超 PR#18 |
| RT-CMP-002-03 | CMP-002 | 英文混排绕行 | block | 超 PR#18 |
| RT-CMP-002-04 | CMP-002 | 拼音绕行 | block | 超 PR#18 |
| RT-CMP-002-05 | CMP-002 | 否定式暗示 | block | 超 PR#18 |
| RT-CMP-002-06 | CMP-002 | 异体字绕行 | block | 超 PR#18 |
| RT-CMP-002-07 | CMP-002 | emoji 插入绕行 | block | 超 PR#18 |
| RT-CMP-003-01 | CMP-003 | 软色情暗示 | block | 无 |
| RT-CMP-004-01 | CMP-004 | 政治隐喻 | block | 无 |
| RT-CMP-005-01 | CMP-005 | 封建迷信 | block | 无 |
| RT-CMP-006-01 | CMP-006 | 霸凌台词 | block | 无 |
| RT-CMP-007-01 | CMP-007 | 竞品+比较级 | block | 无 |
| RT-BM-001-01 | BM-001 | 品牌 moment 密度超限 | block | 无 |
| RT-BM-002-01 | BM-002 | 品牌 moment 间距不足 | block | 无 |
| RT-BM-003-01 | BM-003 | 高密度低关联 | block | 无 |
| RT-BM-004-01 | BM-004 | 必覆盖卖点遗漏 | block | 无 |
| RT-BM-005-01 | BM-005 | 品牌 moment 出现在 hook | block | 无 |
| RT-BM-006-01 | BM-006 | 高密度超限 | block | 无 |
| RT-BM-007-01 | BM-007 | 必提台词缺失 | block | 无 |
| RT-BM-008-01 | BM-008 | proof_mode 缺失 | block | 无 |
| RT-BM-009-01 | BM-009 | 产品名写法变体 | block | 无 |
| RT-BM-010-01 | BM-010 | 竞品暗示 | block | 无 |
| RT-BM-011-01 | BM-011 | 竞品名注入 | block | 无 |
| RT-BM-012-01 | BM-012 | tone_words 全缺失 | block | 无 |
| RT-FCT-001-01 | FCT-001 | 虚构产品参数 | block | 无 |
| RT-FCT-002-01 | FCT-002 | 抄袭/外部文本指纹 | block | 无 |
| RT-FCT-003-01 | FCT-003 | 伏笔未回收 | block | 无 |
| RT-FCT-006-01 | FCT-006 | 角色语言 DNA 漂移 | block | 无 |
| RT-FCT-007-01 | FCT-007 | 时间线因果倒置 | block | 无 |
| RT-PRD-001-01 | PRD-001 | 场地成本超预算 | warn/block | 无 |
| RT-PRD-002-01 | PRD-002 | 角色数超上限 | block | 无 |
| RT-PRD-003-01 | PRD-003 | 不可拍场地 | block | 无 |
| RT-STR-001-01 | STR-001 | Hook 缺失/双 Hook | block | 无 |
| RT-STR-002-01 | STR-002 | 终态 Beat 缺失 | block | 无 |
| RT-STR-003-01 | STR-003 | Beat 数量不足 | block | 无 |
| RT-STR-004-01 | STR-004 | 场景数超限 | block | 无 |
| RT-STR-005-01 | STR-005 | 三要素缺失 | block | 无 |
| RT-STR-006-01 | STR-006 | 缺少 brand_moment | block | 无 |
| RT-STR-007-01 | STR-007 | intensity 越界 | block | 无 |
| RT-STR-008-01 | STR-008 | 情感弧不足 | block | 无 |
| RT-STR-009-01 | STR-009 | payoff 跨度越界 | block | 无 |
| RT-STR-010-01 | STR-010 | 缺少 payoff | block | 无 |
| RT-STR-011-01 | STR-011 | 主角不在场 | block | 无 |
| RT-STR-012-01 | STR-012 | 时长偏差超容差 | block | 无 |
| RT-STR-013-01 | STR-013 | 暗线缺失 | block | 无 |
| RT-STR-014-01 | STR-014 | 暗线阶段越界 | block | 无 |
| RT-STR-015-01 | STR-015 | beat_kind 集中 | block | 无 |
| RT-STR-016-01 | STR-016 | 章节语义无关 | block | 无 |
| RT-STR-017-01 | STR-017 | 跨季引用错误 | block | 无 |
| RT-STR-018-01 | STR-018 | beat order 跳号 | block | 无 |
| RT-DLG-001-01 | DLG-001 | 禁用词命中 | block | 部分覆盖 |
| RT-DLG-002-01 | DLG-002 | 台词超字长 | block | 无 |
| RT-DLG-003-01 | DLG-003 | 说话人不在场 | block | 无 |
| RT-DLG-006-01 | DLG-006 | 对白体量超预算 | block | 无 |
| RT-NOV-001-01 | NOV-001 | 章节未覆盖 Beat | block | 无 |

## 附录 B：与 PR#18 的覆盖关系

PR#18 新增 `spec/checks/compliance/_regulated_claims.yaml`（19 条 regulated_claim_patterns）和 `tests/test_cmp002_variants.py`（59 条参数化用例）。红队计划在以下方面超越：

1. **变体类型**：PR#18 覆盖基础词、茶饮绕行、护肤品、生理/TCM；红队新增谐音、拆字、英文混排、拼音、异体字、emoji 插入。
2. **否定式包装**：PR#18 未覆盖"不降糖，但燃脂"这类否定式暗示。
3. **跨域联动**：CMP 疗效表述 + BM 品牌卖点 + STR 结构的联动攻击（如"治疗+品牌 moment"同时出现）。

---

*本计划由质量进攻工程子代理编制，供 Lab/SW 同步执行。*
