# 2026-03-15 `search_spots` 城市参数解析修复

## 背景

景点搜索工具 [mcp_server.py](/d:/20251224/AI_Study/OpenAgents/mcp_server.py) 在处理自然语言查询时，会把整句用户问题直接塞进高德 POI API 的 `city` 参数。

典型问题：

- `如皋市 好玩的地方`
- `如皋市有什么好玩的地方推荐吗？`
- `故城县景点有哪些`

这些都不是合法的纯城市名 / 区县名。

## 改前逻辑

改前实现位于 [mcp_server.py](/d:/20251224/AI_Study/OpenAgents/mcp_server.py) 的 `search_spots()`：

- 只要 `query` 中包含 `县 / 市 / 区 / 镇 / 州`
- 就执行：
  - `params["city"] = query`
  - `params["keywords"] = "景点 旅游 风景"`

这会导致：

- `city="如皋市有什么好玩的地方推荐吗？"`
- `city="故城县景点有哪些"`

从而让高德 API 的城市过滤变得不稳定。

## 本次修复

新增了一个很薄的地名提取函数：

- `_extract_location_hint(query: str) -> str`

规则：

- 从自然语言里提取类似行政区划的 token
- 优先取最后一个非 `省` 的地名
- 例如：
  - `如皋市有什么好玩的地方推荐吗？` -> `如皋市`
  - `江苏省南通市如皋市景点推荐` -> `如皋市`
  - `故城县景点有哪些` -> `故城县`

然后在 `search_spots()` 中改为：

- `params["city"] = 提取出的纯地名`
- 不再把整句自然语言直接传给 `city`

## 影响范围

只修改了：

- [mcp_server.py](/d:/20251224/AI_Study/OpenAgents/mcp_server.py)

未修改：

- `travel_router`
- `spot_agent` 提示词
- RAG 检索逻辑
- 其他 MCP 工具

## 结论

这次修复解决的是：

- “高德 POI 的 `city` 参数被错误塞入整句自然语言” 这个实现 bug

这不是景点链路卡顿的全部原因；RAG 检索慢的问题仍然独立存在。
