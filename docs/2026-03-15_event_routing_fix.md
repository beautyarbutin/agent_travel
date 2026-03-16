# 2026-03-15 路由隔离修复记录

## 背景

本次修复针对多 Agent 抢答、互相触发、近似无限循环的问题。

目标行为：

1. 用户寒暄时，只有 `travel_router` 接待。
2. 用户问天气时，`travel_router` 只分发给 `weather_agent`，其他 Agent 不动。
3. 用户问景点时，`travel_router` 只分发给 `spot_agent`，其他 Agent 不动。
4. 用户问路线时，`travel_router` 先做指代消解，再只分发给 `plan_agent`。

## 改前状态

### 1. 所有 Agent 都在监听公共频道

改前这 4 个配置都使用了广播式监听：

- [travel_router.yaml](/d:/20251224/AI_Study/OpenAgents/agents/travel_router.yaml)
- [weather_agent.yaml](/d:/20251224/AI_Study/OpenAgents/agents/weather_agent.yaml)
- [spot_agent.yaml](/d:/20251224/AI_Study/OpenAgents/agents/spot_agent.yaml)
- [plan_agent.yaml](/d:/20251224/AI_Study/OpenAgents/agents/plan_agent.yaml)

共同特征：

- `react_to_all_messages: true`
- 子 Agent 依赖 prompt 和关键词决定“该不该抢答”

这会导致：

- `weather_agent` 回复后，`travel_router` 还能看到并继续处理
- `plan_agent` / `spot_agent` 也可能把天气消息当成自己的输入
- 一个 Agent 的回复文本里只要出现“景点”“路线”等词，就会继续触发其他 Agent

### 2. 路由器在专业问题上也会继续发频道消息

改前 `travel_router` 的提示词虽然说自己是路由器，但在实际运行中仍可能：

- 转发给专家 Agent
- 同时自己再在频道里补一句说明

结果是用户先看到 router，再看到专家，重复且容易触发下一轮误判。

### 3. 子 Agent 会主动跨域引导

改前 `weather_agent`、`spot_agent`、`plan_agent` 的回复倾向于追加类似内容：

- “我还可以帮您查景点”
- “我也可以帮您规划路线”
- “要不要我继续推荐别的内容”

这些跨域话术会把已经完成的单任务，再次扩展成多任务，增加循环风险。

## 本次改动

### 1. `travel_router` 改为只处理公共频道消息

文件：

- [travel_router.yaml](/d:/20251224/AI_Study/OpenAgents/agents/travel_router.yaml)

调整：

- `react_to_all_messages: true` 改为 `false`
- 新增 `triggers`
  - `thread.channel_message.notification`
  - `thread.reply.notification`
- 明确规则：
  - 如果发送者是 `travel_router` / `weather_agent` / `spot_agent` / `plan_agent`
  - 立即 `finish`
  - 不回复、不转发
- 对天气/景点/行程请求：
  - 只分发
  - 不再自己补频道消息

### 2. 3 个子 Agent 改为只处理 direct message

文件：

- [weather_agent.yaml](/d:/20251224/AI_Study/OpenAgents/agents/weather_agent.yaml)
- [spot_agent.yaml](/d:/20251224/AI_Study/OpenAgents/agents/spot_agent.yaml)
- [plan_agent.yaml](/d:/20251224/AI_Study/OpenAgents/agents/plan_agent.yaml)

统一调整：

- `react_to_all_messages: true` 改为 `false`
- 删除原来的关键词广播监听逻辑
- 新增 `triggers`
  - `thread.direct_message.notification`
- 明确规则：
  - 只处理来自 `travel_router` 的 direct message
  - 如果 sender 不是 `travel_router`，立即 `finish`

### 3. 子 Agent 统一发回 `general`，不再尝试跨域追加

改前：

- 常用 `reply_channel_message` 或 `send_channel_message`
- 回复中容易追加其他领域的建议

改后：

- 统一要求优先使用 `send_channel_message(channel="general", text=...)`
- 明确禁止跨域引导
  - `weather_agent` 只讲天气
  - `spot_agent` 只讲景点
  - `plan_agent` 只讲行程/路线

### 4. 覆盖子 Agent 的默认 `user_prompt_template`

补充原因：

- OpenAgents 默认模板会在 direct message 场景下提示模型：
  - “To reply to a direct message: use `reply_direct_message`...”
- 但当前消息工具集中并没有 `reply_direct_message` 这个工具
- 会导致模型在 direct message 任务里直接 `finish(reason="reply_direct_message 工具不可用")`

本次处理：

- 为 `weather_agent` / `spot_agent` / `plan_agent` 显式覆盖 `user_prompt_template`
- 保留上下文注入
- 移除默认模板里那段对 `reply_direct_message` 的误导说明
- 让模型只依据系统指令选择 `send_channel_message(channel="general", text=...)`

## 改后预期行为

### 示例 1

用户：`在吗？`

预期：

- 只有 `travel_router` 回复接待语

### 示例 2

用户：`故城县的天气如何？`

预期：

- `travel_router` 读取记忆并识别天气意图
- `travel_router` 发送 direct message 给 `weather_agent`
- `travel_router` 不再发业务内容
- `weather_agent` 查询后在 `general` 回复
- `spot_agent` / `plan_agent` 不动

### 示例 3

用户：`故城县有什么好玩的地方？`

预期：

- `travel_router` 分发给 `spot_agent`
- 只有 `spot_agent` 回复

### 示例 4

用户：`从那里到德州市有多远？`

前提：

- 上文已记录 `current_city=故城县`

预期：

- `travel_router` 做指代消解
- 将任务改写为“从故城县到德州市有多远？”
- 分发给 `plan_agent`
- 只有 `plan_agent` 回复

## 本次实际修改文件

- [travel_router.yaml](/d:/20251224/AI_Study/OpenAgents/agents/travel_router.yaml)
- [weather_agent.yaml](/d:/20251224/AI_Study/OpenAgents/agents/weather_agent.yaml)
- [spot_agent.yaml](/d:/20251224/AI_Study/OpenAgents/agents/spot_agent.yaml)
- [plan_agent.yaml](/d:/20251224/AI_Study/OpenAgents/agents/plan_agent.yaml)

## 未改动文件

以下内容本次没有动：

- [mcp_server.py](/d:/20251224/AI_Study/OpenAgents/mcp_server.py)
- [.env](/d:/20251224/AI_Study/OpenAgents/.env)
- RAG 索引与景点数据
- 前端 / Studio / UI 逻辑

## 风险说明

这次修复的核心是“入口隔离”，不是大规模重构。

仍需关注两点：

1. 子 Agent 现在固定回 `general`，不再依赖原消息线程 `reply_to_id`
2. 如果 OpenAgents 对 `thread.reply.notification` 的实际分发语义与当前日志不同，router 的线程内追问行为还需要一次真实对话验证
3. 子 Agent 的 `user_prompt_template` 现在是仓库内显式覆盖版本；后续如果升级 OpenAgents，需要重新核对模板兼容性

## 回滚方式

如果本次配置不符合预期，只需回滚这 4 个 YAML 文件：

- [travel_router.yaml](/d:/20251224/AI_Study/OpenAgents/agents/travel_router.yaml)
- [weather_agent.yaml](/d:/20251224/AI_Study/OpenAgents/agents/weather_agent.yaml)
- [spot_agent.yaml](/d:/20251224/AI_Study/OpenAgents/agents/spot_agent.yaml)
- [plan_agent.yaml](/d:/20251224/AI_Study/OpenAgents/agents/plan_agent.yaml)
