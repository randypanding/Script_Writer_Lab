# CNB CodeBuddy NPC 集群调度使用指南

> 适用仓库：`Cloudbird-Software/talk`（CNB 私有仓库）
> 平台：腾讯云原生构建（CNB）<https://cnb.cool>，OpenAPI 基址 `https://api.cnb.cool`
> 目标：用仓库的 100 个 issue（#1–#100）作为并行对话窗口，通过 `@CodeBuddy` 触发免费的一次性 NPC 沙箱，实现类似 swarm agents 的分布式任务执行。

***

## 1. 这套机制是什么

CNB 平台内置的 CodeBuddy NPC 支持异步工作模式：当你在某个 issue 下发出一条以 `@CodeBuddy` 开头的评论时，平台会拉起一个一次性隔离容器沙箱，由 NPC 自主执行命令，并把结果以一条新评论回写到该 issue。整个过程无需持续值守，属于"投递即跑"。

我们把这个能力与"issue 即窗口"结合，构成一个廉价的 agent 集群：仓库里预置的 100 个 issue，每个都是一条可独立占用的任务通道。任意一个 agent（脚本、另一个 LLM、人或你自己）都能在同一时刻分别抢占不同的窗口、各自下达互不干扰的指令，从而把单条会话扩展成最多 100 路并行的执行流。

***

## 2. 前置条件

* 一个有效令牌（默认即为本文稿使用的 Bearer 令牌），拥有该仓库的 `issues:rw` / issue 读写权限。

* 仓库 `Cloudbird-Software/talk` 已创建好 #1–#100 共 100 个调度窗口（已完成）。

* 网络可直连 `https://api.cnb.cool`。

***

## 3. 核心思路：窗口的占用状态

一个窗口（一个 issue）在同一时刻只能投递一个任务，所以抢占前必须先判断它是否空闲。判定规则只有一条：

| 状态       | 判定条件                                                                                          | 含义                 |
| -------- | --------------------------------------------------------------------------------------------- | ------------------ |
| 空闲（可抢占）  | 最早的一条评论之后没有待回复的指令，即该 issue 最后一条评论是 **CodeBuddy 的回复**（`author.is_npc == true`）；或该 issue 没有任何评论 | 上一个任务已收尾，可以投递新任务   |
| 占用中（勿抢占） | 该 issue 最后一条评论是 **人类/Agent 的指令**（`author.is_npc == false`），CodeBuddy 尚未回复                     | NPC 正在执行或排队，抢占会打乱它 |

> 注意判定基准不是"有没有评论"，而是"最后一条评论来自谁"。只要最后落在 issue 上的是一条 `@CodeBuddy` 指令，就视为占用中；只要最后落到的是 NPC 的回复，就回到空闲。

***

## 4. 三步流水线（每个 Agent 的完整闭环）

> 约定：下文 `$TOKEN` 为你的 Bearer 令牌；`$REPO = Cloudbird-Software/talk`。

### 4.1 抢占一个空闲窗口

拉取全部 issue，筛选出"空闲"的那些（最后一条评论来自 CodeBuddy，或无评论），从中随机取一个作为本次任务通道。

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/vnd.cnb.api+json" \
  -H "Accept: application/vnd.cnb.api+json" \
  "https://api.cnb.cool/$REPO/-/issues?page_size=200"
```

对每个 issue 调用评论接口取最后一条评论，判断其 `author.is_npc`：

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/vnd.cnb.api+json" \
  -H "Accept: application/vnd.cnb.api+json" \
  "https://api.cnb.cool/$REPO/-/issues/{number}/comments?page_size=50"
```

* 评论为空数组，或最后一条 `author.is_npc == true` → 空闲，可抢占。

* 最后一条 `author.is_npc == false` → 占用中，跳过。

一个可行的采样方式：先从 `list-issues` 结果里随机挑 N 个候选，再逐个查最后评论，命中空闲即占用；若全部占用则重试新一批。

### 4.2 在窗口内下达指令

向选中的 issue 的 `number` 发送评论，正文以 `@CodeBuddy` 开头，后接具体任务。对于需要真实操作沙箱的任务，打开工作模式（`work_mode: true`）。

```bash
curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/vnd.cnb.api+json" \
  -H "Accept: application/vnd.cnb.api+json" \
  -d '{"body":"@CodeBuddy 请执行……（你的具体指令）","work_mode":true}' \
  "https://api.cnb.cool/$REPO/-/issues/{number}/comments"
```

