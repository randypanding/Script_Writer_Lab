# PM 进场执行手册（2026-09-01 重构后基线）
> 面向：AI 项目经理 agent。目标：进场后**无需开发**，立即开始质量进攻的
> 执行与验证。本手册由 2026-09-01 全仓重构产出，所有"已验证"条目均在本环境实测复跑过。

## 0. 仓库格局（正朔认定）
存在两条线，**你的工作对象是后一条**：
| 线 | 地址 | 状态 |
|---|---|---|
| 1. Go 门禁引擎 songguard | `Cloudbird-Software/Script_Writer`（组织仓，main） | **已停滞**，非工作对象 |
| 2. 小说生成主项目 NSC | `randypanding/Script_Writer` @ `Developing` | **正朔主线**（Python `nsc`，p0-p7 编译管线） |
| 3. 改进实验室 | `randypanding/Script_Writer_Lab` @ `Developing` | **配套改进线**（语料/判官/优化循环/训练规格） |
> **路径纪律**：不写死环境路径。SW checkout 位置由 `scripts/boot_check.py` 探测
> （`--sw` 参数 / `LAB_SW_PATH` 环境变量 > `lab.toml [paths].script_writer_checkout` >
> 邻居目录 `../Script_Writer` / `../Script_Writer_dev` / `../sw` 候选）。Lab 对 SW 的
> pinned 依赖（`../Script_Writer`）由探测解析，勿手工假设 `/data/repos/*` 等任何固定路径。
> **分支纪律**：两个仓库都有 main 分支，main 不是最新开发成果，一律用 `Developing`。

## 1. 进场第一步：自检
```bash
cd <lab_root> && uv run python scripts/boot_check.py          # 快速(秒级)
uv run python scripts/boot_check.py --full   # 含两仓测试套件(约 3-5 分钟)
```
退出码 0=就绪；1=有阻断项（脚本逐条打印"缺什么→找谁要"）。
**本环境实测（2026-09-01）**：就绪 8 | 警告 4 | 阻断 5，`EXIT=1`。阻断项全部是
**owner 待注入资源**（见 §2），不是代码问题。资源到一项验一项（`--full` 复跑），
全绿即进入真实跑批验证阶段。

## 2. 资源清单（owner 注入项——进场先向 owner 要这些）
| # | 资源 | 注入方式 | 解锁什么 |
|---|---|---|---|
| R1 | LLM key ×2 家族（生成+sealed 判官，如百炼 qwen + glm/deepseek） | SW: `export OPENAI_API_KEY=`；Lab: `.env` 的 `GEN_API_KEY`/`JUDGE_SEALED_API_KEY` | 真实端到端生成、W2 sealed 判官、champion 仲裁 |
| R2 | LAB_SEAL_KEY | `.env`（owner 自行保管备份）；无则只做哈希校验 | 封印 HMAC 防线（弱化但可用） |
| R3 | 1665 部语料本体（`corpus/store/` + `out/pairs/` 打包） | 拷入 `corpus/store/`、`out/pairs/`（均 gitignored） | 判官考试（每轴 ≥100 对）、偏好对（T1 数据）、锚复现 |
| R4 | CNB_TOKEN | `.env` | 免费算力（判官投票/合成改写，1 核写手池） |
| R5 | 头部网文/短剧电子版 | `corpus/inbox/` 后 `uv run python -m lab.corpus ingest` | ADR-0004 Q5 范例库、治愈锚补料（现仅 1 部 15 卡） |
**key 安全纪律**：key 只进 `.env`（gitignored）/环境变量，绝不进任何被跟踪文件；
泄漏守卫（`scripts/corpus_leak_guard.py`）跑在 CI，语料/密钥入 git 直接红。

