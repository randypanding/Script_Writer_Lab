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
make ci
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

## 状态(bootstrap)

L-00 → L-17 代码全部落地,`make ci` 全绿;真实语料已入库(1600+ 部,2GB 级)。
剩余开放项(无 API key / 等上游):L-03/L-08/L-17 的真实 LLM 跑、SW champion 刻印 —— 见各 PR 偏差记录。
优化 agent 从 `OPTIMIZER.md` 进场。
