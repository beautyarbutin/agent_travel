# 相对原版 OpenAgents 的本地改造说明

## 0. 说明

- 对比基线：`https://github.com/wxj123-del/OpenAgents` 的 `master` 分支
- 对比时间：2026-03-15
- 本文统计对象：当前本地工作区现状，包含未提交文件
- 这份文档用于补全 [implementation_plan.md](/d:/20251224/AI_Study/OpenAgents/implementation_plan.md) 中未完全记录的改动

一句话总结：

- 原版仓库本质上是一个“只有 4 个 YAML 智能体配置 + 说明文档”的轻量示例
- 你现在的本地项目已经被扩展成“本地模型 + 多 Agent 路由 + MCP 工具 + RAG + 记忆 + 评测/微调资产”的完整实验仓库

---

## 1. 一眼看懂的总差异

| 维度 | 原版项目 | 当前本地项目 |
| --- | --- | --- |
| Agent 协作方式 | 广播式，所有 Agent 监听公共频道，靠关键词决定是否回复 | `travel_router` 统一接待并分发，子 Agent 只处理 direct message |
| LLM | `glm-4.7` | `local-qwen`，实际使用 LM Studio 部署的 Qwen3.5-4B |
| 业务能力来源 | Prompt 内置静态知识 | MCP 工具 + 高德 API + Open-Meteo + 本地 RAG |
| 天气能力 | Prompt 回答/静态知识范式 | 动态天气查询工具 |
| 景点能力 | Prompt 内置少量热门城市景点 | 高德 POI + 本地景点知识库 + Hybrid RAG |
| 路线能力 | Prompt 规划 | 高德驾车路线工具 |
| 记忆能力 | 无持久化记忆 | `save_context` / `get_context` 本地文件记忆 |
| 项目形态 | 配置示例 | 可运行原型 + 数据集 + 索引 + 评测 + LoRA 资产 |

---

## 2. 核心文件差异表

### 2.1 文档层

| 文件 | 原版 | 当前本地 | 备注 |
| --- | --- | --- | --- |
| `README.md` | 原版主说明文档 | 仅把模型相关表述从 `GLM-4.7` 改成了 `Qwen3.5-4B / LM Studio` | 架构描述仍大量保留原版“广播+关键词触发”思路，已不是当前运行时真相 |
| `docs/travel_assistant_design.md` | 原版附带设计文档 | 与 `README.md` 同步做了模型名替换 | 仍带有原版广播式架构描述 |

### 2.2 Agent 配置层

| 文件 | 原版行为 | 当前本地行为 | 关键变化 |
| --- | --- | --- | --- |
| `agents/travel_router.yaml` | 接待员，只做寒暄和一般咨询；广播监听 | 总控路由器；读取记忆、做指代消解、通过 `send_direct_message` 分发到子 Agent | 新增 `memory_mcp_server`、sender 过滤、事件触发器、禁止自己调用天气/景点/路线工具 |
| `agents/weather_agent.yaml` | 靠关键词在公共频道直接回答天气 | 只接 `travel_router` 的 direct message；通过 MCP `get_weather` 查询真实天气后回频道 | 新增 `user_prompt_template`、MCP 接入、direct-message 触发器、禁止跨域回答 |
| `agents/spot_agent.yaml` | 内置热门城市景点静态知识；公共频道关键词触发 | 只接 `travel_router` 的 direct message；通过 `search_spots` / `search_local_knowledge` 回答景点问题 | 从静态 prompt 知识库改成了工具驱动 + RAG；近期又调整成“城市级问题 POI 优先” |
| `agents/plan_agent.yaml` | 靠 prompt 做行程规划；公共频道关键词触发 | 只接 `travel_router` 的 direct message；读取记忆并可调用 `get_driving_route` | 新增 MCP、上下文记忆、路线工具、严格的工具回复规范 |

### 2.3 一个重要现实差异

原版的 4 个 YAML 都是“提示词主导”的轻量配置。  
你现在的 4 个 YAML 已经变成“事件路由 + 工具调用 + 本地记忆 + 频道消息工具”的工作流配置。

