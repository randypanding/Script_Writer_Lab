# Script_Writer_Lab · 游乐场

为 `../Script_Writer`(交付物仓库)提供三件事:**"好"的定义(指标注册表)、外部固定契约(sealed 评测)、自优化实验场(OEO 循环)**。
本仓库不产出任何客户交付物;交付物仓库对本仓库是**只读依赖**(pinned checkout,路径见 `lab.toml`)。

## 三条铁律

1. **`corpus/` 只进不出。** 剧本原文永不提交 git、永不复制进交付物仓库、优化 agent 永不接触原文;只有 `mined/` 下的**聚合洞察**(统计分布、规则候选、词典)可进 git。CI 有泄漏守卫(`make guard`)。
2. **`contract/` 是外部固定契约。** 优化器只读;任何改动需人类确认 + ADR;sealed 文件带哈希锁,篡改即 `lab contract verify` 失败。
3. **洞察回流交付物只有一条路:对 `../Script_Writer` 提 PR**,走它自己的 ADR + spec-guard 流程。

## 快速开始

```bash
uv sync
cp .env.example .env        # 填三个模型家族的 key(生成 / dev 判官 / sealed 判官)
# 把剧本放进 corpus/inbox/(任意格式,只进不出)
make ci                # Windows 无 make 时:uv run python scripts/ci.py(完全同构)
```

## 常用命令

| 作用 | 命令 |
|---|---|
| 语料入库(docx/doc/pdf/txt → store,simhash 去重) | `uv run python -m lab.corpus ingest corpus/inbox` |
| 统计卡重算 / 正常带(bands 按 kind 分组) | `uv run python -m lab.corpus restat` / `stats` |
| 偏好对生成(≥3000,schema 强校验) | `uv run python -m lab.pairs build` |
| AI 味词典(三信号+PMI) | `uv run python -m lab.slop` |
| 合成 brief(dev 30/val 15,卡方) | `uv run python -m lab.briefs` |
| 判官考试(需 key) | `uv run python -m lab.judgekit exam --pairs out/pairs/exam.jsonl` |
| 五面板 | `uv run python -m lab.report` |
| 契约封印/校验 | `uv run python -m lab.contract_guard seal contract` / `verify contract` |

真实 LLM 相关(--run-llm 门控)与上游 SW 运行见 `docs/WORK_ORDERS.md` 各卡验收命令。

## 状态

L-00 → L-17 代码全部落地,`make ci` 全绿(141 passed, 13 skipped)。
质量进攻(ADR-0004, 2026-09-01)Lab 侧地基已落地:
- **Q1 判官轴**:新增 `reading_attraction`(阅读吸引力·追读性)轴——criteria 6 信号 +
  judgekit AXES 11 轴 + 退化算子 D18/D19 + pairs/schema 同步。
- **Q3 门禁分层**:`spec/gates_layers.yaml`——81 条规则分账房 51(保留 block)/
  创作 30(降级评价),机器可读。
- **Q5 套路注册表**:`spec/genre_shapes/`——六桶锚 + 张力曲线 + 结构约束,机读形状卡。
- **训练路线 T1-T3**:`spec/training/`——判官蒸馏 7B / craft 评分器 ≤2B / AI 味检测,
  各含数据源与验收线。
- **进场手册**:`docs/PM_ONBOARDING.md`(去环境路径,可执行) + `docs/QUALITY_OFFENSIVE_EXECUTION.md`(SW 侧执行清单)。
SW 侧改动待执行(走对 SW 的 PR + ADR):Q1 权重 / Q2 p6 解绑 / Q3 创作层退出修订 / Q4 best-of-3 / Q5 六桶映射。
剩余开放项(无 API key / 等上游):真实 LLM 跑、T1-T3 数据(owner 投料 R1-R5)、SW champion 刻印。
优化 agent 从 `OPTIMIZER.md` + `docs/PM_ONBOARDING.md` 进场。
