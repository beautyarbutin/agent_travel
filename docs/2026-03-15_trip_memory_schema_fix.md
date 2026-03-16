# 2026-03-15 跨城行程记忆补强修复记录

## 背景

本次修复针对跨城行程规划中的记忆缺失问题。

典型失败场景：

- 先问：`从故城县到如皋市有多远？`
- 再问：`我想今天出发，我有三天的时间，请帮我规划行程。`

此前系统只有 `current_city`，没有：

- `origin_city`
- `destination_city`
- `departure_time`
- `trip_days`

结果是第二轮规划时，`plan_agent` 只能把上一轮记忆压缩成单一城市，容易误判成“如皋市三天行程”，甚至跑去调用景点检索工具。

## 改前状态

### 1. 记忆结构无法表达跨城任务

原来的记忆工具只支持：

- `current_city`
- `current_spot`
- `travel_party`
- `preferences`
- `notes`

这适合天气、景点和简单指代消解，但不适合表达：

- 从哪里出发
- 去哪里
- 什么时候出发
- 计划玩几天

### 2. `travel_router` 只能保存单城市信息

改前 `travel_router` 只知道：

- 提到城市就写入 `current_city`
- 提到时间/预算就塞到 `notes`

这会让 `从故城县到如皋市，今天出发，三天行程` 这种请求在记忆里丢失结构。

### 3. `plan_agent` 会把跨城规划误当成单城市游玩

改前 `plan_agent` 的提示词主要围绕：

- 单城市多日游
- 路线查询

但没有明确告诉它：

- 如果记忆中同时出现出发地和目的地，要优先视为跨城问题
- 不要再去调用 `search_spots` / `search_combined` 做景点深检索

## 本次改动

### 1. 扩展记忆 schema

文件：

- [memory_tools.py](/d:/20251224/AI_Study/OpenAgents/tools/memory_tools.py)
- [memory_mcp.py](/d:/20251224/AI_Study/OpenAgents/memory_mcp.py)
- [mcp_server.py](/d:/20251224/AI_Study/OpenAgents/mcp_server.py)

新增字段：

- `origin_city`
- `destination_city`
- `departure_time`
- `trip_days`

兼容策略：

- 保留 `current_city`
- 不删除旧字段
- weather / spot 仍可继续只依赖 `current_city`

### 2. `travel_router` 增加跨城槽位提取规则

文件：

- [travel_router.yaml](/d:/20251224/AI_Study/OpenAgents/agents/travel_router.yaml)

调整：

- 读取记忆时，显式关注出发地、目的地、出发时间、行程天数
- 对 `从A到B` / 跨城规划请求，要求提取并保存：
  - `origin_city`
  - `destination_city`
- 如果 A 明确是用户当前所在位置，同时保存 `current_city=A`
- 如果用户后续只说：
  - `今天出发`
  - `三天时间`
  - `帮我规划行程`
  但记忆里已有 `origin_city / destination_city`，则必须补全后再转发给 `plan_agent`

### 3. `plan_agent` 改为跨城优先思维

文件：

- [plan_agent.yaml](/d:/20251224/AI_Study/OpenAgents/agents/plan_agent.yaml)

调整：

- 先 `get_context`
- 如果记忆中同时有 `origin_city` 和 `destination_city`，优先视为跨城问题
- 如果是跨城问题，先调用 `get_driving_route(origin=..., destination=...)`
- 明确禁止调用：
  - `search_spots`
  - `search_local_knowledge`
  - `search_combined`
- 保留 `current_city` 作为单城市规划兜底

## 改后预期行为

### 示例 1：跨城路线

用户：`从故城县到如皋市有多远？`

预期：

- router 保存：
  - `current_city=故城县`
  - `origin_city=故城县`
  - `destination_city=如皋市`
- router 转发给 `plan_agent`
- `plan_agent` 调 `get_driving_route("故城县", "如皋市")`

### 示例 2：后续补充三天规划

用户：`我想今天出发，我有三天的时间，请帮我规划行程。`

前提：

- 记忆中已有：
  - `origin_city=故城县`
  - `destination_city=如皋市`

预期：

- router 补全问题后转发：
  - `从故城县到如皋市，今天出发，有三天时间，请帮我规划行程。`
- router 保存：
  - `departure_time=今天出发`
  - `trip_days=三天`
- `plan_agent` 不再走景点 RAG，而是：
  - 先查路线
  - 再给出包含路途的三日规划

## 本次实际修改文件

- [memory_tools.py](/d:/20251224/AI_Study/OpenAgents/tools/memory_tools.py)
- [memory_mcp.py](/d:/20251224/AI_Study/OpenAgents/memory_mcp.py)
- [mcp_server.py](/d:/20251224/AI_Study/OpenAgents/mcp_server.py)
- [travel_router.yaml](/d:/20251224/AI_Study/OpenAgents/agents/travel_router.yaml)
- [plan_agent.yaml](/d:/20251224/AI_Study/OpenAgents/agents/plan_agent.yaml)

## 未改动文件

以下内容本次没有动：

- [weather_agent.yaml](/d:/20251224/AI_Study/OpenAgents/agents/weather_agent.yaml)
- [spot_agent.yaml](/d:/20251224/AI_Study/OpenAgents/agents/spot_agent.yaml)
- 天气查询实现
- 景点 RAG 与 POI 检索实现
- 前端与 OpenAgents 框架代码

## 风险说明

本次修复是“新增字段 + 提示词补强”，不是大规模重构。

已控制的风险：

- 没有删除 `current_city`
- 没有改变 weather / spot 的读写方式
- 没有改路由隔离机制

仍需运行验证的点：

1. `travel_router` 是否能稳定把跨城补充条件改写成显式的 `从A到B`
2. `plan_agent` 在本地小模型下，是否会严格遵守“不调用景点检索工具”的约束
3. 多轮对话中如果用户改口目的地，router 是否能覆盖旧的 `destination_city`

## 回滚方式

如果本次修复不符合预期，只需回滚以下 5 个文件：

- [memory_tools.py](/d:/20251224/AI_Study/OpenAgents/tools/memory_tools.py)
- [memory_mcp.py](/d:/20251224/AI_Study/OpenAgents/memory_mcp.py)
- [mcp_server.py](/d:/20251224/AI_Study/OpenAgents/mcp_server.py)
- [travel_router.yaml](/d:/20251224/AI_Study/OpenAgents/agents/travel_router.yaml)
- [plan_agent.yaml](/d:/20251224/AI_Study/OpenAgents/agents/plan_agent.yaml)
