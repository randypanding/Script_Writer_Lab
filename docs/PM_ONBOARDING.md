# PM 进场执行手册（2026-08-31 审查后基线）

> 面向：AI 项目经理 agent。目标：进场后**无需开发**，立即开始压力测试/红队/
> 质量产出验证工作。本手册由 2026-08-31 全仓审查产出，所有"已验证"条目均在本
> 环境实测复跑过。

## 0. 仓库格局（正朔认定）

存在三条线，**你的工作对象是后两条**：

| 线 | 地址 | 状态 |
|---|---|---|
| 1. Go 门禁引擎 songguard | `Cloudbird-Software/Script_Writer`（组织仓，main） | **已停滞**，非工作对象 |
| 2. 小说生成主项目 NSC | `randypanding/Script_Writer` @ `Developing` | **正朔主线**（Python `nsc`，p0-p7 编译管线） |
| 3. 改进实验室 | `randypanding/Script_Writer_Lab` @ `Developing` | **配套改进线**（语料/判官/优化循环） |

本地布局：`/data/repos/sw`（SW）+ `/data/repos/swlab`（Lab）；
软链 `/data/repos/Script_Writer → sw` 保证 Lab 的 pinned 路径 `../Script_Writer` 生效。
**注意**：两个仓库都有 main 分支，main 不是最新开发成果，一律用 `Developing`。

## 1. 进场第一步：自检

```bash
cd /data/repos/swlab && uv run python scripts/boot_check.py          # 快速(秒级)
uv run python scripts/boot_check.py --full   # 含两仓测试套件(约 3-5 分钟)
```

退出码 0=就绪；1=有阻断项（脚本会逐条打印"缺什么→找谁要"）。
当前已知阻断项全部是 **owner 待注入资源**（见 §2），不是代码问题。

## 2. 资源清单（owner 注入项——你需要向 owner 要的东西）

| # | 资源 | 注入方式 | 解锁什么 |
|---|---|---|---|
| R1 | LLM key ×2 家族（生成+sealed 判官，如百炼 qwen + glm/deepseek） | SW: `export OPENAI_API_KEY=`；Lab: `.env` 的 `GEN_API_KEY`/`JUDGE_SEALED_API_KEY` | 真实端到端生成、W2 sealed 判官、champion 仲裁 |
| R2 | LAB_SEAL_KEY | 已由 2026-08-31 审查重封印，新 key 在 swlab `.env`（owner 自行保管备份） | 封印 HMAC 防线 |
| R3 | 1665 部语料本体（`corpus/store/` + `out/pairs/` 打包） | 拷入 `corpus/store/`、`out/pairs/`（均 gitignored） | 判官考试（每轴 ≥100 对）、偏好对、锚复现 |
| R4 | CNB_TOKEN | `.env` | 免费算力（判官投票/合成改写，1 核写手池） |
| R5 | 头部网文/短剧电子版（owner 已表示可找） | `corpus/inbox/` 后 `uv run python -m lab.corpus ingest` | ADR-0004 Q5 范例库、治愈锚补料（W3） |

**key 安全纪律**：key 只进 `.env`（gitignored）/环境变量，绝不进任何被跟踪文件；
泄漏守卫（`scripts/corpus_leak_guard.py`）跑在 CI，语料/密钥入 git 直接红。

## 3. 已验证的命令基线（2026-08-31 本环境实测）

| 命令 | 结果 |
|---|---|
| SW: `uv run pytest -m "not llm" -n auto -q` | **全绿**（~637 通过，含快照） |
| SW: `make spec-guard`（7 守卫） | 全过 |
| SW: `uv run pytest tests/test_pipeline_stub.py` | 全过（无 LLM 桩端到端） |
| SW: `uv run nsc render tests/fixtures/golden/demo_tea_ir.json --out /tmp/rt` | 过：novel.txt/screenplay.fountain/storyboard.csv，锚点 12/12 |
| SW: `make db-rebuild` | 过（空库——cases/export 全 0 字节，检索层冷启动） |
| Lab: `uv run ruff check . && uv run pytest -q` | **全绿**（138 通过） |
| Lab: `uv run python scripts/corpus_leak_guard.py` | **通过**（封印已修复） |
| Lab: `uv run python scripts/boot_check.py` | 5 阻断（全为资源缺口） |

未验证（缺 key）：`uv run nsc run examples/demo_tea/brief.yaml --profile short_drama_v1`
真实 LLM 端到端（tests/test_pipeline_llm.py 带 `llm` marker，`--run-llm` 开启）。
历史真实跑批记录：南浪仔全链路 attempt3 全绿 70min（round28 台账）。

## 4. 现状基线（你要知道的"家底"）

- **优化战役进度**：round 0-28 已打完（见 `optimizer/notebook.md`）；
  当前 champion = **v4-nolan-r3**（craft_bench 0.839，2026-08-27）。
- **契约**：promotion 契约 v2（ADR-0003）——主攻轴 craft_bench（提升>0.02 晋升），
  防崩地板 transportation 单轴，placement/l0_dialogue 只报告。
- **判官**：考试从未全过（CNB 免费集群仅 transportation 0.89 过闸，其余 0.5-0.77
  系随机后端能力天花板）；**所有 champion 的 sealed_score=null**。判官门禁
  `judge_gate_enabled: false`（只出报告）。
- **craft_shape**：题材参数化已落地（SW ADR-0019，默认"爆款通用"+治愈成长桶），
  round28 验证治愈形状原生落地。
- **已知 negative result**（不要重蹈）：W4 demo_tea 泛化——champion 配置 5 attempts
  五种门禁死法，一过能力不迁移，harness 硬化是 brief 特异的。
