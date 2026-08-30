# CNB 免费额度压榨手册(实证 + 官方文档)

> 来源:[CNB 定价](https://docs.cnb.cool/zh/pricing.html)、[构建节点](https://docs.cnb.cool/zh/build/build-node.html)、[语法手册 runner.cpus](https://docs.cnb.cool/zh/build/grammar.html)、[NPC 自定义](https://docs.cnb.cool/zh/build/npc.html)。
> 计费实证:用户后台用量统计确认 NPC 沙箱扣"云原生开发-CPU",不按"构建"。

## 1. 我们的负载面对的三条计费线

| 计费项 | 免费额度 | 超额 | 我们的暴露面 |
|---|---|---|---|
| 云原生开发-CPU | 1600 核时/月(月底清零) | 0.125 元/核时 | NPC 沙箱容器(CPU × 实际运行时长;每 5min 按规格预冻结) |
| AI Credits | 500 credits/月 | 0.05 元/credit,**用尽后 NPC 直接不可用** | NPC 的模型 token 消耗 |
| 云原生构建-CPU | 160 核时/月 | 0.125 元/核时 | 不碰(我们不跑构建流水线) |

关键机制:构建节点**默认 8 核**(`runner.cpus` 范围 1–64);核时 = 核数 × 实际时长;额度不足时预冻结直接杀任务。

## 2. 负载账本(判官全考 = 2000 个打包投票任务)

- 默认 8 核、QA 任务实际运行 ~1 min:8 × 1/60 ≈ **0.13 核时/任务** → 全考 ≈ 267 核时(1600 额度的 1/6,一个月只能考 ~6 次);
- 降配到 1 核:**0.017 核时/任务** → 全考 ≈ 33 核时 → **每月可考 ~48 次**(8× 提升);
- 打包投票(5 组/条评论)已省 5× 任务数;文本截断 1200→800 字符再省 token(AI Credits);
- 纯问答任务用 `work_mode=false`(不启用沙箱写权限,运行更短)。

## 3. 三个降配/增效杠杆(按收益排序)

### 杠杆一(最大):`runner.cpus: 1` —— NPC 事件流水线降配

默认 NPC 流水线 8 核,纯投票/改写任务 1 核足够。但系统 CodeBuddy 的默认流水线不受我们仓库控制,
**解法是定义自定义 NPC**(官方支持,NPC 流水线配置归 NPC 所属仓库——即我们的 talk 仓):

- `ops/cnb_npc_config/.cnb.yml`:给 `issue.comment@npc` / `pull_request.comment@npc` 事件挂 `runner.cpus: 1` 的最小流水线;
- `ops/cnb_settings.yml`:顺便定义固定人格的「判官」角色(systemPrompt 锁死评判纪律——还顺带解决随机后端风格漂移);
- 之后指令用 `@Cloudbird-Software/talk(判官)` 提及(自定义 NPC 提及语法:`@仓库路径(角色名)`)。

### 杠杆二:固定判官人格(顺带的质量杠杆)

`.cnb/settings.yml` 里给「判官」写死:逐信号评估、只回字母、不做解释。
随机后端模型不变,但角色 prompt 固定 → 位置偏差与格式合规都会改善。

### 杠杆三:评论经济(已在 swarm v2 落地)

打包(5 组/条)、文本截断、弃票不重投。评论数也是窗口寿命(100 封顶)。

## 4. 部署步骤(talk 仓,需要仓库写权限——本令牌只有 issues:rw)

1. 把 `ops/cnb_npc_config/.cnb.yml` 放进 `Cloudbird-Software/talk` 根目录(文件名必须就是 `.cnb.yml`);
2. 把 `ops/cnb_settings.yml` 的内容合入该仓 `.cnb/settings.yml`(没有则新建);
3. 提交到默认分支即生效(配置合并:本仓 NPC 事件覆盖系统默认)。

## 5. 验证方法(改完后跑)

```bash
uv run python -c "from lab.swarm import run_task; print(run_task('真实执行 nproc 并贴出输出', work_mode=True)[:200])"
```
预期输出 `1`(原默认 8)。再跑一次打包投票冒烟,确认回复人格为「判官」且格式合规。

## 6. 用量观测

- 组织 → 设置 → 用量管理(我们令牌的 API 无用量查询端点,只能网页看);
- 本侧账本:`transcripts/transcripts.db` 每次 swarm 调用一行(caller=`lab.judgekit.vote` 等),任务数 × 0.017 核时即本侧预估。

## 7. round28 重大纠正:杠杆一原部署无效,正确机制=自定义 NPC(2026-08-28 实证)

原 §3 杠杆一声称"把 .cnb.yml 放进池仓即对 NPC 事件降配 1 核"。**这是错的**——
部署后所有生成/标注任务仍走 @CodeBuddy(系统 NPC)=平台默认流水线 **8 核计费**,
当年"nproc=1"验证结果是假阳性(round28 复测:旧池 cgroup quota=800000 即 8 核)。

### 实证结论(三个对照实验)

| 提及目标 | nproc | 原因 |
|---|---|---|
| `@CodeBuddy`(系统 NPC) | 8 | 走平台默认流水线,**仓库 .cnb.yml 不参与合并** |
| `@{pool}/(判官)`(自定义 NPC) | 1 | 自定义 NPC 合并其所属仓 `.cnb.yml` 的 `runner.cpus: 1` |
| `@{pool}/(写手)`(自定义 NPC) | 1 | 同上 |

即:**只有"自定义 NPC"才吃到本仓 `.cnb.yml` 的降配**。核时差距 = **8×**。
此前所有生成/标注/改写任务(annotate/genre_classify/shim/degrade)都按 8 核计费——
这是额度消耗远超预估的主因。判官投票(judgekit 默认 mention=判官)一直正确地跑在 1 核。

### round28 的正确部署(已生效)

1. 新建主池 `zhuzhu-team/swarm-pool`(全权限令牌;旧池 `Cloudbird-Software/swarm-pool`
   转备用,100 窗口仍在,旧令牌备份于 .env 注释);
2. 池仓 `.cnb/settings.yml` 定义两个自定义角色:**判官**(评判,只回字母)+**写手**
   (生成/标注/改写,严格按指令输出要求格式,禁解释/栅栏/拒答);
3. 代码侧生成 mention 全部 `@CodeBuddy` → `swarm.WRITER_MENTION`(env `CNB_WRITER_MENTION`
   可覆盖,默认 `@{CNB_SWARM_REPO}(写手)`);lab.toml 两个 swarm 槽位 mention 同步指镜像;
4. 写手人格实测:标注格式任务返回合法 JSON 数组零废话 + nproc=1;
5. 主池窗口:#1–#30 已开(swarm 健康检查会在不足时自动补开,需令牌有 issue 写权限)。

### 成本口径(修正后)

- 1 核 NPC 任务 ≈ 0.017 核时/条(手册 §2 原计算现在才真正成立);
- 同样 1600 核时/月:8 核跑法 ≈ 6 次全考量级 vs 1 核跑法 ≈ 48 次;
- 监控:本侧 `transcripts/transcripts.db` 每调用一行,任务数 × 0.017 即核时预估。