## 3. 已验证的命令基线（2026-09-01 本环境实测）
| 命令 | 结果 |
|---|---|
| Lab: `uv run pytest -q` | **全绿 141 passed, 13 skipped**（含 reading_attraction 轴测试） |
| Lab: `uv run ruff check .` | 待跑（见 §9 例行） |
| Lab: `uv run python scripts/boot_check.py` | EXIT=1，5 阻断（全为 owner 资源缺口，非代码问题） |
| Lab: `uv run python scripts/corpus_leak_guard.py` | 通过（封印已修复） |
| Lab: `uv run python -m lab.judgekit exam`（无 key） | 走 CNB 降级路径 / 只读基线 |
| SW: `uv run pytest -m "not llm" -n auto -q` | 全绿（含快照；**口径见下方备注**） |
| SW: `uv run make spec-guard`（7 守卫） | 全过 |
| SW: `uv run nsc render tests/fixtures/golden/demo_tea_ir.json --out /tmp/rt` | 过：novel.txt/screenplay.fountain/storyboard.csv，锚点 12/12 |
| SW: `uv run make db-rebuild` | 过（空库——cases/export 全 0 字节，检索层冷启动） |
> **备注（重要）**：另一轮 agent 宣称的"SW 637 通过 / Lab 138 通过"基线是在其自身环境
> 跑的，数字与本次实测有出入（Lab 本次 141 通过，因新增 reading_attraction 相关 3 测试）。
> **一切以你在本环境实测为准**——每个"已验证"都要自己复跑，不采信他人环境的数字。
> 真实 LLM 端到端（`tests/test_pipeline_llm.py` 带 `llm` marker，`--run-llm` 开启）
> 因缺 key 未验证。历史真实跑批：南浪仔全链路 attempt3 全绿 70min（round28 台账）。

## 4. 现状基线（你要知道的"家底"）
- **优化战役进度**：round 0-28 已打完（`optimizer/notebook.md`）；champion = v4-nolan-r3
  （craft_bench 0.839，2026-08-27）。
- **契约**：promotion 契约 v2（ADR-0003）——主攻轴 craft_bench（提升>0.02 晋升），
  防崩地板 transportation，placement/l0_dialogue 只报告。sealed_quota=20。
- **判官**：考试从未全过（CNB 免费集群仅 transportation 0.89 过闸）；所有 champion 的
  sealed_score=null；判官门禁 `judge_gate_enabled: false`（只出报告）。
- **质量进攻（ADR-0004）**：五项改造 + 训练路线已立项，本重构已完成其 Lab 侧地基：
  - Q1 判官轴重构 → **Lab 侧已落地**：`criteria/reading_attraction.md` 新轴（6 信号）+
    judgekit AXES 11 轴 + 退化算子 D18/D19 + pairs/schema 同步 + 测试更新。
    **SW 侧待办**：rubric_v1 权重再平衡（prose_craft 0.10→0.25、reading_attraction 0.15、
    naturalness 0.25→0.15、placement 0.20→0.15 实物 brief 恢复 0.20）。
  - Q2 p6 逐字锚定解绑 → **proposal 级**（Lab 只产文档）：NOV-001 从逐字织入放宽为
    beat 级 anchor_map（beat_id 必须、line_ids 可选）。SW 侧待办。
  - Q3 门禁分层 → **Lab 侧已落地**：`spec/gates_layers.yaml`（81 条规则分账房 51 /
    创作 30，机器可读）。**SW 侧待办**：创作层规则从修订 brief 的 WHAT TO CHANGE 摘除。
  - Q4 p6 best-of-3 → **proposal 级**：正文层选择压力（R3 实证"选择压力>指令微调"）。
  - Q5 头部范例库 → **Lab 侧已落地**：`spec/genre_shapes/`（套路注册表：六桶锚+
    张力曲线+结构约束，机读）。**数据前提**：owner 投放头部语料（R5）+ 修订 L-D2 为
    "带内=不出错，头部锚=好"（owner 裁决点）。
  - 训练路线 T1-T3 → **Lab 侧已落地**：`spec/training/`（判官蒸馏 7B / craft 评分器 ≤2B /
    AI 味检测器，各含数据源、验收线、落地步骤）。**数据前提**：R3 语料 + R1 key。
- **craft_shape**：题材参数化已落地（SW ADR-0019，默认"爆款通用"+治愈成长桶），
  round28 验证治愈形状原生落地。六桶全量映射是 Q5 执行子项。
