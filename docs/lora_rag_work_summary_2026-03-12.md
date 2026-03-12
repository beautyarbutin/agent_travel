# OpenAgents LoRA / RAG 工作纪要

日期：2026-03-12

## 一、当前项目目标

基于 OpenAgents 搭一个旅游助手，核心能力包括：

- `travel_router`：意图识别、路由、参数构造
- `weather_agent`：天气查询
- `spot_agent`：景点介绍、推荐、攻略表达
- `plan_agent`：路线规划、行程安排
- 最终部署方式：本地 `LM Studio`

当前项目实际架构不是“一堆模型”，而是：

- `4 个逻辑 agent`
- 目前都共用同一个 `LM Studio` 模型入口 `local-qwen`

相关项目文件：

- `agents/travel_router.yaml`
- `agents/spot_agent.yaml`
- `agents/weather_agent.yaml`
- `agents/plan_agent.yaml`
- `.env`

## 二、这次对话已完成的工作

### 1. 梳理了数据建设方向

明确拆成两条线：

- `Tool-calling / router 数据`
  - 目标：意图识别、工具路由、参数构造
- `旅游内容 / spot 数据`
  - 目标：景点介绍、推荐表达、内容组织

结论：

- `router` 和 `spot` 不能混成一个 LoRA 训练

### 2. 下载并整理了公开数据集

LoRA / 训练相关：

- `Open-Travel`
- `ChinaTravel`
- `Cultour`

RAG / 知识库相关：

- `China City Attraction Details`
- `China312`

其中：

- `China City Attraction Details` 已解压，适合作为主景点知识库
- `China312` 适合作为空间与历史文化补充数据

### 3. 盘点了本地可用训练数据

当前关键训练数据：

- `data/lora_ready/01_tool_calling.json`
- `data/lora_ready/01_tool_calling_lf.json`
- `data/lora_ready/02_spot_cultour_clean.json`
- `data/spots_knowledge.json`

角色定位：

- `01_tool_calling.json`
  - 原始 router 数据，偏 `gpt + tool_calls`
- `01_tool_calling_lf.json`
  - 为 LLaMA-Factory 训练转换后的版本
- `02_spot_cultour_clean.json`
  - 可直接做普通 SFT 的 `spot` 数据
- `spots_knowledge.json`
  - 更适合做 RAG 原料，或以后再合成 QA 数据

### 4. 修复了 router 数据格式问题

训练 `router` 时，LLaMA-Factory 一开始报：

- `Cannot find valid samples`

根因：

- 当前训练链路不吃当时的 `gpt + tool_calls` 版本
- 训练可用格式需要：
  - `human`
  - `function_call`
  - `observation`
  - 最后一条非空 `gpt`

新增并使用：

- `tools/convert_toolcalls_to_function_call.py`

同时生成：

- `data/lora_ready/01_tool_calling_lf.json`

### 5. 完成了 router LoRA 训练

训练要点：

- 模型：`Qwen3.5-4B`
- 模板：`qwen3_5_nothink`
- 学习率：`5e-5`
- epoch：`2`
- batch：`2`
- grad accumulation：`8`
- val size：`0.1`

结果：

- 训练成功完成
- `eval_loss` 持续下降
- 最优不是 final，而是中间 checkpoint

最终结论：

- `router_lora` 选 `checkpoint-60`

### 6. 完成了 spot LoRA 训练

训练要点：

- 数据集：`spot_cultour`
- 学习率：`3e-5`
- epoch：`1`
- cutoff：`1536`
- batch：`2`
- grad accumulation：`8`
- val size：`0.05`

结果：

- 训练成功完成
- `eval_loss` 从 `1.9469` 一路降到 `1.8405`
- 无明显过拟合

最终结论：

- `spot_lora` 选 `final / checkpoint-523`

### 7. 画出了 router / spot 的训练和验证曲线

结论已经明确：

- `router`：中间 checkpoint 最优
- `spot`：final 最优

### 8. 明确了 LM Studio 部署约束

关键事实：

- 当前项目是 `4 个 agent 共用 1 个 LM Studio 模型`
- 不是“每个 agent 都单独一个模型”

因此部署上有两条路：

#### 路线 A：保持当前单模型架构

优点：

- 改动最小
- 最快落地

缺点：

- 只能选一个模型给全部 agent 共用
- `router` 和 `spot` 的 LoRA 目标会冲突

#### 路线 B：改成多模型架构

示例：

- `travel_router` -> router 模型
- `spot_agent` -> spot 模型
- `weather_agent / plan_agent` -> base 模型或未来专属模型

优点：

- 各 agent 更专用

缺点：

- 需要改当前 OpenAgents 的模型路由方式
- 不再是一个 `local-qwen` 打天下

## 三、当前最重要的技术结论

### 1. 为什么 `spot_lora + 原模型` 会把路线问题答得很离谱

这不是“模型没加载上”，而是任务本身不匹配。

原因有四个：

