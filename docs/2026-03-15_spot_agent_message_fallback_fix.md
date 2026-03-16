# 2026-03-15 spot_agent 消息补发修复记录

## 背景

此前 `spot_agent` 出现过一种典型失败：

1. 已成功调用景点工具
2. LLM 在日志里生成了完整景点答案
3. 但没有调用 `send_channel_message` 或 `reply_channel_message`
4. 结果前端没有任何可见回复

这个问题在 `weather_agent` 和 `travel_router` 上不明显，但在 `spot_agent` 上更容易出现，因为景点回答更长、更容易让小模型直接输出纯文本。

## 改前状态

- `spot_agent` 使用默认的 `CollaboratorAgent`
- 如果模型直接输出纯文本、没有 tool call：
  - OpenAgents 只记录一条 `COMPLETE`
  - 不会自动帮它把文本发到频道
- 前端只能看到真正的消息事件，所以这类回答会“日志里有，界面里没有”

## 本次改动

### 1. 新增 `spot_agent` 专属 runner

文件：

- [spot_agent_runner.py](/d:/20251224/AI_Study/OpenAgents/spot_agent_runner.py)

新增类：

- `SpotFallbackAgent`

做法：

- 继承 `CollaboratorAgent`
- 保留原有路由与工具执行逻辑
- 只在 `run_agent()` 完成后，额外检查 trajectory

### 2. 触发补发的条件非常窄

只有同时满足以下条件，才会自动补发到 `general`：

1. 当前消息来自 `travel_router`
2. 当前事件是 direct message 场景
3. 本轮已经成功调用过景点工具之一：
   - `search_spots`
   - `search_local_knowledge`
   - `search_combined`
4. 本轮没有调用过：
   - `send_channel_message`
   - `reply_channel_message`
5. 本轮结束原因是：
   - `Agent provided direct response`
6. 且 direct response 文本非空

这样可以避免把其他 agent 的行为、或者 `spot_agent` 的误触发回答也自动发出去。

### 3. `spot_agent.yaml` 切换到本地自定义 runner

文件：

- [spot_agent.yaml](/d:/20251224/AI_Study/OpenAgents/agents/spot_agent.yaml)

改动：

- `type` 从 `openagents.agents.collaborator_agent.CollaboratorAgent`
- 改为 `spot_agent_runner.SpotFallbackAgent`

其余 prompt、触发器和 MCP 配置保持不变。

## 为什么这样改更稳

这次没有改全局 orchestrator，也没有改 weather / plan / router。

只把补发兜底限定在 `spot_agent` 自己身上，副作用更小：

- 问天气时，不会因为这次修复让 `spot_agent` 抢答
- 问闲聊时，不会因为这次修复让 `spot_agent` 乱发消息
- 只有已经完成景点检索、但忘记发消息的那一类 case 会被兜底

## 本次实际修改文件

- [spot_agent_runner.py](/d:/20251224/AI_Study/OpenAgents/spot_agent_runner.py)
- [spot_agent.yaml](/d:/20251224/AI_Study/OpenAgents/agents/spot_agent.yaml)

## 未改动文件

以下内容本次没有动：

- [travel_router.yaml](/d:/20251224/AI_Study/OpenAgents/agents/travel_router.yaml)
- [weather_agent.yaml](/d:/20251224/AI_Study/OpenAgents/agents/weather_agent.yaml)
- [plan_agent.yaml](/d:/20251224/AI_Study/OpenAgents/agents/plan_agent.yaml)
- OpenAgents 全局 `orchestrator.py`

## 验证重点

重启 `spot_agent` 后，优先测试：

1. `如皋市有什么好玩的？`
2. `故城县景点推荐`

预期：

- 如果模型正常调用 `send_channel_message`，行为与之前相同
- 如果模型再次只输出纯文本但忘了发消息，`SpotFallbackAgent` 会自动补发到 `general`

## 回滚方式

如需回滚，只需：

1. 将 [spot_agent.yaml](/d:/20251224/AI_Study/OpenAgents/agents/spot_agent.yaml) 的 `type` 改回 `openagents.agents.collaborator_agent.CollaboratorAgent`
2. 删除或忽略 [spot_agent_runner.py](/d:/20251224/AI_Study/OpenAgents/spot_agent_runner.py)