这意味着当前项目比原版更强，但也比原版多了几个新的失败点，例如：

- 模型是否真的调用了消息工具
- 子 Agent 是否只响应 direct message
- 工具返回是否足够快
- RAG 是否在该场景被正确使用

---

## 3. 原版没有、当前新增的核心运行模块

### 3.1 MCP 与运行时

| 文件 | 作用 |
| --- | --- |
| `mcp_server.py` | 新增统一旅游 MCP 服务，暴露天气、景点、RAG、路线、记忆读写等工具 |
| `memory_mcp.py` | 新增独立记忆 MCP，只给 `travel_router` 使用，避免 router 直接拿到业务工具 |
| `start_all.bat` | 一键启动 OpenAgents Network 与 4 个 Agent |
| `web_ui.py` | 新增 Gradio 原型界面，属于额外 UI 实验 |

### 3.2 工具模块

| 文件 | 作用 |
| --- | --- |
| `tools/weather_tools.py` | 当前天气实现：高德地理编码 + Open-Meteo 实时天气 |
| `tools/spot_tools.py` | 当前景点深度检索实现：BM25 + FAISS + bge-small-zh + 高德 POI 融合 |
| `tools/map_tools.py` | 高德路线工具原型 |
| `tools/memory_tools.py` | 本地文件记忆读写，落盘到 `storage/user_context.json` |

### 3.3 数据构建与评测工具

原版仓库没有 `tools/` 目录。当前本地新增了大量数据处理、评测、微调辅助脚本，例如：

- `tools/build_spot_vectors.py`
- `tools/convert_csv_to_json.py`
- `tools/add_batch_guides.py`
- `tools/eval_rag.py`
- `tools/eval_spot_answers.py`
- `tools/eval_tool_calling.py`
- `tools/generate_finetune_data.py`
- `tools/generate_finetune_data_v2.py`
- `tools/build_router_eval_dataset.py`
- `tools/build_spot_eval_cases.py`

这说明本地项目已经从“Agent 配置示例”演化成“带数据生产和评测链路的实验仓库”。

---

## 4. 数据与知识库改造

原版仓库没有本地数据目录、向量索引或知识库。当前本地新增了完整的数据资产：

### 4.1 新增目录

- `data/`
- `storage/`
- `models/`
- `reports/`

### 4.2 当前景点知识库

`data/spots_knowledge.json` / `storage/doecment.json` 当前共 `15723` 条，来源构成为：

| 来源 | 条数 |
| --- | ---: |
| `Kaggle/去哪儿网` | 14581 |
| `CrossWOZ景点库` | 465 |
| `独家手写攻略` | 347 |
| `China312地理数据集` | 312 |
| `香港旅游指南QA` | 18 |

相关文件：

- `data/spots_knowledge.json`
- `data/spots_knowledge.md`
- `data/archive/`
- `data/datasets_rag/`
- `data/datasets_lora/`
- `data/lora_ready/`

完整的 RAG 专题总览、演进、检索公式、评测结果和技术债，见：

- `docs/RAG_全量工作总览_2026-03-18.md`

### 4.3 向量索引与记忆文件

`storage/` 目录中新增：

- `faiss_index.bin`
- `doecment.json`
- `user_context.json`
- `vectors.json`

这代表你已经把景点知识从“prompt 里写死的静态文本”升级成了“可检索的本地知识库”。

---

## 5. 模型、微调与训练数据改造

原版项目没有模型资产、LoRA 权重或训练数据。当前本地新增了以下内容：

### 5.1 模型与 LoRA 目录

- `models/Qwen3.5-4B-travel-lora/`
- `models/router_lora_2026-03-12/`
- `models/spot_lora_2026-03-12/`
- `models/router_lora_2026-03-12.tar.gz`
- `models/spot_lora_2026-03-12.tar.gz`

### 5.2 训练/微调数据

- `openagents_tool_calling_v2.json`：`609` 条
- `openagents_sft_dataset.json`：`609` 条

### 5.3 模型处理脚本

