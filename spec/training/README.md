# 训练路线 · spec/training/README.md
# 质量进攻路线 T1-T3(ADR-0004)的总览与路由

> 训练哲学的落地版:**评估模型优先于生成模型**。在判官可信之前,任何生成微调
> 都无法证伪收益;判官可信之后,生成质量提升是优化闭环的副产品。

## 优先级与依赖

```
T1 判官蒸馏 7B ◄───────── 最高杠杆,最先做
   │  依赖:out/pairs ≥3万对(owner 投料后 make pairs)
   ▼
T2 craft 评分器 ≤2B ◄──── 复用 T1 的 pairs 训练集 + craft_anchors_v2
   │  依赖:T1 数据就绪
   ▼
T3 AI 味检测器 ◄───────── 优先级最低,可规则过渡
   依赖:corpus(真人负样本)+ SW 历史产物(正样本)
```

- **T1 不做,T2/T3 也不做**:三者共享数据管道,且 T2 依赖 T1 的 pairs 规模。
- **生成微调(暂缓)**:不在本路线内。判官可证伪 → 再考虑(ADR-0004 明确暂缓)。

## 三模型分工

| 模型 | 规模 | 输入 → 输出 | 解决什么 |
|---|---|---|---|
| T1 判官蒸馏 | 7B | 两段 → 偏好+分 | 判官考试本地化、优化闭环成立 |
| T2 craft 评分器 | ≤2B | 单段+题材+轴 → 1-20 分+缺陷信号 | 逐段定位短板,选择压力下沉正文层 |
| T3 AI 味检测 | ≤2B | 单段 → AI 概率+位置 | 反 AI 味工程化防线 |

## 数据资产现状(2026-09)

| 资产 | 状态 | 缺口 |
|---|---|---|
| out/pairs | 未生成 | owner 注入 corpus 后 make pairs |
| corpus/store | 空 | owner 注入 1665 部语料 |
| mined/craft_anchors_v2.json | 就绪 | 六桶锚(治愈桶仅 1 部,待补料) |
| mined/slop_lexicon.yaml | 就绪 | 规则级,T3 的浅模型过渡可用 |
| mined/metrics_registry/slop_density.yaml | 就绪 | 评分器指标口径 |

## 每步完成的判定

- T1:见 T1_judge_distill.md §5(一致性 ≥0.90,成本下降 ≥10×)
- T2:见 T2_craft_scorer.md §6(Spearman ≥0.80,延迟 ≤300ms)
- T3:见 T3_ai_taste.md §6(AUC ≥0.92,误杀 ≤5%)

## 与 SW 的协作边界
- T1/T2/T3 的模型注册在 Lab(models/ 槽位),但**接入 SW 的 nsc 管线只能走对 SW 的
  PR + ADR**(Lab 宪法:洞察回流不直改 SW)。详见 adr/0004 执行子项。