- **已知 negative result**（不要重蹈）：W4 demo_tea 泛化——champion 配置 5 attempts
  五种门禁死法，一过能力不迁移，harness 硬化是 brief 特异的。
- **产物样例**（读质量用）：`deliverables/2026-08-31/南浪仔-v5-craftshape/novel.md`
  （24k 字，治愈形状）；更早的 v3-全绿、下午三点在 `deliverables/2026-08-26/`。

## 5. 质量问题诊断与改造路线（你的主战场）
owner 核心不满："小说从'不出错'变成'真正能读、好读，网文 70-80 分水平'"。
四根因（2026-08-31 审查实证）+ 五项改造（Q1-Q5）+ 训练路线（T1-T3）全部写在
**`adr/0004-quality-offensive-roadmap.md`**（状态 accepted + 执行子项清单）。
**你的执行顺序约束**（ADR-0004 后果节）：
1. **Q5 投料应先于 Q3 全量降级**（中间态质量风险：创作层门禁撤了、范例库没到位，
   质量可能不升反降）——所以先向 owner 要 R5，Q1/Q2/Q4 可在 key 到位后先行。
2. 每项改造 = 一个 optimizer 会话（一个假设、一次改动、一次 `lab ab`、一条日志——
   见 OPTIMIZER.md 纪律）。一个假设/一次改动/一次验证/一条日志。
3. Lab 侧已就绪的资产（轴/分层/训练规格/套路注册表）直接消费；SW 侧改动必须
   走对 SW 的 PR + ADR（Lab 宪法：洞察回流不直改 SW）。

### 上一份外部分析师意见的核实与修正（供参考，避免被误导）
| 分析师论点 | 核实结果 |
|---|---|
| "NOV-001 要求每句对白逐字织入" | **半对**：NOV-001 规则本体是"章节 100% 覆盖 Beat"；逐字对白约束在 p6_prose.py 实现层（L131） |
| "82 条门禁" | 实测 **81 条**（含 DSL.md 里 1 条示例；见 spec/gates_layers.yaml 全量分类） |
| "判官 90% 注意力管品牌合规，10% 管文笔" | 方向对数字不准：品牌/合规向合计 **0.60**（naturalness 0.25+placement 0.20+transportation 0.15），prose_craft 0.10 |
| "判官偏爱广告式顺滑"（round24） | **成立**，有台账记录；Q1 权重再平衡正对此 |
| "语料 hook_density 全 0、锚定义平庸" | **成立**（mined/bands.yaml/corpus_stats.md）；Q5 范例库正对此 |
| "Lab 无训练代码、L-D10 暂缓" | **成立**（无 torch/transformers/peft 依赖）；T1-T3 规格已就绪，等数据到位后落地 |
| 治愈锚仅 1 部 15 卡（薄料） | **成立**（验收线 ≥8 部，语料内已无第二部治愈作品，只能 owner 投料） |
| NarraCat 分层纪律（账房硬门/创作引导/评价度量） | 方向采纳进 ADR-0004；**本项目小说承载品牌营销目标，账房层门禁不能删**（owner 明确要求） |

## 6. 你可以立即开始的工作（不等资源）
按依赖排序，前四项零 key 零语料可做：
1. **demo_tea 专项加固轮**（round28 下轮候选 #1）：把 W4 实证的五类死因
   （p2 空 hook_promise / DLG-006 对白偏短 / CMP-002 疗效表述 / p6 anchor_map
   幻觉 line_id / p2 空 hook×6）逐个变机械兜底；p6 anchor_map 幻觉 line_id
   机械校验前置最适合先做（round14 方法论：结构性约束一律机械兜底）。
   ——与 ADR-0004 Q3 不矛盾：账房层加固照做，创作层降级走 ADR 流程。
2. **boot_check 阻断项跟踪**：R1-R5 到一项验一项（`--full` 复跑），全绿即进入
   "真实跑批验证"阶段。
3. **红队测试计划**（纯写文档+桩跑）：针对账房层门禁的对抗用例集——
   CMP 疗效表述变体、品牌事实冲突注入、结构完整性破坏——用
   `tests/fixtures/broken/INV-*.json` 模式扩展，全部无 LLM 可跑。
