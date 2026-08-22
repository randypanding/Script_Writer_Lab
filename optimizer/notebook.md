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
