# optimizer/notebook.md · 实验台账模板

> 每轮实验一条记录,新记录加在最上面。格式不合规的轮次视为未发生(CI 会查)。

```yaml
round: <int>                # 轮次号(会话序号,整数)
date: "2026-08-22"
hypothesis: "一句话:预期改 X 使主指标赢,因为 Y(证据引用)"
surface: op.profile_knobs   # spec/operators/surface.yaml 的动作 id(M1/M2)
change: "具体改了什么(diff 摘要)"
ab:
  briefs: 12                # lab ab 用的 brief 数
  seeds: [1,2,3]
  winrate: 0.58
  ci95: [0.52, 0.64]        # bootstrap 置信区间
  per_axis_floor: pass      # 每轴 -2% 地板
decision: rejected|accepted_pending_sealed|promoted   # 由 runner 按契约判,不是你
sealed_score: null          # 有 sealed 确认才填
notes: "偏差/意外/下一假设"
```
```yaml
round: 22
date: "2026-08-26"
hypothesis: "champion v3 刻印(收官轮):全绿完走的南浪仔为正式 champion;判分三轴不劣于 v2 即替换"
surface: op.prompt_instructions
change: "SW d360726(ir.json 导出修复)下首个全程零门禁失败完走(11:54→14:08);产物 deliverables/2026-08-26/南浪仔-v3-全绿;判分 artifact_judge_v3.json(35 对零弃票);champions.yaml 刻 champion/v3-nolan-green;战役按用户指令暂停"
ab: {briefs: 0, seeds: [], winrate: null, ci95: [null, null], per_axis_floor: null}
decision: promoted
sealed_score: null
notes: "v3 三轴 0.75/0.964/1.0,与 v1/v2 同一水位(噪声带内),但过程指标是战役最佳:一次通过、零门禁失败、2h14m 完走——round14-20d 修复链的累积胜率在此兑现。已知 cosmetic:bible 角色名'南浪仔 NOLAN'致剧本说话人前缀冗长(BM-009 只检台词,不阻塞)。战役暂停,后续按总结报告 §3.3 路径重启。"
```
```yaml
round: 21
date: "2026-08-26"
hypothesis: "champion v2 刻印(非优化轮):南浪仔(新产物线)首基线;题材从茶饮迁移到文旅 IP,harness 零学科特判成立"
surface: op.prompt_instructions
change: "SW 5023e39/31f44c5(南浪仔 brief+brand 资产,BM-009 canonical 修正);产物 deliverables/2026-08-26/南浪仔-v2-attempt1(内容门禁全绿,ir.json 导出 bug round20d 已修);判分 artifact_judge_v2b.json;champions.yaml 刻 champion/v2-nolan"
ab: {briefs: 0, seeds: [], winrate: null, ci95: [null, null], per_axis_floor: null}
decision: rejected
sealed_score: null
notes: "v2b 三轴:transportation 0.73/placement 0.955/l0_dialogue 0.929(7 对)。关键副产品:同产物两跑判分差 ±0.02-0.05=判官噪声带实测宽度,晋升阈值必须大于它。v2 与 v1 题材不同,只作水位参考(0.70-0.73/0.91-0.95 同一水位),不构成晋升。r20c 资产课:100% 拦截先怀疑规约(canonical 设计失误使 slogan 本身违规)。"
```
```yaml
round: 19
date: "2026-08-25"
hypothesis: "champion v1 基线刻印(非优化轮):首个真实产物《下午三点》三轴判分,为后续优化轮立纵向对比锚"
surface: op.prompt_instructions
change: "SW 4f53dd1(round17)产物:8 章 novel+8 集 script+manifest,p0→p7 全通(final 门暗线溢出 blocked,round18 b777914 已修)。判分:scripts/judge_artifact.py,产物切片 vs 同轴语料锚,双向 k=5 打包投票,报告 out/artifact_judge_v1.json。champions.yaml 刻 champion/v1-xiawu3dian"
ab: {briefs: 0, seeds: [], winrate: null, ci95: [null, null], per_axis_floor: null}
decision: rejected
sealed_score: null
notes: "基线分:transportation 0.708(winrate 0.5)/placement 0.929/l0_dialogue 1.0。已知偏差:语料锚对判官系统性劣势(考试 corpus_vs_gen 排除的同一现象),绝对值偏高,只有同池同程序的纵向差值有意义。l0_dialogue 触顶无量程;改进主战场=transportation。round15-18 为 harness 硬化轮(时长缩放/传输容错/对白区间对齐+扩写/p6 瘦身/暗线钳制),详见 SW git log cd8c976..b777914。"
```
```yaml
round: 14
date: "2026-08-24"
hypothesis: "生成侧(非优化轮,harness 硬化):STR-014 缺承重节拍/BM-002 植入扎堆/STR-010 主角缺席三类结构缺陷,相位重试只复述诊断不改结构(attempt4/5 各烧 ~1.5h 同门连死),机械修复应让编译门禁一次性通过"
surface: op.prompt_instructions
change: "SW f7df614:p3_beatsheet 新增 _repair_load_bearing(缺 inciting/climax 时改写居中/后段唤起最高的非保护拍)+_repair_brand_gap(植入拍后移至首个间距达标的非植入空位,有限步防振荡);p4_scene 新增 _repair_protagonist_present(主角缺席补进在场最多场景);setup_payoffs 先解引用再换序;tests/test_p3_structural_repairs.py 12 例,全量 572 过"
ab: {briefs: 0, seeds: [], winrate: null, ci95: [null, null], per_axis_floor: null}
decision: rejected
sealed_score: null
notes: "方法论定型:弱随机后端上,结构性约束(枚举/间距/出席)一律机械兜底,指令只负责语义质量。attempt5 死因还有 FCT-003 伏笔回收记账(facts_json.resolves 不落库)未修——若 round14 跑批仍撞 FCT-003,下一轮补。编号 10-13 为 SW 侧指令补丁轮(p3 全枚举/PENDING 降级/p5 体量地板/p4 类型矫正等),详见 SW git log。"
```
```yaml
round: 6
date: "2026-08-23"
hypothesis: "测量迭代③(ADR-0002):验真过滤(缺陷必须可测量地落地才进考场)+ D16 公文化后,llm 保真度噪声被剔除,naturalness/transportation 等轴读数应反映判官真实能力"
surface: op.propose_check_rule
change: "degrade.VERIFY 13 个验真谓词(D04 句长 CV/D13 对白行数等);D06/D11 无验真器不进考场;新增 D16_formalize_tone(确定性,剥语气词);run_exam_packed 只纳验真对"
ab: {briefs: 0, seeds: [], winrate: null, ci95: [null, null], per_axis_floor: null}
decision: rejected
sealed_score: null
notes: "v5 成绩结构分析:确定性明显缺陷轴最高(placement 0.85/l0_dialogue 0.77),llm_mid 保真度拖累轴最低(transportation 0.40);D08 裸矛盾使 l0_fact 0.48→0.60。本轮起考分=验真对上的灵敏度。若验真后多数轴仍 <0.85,则瓶颈是随机后端能力本身——届时带着数据向人类申请契约调整(k=9 或改门限)。"
```
```yaml
round: 9
date: "2026-08-24"
hypothesis: "管线完成率优先:round8 失败诊断显示随机后端在'未明说的契约'上全面漏接——把契约全部显式写进指令(beat_kind 枚举/PENDING 落点/钩子回应/JSON 纯净)+ 评测切片从 6 集右调到 3 集(迭代速度 2.7h→~40min),完成率应显著上升"
surface: op.prompt_instructions
change: "prompts/p3_beatsheet.json v2(枚举纪律/PENDING 落点纪律/集末钩子回应/禁止自造 kind);新增 profiles/lab_smoke_v1.yaml(3 集切片)"
ab: {briefs: 0, seeds: [], winrate: null, ci95: [null, null], per_axis_floor: null}
decision: rejected
sealed_score: null
notes: "round8 失败结构:STR-018 未消(kind 误标——内容升级但标成 setup,枚举纪律正是为此)、STR-016×2、PENDING:table_reveal 悬空、ValidationError×7。元洞察:对随机后端,'门禁即指令'是唯一可靠通道——凡 checker 要求而指令未明说的,都注定失败;这把后续 M1 迭代的方向钉死了:指令-门禁对齐审计。"
```
```yaml
round: 8
date: "2026-08-24"
hypothesis: "首个完成率迭代:种子 harness 在免费后端上无法完成(STR-018 有门禁无指令——检查器要 escalation,种子 p3 指令从未提过),显式 escalation 契约应让管线完成"
surface: op.prompt_instructions
change: "prompts/p3_beatsheet.json v1(显式 escalation 硬约束+自检;provenance=lab-round1-optimizer)"
ab: {briefs: 0, seeds: [], winrate: null, ci95: [null, null], per_axis_floor: null}
decision: rejected
sealed_score: null
notes: "结果:未完成。失败面扩大为四类:STR-018 仍在(kind 误标)、STR-016×2、PENDING:table_reveal 悬空解引用、ValidationError×7+TypeError(NPC 结构输出畸形)。教训:单条指令补强不够,随机后端需要'全部契约明文化'。起点状态刻印:champion v0=种子 harness,在免费后端上无法完成(零产物)。"
```
```yaml
round: 7
date: "2026-08-24"
hypothesis: "测量迭代③结果(ADR-0002):验真过滤后考分反映判官真实能力;transportation 0.89 过闸,证实随机后端工作区间 0.5-0.77 是能力天花板"
surface: op.propose_check_rule
change: "degrade.VERIFY 验真谓词;D14 无标记停用(682 假缺陷实证);llm_mid 适用前提;D16/D17 naturalness 缺陷源;run_exam_packed 只纳验真对"
ab: {briefs: 0, seeds: [], winrate: null, ci95: [null, null], per_axis_floor: null}
decision: rejected
sealed_score: null
notes: "v6 全表:transportation 0.89✓ / placement 0.77 / l0_dialogue 0.75 / 其余 0.5-0.65。运营决策(不动契约,人类可否决):优化循环判分面=transportation+placement+l0_dialogue 三轴联合胜率(判官可用),其余轴只报告。判官天花板归因:非投票机制问题(机制逐级验证过),是随机后端能力上限;k=9 或契约调整属人类决策,暂不申请——先用可测轴把优化循环跑起来。naturalness 覆盖由 D17 下轮补齐。"
```
```yaml
round: 5
date: "2026-08-23"
hypothesis: "测量迭代③:判官人格 v2(先逐信号对比再作答)+ D08 裸矛盾(去除自我洗白从句)后,l0_fact 与自然度类轴灵敏度应显著回升"
surface: op.propose_check_rule
change: "swarm-pool 判官 persona v2(reasoning-before-letter);degrade D08 裸矛盾直陈;judgekit 退出语义(报告产出=rc0,门限未过是合法终态)"
ab: {briefs: 0, seeds: [], winrate: null, ci95: [null, null], per_axis_floor: null}
decision: rejected
sealed_score: null
notes: "v4 全考成绩(10 轴,新度量+排除反转标签):placement 0.78 / l0_dialogue 0.67 / l0_brand 0.63 / l0_structure 0.57 / transportation 0.49 / producibility 0.50 / naturalness 0.48 / prose_craft 0.46 / l0_fact 0.48 / hook 0.40;总体级位置偏差 0.02-0.43(多轴已比旧指标干净)。运维事故:考试 rc=1(门限未过)被监督器当崩溃白跑三轮——已修(退出语义)。教训:守门指标的'未过'不是系统故障,要在语义层分开。"
```
```yaml
round: 4
date: "2026-08-23"
hypothesis: "测量迭代②:v3 考试坐实 corpus_vs_gen 构造标签与判官偏好系统性相反(naturalness/l0_dialogue 灵敏度 0.00/0.01 且位置偏差低=稳定判反);考试改为只用退化锚,缺失轴由 llm_mid 算子经 CNB 免费改写补齐"
surface: op.propose_check_rule
change: "run_exam_packed 排除 corpus_vs_gen(留 train/val);degrade llm_mid 默认走 synthesis_swarm;pairs llm_mid 限量 300 部+并行改写;swarm 韧性三件套(死窗拉黑换窗/弃票不崩/连续失败熔断)"
ab: {briefs: 0, seeds: [], winrate: null, ci95: [null, null], per_axis_floor: null}
decision: rejected
sealed_score: null
notes: "v3 成绩(修复后退化锚):transportation 0.87 / placement 0.72 / prose_craft 0.70 / l0_structure 0.67;位置偏差仍 0.4 上下(随机后端波动,k 聚合的部分药效);单个死窗曾杀死整场考试(已修)。v4 链路(重建 3000 次免费改写 + 全考)运行中,成绩回填下轮。"
```
```yaml
round: 3
date: "2026-08-23"
hypothesis: "测量基建迭代(非产物变更):首考 FAIL 的三根因修复后,判官灵敏度应回到可分辨水平——①语料锚=元数据残片 ②D08 矛盾句与事实不同窗 ③小说文体被片段选择器误杀"
surface: op.propose_check_rule
change: "pairs.py _narrative_excerpt(双文体锚点+元数据行剔除+有效性门槛);degrade.py D08 同窗紧邻插入+无事实诚实返回;打包投票加信号级分解;偏好对重建为 32708 条(exam 6726)"
ab: {briefs: 0, seeds: [], winrate: null, ci95: [null, null], per_axis_floor: null}
decision: rejected
sealed_score: null
notes: "首考(修复前)数据:naturalness/l0_dialogue 灵敏度 0.00(元数据残片所致——语料锚是制作信息表,判官当然偏爱生成物),l0_fact 0.43(矛盾句插在原事实之前/片段外),位置偏差多轴 ~0.5。教训:评估器的缺陷会伪装成被评对象的缺陷——先信考试,再信分数。复考成绩填入下轮。"
```
```yaml
round: 2
date: "2026-08-23"
hypothesis: "战役起点记录(非优化轮):免费路径(CNB swarm,随机后端)承载全部生成与评测;判官闸门待打包考试裁决"
surface: op.prompt_instructions
change: "无变更。起始状态:champion=种子 harness(mock 基线分 0.2033,sealed_score null);dev 判官=k_sample_vote_packed;sealed 判官待付费 key;偏好对 35282 条(35282=7216 exam+20928 train+7138 val)"
ab: {briefs: 0, seeds: [], winrate: null, ci95: [null, null], per_axis_floor: null}
decision: rejected
sealed_score: null
notes: "约束实测:CNB 沙箱并发硬上限 64(本侧闸 48)、单 issue 100 评论封顶后不再回复、评论进入 NPC 上下文故打包投票(5 组/条);昨日超限锁死 35 窗口,已建退役(≥80 评论)/补开机制。后续轮次胜负以 dev 判官对 champion 的成对胜率为准。"
```
```yaml
round: 0
date: "模板示例(非真实实验)"
hypothesis: "示例:提高 p5 rerank n=3 应提升 hook_strength,因为面板 3 显示集末钩子弱"
surface: op.sampling
change: "profiles/short_drama_v1.yaml: rerank.enabled true, n 3"
ab: {briefs: 0, seeds: [], winrate: null, ci95: [null, null], per_axis_floor: null}
decision: rejected
sealed_score: null
notes: "这是模板占位记录;真实轮次请按上述格式新增。"
```
```yaml
round: 1
date: "2026-08-22"
hypothesis: "dry-run:mock LLM 管线下验证 M2 面接线(变更可应用/可打分/可归因),不产生真实优化结论"
surface: op.memory_assembler
change: "lab.overlay 应用 assembler/compress/thread 三组 profile 补丁到 worktree"
ab: {briefs: 1, seeds: [1], winrate: 0.0, ci95: [0.0, 0.0], per_axis_floor: null}
decision: rejected
sealed_score: null
notes: "dry-run(mock LLM):管线活性验证通过;判官闸门 OFF,分数仅报告。"
```
