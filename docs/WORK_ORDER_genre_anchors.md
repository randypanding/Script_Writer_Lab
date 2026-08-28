# 工作指令书 · 题材分带锚（W1）与游乐场使用手册

> 写给接手的 agent（或人）：本文档自足。照做即可，不需要问任何人。
> 目标：**把"好小说"的度量锚从"全爆款一刀切"升级为"分题材分带"**，
> 让治愈系、爽文系、悬疑系各有自己的工艺形状基准，并复判现有产物。
> 纪律红线在 §6，违反任何一条 = 工作作废。

---

## 0. 背景一句话

我们有一台小说/短剧生成器（Script_Writer,下称 **SW**）和一个优化游乐场
（Script_Writer_Lab,下称 **Lab**）。已证明：用"爆款频率为锚"的正向契约能把产物戏剧工艺分
（craft_bench）从 0.56 推到 0.84；但锚来自混题材爆款（复仇/爽文为主），
对治愈系 IP 失真（实证：conflict person 83% 的锚不适用于治愈系，Lab round25）。
你的任务：把锚按题材分开，并复判。

## 1. 基础设施地图（全部已存在，直接用）

| 资产 | 位置 | 用途 |
|---|---|---|
| 语料（禁地，永不入库） | `Lab/corpus/inbox/` | 42 部爆款短剧（docx/pdf）+ 309 位作者网文（GBK txt），共 54G |
| 语料抽取 | `Lab/scripts/corpus_extract.py` | docx/GBK→纯文本，按集/章切分，头60%/中20%/尾20% 取样 |
| 戏剧标注器 | `Lab/scripts/annotate_corpus.py` | CNB 沙箱标注：张力/钩型/收束/冲突/信息差/转折/赌注/反转合法性。**k=3 多数票**，一致率考试 0.73 已过 |
| craft_bench 评分 | `Lab/scripts/craft_bench.py` | 标注卡→加权达标率（当前锚=315 卡混题材频率） |
| 三轴判分 | `Lab/scripts/judge_artifact.py` | 产物 vs 语料锚成对比较（双向 k=5 打包投票） |
| 免费 LLM 通道 | `Lab/src/lab/swarm.py` + `cnb_shim.py` | CNB issue 评论触发 CodeBuddy 沙箱，随机后端，并发闸 48 |
| 分类法文档 | `Lab/docs/craft_taxonomy_v1.md` | 现版六族模式与锚值（混题材） |
| 已过标注卡（示例） | `Lab/out/annotate/*.jsonl`（gitignored） | 24 部试点 ×15 单元的产出形态 |
| 台账 | `Lab/optimizer/notebook.md` | 每轮实验一条记录，格式不合规视为未发生 |
| 晋升契约 | `Lab/contract/objective.yaml`(v2) + `champions.yaml` | craft_bench 主攻（+0.02 晋升）/transportation 地板（噪声带 0.05） |

**语料原文红线**：`corpus/` 内容永不提交 git、永不跨仓复制、不出现在任何文档里
（聚合统计/频率/模式清单可以，`mined/` 只放聚合产物）。

## 2. 怎么跑起来（每条命令都验证过）

```bash
# ① 起免费 LLM 通道（判分/标注/生成都需要）
cd /d/Projects/Script_Writer_Lab && bash scripts/supervise.sh shim_service uv run python -m lab.cnb_shim
# 验证: powershell -c "(Test-NetConnection 127.0.0.1 -Port 8400).TcpTestSucceeded" → True

# ② 跑一个产物(以 南浪仔 brief 为例;SW 的 config/models.yaml api_base 须指 127.0.0.1:8400)
bash scripts/supervise.sh <任务名> bash -c "set -o pipefail; cd /d/Projects/Script_Writer && \
  OPENAI_API_KEY=dummy NSC_NO_CACHE=1 uv run nsc run examples/hainan_nolan/brief.yaml --profile lab_smoke_v1"
# 产物在 Script_Writer/out/<标题>/(novel.md+script.md+ir.json),全绿约 2.5-3.5h

# ③ 标注一部作品(任意语料或产物 script)
uv run python scripts/annotate_corpus.py <文件> --units 15 --workers 16
# 产出 out/annotate/<作品>.jsonl;批量: --pilot(读 out/annotate/pilot_works.json,断点续跑)

# ④ craft_bench 打分
uv run python scripts/craft_bench.py out/annotate/<作品>.jsonl

# ⑤ 三轴判分(对 champion 复判用)
uv run python scripts/judge_artifact.py <产物目录> <tag> --pairs 20 --k 5 --brand-re "南浪仔|NOLAN|长臂猿"
```

**supervise 纪律**：一切长任务必须 `scripts/supervise.sh <名> <命令>` 包裹（重试≤5、
`out/<名>.status.json`+`.log`）；杀进程必须 `powershell -c "taskkill /PID <根PID> /T /F"`
整树杀且先 `Get-CimInstance Win32_Process` 确认父子（模式匹配加 `-notmatch 'Get-CimInstance'` 防误杀自己）。

## 3. W1 任务分解（按序执行,每步有验收）

