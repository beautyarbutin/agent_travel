# 2026-03-15 `plan_agent` 酒店查询接入高德 POI

## 背景

用户问“有酒店推荐吗”时，系统此前没有任何真实的酒店查询工具。

结果是：

- `travel_router` 把住宿问题交给了 `plan_agent`
- `plan_agent` 没有可调用的酒店工具
- 小模型直接编造了酒店名称，前端看起来像“推荐成功”，实际是 hallucination

这次修复的目标很明确：

- **不做房价、房态、预订**
- **只做“这个城市有哪些酒店/住宿可以选”**
- 数据源统一交给 **高德 POI**

## 改动前

### 运行时问题

- `mcp_server.py` 没有 `search_hotels`
- `plan_agent.yaml` 不知道如何处理酒店/住宿请求
- `travel_router.yaml` 也没有把酒店请求当成正式意图类型

### 风险

- 用户一问住宿，模型很容易自由发挥
- 回复中的酒店名称无法保证真实存在

## 本次改动

### 1. MCP 新增酒店查询工具

文件：

- `mcp_server.py`

新增：

- `_search_poi_by_type(...)`
- `search_hotels(query)`

实现方式：

- 走高德 `place/text`
- 使用住宿类 POI 编码 `100000`
- 默认关键词为 `酒店 住宿 宾馆 民宿`
- 返回：
  - 酒店名称
  - 行政区划
  - 地址
  - 评分（如高德返回）
  - 参考消费（如高德返回）
  - 电话（如高德返回）

### 2. `travel_router` 正式支持“酒店/住宿”意图

文件：

- `agents/travel_router.yaml`

修改点：

- 把酒店/住宿纳入正式分发意图
- 酒店请求统一交给 `plan_agent`
- 如果是“那边住哪里方便”这类追问，且记忆中有 `destination_city`，优先用 `destination_city` 做指代消解
- 示例中新增：
  - `如皋市有酒店推荐吗？`
  - `那边住哪里方便？`

### 3. `plan_agent` 正式接管酒店查询

文件：

- `agents/plan_agent.yaml`

修改点：

- 核心能力新增“酒店/住宿推荐”
- 工具规则新增：酒店请求必须调用 `search_hotels`
- 明确禁止：如果没有工具结果，绝对不能编造酒店名称
- 上下文规则新增：酒店追问优先使用 `destination_city`，没有再退回 `current_city`
- 回复模板新增“住宿建议”格式

### 4. 酒店结果输出增强

在接通真实酒店 POI 后，又追加了一轮结果增强，目的不是增加新数据源，而是让回答更像旅游助手，而不是机械罗列酒店名单。

增强位置：

- `mcp_server.py`
- `agents/plan_agent.yaml`

增强内容：

- `search_hotels` 会根据酒店名称和地址自动打标签并分组
- 当前分组包括：
  - `商圈便利`
  - `古城周边`
  - `交通方便`
  - `景区周边`
  - `特色民宿`
  - `综合住宿`
- 每个酒店条目会尽量补：
  - 评分
  - 参考消费
  - 电话
  - 标签（如“吃饭购物方便”“适合赶车或中转”“偏特色住宿”）
- `plan_agent` 会优先利用这些分组来组织回答，而不是生硬地输出一长串酒店名

## 改动后预期行为

### 示例 1

用户：

```text
如皋市有酒店推荐吗？
```

期望链路：

1. `travel_router` 识别为酒店请求
2. `travel_router -> plan_agent`
3. `plan_agent` 先 `get_context()`
4. `plan_agent` 调 `search_hotels(query="如皋市有酒店推荐吗？")`
5. `plan_agent` 用 `send_channel_message(...)` 返回真实酒店 POI 列表

### 示例 2

前文记忆里有：

- `origin_city=故城县`
- `destination_city=如皋市`

用户追问：

```text
那边住哪里方便？
```

期望链路：

1. `travel_router` 用 `destination_city=如皋市` 补全“那边”
2. 发给 `plan_agent`：`如皋市住哪里方便？推荐几个酒店。`
3. `plan_agent` 调 `search_hotels`
4. 返回真实高德 POI 酒店列表

## 影响范围

本次只动了以下三处：

- `mcp_server.py`
- `agents/travel_router.yaml`
- `agents/plan_agent.yaml`

没有动：

- `weather_agent`
- `spot_agent`
- RAG 知识库
- memory schema

## 本地验证

建议重启：

- `travel_router`
- `plan_agent`
- `mcp_server.py`

建议回归测试：

1. `如皋市有酒店推荐吗？`
2. `那边住哪里方便？`
3. `故城县今天天气如何？`
4. `如皋市有什么好玩的？`
5. `从故城县到如皋市怎么走？`

重点确认：

- 酒店问题不再出现瞎编酒店名
- 酒店回复能按“商圈/古城/交通/景区”等维度给出更有用的住宿建议
- 仍然不会干扰天气、景点、路线三条链路