请求体为 `api.PostIssueCommentForm`：`body`（正文，必填）、`work_mode`（布尔，开启真实沙箱执行）。发布后即认为该窗口已被占用。

编写指令时建议做到的几点：

* 让 NPC 明确"真实执行并回报真实输出"，而不是"描述你会做什么"。

* 要求它贴出实际命令和输出（如退出码、passed/failed、关键日志），便于事后核验。

* 一步到位给出目标，避免需要你再回一条来纠偏的长对话。

### 4.3 观测结果（轮询窗口的回复）

NPC 异步执行，需要轮询该 issue 的评论，直到出现一条新的、作者为 CodeBuddy（`is_npc == true`）且时间晚于你的指令的回复。

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/vnd.cnb.api+json" \
  -H "Accept: application/vnd.cnb.api+json" \
  "https://api.cnb.cool/$REPO/-/issues/{number}/comments?page_size=50"
```

轮询策略建议：每 15–60 秒拉一次，普通问答约 10–40 秒返回，涉及 clone、装依赖、跑测试的任务约 1–3 分钟。取到 NPC 回复后：

* 解析回复正文，检查是否包含你要求的真实输出（例如克隆的 HEAD sha、`pytest` 的 passed/failed、`退出码 0` 等），据此判断沙箱与执行能力是否达标。

* 如需二次会话，可以直接在同一窗口再发一条 `@CodeBuddy` 指令作为该窗口的续用；若换成新任务，则释放窗口，换一个空闲窗口开始新一轮。

***

## 5. 空闲窗口的判定脚本示例（Python）

```python
import json, random, subprocess, sys

TOKEN = "<你的令牌>"
REPO = "Cloudbird-Software/talk"
H = ["-H", f"Authorization: Bearer {TOKEN}",
     "-H", "Content-Type: application/vnd.cnb.api+json",
     "-H", "Accept: application/vnd.cnb.api+json"]
BASE = f"https://api.cnb.cool/{REPO}"

def curl(url):
    return json.loads(subprocess.run(
        ["curl", "-s", *H, url], capture_output=True, text=True).stdout)

def is_free(number):
    comments = curl(f"{BASE}/-/issues/{number}/comments?page_size=50")
    if not comments:
        return True
    return comments[-1]["author"].get("is_npc") is True

issues = curl(f"{BASE}/-/issues?page_size=200")
shuffle = sorted(issues, key=lambda _: random.random())
free = [i["number"] for i in shuffle if is_free(i["number"])]
print("空闲窗口示例：", free[:10])
```

把 4.2 的指令发布动作接在这个判断之后，即为一个可独立运行的抢占-投递-观测闭环。

***

## 6. 并行与资源纪律

* 并发上限受 N 个窗口约束：同一时刻最多 N 个任务在跑（N 为当前空闲窗口数，这里预算总池为 100）。

* 每个窗口同一时间只投递一个任务；发布"@CodeBuddy 指令"即视为锁定该窗口，未拿到回复前不要重复投递到同一窗口。

* 抢占到窗口后尽快投递，避免占用不执行造成窗口空转。

* 若某窗口的 NPC 回复异常或报错，可直接在同一窗口再发一条修正指令，或标记该窗口后换其它空闲窗口。

* 任务间应相互解耦——不要在一个窗口里承载多个相互依赖的原子任务；有依赖的子任务在同一窗口内用连续评论串联。

***

## 7. 常见问题

* 如何判断 NPC 真的执行了，而不是复述？要求它在回复正文里贴出命令 + 原始输出（退出码、通过数、HEAD sha 等），并核对与仓库/预期是否一致。

* 某窗口一直没回复怎么办？先确认它是占用态还是空闲态；占用态表示上一个任务未收尾，等待其回帖或换其它空闲窗口。

* 临时免费额度用尽会怎样？NPC 可能拒绝继续执行或提示额度；此时应停手并留意令牌/额度状态，避免空跑。

***

## 8. 已就位的调度池速查

* 仓库：`Cloudbird-Software/talk`

* 窗口池：issue #1–#100（编号连续、无缺号）

* 触发语法：评论以 `@CodeBuddy` 开头 + 具体指令（执行类任务建议 `"work_mode": true`）

* 交互地址：issue `https://cnb.cool/Cloudbird-Software/talk/-/issues/{number}`

* 令牌账号：`cnb.dQQ3yYJOAGA`（昵称：潘鼎）

> 安全提示：令牌与外部 PAT（如 GitHub PAT）为敏感凭据。若这套窗口后续交给多个 agent 共用，请评估是否需要轮换令牌、限制读写权限或改为只投递不含凭据的任务。