- `models/merge_lora.py`
- `models/merge_shard2.py`
- `models/test_model.py`
- `convert_dataset.py`

这部分说明你不仅改了运行时，还做了本地模型适配、工具调用数据集构建和 LoRA 训练实验。

---

## 6. 文档与排障记录新增

原版 `docs/` 只有一份：

- `docs/travel_assistant_design.md`

当前本地新增了多份工程记录：

- `implementation_plan.md`
- `docs/2026-03-15_event_routing_fix.md`
- `docs/2026-03-15_search_spots_city_parsing_fix.md`
- `docs/2026-03-15_spot_agent_poi_first_strategy_fix.md`
- `docs/lora_rag_work_summary_2026-03-12.md`
- `docs/lora评测总结.md`
- `docs/lora真实badcase汇总.md`
- `docs/RAG_interview_guide.md`
- `docs/cursor_note.md`

也就是说，本地项目已经积累了比较完整的实验与排障轨迹，而不再只是“最终配置结果”。

---

## 7. 当前运行架构，和原版最大的本质区别

### 原版

- 4 个 Agent 都在公共频道里监听消息
- 依靠关键词判断要不要回答
- `weather/spot/plan` 主要靠 prompt 自身的内置知识
- 没有持久化上下文记忆
- 没有外部 API / 没有 RAG / 没有 MCP

### 当前本地

- `travel_router` 负责接待、意图识别、记忆读取、指代消解、任务转发
- `weather_agent / spot_agent / plan_agent` 主要处理 router 发来的 direct message
- 具体业务能力主要来自工具：
  - 天气：`get_weather`
  - 景点：`search_spots` / `search_local_knowledge` / `search_combined`
  - 路线：`get_driving_route`
  - 记忆：`save_context` / `get_context`
- 引入了本地知识库、FAISS 索引、评测数据与微调实验

这就是为什么你现在的系统行为、问题类型、排障方式，和原版项目已经很不一样。

---

## 8. 需要特别说明的“文档漂移”

当前仓库里有几份文档已经和真实运行时出现偏差：

### 8.1 `README.md` / `docs/travel_assistant_design.md`

这两份文档虽然已经把模型名改成了本地 Qwen，但整体架构描述仍然主要是原版的：

- 广播监听
- 关键词触发
- Prompt 主导的静态回答

它们不能完整代表当前运行时。

### 8.2 `implementation_plan.md`

这份文档记录了很多真实改造方向，但不是完整清单，而且部分内容已经过时或互相冲突。  
例如天气部分曾同时出现过：

- OpenWeatherMap 版本
- 高德地理编码 + Open-Meteo 版本

因此，这份新文档的定位是：

- 用于完整梳理“相对原版到底改了什么”
- 而不是继续把历史计划与当前代码混写在一起

---

## 9. 非核心功能改造，但属于本地工作区新增内容

以下内容也属于相对原版新增，但更偏本地实验或辅助资产：

- `0314eval/`
- `agent_travel/`
- `install_log.txt`
- `install_log2.txt`
- `log.txt`
- `tmp_*.txt / tmp_*.html`
- `start_all.bat - 快捷方式*.lnk`
- `LLaMA-Factory微调.pdf`

这些文件说明本地工作区不仅承载运行代码，也承载了实验记录、临时排障文件和外部资料。

---

## 10. 最终结论

相对原版 `wxj123-del/OpenAgents`，你本地项目的改动可以概括为 6 类：

1. 把原版的广播式关键词聊天，改造成了以 `travel_router` 为中心的多 Agent 路由系统
2. 把原版的 prompt 内置知识，改造成了 MCP 工具驱动的天气 / 景点 / 路线能力
3. 新增了本地上下文记忆机制
4. 新增了景点 RAG 知识库、向量索引与评测体系
5. 新增了本地模型微调与工具调用数据集
6. 新增了大量排障、评测和实验文档

所以当前仓库已经不是“原版 OpenAgents 示例的轻微改动”，而是一个在原版骨架上持续扩展出来的本地旅游 Agent 实验平台。