- `spot_lora` 学的是景点内容表达，不是路线规划
- 在 LLaMA-Factory Chat 里单独聊天时，并没有真实调用 `get_driving_route`
- 这个问题本来应该交给 `plan_agent`，而不是 `spot_agent`
- 训练数据里 `spot` 更偏开放式旅游描述，模型一旦答到不擅长的问题，就容易编长篇、重复、胡扯

所以像“衡水到如皋怎么走”这种问题：

- 对 `spot_lora` 来说是越权问题
- 对没有真实工具执行的单模型聊天页来说，更容易幻觉

这说明：

- `spot_lora` 不适合直接拿来当全局共享模型去回答路线问题
- 也说明当前 LoRA 是“专用微调”，不是“万能升级包”

### 2. 当前最稳的部署思路

如果现在不想大改架构，先走这条：

1. 先保留当前 `4 agent 共用 1 模型` 的方式
2. 优先导出并测试 `router` 方向的模型
3. 不要先把 `spot_lora` 当成整个系统的唯一共享模型

原因：

- 系统入口是 `travel_router`
- 天气和路线本来主要靠工具
- `spot_lora` 对景点回答有帮助，但会污染非景点任务

## 四、当前推荐的模型选择

### 方案 1：不改架构，继续单模型部署

优先级建议：

1. 先试 `router` 方向模型
2. 如果整体路由更稳，再决定是否继续细分

不建议：

- 一上来就把 `spot_lora` 当成全局共享模型

### 方案 2：改成多模型部署

如果后面愿意改架构，建议这样拆：

- `travel_router` -> `router_lora (checkpoint-60)`
- `spot_agent` -> `spot_lora (final)`
- `weather_agent` -> base 模型
- `plan_agent` -> base 模型，后续再训练专属 `plan_lora`

## 五、接下来的 TODO

### 高优先级

- [ ] 决定最终部署路线：`单模型` 还是 `多模型`
- [ ] 如果继续单模型，优先导出并测试 `router` 方向模型
- [ ] 在 AutoDL 上做 merge / export，不要在本地直接拿 adapter 给 LM Studio 用
- [ ] 在 LM Studio 做一次实际联调，验证 router 是否能稳定走工具

### 中优先级

- [ ] 给 `plan_agent` 准备专属训练数据
- [ ] 给 `router` 做 benchmark 评测
- [ ] 用公开 benchmark + 自建样本对比 base 与 LoRA merged 模型
- [ ] 清洗 `spot_cultour` 中的酒店腔/客服腔样本

### 低优先级

- [ ] 把 `spots_knowledge.json` 转成更高质量 QA 数据
- [ ] 把 `China City Attraction Details` 入库到 RAG
- [ ] 把 `China312` 的 KML 再结构化抽取

## 六、推荐的下一步顺序

最稳顺序：

1. 先确认你是否坚持“LM Studio 只加载一个模型”
2. 如果是，优先导出 `router` 方向模型做联调
3. 在当前 OpenAgents 里做真实对话测试
4. 如果 `spot` 表现仍弱，再考虑改成多模型架构
5. 之后再补 `plan_agent` 的专属 LoRA

## 七、如何在 AutoDL 上验证 `router_lora` 是否真的成功

建议不要只在 LLaMA-Factory 的普通聊天页里问一句话看感觉，而是做三层验证。

### 1. 先做最小链路验证

用 `checkpoint-60` 加载后，在 LLaMA-Factory Chat 中问这类问题：

- `帮我查一下衡水的天气`
- `推荐一下厦门有什么好玩的`
- `帮我规划一下北京两日游`

期待现象不是“自然语言答得多漂亮”，而是：

- 是否先做路由判断
- 是否倾向于输出工具调用相关行为
- 是否不再乱答无关长篇内容

### 2. 再做结构化验证

最稳的方法是准备一小批 `router` 样本做人工回归测试，至少覆盖：

- `weather`
- `spot`
- `plan`
- `chat`

判断标准：

- 意图是否分对
- 工具名是否对
- 参数是否对
- 是否少废话

### 3. 最终做真实系统联调

真正决定 `router_lora` 成不成功的，不是裸聊，而是接回当前 OpenAgents：

- `travel_router.yaml`
- `spot_agent.yaml`
- `weather_agent.yaml`
- `plan_agent.yaml`

测试时重点看：

- 天气问题是否转给 `weather_agent`
- 景点问题是否转给 `spot_agent`
- 路线问题是否转给 `plan_agent`
- 是否正确保存 `current_city` 等上下文

### 4. 不要用这些现象误判失败

以下情况不能直接说明 `router_lora` 失败：

- 在普通聊天页里没有真实工具执行
- 单独让 `router` 回答一个应该由子 agent 处理的问题
- 只看一两句自然语言表现，不看是否正确路由

结论：

- `router_lora` 的核心验收指标是“路由对不对”，不是“裸聊像不像万能助手”

## 八、当前定版结论

- `router_lora`：用 `checkpoint-60`
- `spot_lora`：用 `final / checkpoint-523`
- `spot_lora` 不适合直接当全局共享模型回答路线问题
- 当前项目如果不改架构，优先测试 `router` 方向模型，而不是 `spot` 方向模型
