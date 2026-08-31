# ADR-0004：质量进攻路线——从"不出错"到"好读"的五项改造

- 状态：proposed（2026-08-31 审查报告提出，待 owner 裁决后由 optimizer 逐项执行）
- 影响层：SW spec/rubrics · SW src/nsc/passes/p6_prose.py · SW spec/checks · Lab criteria/ · 案例检索层
- 关联：ADR-0001 L-D2（三锚）· ADR-0003（契约 v2）· SW docs/DEVELOPING.md 遗留问题清单

## 背景

第二阶段总结（2026-08-28）owner 判断："单纯的门禁/禁止性要求不能让小说变好"。
2026-08-31 全仓审查实证四个结构性根因（相互叠加，非单点 bug）：

1. **判官奖励平淡**：rubric_v1 六轴中品牌/合规向（naturalness+placement+transportation）
   合计 0.60，文笔（prose_craft）仅 0.10，且**无"追读性"维度**；round24 实证判官
   偏爱"广告式顺滑"版本（R3 craft 最好、判官偏爱 v3）。
2. **p6 逐字对白锚定**：p6_prose.py 要求每句剧本对白逐字织入小说段落
   （`str(ln.get("text")) in para_blob`，NOV-001 覆盖率的实现层）——写手只能在
   固定台词之间织补连接段，无重写自由，是平淡的最大硬来源。
3. **39 条 block 门禁主导修订循环**：修订 brief 以"消违规"为目标，LLM 向
   "合规且中庸"收敛；W4 实证一过能力不迁移（demo_tea 5 attempts 五种门禁死法，
   harness 硬化是 brief 特异的）。
4. **语料锚把"好"定义为平庸**：corpus hook_density P50=0、novel dialogue_ratio
   中位 0.02——模板化短剧分布的群体均值定义"带内=好"（L-D2 锚的先天缺陷）。

参照系：narracat-novel-agent 的分层纪律——客观一致性归账房层做硬门、主观质量归
创作层喂范例+选择压力、评价层只度量不阻断。与本项目第二阶段已验证的
"正向契约+选择压力+craft_bench"（craft_bench 0.559→0.839）同向。

## 决定（五项改造，按期望值排序）

### Q1 判官轴重构（对应根因 1）

- 新增第七轴 `reading_attraction`（追读性，applies_to: chapter/episode）：
  question="这段读完想不想翻下一页？有没有一个具体可转述的记忆点？"
  positive_signals=[章末钩具体可感, 悬念指向具体对象, 情绪有起伏落差, 存在可转述名场面]；
  negative_signals=[章末无钩, 悬念空泛, 情绪平直, 读完无记忆点]。
- 权重再平衡：prose_craft 0.10→0.25，reading_attraction 新增 0.15，
  naturalness 0.25→0.15，placement_integration 0.20→0.15（实物产品 brief 恢复 0.20）。
- placement 轴 anchor 从"顺滑展示"改为"戏剧化融入"（产品是解决冲突的必要条件、
  卖点由后果体现——positive_signals 已有，anchor 权重未跟上）。
- 配套：Lab criteria/ 新增 reading_attraction.md；改 rubric 必须重跑 make judge-cal
  （GATES.md 既有纪律）；阈值进 eval/thresholds.yaml。

### Q2 p6 逐字锚定解绑（对应根因 2）

- NOV-001 从"对白逐字织入"放宽为"戏剧功能锚定"：每个 beat 的戏剧功能可识别
  （冲突发生、价值转换、钩子落地），小说写手有权重写对白。
- 实现路径：p6_prose.py 的逐字校验改为 beat 级 anchor_map（beat_id 必须存在，
  line_ids 变为可选引用）；剧本（p7 screenplay.fountain）仍走 p5 逐字对白——
  剧本是执行物、小说是确认物，两者文体解耦。
- 风险控制：先用一个 brief 跑 A/B（旧约束 vs 新约束），看 craft_bench 与
  reading_attraction 双升再全量；anchor 覆盖率报表保留（信息不丢）。