4. **slop_lexicon 清洗**（T3 前置）：去掉品牌专名假阳性（"小林""门店吧台"），
   纯文本处理，语料不在也能做（词典在 mined/）。
5. （key 到位后）**真实 e2e + 判官考试**：`pytest tests/test_pipeline_llm.py --run-llm`
   → `lab.pairs build` → `lab.judgekit exam`——把判官考试全过闸做成第一个里程碑，
   并作为 T1 判官蒸馏的数据起点。

## 7. 质量进攻的执行优先级（ADR-0004 执行子项，按依赖排序）
| 顺序 | 任务 | 前置 | Lab 侧资产 | SW 侧动作（PR+ADR） |
|---|---|---|---|---|
| 1 | Q5 范例库投料 | owner R5 语料 | spec/genre_shapes/ 就绪 | 六桶全量映射 craft_shape；L-D2 修订 |
| 2 | Q1 判官轴 + 权重 | key（判官可跑） | reading_attraction 轴已落地 | rubric_v1 权重再平衡；make judge-cal |
| 3 | Q2 p6 解绑 | 判官可跑（A/B 验证） | proposal 文档 | p6_prose.py beat 级 anchor_map |
| 4 | Q3 门禁分层降级 | **Q5 投料后** | spec/gates_layers.yaml 就绪 | 创作层规则退出 WHAT TO CHANGE |
| 5 | Q4 p6 best-of-3 | key（写手池） | — | p6 正文层选择压力 |
| 6 | T1 判官蒸馏 | R3 语料 → pairs ≥3万 | spec/training/T1 就绪 | 模型接入（ADR-0005） |
| 7 | T2 craft 评分器 | T1 数据 | spec/training/T2 就绪 | 接入 nsc（ADR-0006） |
| 8 | T3 AI 味检测 | 语料 + SW 产物 | spec/training/T3 就绪 | 接入质检（ADR-0007） |

## 8. 纪律速查（违反会被 CI/守卫拦）
- **Lab 三铁律**（ADR-0001）：`corpus/` 只进不出；`contract/` 哈希锁
  （改契约必须 owner re-seal）；洞察回流只走对 SW 的 PR，Lab 不直接改 SW。
- **SW 依赖方向**：Lab 对 SW 是 pinned 只读依赖（subprocess 调 `uv run nsc ...`，
  禁止 import）。
- **optimizer 会话纪律**（OPTIMIZER.md）：一个假设/一次改动/一次 `lab ab`/一条日志；
  只动 M1/M2 面；M3（规则/阈值/rubric）只能写 ADR 建议文本——ADR-0004 就是
  按这个规矩预置给你的提案，owner 裁决前不得直接改 SW 的 rubric/门禁。
- **改判官轴/退化算子**：Lab criteria/ 与 spec/degradation/operators.yaml 是
  judgekit 与 degrade 的强一致源（注册表与 spec 必须一一对应），改任一处必须同步
  另一处并跑 `pytest tests/test_judgekit.py tests/test_degradation.py`。
- **封印**：改 `contract/` 下任何文件会让 guard 红；需 owner 执行
  `LAB_SEAL_KEY=<key> uv run python -m lab.contract_guard seal contract`。
- **SW 侧**（AGENTS.md）：prompts/ 不得手改（守卫拦截）；改 spec 资产必须带 ADR；
  一个 PR 一件事，diff<400 行。

## 9. 环境 quirk（本沙盒实测）
- 本文件**不写死任何绝对路径**。SW checkout 一律经 boot_check 探测
  （`--sw` / `LAB_SW_PATH` / lab.toml / 邻居目录）。Grep/Read 工具对 SW 部分子目录
  偶发 IO 错误（工具层问题），用 `git grep` / `uv run python` 兜底。
- SW 依赖装了 sentence-transformers（BGE-M3 本地嵌入），首次 import 慢属正常。
- 时区 Asia/Shanghai；语料原机路径 `D:/Projects/Script_Writer_Lab/corpus/store`
  （bands.yaml 的 data_source 是历史记录，不影响本环境）。
- 例行自检：`uv run ruff check . && uv run pytest -q && uv run python scripts/boot_check.py`。
