# 质量进攻执行清单 · docs/QUALITY_OFFENSIVE_EXECUTION.md
> ADR-0004 的执行子项拆分。本文档是**对 SW 的提案清单**（Lab 宪法：洞察回流只走
> 对 SW 的 PR + ADR，Lab 不直接改 SW）。每项 = 一个 optimizer 会话（一个假设/
> 一次改动/一次 lab ab/一条日志），每个 SW 侧改动 = 一个独立 PR（diff<400 行）。
> Lab 侧已就绪资产直接消费；owner 裁决前不得直接改 SW 的 rubric/门禁。

## 执行顺序（约束链）
1. **Q5 投料先于 Q3 全量降级**（中间态质量风险：创作层门禁撤了、范例库没到位，
   质量可能不升反降）。
2. Q1/Q2/Q4 可在 key 到位后先行（不依赖 R5 语料）。
3. T1-T3 依赖 R3 语料（pairs 数据），在数据到位后按 T1→T2→T3 顺序执行。

## Q1 · 判官轴重构（SW 侧：rubric 权重 + 阈值）
**Lab 侧已就绪**：`criteria/reading_attraction.md`（6 信号）· judgekit AXES 11 轴 ·
退化算子 D18（章末钩平铺化）/ D19（悬念空泛化）· pairs/schema 同步 · 测试全绿（141 passed）。
**SW 侧改动**：
1. rubric_v1 新增 reading_attraction 轴（applies_to: chapter/episode，评估对象=小说确认物）。
2. 权重再平衡：prose_craft 0.10→0.25、reading_attraction 新增 0.15、naturalness 0.25→0.15、
   placement_integration 0.20→0.15（实物产品 brief 恢复 0.20）。
3. placement 轴 anchor 从"顺滑展示"改"戏剧化融入"。
4. 阈值进 eval/thresholds.yaml；改 rubric 后重跑 make judge-cal（GATES.md 纪律）。
**验收**：同对双次判官一致性不降；round 级 craft_bench 读数可对比；reading_attraction
轴分数与人工"想不想翻页"排序相关 ≥0.7（抽样验证）。

## Q2 · p6 逐字锚定解绑（SW 侧：p6_prose.py）
**Lab 侧已就绪**：proposal 文档（本文件即提案）。
**SW 侧改动**：
1. p6_prose.py 的逐字校验（`str(ln.get("text")) in para_blob`）改为 beat 级 anchor_map：
   beat_id 必须存在，line_ids 变为可选引用。写手有权重写对白（戏剧功能锚定）。
2. 剧本（p7 screenplay.fountain）仍走 p5 逐字对白——剧本是执行物、小说是确认物，两者解耦。
3. anchor 覆盖率报表保留（信息不丢）。
**风险控制**：先一个 brief 跑 A/B（旧约束 vs 新约束），craft_bench + reading_attraction
双升再全量。
**验收**：NOV-001 覆盖语义从"逐字"变"beat 级"后，小说正文对白与剧本允许合理差异；
A/B 中新约束 craft_bench 不降、reading_attraction 升。

## Q3 · 门禁分层：写法类退出修订闭环（SW 侧：修订 brief 消费层）
**Lab 侧已就绪**：`spec/gates_layers.yaml`（81 条规则分账房 51 / 创作 30，机器可读，已核对）。
**SW 侧改动**：
1. 修订 brief 的 WHAT TO CHANGE 只消费账房层规则（CMP/BM/FCT/PRD/STR/DLG 制作项/NOV-001）。
2. 创作层规则（PRS 全部 + NOV 文笔类 + CRAFT）降级为评价类：仍度量、进 dashboard，
   不再驱动修订循环。
3. CRAFT-001 对治愈系按锚降权（genre_exempt 或按桶取阈值，与 genre_shapes 对齐）。
**执行前提**：Q5 范例库投料完成（否则中间态质量风险）。
**验收**：修订 brief 不再把"消 PRS 违规"当目标；champion 迭代里 craft_bench 不降、
reading_attraction 升；创作层规则命中数进 dashboard 可追溯。

## Q4 · p6 best-of-3 选择压力（SW 侧：p6 写手池）
**Lab 侧已就绪**：方法论（R3 实证"选择压力>指令微调"）。
**SW 侧改动**：
1. p6 正文层 best-of-3 + 判官选择（正交互补：账房层门禁保留做过滤，创作层用选择压力提升）。
2. 受 per_run_usd 8.0 预算约束，先只 p6 启用（p2/p3 的 best-of-n 已有）。
**验收**：p6 单轮提升可见；craft_bench 或 reading_attraction 升。

## Q5 · 头部范例库替换均值锚（SW 侧：检索层 + 注入；数据前提 owner R5）
**Lab 侧已就绪**：`spec/genre_shapes/`（六桶锚 + 张力曲线 + 结构约束，机读）。
**SW 侧改动**：
1. craft_shape 从两形状（爆款通用/治愈成长）扩为六桶全量映射（消费 genre_shapes）。
2. 语料用法从"统计带"升级为"范例库"：按题材 × beat 类型/情绪抽**高分段落**
   （非均值段），带机制注解，去标识化后注入 p5/p6 上下文。
3. 修订 L-D2：从"带内=好"改为"带内=不出错，头部锚=好"（owner 裁决点）。
**数据前提**：owner 投放头部语料（R5）到 corpus/inbox/；治愈锚补料（≥8 部）。
**验收**：注入范例后 craft_bench 升；范例段落无 ≥10 字原文残留（抗抄袭守卫）。

## T1-T3 · 训练路线（Lab 侧规格就绪，数据到位后执行）
- **T1 判官蒸馏 7B**：out/pairs ≥3 万 → DPO → exam 与云判官一致性 ≥0.90 → ADR-0005。
- **T2 craft 评分器 ≤2B**：T1 数据 + craft_anchors_v2 → Spearman ≥0.80 → 接入 nsc → ADR-0006。
- **T3 AI 味检测**：AI 生成 + 真人语料双样本 → AUC ≥0.92、误杀 ≤5% → 接入质检 → ADR-0007。
- 暂缓：正文生成微调（判官可证伪后再考虑）。

## 完成判定（逐项）
- [ ] Q1：reading_attraction 轴已上 rubric，权重再平衡生效，make judge-cal 全绿
- [ ] Q2：p6 beat 级 anchor_map 生效，A/B 双升
- [ ] Q3：修订 brief 只消费账房层，创作层降级为评价
- [ ] Q4：p6 best-of-3 生效
- [ ] Q5：六桶 craft_shape 全量映射，范例库注入生效，L-D2 已修订
- [ ] T1/T2/T3：按各自验收线达标，ADR-0005/0006/0007 落地

## 记账
每完成一项：更新本清单打勾 + 写 ADR（SW 侧改动）或更新 Lab ADR 台账。
本清单与 ADR-0004 是同一路线的两层视图（ADR=决定，本文档=执行跟踪）。