### Q3 门禁分层：写法类检查退出修订闭环（对应根因 3）

- 81 条规则按对象重分类：
  - **账房层（block 保留）**：CMP 合规、BM/FCT 品牌事实、STR 结构完整性、
    FCT 一致性、PRD 可拍性——营销目标的硬约束，不动。
  - **创作层（PRS 全部 + NOV 文笔类）**：从修订 brief 的 WHAT TO CHANGE 摘除，
    降级为评价类——仍被度量、进 dashboard，但不再驱动修订循环。
- 判断依据：W4 的"一过能力不迁移"证明门禁在教 agent"过这门"而非"写得好"；
  round14 方法论（结构性约束机械兜底）继续适用于账房层。

### Q4 p6 best-of-3 选择压力（对应根因 3 的正向补位）

- 正文层上 best-of-3 + 判官选择（R3 实证"选择压力>指令微调"：R2 纯指令 +0.21
  但丢 placement，R3 加选择压力后 placement 从 0.765 救回 0.850）。
- 成本：正文是读者直接看到的层，选择压力收益最大；受 per_run_usd 8.0 预算约束，
  可先只在 p6 启用（p2/p3 的 best-of-n 已有）。

### Q5 头部范例库替换均值锚（对应根因 4，需 owner 投料）

- 语料用法从"统计带"升级为"范例库"（narracat novel-style-reference 机制）：
  按 craft_taxonomy_v2 六桶题材 × beat 类型/情绪抽取**高分段落**（非均值段），
  每条带机制注解（钩子为什么抓人、台词怎么演潜台词），去标识化后注入 p5/p6 上下文。
- 数据前提：owner 投放头部网文/短剧语料（R5）——现语料 hook_density 全 0，
  均值带内=平庸；范例库锚全部取头部作品，与 L-D2 的"带内=好"是根本对立，
  需 owner 裁决修订 L-D2 为"带内=不出错，头部锚=好"。

## 训练路线（L-D10 解冻的第一步，数据优先级倒挂原则）

评估数据现成（退化算子+语料+标注卡）、生成配对数据缺失——**先蒸馏评估模型，再谈生成**：

| 优先级 | 模型 | 数据 | 用途 |
|---|---|---|---|
| T1 | 判官/Verifier 对判模型（7B 级） | out/pairs 偏好对（3 万+，label 由构造保证） | OEO 循环低成本全量跑，替代外部判官 |
| T2 | craft 工艺评分器（≤2B 多标签） | 522 张标注卡 + 扩标 | 套路参数化的全量评估基础设施 |
| T3 | AI 味检测器（分类器） | 生成物（坏）+ 语料（好）双样本源 | slop_lexicon 从查词升级到认句式，只做度量不进门禁 |
| 暂缓 | 正文生成微调 | 需高质量配对（现缺） | 触发条件：外部 LLM 成本成瓶颈且生成质量稳定 |

- T1 的纪律：sealed 判官保持跨家族强模型（宪法既有条款），蒸馏只替换 dev 判官；
  判官模型先考试后上岗（judgekit exam 机制不变）。
- T3 前置：清洗 slop_lexicon 品牌专名噪声（"小林""门店吧台"系 PMI 假阳性）。

## 后果

- 正向：四根因全部有对应解；与已验证的第二阶段方向（选择压力+正向契约）同向，
  非推翻重来。
- 成本：Q2 解绑后 anchor 报表语义变化（对白级→beat 级），CHANGELOG 必须记录
  对外接口变更；Q5 需要新语料投放 + L-D2 修订（owner 裁决点）。
- 风险：Q3 门禁降级后，写法质量的兜底从"阻断"变为"度量+范例"，若范例库
  未就位（Q5 卡料），中间态质量可能不升反降——**执行顺序上 Q5 投料应先于
  Q3 全量降级**，Q1/Q2/Q4 可先行。
