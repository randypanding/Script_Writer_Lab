# T1 · 判官蒸馏 7B(评估模型优先于生成模型)
# 训练规格 · 对应 ADR-0004 T1(解冻第一步,L-D10)

> 定位:质量进攻的最高杠杆。当前判官是"云上大模型逐轴逐信号打分",一次判官考试
> 成本高、不可本地化、不可并发。T1 把它蒸馏成 7B 级本地模型,让"判官考试+优化
> 迭代"能从每周十几次变成每天几百次——这是把质量从"人工把舵"变成"自动优化
> 循环"的前提。
>
> 为什么评估优先于生成:没有可信的本地判官,优化 agent 无法知道哪次改动变好了;
> 生成模型微调做了也无法证伪收益(会污染归因)。判官可信 → 优化闭环成立 →
> 生成质量提升是副产品。这符合"评估模型优先于生成模型"路线。

## 1. 目标能力
对给定的两段短剧/小说文本(A/B),逐轴输出偏好与细粒度分,能力等价于云判官
judgekit(AXES 11 轴,含 reading_attraction)。不要求创造性,只要求判断力与一致性。

## 2. 数据来源:preference pairs(out/pairs)
- **格式**:pairs JSONL(contract/schemas/pairs.schema.yaml,每对含 axis/a_text/b_text/label/
  construction/split)。label 由构造保证,不来自模型判断(核心设计,见 L-06)。
- **构造通道**(src/lab/pairs.py):
  1. `corpus_degraded`:真实语料 × 退化算子(17 个缺陷源 D01-D17,含新 D18/D19),
     缺陷可测量地落进 → 验真器把关,label 已知。
  2. `corpus_vs_gen`:真实语料 vs 生成文本,构造不可判定的"谁好" → 这类对不进
     judgekit 考试(verify_pair=False),但可进 train 做辅助信号。
  3. `gen_degraded`:生成文本 × 退化算子,用于判官对自己产物的灵敏度。
- **规模门槛**:
  - exam 门:≥100 对/轴(契约值,judges.yaml),11 轴 → 首期 1100+。
  - T1 起训:≥3 万对(含 11 轴),split 按 script_id 切分防泄漏(exam 不漏进 train)。
- **当前缺口(owner 待注入)**:corpus/store 语料库、out/pairs 尚未生成。
  进场第一步 = 投料(见 docs/PM_ONBOARDING.md R3)+ 跑 pairs build。

## 3. 模型选择与蒸馏方案
- **底座**:7B 级(如 Qwen2.5-7B-Instruct 或同量级),偏好对齐用 DPO 或 SimPO。
- **为什么 7B 够**:判官任务是"两段已给定文本的比较+打分",不要求世界知识生成;
  11 轴信号都是局部语言学/结构特征,7B 容量充足。7B 可单卡(24G)推理,本地并发。
- **蒸馏信号**(3 路):
  1. **偏好标签**(primary):pairs 的构造 label(a_win/b_win)——这是"铁标签",无模型噪声。
  2. **云判官分数回归**(辅助):用现有云判官对 train 子集打细粒度分,让 7B 回归
     分数分布(不只学相对序,还学绝对分尺度)。注意:只对 train 子集打,exam 保持纯构造。
  3. **自一致性正则**:同对双次打分方差最小化(judgekit 已有 score_pair 双向取均,
     蒸馏时把"双向一致"作为训练目标之一)。
- **验收**:
  - exam 集上 7B 与云判官一致性 ≥ 0.90(同对被判方向一致率)。
  - 7B 与云判官在各轴分数 Spearman ≥ 0.85。
  - 退化灵敏度:7B 对 D01-D19 注入的缺陷,方向正确率 ≥ 云判官 × 0.95。

## 4. 落地步骤(agent 进场后)
1. owner 注入 corpus + keys(PM_ONBOARDING R1-R5)。
2. `make pairs` 生成 out/pairs;校验 schema 通过、按 script_id 切 split。
3. 跑一轮 judgekit exam(云判官基线读数,记录各轴 sensitivity/block/transitivity)。
4. 7B 用 train 子集做 DPO;val 上迭代至通过验收线。
5. 注册为 `models/distilled_judge` 槽位,替换 exam/optimize 循环里的云判官调用
   (可保留云判官做周期抽检,防漂移)。
6. ADR-0005 记录蒸馏结果与验收数据。

## 5. 判定标准(什么时候算"这步做完了")
- [ ] out/pairs ≥ 3 万对,exam ≥ 1100(11 轴 × 100),schema 全通过
- [ ] 7B 判官在 exam 上与云判官一致性 ≥ 0.90
- [ ] 本地判官已接入 optimize 循环,单轮迭代成本下降 ≥ 10×
- [ ] ADR-0005 落地,记录实测数据

## 6. 风险与规避
- **数据泄漏**:exam 的 script_id 严禁进 train(已有契约,执行时校验)。
- **判官退化**:蒸馏后周期用云判官抽检 exam 子集,灵敏度掉线即回滚。
- **对太少**:3 万对未达标先不训,用 degrade 算子扩充(每个算子可多 severity/seed
  采样),不靠编造偏好。
