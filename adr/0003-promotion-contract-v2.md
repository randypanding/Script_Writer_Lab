# ADR-0003：promotion 契约 v2——craft_bench 主攻 + 判官三轴降防崩地板

- 状态：accepted（2026-08-27 owner 裁决："同意你的变更，现在应该奖励好，而不是奖励平淡"）
- 影响层：contract/objective.yaml · contract/promotion.yaml · champions.yaml · optimizer 工作方式

## 背景

round23/24 实证冲突：R2/R3 两轮把 craft 五维持续推向爆款水位（craft_bench 0.559→0.766→0.839），
但判官 placement/l0_dialogue 两轴连续破 2% 地板，两轮均 rejected。审查（docs/placement_axis_review.md）
定位：placement 轴对 IP 类 brief 退化为"品牌符号密度"度量（与冲突场景天然互斥），
且"不破坏节奏"信号超出弱判官能力；l0_dialogue 自 v1 起触顶无量程。
继续让这两轴把守地板 = 系统性奖励平淡、惩罚戏剧——与优化目标本身矛盾。

## 决定

1. **主攻轴 = craft_bench**（scripts/craft_bench.py）：爆款 315 卡实证频率为锚的加权达标率，
   标注器经一致性考试（k=3 多数卡，0.73）。晋升要求 craft_bench 相对 champion 提升 > 0.02。
2. **防崩地板（IP brief）= transportation 单轴**：三轴中唯一既有量程又无类型失真的轴。
   地板 = champion 值 - 噪声带（0.05，v2/v2b 同产物双跑实测）。
3. **报告轴（IP brief）= placement_integration + l0_dialogue**：只记录不进判定
   （前者 IP brief 失真，后者触顶无量程；实物产品 brief 时 placement 恢复进地板）。
4. L0 全过（SW spec/checks block 规则）与一过率监控（docs/first_pass_baseline.md）不变：
   质量上升不得以一过率崩塌为代价。

## 后果

- R3 按 v2 契约复判：craft_bench 0.839 vs v3 0.559（+0.28 ≫ 0.02）、transportation 0.750 = v3 地板
  → 晋升 champion/v4-nolan-r3。
- sealed 判官缺位不变（零预算）；craft_bench 的标注器消费 CNB 配额，计入窗口经济。
- 风险：craft_bench 锚定"当前爆款频率"，爆款形态演化时锚需重标（每年 or 每季度复标试点）。
