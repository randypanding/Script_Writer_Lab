# placement 轴 rubric 审查（round24 后续,2026-08-27）

## 结论：rubric 文本本身合理，偏差在两个更微妙的机制上

`criteria/placement_integration.md` 四个信号（卖点覆盖/剧情咬合/频次自然/不破坏节奏）字面上
并没有奖励平淡——"不破坏节奏"甚至应该在奖励戏剧。但 R3 vs v3 的实证（0.850 vs 0.964，
逐对 15 胜 5 平 0 败）说明轴实际度量的不是这些信号的合成，而是：

1. **对文旅 IP 类 brief,"卖点覆盖/频次自然"退化为"品牌符号密度"**。
   南浪仔的"产品"是 IP 形象与海南元素——v3 的温柔场景里 暖阳黄/浪声/雨林 符号持续铺满;
   R3 的对峙场景围绕人与人冲突展开,符号密度自然被稀释。判官读到的"覆盖/频次"少了,
   尽管"剧情咬合"其实更深。对实物产品(茶饮),符号=产品实体,密度与剧情可以兼得;
   对 IP,密度与戏剧冲突天然互斥——**这是 brief 类型依赖的度量失真**。
2. **"不破坏节奏"要求判官判断张力——这恰是弱判官最差的信号**(判官考试:
   灵敏度上限=后端能力)。弱判官实际执行时,这个信号大概率被忽略或反转,
   前三个密度类信号主导了得分。

## 对 promotion 契约的含义

- placement 轴在"实物产品 brief"上仍有区分度(v1 茶饮的 0.929 触顶区),
  在"IP brief"上系统性偏向低密度-低冲突文本——**不能作为 IP 类产物的主攻轴**;
- craft_bench(爆款 315 卡频率锚)不含符号密度项,直接量戏剧工艺,无此失真;
- 建议(待 owner 决,contract 变更):promotion = 三轴地板(防崩)+ craft_bench 主攻;
  placement 轴对 IP brief 只作报告,不进地板。

## 证据索引

- v3 vs R3 逐对:out/artifact_judge_v3.json / artifact_judge_r3.json;
- rubric 原文:criteria/placement_integration.md;
- craft 对照:optimizer/notebook.md round 23/24。
