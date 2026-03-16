# 2026-03-15 `spot_agent` 城市级景点检索策略修复

## 背景

在“如皋市有什么好玩的”“故城县景点推荐”这类问题上，`travel_router` 已经能正确分发给 `spot_agent`，但 `spot_agent` 回复经常很慢，甚至看起来像没有回复。

排查日志后确认：

- `travel_router` 已成功发送 direct message 给 `spot_agent`
- `spot_agent` 已收到任务
- 卡点出现在 `search_local_knowledge("如皋市景点推荐")`

这说明问题不在路由，而在 `spot_agent` 的检索策略。

## 改前状态

改前 [spot_agent.yaml](/d:/20251224/AI_Study/OpenAgents/agents/spot_agent.yaml) 把景点检索写成了“必须组合使用 API + RAG”：

1. 先 `get_context`
2. 再 `search_local_knowledge`
3. 再 `search_spots`

这会导致：

- 城市级泛推荐也被强制先跑 RAG
- 首次加载 RAG 很慢
- 对“如皋市景点推荐”这类查询，RAG 结果质量也不稳定
- 用户看到的是长时间无回复

## 本次改动

只修改了：

- [spot_agent.yaml](/d:/20251224/AI_Study/OpenAgents/agents/spot_agent.yaml)

未修改：

- `travel_router`
- `mcp_server.py`
- `weather_agent`
- `plan_agent`
- 本地 RAG 实现本身

策略调整为：

1. 城市级/区县级泛推荐问题，优先只调用 `search_spots`
2. 只有在以下情况才调用 `search_local_knowledge`
   - 用户明确问攻略、避坑、怎么玩、拍照机位、美食、路线
   - 用户问的是某个具体景点
   - 高德 POI 结果不足，需要补深度信息
3. 如果两个工具都要用，先 `search_spots`，再 `search_local_knowledge`

## 预期效果

针对以下问题：

- “如皋市有什么好玩的？”
- “故城县景点推荐”
- “哪里值得去？”

`spot_agent` 应优先快速返回高德 POI 结果，不再默认先卡在 RAG 上。

针对以下问题：

- “衡水湖怎么玩？”
- “水绘园有什么避坑建议？”
- “故城县有没有拍照机位推荐？”

`spot_agent` 才应补充调用 RAG，提供深度攻略。

## 结论

这次修复解决的是：

- `spot_agent` 在城市级景点推荐问题上默认先跑 RAG，导致慢响应或无响应的策略问题

这不是 RAG 数据质量本身的最终修复；RAG 精度和召回质量仍可后续继续优化。
