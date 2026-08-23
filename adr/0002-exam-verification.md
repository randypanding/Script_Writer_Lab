# ADR-0002 · 考试验真过滤与 D16 公文化算子

status: accepted

## 背景

v5 全考(判官人格 v2 + 裸矛盾 D08)后仍全面未过闸。成绩结构显示:**判官灵敏度读数被退化对保真度拖累**——llm_mid 算子由 CNB 随机后端改写,退化不保真(有时改写后反而更好),naturalness(D06)/transportation(D11)/hook(D03)等轴的读数不可信。同时 naturalness 轴缺少确定性缺陷源。

## 决策

1. **验真过滤**:`lab.degrade.VERIFY` 为每个算子定义可测量的验真谓词(如 D04:句长 CV 必须真的下降;D13:对白行数必须真的减少)。`run_exam_packed` 只接纳验真通过的对;无验真器的算子(D06/D11)的对不进考场——宁可缺考,不造假分。验真在考试时计算,对文件不加字段(pairs schema 不变)。
2. **D16_formalize_tone**(deterministic, naturalness):剥对白句末语气词,给 naturalness 一个确定性、可验真的缺陷源。

## 依据

- v5 成绩:transportation 0.40(上轮 0.49)/naturalness 0.51,而偏差极干净(0.03-0.05)——判官稳定地"看不出差异",符合"差异本身不稳定存在"的解释;
- D04/D13 等 llm 改写后经确定性指标可验证缺陷是否落地——验真后的对标签仍由构造保证(筛选即构造)。
