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
round: 28
date: "2026-08-31"
hypothesis: "craft_shape 题材参数化(SW ADR-0019)后,治愈系 brief 全链路可完成且产物原生呈治愈形状(不强插反派);demo_tea 泛化可一过"
surface: op.prompt_instructions
change: "SW 4a8bbe6 spec/craft_shape.yaml+机制注入+签名/编译版p3 参数化+CRAFT-001 题材豁免(01c3856 修 JMESPath ||吞 false 与 assert 反逻辑双缺陷);Lab d2ccda4 CNB 主池切 zhuzhu-team/swarm-pool+写手角色(自定义NPC 才吃 cpus:1,系统@CodeBuddy 8核计费 8× 超耗实证),写手人格补数字目标纪律(mirror 471a41f)"
ab: {briefs: 2, seeds: [1], winrate: null, ci95: [null, null], per_axis_floor: null}
decision: rejected
sealed_score: null
notes: "★南浪仔验证跑 attempt3 全绿(70min,数字目标纪律后 DLG-006 绝迹):IR 实证无 antagonist(roles=protagonist/customer_proxy/ally/foil),hook 出现【悬】【承】温和标注——治愈形状原生落地。fresh 卡(n=6) vs 治愈锚 0.835(vs 复仇锚 0.531),与 v4 新鲜卡 0.876 在薄卡噪声带内等价:参数化未伤工艺且去除了错位冲突压力。champion 维持 v4(同锚对比 -0.04<噪声带,无晋升依据,未跑 judge 轴)。★W4 泛化结论:demo_tea 5 attempts 五种门禁死法(p2 空 hook×6/DLG-006 短对白×2 轮/CMP-002 疗效/p6 anchor_map 幻觉 line_id)——一过能力不迁移,harness 硬化是 brief 特异的(南浪仔吃了 round8-25 全部加固,demo_tea 没有);新 brief 上线需自己的加固周期或付费后端。★CNB 成本:写手 1 核池全链路跑通,核时降到原 1/8;两跑批+标注全程镜像池零故障。下轮候选:①治愈锚补料重标(卡 owner 语料);②demo_tea 专项加固轮(把五类死因逐个变机械兜底);③p6 anchor_map 幻觉 id 机械校验前置。"
```
```yaml
round: 27
date: "2026-08-28"
hypothesis: "治愈锚薄料的直接原因是金榜题名标注 0 卡;补标该作可把治愈锚加厚到 2 部 25 卡"
surface: op.propose_check_rule
change: "corpus_extract.py 双修(<w:p> 带属性剥壳残渣 + 场号 x-1 分集兜底);scripts/compute_anchors.py 新增(锚表可复现,聚合口径固化);genre_map 金榜题名 k=2 复核改判;craft_anchors_v2.json v2.1;v4 产物卡重标(out/annotate/南浪仔v4-script.jsonl,6 卡)"
ab: {briefs: 0, seeds: [], winrate: null, ci95: [null, null], per_axis_floor: null}
decision: promoted
sealed_score: null
notes: "★复核实证:金榜题名六维形状(hook .80/person .60/张力 4.0-5.0-4.0)离治愈桶 L1 0.208,反而离历史/都市(0.17)更近;冻结分类器 k=2 双标两跑一致判'复仇爽文'——原'治愈'判定系单跑误差,按 W1.1 规则改判。genre_map 治愈桶 2→1,复仇桶 5→6 部(55→65 卡,锚 person .82→.78/hook .69→.71)。治愈锚保持 1 部 15 卡暂定态——语料内已无第二部治愈作品,补料正式卡在 owner 投放治愈语料。五维口径复现验证:六个未变动桶与 v2.0 冻结值逐项一致;张力曲线改池化等分三段口径(手算值有 ≤0.15 偏差,以脚本为准)。v4 复判(新鲜产物卡 n=6):vs 治愈锚 0.876/vs 复仇锚 0.671/vs v1 混锚 0.659——round26 的 1.000 系旧卡读数,n=6 单卡翻转 ±0.17,'六维满配'表述收回,但三锚读数排序不变(治愈形状确证),champion 维持 v4。★交接遗留:contract/.seal.lock.json 与 judges/objective.yaml 失配(6d30175 契约 v2 更新后未重封印),corpus_leak_guard 第三防线在干净树上即失败,重封印需 owner 的 LAB_SEAL_KEY(已验证本机无此 env)。"
```
```yaml
round: 26
date: "2026-08-28"
hypothesis: "W1 分题材锚落地后,南浪仔 v4 的'缺口'应被证明是锚错位而非产物缺陷"
surface: op.propose_check_rule
change: "genre_classify.py(476 部入桶,考试 0.73)+W1.2 扩标 31 部(累计 56 部 522 卡)+mined/craft_anchors_v2.json(六桶锚带)+craft_bench --genre+docs/craft_taxonomy_v2.md"
ab: {briefs: 0, seeds: [], winrate: null, ci95: [null, null], per_axis_floor: null}
decision: promoted
sealed_score: null
notes: "复判:v4 vs 治愈锚=1.000(六维全达/超标),vs 复仇锚=0.824,vs v1 混锚=0.839——'conflict person 缺口'确证为锚错位:复仇系 0.82 vs 治愈系 0.33,是题材工艺形状差异不是产物缺陷。champion v4 维持,证据链闭环。★警告:治愈锚=1 部 15 卡(薄料,未达 W1.1 验收线),补料重标前不做进一步工艺加压。题材分布另证:短剧语料复仇52+甜宠39 主导(混锚偏倚来源)。下轮含义:CRAFT-001 对治愈系降权,指令按题材参数化。"
```
```yaml
round: 25
date: "2026-08-28"
hypothesis: "R4 季弧层 best-of-3 重排能推 conflict person 50%→爆款 83%(弧级'独自旅行'结构在 p2 定型)"
surface: op.sampling
change: "SW 6561536+973243a:p2 arc_best_of=3+五标准重排;setup_payoff.kind 枚举归一(R4 attempt1 实证)"
ab: {briefs: 1, seeds: [1], winrate: null, ci95: [null, null], per_axis_floor: fail}
decision: rejected
sealed_score: null
notes: "全绿落地(attempt 4,一过率 1/4=25%——枚举漂移+NOV-002 各杀一次,代价已记录)。craft_bench 0.8395 vs v4 0.839(+0.0005,远低于 +0.02 阈值):conflict person 50% 原地不动,arc 重排未再产生增益——杠杆饱和。transportation 0.65 破地板(v4 0.75,winrate 0.3)。★关键洞察:conflict person 83% 的锚来自复仇/爽文类爆款,南浪仔是治愈系 IP(tone_words=治愈/松弛)——强拉 person 冲突会破坏题材气质;锚值需要分题材(下次标注按类型聚类分锚),当前缺口部分是锚的错位不是产物的缺陷。结论:本轮杠杆对当前 brief 已饱和,champion 维持 v4。"
```
```yaml
round: 24
date: "2026-08-27"
hypothesis: "R3 best-of-3+监制重排(三标准含植入自然)能兼得戏剧与 placement,越过 v3 三轴地板"
surface: op.sampling
change: "SW 443e604:p3 _best_of_n+_rerank(张力/植入自然/赌注一致)+profile.pipeline.beats_best_of=3"
ab: {briefs: 1, seeds: [1], winrate: null, ci95: [null, null], per_axis_floor: fail}
decision: rejected
sealed_score: null
notes: "一次全绿(3h03m,连续第三批 1/1)。craft 五维史上最佳:hook 75%(=爆款)/cliffhanger 75%/scene_turn 88%/conflict person 50%(逐轮 25→33→50 爬升)/info_gap 50%。三轴:transportation 0.750 平 v3;placement 0.850(v3 0.964,逐对 15 胜 5 平 0 败——较 R2 的 0.765 大幅回升但未回 v3);l0_dialogue 0.909(v3 1.0)。契约判决:两轴破地板,rejected。★重大副产品——判官轴与 craft 基准首次正面冲突:craft 说 R3 最好,判官偏爱 v3。判读:placement 轴 rubric 奖励'广告式顺滑展示',而爆款实证(83% person 冲突)要求'戏剧化融入'——判官可能在奖励平淡,与 corpus_vs_gen 反向(判官考试 round1)同一族度量偏差。处置建议(待 owner 决):①promotion 契约升级为'三轴地板(防崩)+craft_bench 提升(主攻)'——标注器已验证(0.73 一致率),爆款频率是客观锚;②placement 轴 anchor/rubric 审查。"
```
```yaml
round: 23
date: "2026-08-27"
hypothesis: "R2 正向契约(315 卡实证的三缺口:钩型/信息差/对手)能收敛 v3 的平淡缺口且不降级三轴"
surface: op.prompt_instructions
change: "SW 4780fa0:CRAFT-001/002 warn 检查(对手同场/信息差)+p1-p4 signature 正向指令(antagonist 必有/秘密/premise/赌注升级/钩型配额/arousal 真评/对手戏/knowledge_state)"
ab: {briefs: 1, seeds: [1], winrate: null, ci95: [null, null], per_axis_floor: fail}
decision: rejected
sealed_score: null
notes: "一次全绿(2h34m,一过率 1/1 无代价)。craft 三缺口两收敛:hook 攻击型 37%→67%、info_gap 25%→67%、scene_turn 62%→100%、张力序列 [4,4,5,4,4,5];conflict person 25%→33% 仍远低(self 50%)。三轴:transportation 0.75→0.764(winrate 0.50→0.64 上行),l0_dialogue 1.0→0.938(噪声带边),placement 0.964→0.765(-0.20 破地板——但逐对分析:0 败 7 平,是'碾压变打平'不是'变差')。判读:戏剧指令挤占了 IP 高光时刻的展示空间。下一假设 R3:best-of-3+张力重排,选择标准同时纳入 placement,证明两个目标可兼得。promotion 契约不破:轴地板失败即 rejected,记档不晋升。"
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
```yaml
round: "PM-2026-09-01"
date: "2026-09-01"
hypothesis: "PM 进场协调轮(非优化轮,不打分):资源接线+demo_tea 加固+Q1/Q5 启动,为后续 M1/M2 轮次铺路"
surface: n/a
change: "①R1 key 接线:longcat 402 枯竭→glm-5.3-flash(GEN/DEV)+stepfun(SEALED),Lab/SW 模型槽位 failover 已合并(Lab#6/SW#22);②demo_tea 五死因机械兜底 5/5 闭环(SW#17-20 四 PR+STR-014 查实 round14 已闭环);③红队计划(Lab#4+SW#21,51 账房规则 17 用例);④slop_lexicon 品牌假阳性清洗(Lab#3,T3 前置);⑤Q1 rubric 第七轴+权重再平衡(SW#23,ADR-0020 proposed);⑥R5 语料:夸克免登链路打通,2286 文件 7.39GB 入 corpus/inbox,ingest 完成(1609 部,254 重复,367 跳过);⑦glm e2e:p0/p1 字段漂移(*_json→*_)修复(SW#24),全管线验证中"
ab: {briefs: 0, seeds: [], winrate: null, ci95: [null, null], per_axis_floor: null}
decision: rejected
sealed_score: null
notes: "非实验轮,无接受权问题。遗留:R3 原机 1665 部 card/pairs 仍缺(T1 与判官考试 ≥100 对/轴的真卡点);治愈锚显性命名仅 1 部,大概率不达 ≥8 部验收线;hk-gateway 白名单路由广播丢失(git/gh 走 ghfast.top 代理可用);judge-cal 待 SW#23 合并后补跑。"
```
