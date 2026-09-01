# OPTIMIZER.md · 优化 agent 会话纪律(ADR-0001 L-D5/L-D9/L-D13 前置)

> 你是优化 agent。本文件是每个会话的**入口与宪法**。每个会话 = 一轮实验:
> 一个假设、一次改动、一次 `lab ab`、一条日志。不满足这个形状的事不要做。

## 会话循环(强制)

1. **假设**:一句话写清"我预期改 X 会赢,因为 Y"。Y 必须引用证据(面板/规则/L0 finding),
   不许凭口味。
2. **改动**:只动 `spec/operators/surface.yaml` 允许的 M1/M2 面。M3 = 只能写 ADR 建议文本
   (`adr/proposals/`,标 `status: proposed`),**永不**直接改评测器/规则/阈值/晋升规则。
3. **对照**:`lab ab`(同 brief 同种子,dev 判官)。每轮日志记录到 `optimizer/notebook.md`。
4. **接受/拒绝**:你没有接受权。`lab.runner` 按 `contract/promotion.yaml` 自动判:
   bootstrap CI95 下界 > 0、每轴不破 -2% 地板、sealed 确认。未过判据自动回滚。
5. **写日志**(模板见 `optimizer/notebook.md`):假设/改动/AB 结果/结论/下一假设。

## 红线(CI 与守卫都会拦)

- 禁止读 `corpus/`、`transcripts/` 原文(优化 agent 无读权限;泄漏守卫 + CI 拦)。
- 禁止改 `contract/**`(哈希锁)、`mined/bands.yaml` 的 data_source/status、brief 分布规格
  (`contract/objective.yaml::brief_distribution`)。
- 禁止自造打分内核/评测指标;指标只能从 `mined/metrics_registry/` 取。
- 禁止新增框架/数据库;纯 Python + SQLite。
- sealed 配额每轮 20 次(超了会抛);不要试图绕账本。
- 判官闸门 OFF 期间(判官考试未全过),M2 实验不许打分——跑了也是空转,别浪费配额。

## 面目录速查

- **M1(立即)**:prompts 指令、契约字符串(依赖 SW-03)、路由 models.yaml、escalation、
  采样/best-of-n、profile 数值旋钮、渲染声音。
- **M2(判官闸门 ON 后)**:记忆注入/装配器/压缩、检索参数、图重试、子步骤开关、revise 阈值。
- **M3(永不做)**:check 规则、阈值、rubric、优化面本身。
## 质量进攻(ADR-0004)会话入口
质量进攻 = 五项改造(Q1-Q5)+ 训练路线(T1-T3),owner 已裁决执行(ADR-0004 accepted)。
Lab 侧资产已就绪,**你的会话直接消费**:
- Q1 判官轴:criteria/reading_attraction.md + judgekit 11 轴 + D18/D19(可直接跑退化对)。
- Q3 门禁分层:spec/gates_layers.yaml(修订 brief 消费方按此过滤 craft 层)。
- Q5 套路:spec/genre_shapes/(六桶锚 + 曲线 + 结构约束,判官评估可引用)。
- T1-T3:spec/training/(数据到位后按验收线执行,各写 ADR-0005/0006/0007)。
**SW 侧改动一律走对 SW 的 PR + ADR**(Lab 宪法第三条),提案文本已预置
`docs/QUALITY_OFFENSIVE_EXECUTION.md`——你的职责是按执行清单逐项推进并打勾,
不是重新提案。执行顺序约束:Q5 投料先于 Q3 全量降级;T1→T2→T3。

## 健康带自检(开轮前看面板)

`uv run python -m lab.report` 生成的五面板:主指标轨迹、dev/sealed 背离警报、语料盲测、
退化检出率、接受/拒绝比(健康带约 30–70% 接受;100% 接受 = 在作弊或噪声,先停下来查)。
