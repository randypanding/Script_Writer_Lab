# T2 · craft 工艺评分器(≤2B,522 卡级)
# 训练规格 · 对应 ADR-0004 T2

> 定位:T1 判官蒸馏的"瘦身兄弟"。T1 解决"哪段更好"(比较),T2 解决"这段单独
> 到底有多好"(绝对评分),专攻 craft 工艺维度(prose_craft / reading_attraction /
> transportation 等创作层信号)。≤2B 规模,可嵌入 SW 的 nsc 编译管线做逐段实时
> 评分,不依赖云判官往返。

## 1. 目标能力
对单段文本,在 craft 相关轴输出 1-20 细粒度绝对分(与判官分数同尺度),并给出
最突出的 2-3 个缺陷信号名。用于:
- SW 编译后逐段评分,定位"哪一段拉低了整章"。
- 优化 agent 的选择压力下沉到正文层(p6 best-of-3 的快速预筛)。

## 2. 数据来源
- **复用 T1 的 out/pairs 训练集**(同源,不新增语料成本):把偏好对的 a_text/b_text
  各自带上云判官细粒度分,构成"单段 → 分数"回归样本。
- **craft_anchors_v2 六桶锚**(mined/craft_anchors_v2.json):提供题材维度的工艺
  先验——同一段文字,在"复仇爽文"桶下该打几分、在"治愈成长"桶下该打几分
  是不同的。评分器按题材条件化(输入含 genre_id)。
- **NOV/PRS 规则命中作弱标签**:SW 的 craft 层规则(见 spec/gates_layers.yaml craft
  组)命中数可作"缺陷计数"辅助信号,与 LLM 分数联合蒸馏。

## 3. 模型选择
- **底座**:≤2B(如 Qwen2.5-1.5B / 2B 级),LoRA 微调。单张 522 卡(消费级)可训可推。
- **输出头**:score token(1-20)+ 缺陷信号名序列。可用 seq2seq 或 regression head。
- **条件输入**:[text, genre_id, axis] → score。轴可切换,共享底座。

## 4. 验收
- 与云判官在 craft 轴的 Spearman ≥ 0.80(绝对分尺度一致)。
- 缺陷信号召回:对 D04/D05/D16/D17(节奏/slop/公文化/书面化)注入,信号名命中率 ≥ 0.75。
- 单段推理延迟 ≤ 300ms(522 卡级),支持 nsc 管线逐段调用。

## 5. 落地步骤
1. 依赖 T1 的 out/pairs 与 craft_anchors_v2(已就绪)。
2. 用云判官给 train 子集补 craft 轴细粒度分。
3. LoRA 微调;按题材条件化做分组评估(六桶各验)。
4. 注册 `models/craft_scorer` 槽位,接入 SW nsc 的 prose_craft/reading_attraction
   检查(以 ADR + PR 形式对 SW 提案,不改 Lab 直接改 SW)。

## 6. 判定标准
- [ ] craft 轴 Spearman ≥ 0.80
- [ ] 缺陷信号召回 ≥ 0.75
- [ ] 已接入 SW nsc(通过 SW 侧 PR)
- [ ] ADR-0006 落地

## 7. 风险
- **绝对分漂移**:1-20 尺度若只有对比较,回归不稳;用 anchors 做题材条件化缓解。
- **与 T1 重叠**:T2 不重训偏好,只做回归;两者分工,避免重复造轮子。