### W1.1 题材分类（1-2 天）
- 用 `scripts/genre_classify.py`（若已存在）或对每部作品取「标题+作者+前 2000 字」，
  经 CNB swarm 分类到题材桶：**复仇爽文 / 甜宠言情 / 都市日常 / 悬疑探秘 / 玄幻仙侠 /
  历史穿越 / 治愈成长 / 其他**（桶可据首批分布微调，但定稿后冻结进 spec）。
- k=2 双标一致率抽查 ≥0.7（不一致的进"其他"）；产出 `mined/genre_map.json`
  （只含 作品路径→题材，无原文）。
- **验收**：`mined/genre_map.json` 覆盖 ≥300 部；抽查 20 部人工（或强模型）一致率 ≥70%。

### W1.2 分题材扩标（2-4 天，CNB 窗口经济约 3000 评论）
- 每个题材桶取 ≥8 部（不足则全取），每部 15 单元、**k=3 多数票**（已有 `--pilot` 模式，
  改 `pilot_works.json` 按桶分批跑）。
- **验收**：每桶 ≥8 部 × ≥12 张有效卡；总卡数 ≥700；标注过程零人工干预。

### W1.3 分题材锚计算（半天）
- 按桶聚合六维频率（hook_attack/conflict_person/info_gap/cliffhanger_rd/scene_turn/张力曲线前中后），
  写 `docs/craft_taxonomy_v2.md`：每桶一条锚带 + 与混题材锚的差异表。
- **验收**：文档含每桶锚值与样本量；相邻桶至少一维差异显著（|Δ|≥0.15），否则合并该桶并记录理由。

### W1.4 craft_bench 分题材化（半天，改代码）
- `scripts/craft_bench.py` 加 `--genre` 参数（锚值表进 `spec/` 或 `mined/craft_anchors_v2.json`）；
  题材判定规则：brief 的 tone_words/raw_request 关键词映射（如 治愈/松弛→治愈成长桶）。
- **验收**：`uv run pytest`（Lab 有测试则跑）；三代产物（v3/R2/R3）按治愈系锚复算并记录。

### W1.5 champion 复判（半天）
- 南浪仔 v4 按治愈系锚复判：若仍为主攻最优 → 维持 champion 并在 champions.yaml 补记锚版本；
  若新锚下出现更大缺口 → 写下一轮（R5）假设进台账（p4 场景级 best-of 或对手戏配额）。
- **验收**：champions.yaml 有锚版本字段；台账 round 26 记录复判全过程。

## 4. 若继续做优化（R5+），杠杆候选（按期望值）

1. **p4 场景级 best-of-2**（场景卡也有候选空间，成本低于 p3）；
2. **对手戏配额指令**：p2 指令升级为"每集对手戏 ≥1 场且合计时长 ≥ 本集 1/3"（机械可查）；
3. **新题材 brief 泛化验证**（W4）：拿一个新客户 brief 跑 champion 配置，
   验证一过率与 craft_bench 可迁移性——这是商业价值最直接的证据；
4. **sealed 判官**（有付费 key 时）：跨家族校验，判官 rubric 按 craft_bench 校准。

## 5. 度量纪律（本游乐场能跑到今天的全部原因）

1. **先考度量再信分数**：任何新标注器/判官轴，先跑一致性考试（k=3 多数卡 ≥0.7），不过门不放量。
2. **锚就是合同**：锚值表/题材桶冻结进 spec 后才许用于判定；改锚 = 改合同 = 重刻全部基线。
3. **100% 拦截先怀疑规约**：某规则/指标全军覆没或全部满分时，先查度量本身，再查被测对象。
4. **一过率监控**：质量上升不得以一过率崩塌为代价（基线在 docs/first_pass_baseline.md）；
   连续两轮下降 >15% 触发门禁复审。
5. **晋升契约外置**：优化器无权接受自己的改动；craft_bench +0.02 & transportation 不破
   才晋升，否则记 rejected（台账格式见 optimizer/notebook.md 模板）。
6. **判官噪声带 ±0.05**：任何"提升"小于此带一律不算提升。

## 6. 绝对红线（违反=作废）

- corpus 原文不入库、不出仓、不进文档；聚合产物才有 `mined/`。
- 不修改 `contract/`（只有人类能批）；不改 sealed 任何东西。
- 不为过门而改检查器；要让产物过门只能改产物侧（生成/修复器）。
- 每个变更一个轮次 + 台账记录（假设/变更/数据/裁决）；一次改多样 = 无法归因 = 白跑。
- 长任务必 supervise；杀进程必整树；GitHub 推送失败就退避重试（网络常抖，本地 git 是真相）。

## 7. 当前状态快照（2026-08-28）

- champion：`champion/v4-nolan-r3`（craft_bench 0.839，混题材锚）；
- 南浪仔三代产物卡：v3/R2/R3 的六维频率在 `optimizer/notebook.md` round 23-25；
- 已过标注：24 部试点（12 短剧+12 网文）315 卡；标注器一致性 0.73；
- SW main 已含全部机器（PR #15/#16）；Lab main 已含全部文档与工具。