- **产物样例**（读质量用）：`deliverables/2026-08-31/南浪仔-v5-craftshape/novel.md`
  （24k 字，治愈形状）；更早的 v3-全绿、下午三点在 `deliverables/2026-08-26/`。

## 5. 质量问题诊断与改造路线（你的主战场）

owner 的核心不满："小说从'不出错'变成'真正能读、好读，网文 70-80 分水平'"。
四根因（2026-08-31 审查实证）与解法全部写在 **`adr/0004-quality-offensive-roadmap.md`**——
这是你的工作清单，五项改造（Q1-Q5）+ 训练路线（T1-T3）都标了优先级和执行前提。

**执行顺序约束**（ADR-0004 后果节）：Q5 范例库投料应先于 Q3 门禁全量降级
（中间态质量风险）；Q1/Q2/Q4 可在 key 到位后先行。每项改造 = 一个 optimizer 会话
（一个假设、一次改动、一次 `lab ab`、一条日志——见 OPTIMIZER.md 纪律）。

### 上一份外部分析师意见的核实与修正（供你参考，避免被误导）

| 分析师论点 | 核实结果 |
|---|---|
| "NOV-001 要求每句对白逐字织入" | **半对**：NOV-001 规则本体是"章节 100% 覆盖 Beat"；逐字对白约束在 p6_prose.py 实现层（L131） |
| "82 条门禁" | 实测 **81 条**（38 block + 40 warn + 3 info，含 DSL.md 里 1 条 block 示例） |
| "判官 90% 注意力管品牌合规，10% 管文笔" | 方向对数字不准：品牌/合规向合计 **0.60**（naturalness 0.25+placement 0.20+transportation 0.15），prose_craft 0.10 |
| "判官偏爱广告式顺滑"（round24） | **成立**，有台账记录 |
| "语料 hook_density 全 0、锚定义平庸" | **成立**（mined/bands.yaml/corpus_stats.md） |
| "Lab 无训练代码、L-D10 暂缓" | **成立**（无 torch/transformers/peft 依赖，无 GPU 代码） |
| 治愈锚仅 1 部 15 卡（薄料） | **成立**（验收线 ≥8 部，语料内已无第二部治愈作品，只能 owner 投料） |
| NarraCat 分层纪律（账房硬门/创作引导/评价度量） | 方向采纳进 ADR-0004；注意本项目小说承载品牌营销目标，账房层门禁**不能删**（owner 明确要求保留） |

## 6. 你可以立即开始的工作（不等资源）

按依赖排序，前四项零 key 零语料可做：

1. **demo_tea 专项加固轮**（round28 下轮候选 #1）：把 W4 实证的五类死因
   （p2 空 hook_promise / DLG-006 对白偏短 / CMP-002 疗效表述 / p6 anchor_map
   幻觉 line_id / p2 空 hook×6）逐个变机械兜底；p6 anchor_map 幻觉 line_id
   机械校验前置最适合先做（round14 方法论：结构性约束一律机械兜底）。
   ——注意这与 ADR-0004 Q3 不矛盾：账房层加固照做，创作层降级走 ADR 流程。
2. **boot_check 阻断项跟踪**：R1-R5 到一项验一项（`--full` 复跑），
   全绿即进入"真实跑批验证"阶段。
3. **红队测试计划**（纯写文档+桩跑）：针对账房层门禁的对抗用例集——
   CMP 疗效表述变体、品牌事实冲突注入、结构完整性破坏——用
   `tests/fixtures/broken/INV-*.json` 模式扩展，全部无 LLM 可跑。
4. **slop_lexicon 清洗**（T3 前置）：去掉品牌专名假阳性（"小林""门店吧台"），
   纯文本处理，语料不在也能做（词典在 mined/）。
5. （key 到位后）**真实 e2e + 判官考试**：`pytest tests/test_pipeline_llm.py --run-llm`
   → `lab.pairs build` → `lab.judgekit exam`——把判官考试全过闸做成第一个里程碑。

## 7. 纪律速查（违反会被 CI/守卫拦）

- **Lab 三铁律**（ADR-0001）：`corpus/` 只进不出；`contract/` 哈希锁
  （改契约必须 owner re-seal）；洞察回流只走对 SW 的 PR，Lab 不直接改 SW。
- **SW 依赖方向**：Lab 对 SW 是 pinned 只读依赖（subprocess 调 `uv run nsc ...`，
  禁止 import）。
- **optimizer 会话纪律**（OPTIMIZER.md）：一个假设/一次改动/一次 `lab ab`/一条日志；
  只动 M1/M2 面；M3（规则/阈值/rubric）只能写 ADR 建议文本——**ADR-0004 就是
  按这个规矩预置给你的提案**，owner 裁决前不得直接改 SW 的 rubric/门禁。
- **封印**：改 `contract/` 下任何文件会让 guard 红；需 owner 执行
  `LAB_SEAL_KEY=<key> uv run python -m lab.contract_guard seal contract`。
- **SW 侧**（AGENTS.md）：prompts/ 不得手改（守卫拦截）；改 spec 资产必须带 ADR；
  一个 PR 一件事，diff<400 行。

## 8. 环境 quirk（本沙盒实测）

- Grep/Read 工具对 `/data/repos/sw` 的部分子目录偶发 IO 错误（工具层问题，非仓库
  问题），用 `git grep`/`uv run python` 兜底。
- SW 依赖装了 sentence-transformers（BGE-M3 本地嵌入），首次 import 慢属正常。
- 时区 Asia/Shanghai；语料原机路径 `D:/Projects/Script_Writer_Lab/corpus/store`
  （bands.yaml 里的 data_source 字段是历史记录，不影响本环境）。
