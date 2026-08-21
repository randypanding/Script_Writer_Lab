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

## 记录

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
