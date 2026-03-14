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

相关配置：

- [travel_router.yaml](/D:/20251224/AI_Study/OpenAgents/agents/travel_router.yaml)
- [spot_agent.yaml](/D:/20251224/AI_Study/OpenAgents/agents/spot_agent.yaml)
- [weather_agent.yaml](/D:/20251224/AI_Study/OpenAgents/agents/weather_agent.yaml)
- [plan_agent.yaml](/D:/20251224/AI_Study/OpenAgents/agents/plan_agent.yaml)
- [.env](/D:/20251224/AI_Study/OpenAgents/.env)

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

- [Open-Travel](/D:/20251224/AI_Study/OpenAgents/data/datasets_lora/Open-Travel)
- [ChinaTravel](/D:/20251224/AI_Study/OpenAgents/data/datasets_lora/ChinaTravel)
- [Cultour-master](/D:/20251224/AI_Study/OpenAgents/data/datasets_lora/Cultour-master)

RAG / 知识库相关：

- [China_City_Attraction_Details](/D:/20251224/AI_Study/OpenAgents/data/datasets_rag/China_City_Attraction_Details)
- [China312](/D:/20251224/AI_Study/OpenAgents/data/datasets_rag/China312)

其中：

- `China City Attraction Details` 已解压，适合作为主景点知识库
- `China312` 适合作为空间与历史文化补充数据

### 3. 盘点了本地可用训练数据

当前关键训练数据：

- [01_tool_calling.json](/D:/20251224/AI_Study/OpenAgents/data/lora_ready/01_tool_calling.json)
- [01_tool_calling_lf.json](/D:/20251224/AI_Study/OpenAgents/data/lora_ready/01_tool_calling_lf.json)
- [02_spot_cultour_clean.json](/D:/20251224/AI_Study/OpenAgents/data/lora_ready/02_spot_cultour_clean.json)
- [spots_knowledge.json](/D:/20251224/AI_Study/OpenAgents/data/spots_knowledge.json)

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

- 当前训练链路不吃你当时的 `gpt + tool_calls` 版本
- 训练可用格式需要：
  - `human`
  - `function_call`
  - `observation`
  - 最后一条非空 `gpt`

为此新增并使用了：

- [convert_toolcalls_to_function_call.py](/D:/20251224/AI_Study/OpenAgents/tools/convert_toolcalls_to_function_call.py)

同时本地生成了：

- [01_tool_calling_lf.json](/D:/20251224/AI_Study/OpenAgents/data/lora_ready/01_tool_calling_lf.json)

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
- 你在 LLaMA-Factory Chat 里单独聊天时，并没有真实调用 `get_driving_route`
- 这个问题本来应该交给 `plan_agent`，而不是 `spot_agent`
- 训练数据里 `spot` 更偏开放式旅游描述，模型一旦答到不擅长的问题，就容易编长篇、重复、胡扯

所以像“衡水到如皋怎么走”这种问题：

- 对 `spot_lora` 来说是越权问题
- 对没有真实工具执行的单模型聊天页来说，更容易幻觉

这说明：

- `spot_lora` 不适合直接拿来当全局共享模型去回答路线问题
- 也说明你现在的 LoRA 是“专用微调”，不是“万能升级包”

### 2. 当前最稳的部署思路

如果你现在不想大改架构，先走这条：

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

## 六、最新评测结果补充

### 1. router LoRA 的正式评测结论

评测方式：

- 使用项目内 `34` 条 held-out `tool-calling` 路由评测集
- 对比对象：
  - `Qwen3.5-4B Base`
  - `Qwen3.5-4B + Router LoRA (checkpoint-60)`
- 评测脚本：
  - [eval_tool_calling.py](/D:/20251224/AI_Study/OpenAgents/tools/eval_tool_calling.py)
  - [compare_tool_eval.py](/D:/20251224/AI_Study/OpenAgents/tools/compare_tool_eval.py)
- 结果文件：
  - [results (2).json](/D:/20251224/AI_Study/OpenAgents/0314eval/results%20(2).json)
  - [results_new.json](/D:/20251224/AI_Study/OpenAgents/0314eval/results_new.json)
  - [router_compare_internal_local.md](/D:/20251224/AI_Study/OpenAgents/0314eval/router_compare_internal_local.md)

核心结果：

- `Tool-name accuracy`：`51.19% -> 100.00%`
- `Argument exact match`：`19.57% -> 89.13%`
- `Turn exact match`：`48.81% -> 94.05%`
- `Decision tool-name accuracy`：`19.57% -> 100.00%`
- `Sample full-chain success`：`20.59% -> 85.29%`

结论：

- `router_lora` 是这次项目里最明确成功的 LoRA
- 它显著提升了：
  - 意图识别
  - 子 Agent 路由
  - 参数构造
  - 整条调用链成功率

### 2. spot LoRA 的正式评测结论

评测方式拆成两层：

- `项目内 benchmark`
  - 更贴近真实旅游景点问答与推荐任务
- `公开 benchmark`
  - 使用 `CrossWOZ` 转换后的景点公开评测集

这次先完成了公开 benchmark：

- 数据文件：
  - [spot_eval_crosswoz.json](/D:/20251224/AI_Study/OpenAgents/tools/spot_eval_crosswoz.json)
- 转换脚本：
  - [build_spot_eval_from_crosswoz.py](/D:/20251224/AI_Study/OpenAgents/tools/build_spot_eval_from_crosswoz.py)
- 评测脚本：
  - [eval_spot_answers.py](/D:/20251224/AI_Study/OpenAgents/tools/eval_spot_answers.py)
  - [compare_spot_eval.py](/D:/20251224/AI_Study/OpenAgents/tools/compare_spot_eval.py)
- 结果文件：
  - [report (3).md](/D:/20251224/AI_Study/OpenAgents/0314eval/report%20(3).md)
  - [results (3).json](/D:/20251224/AI_Study/OpenAgents/0314eval/results%20(3).json)
  - [report (4).md](/D:/20251224/AI_Study/OpenAgents/0314eval/report%20(4).md)
  - [results (4).json](/D:/20251224/AI_Study/OpenAgents/0314eval/results%20(4).json)
  - [spot_compare_crosswoz.md](/D:/20251224/AI_Study/OpenAgents/0314eval/spot_compare_crosswoz.md)

公开 benchmark 最终对比结果：

- `Base`
  - `Strict success`: `98.00%`
  - `Fact coverage`: `99.00%`
  - `ROUGE-L F1`: `2.66%`
- `Spot LoRA`
  - `Strict success`: `90.67%`
  - `Fact coverage`: `94.33%`
  - `ROUGE-L F1`: `27.36%`

结论：

- `spot_lora` 在这套偏“事实抽取”的公开 benchmark 上不如基座模型
- 但它的 `ROUGE-L F1` 明显更高，说明回答组织和旅游助手式表达更接近参考答案
- 这说明 `spot_lora` 的优化方向更偏：
  - 旅游内容组织
  - 景点介绍风格
  - 推荐式表达
- 它并不是通用事实抽取增强模型

这不是失败，而是一个典型的 `trade-off`：

- `Base` 更像“拿到资料就精准抽字段”
- `Spot LoRA` 更像“会把景点信息组织成旅游助手回答”

项目内 benchmark 这边也已经准备好了：

- 数据文件：
  - [spot_eval_cases.json](/D:/20251224/AI_Study/OpenAgents/tools/spot_eval_cases.json)
- 构建脚本：
  - [build_spot_eval_cases.py](/D:/20251224/AI_Study/OpenAgents/tools/build_spot_eval_cases.py)

这个内部 benchmark 的特点是：

- 来自你自己的：
  - [expanded_test_cases.json](/D:/20251224/AI_Study/OpenAgents/tools/expanded_test_cases.json)
  - [doecment.json](/D:/20251224/AI_Study/OpenAgents/storage/doecment.json)
- 共 `80` 条
- 覆盖：
  - `城市+景点`
  - `精确景点`
  - `Kaggle`
  - `手写`
- 更贴近你项目实际的旅游景点问答和推荐表达

建议最终口径：

- `公开 benchmark`：用于外部验证
- `项目内 benchmark`：用于验证 `spot_lora` 是否更贴近你的真实业务目标

## 七、老师可能会问的 LoRA 面试问题与回答

下面这些问题，是结合“改训练数据数量、rank、target、loss、预测准确率”这类微调项目常见问法，再映射到你这个项目后的高频问题。

### 1. 你为什么做 LoRA，而不是全参数微调？

标准回答：

> 因为我的目标是做任务定向微调，而不是重塑整个模型能力。全参数微调显存和训练成本更高，而 LoRA 冻结原模型，只训练低秩增量矩阵，成本更低，更适合我这种有限显存条件下的实验。

结合本项目：

- `router` 和 `spot` 都是典型的任务定向目标
- `weather` 这类依赖实时 API 的任务，不值得把知识固化进参数
- `plan` 现阶段更依赖工具调用，也不是当前 LoRA 的最高优先级

### 2. 你的 LoRA 核心公式是什么？

标准回答：

> LoRA 的核心是把权重更新写成低秩分解：`W' = W + (alpha / r)BA`。其中原始权重 `W` 冻结，只训练低秩矩阵 `A` 和 `B`。

### 3. rank 为什么常设成 8、16？它除了显存还影响什么？

标准回答：

> `rank` 决定低秩更新的容量，不只是影响显存。rank 太小，模型可能装不下任务所需的变化；rank 太大，参数更多、更容易过拟合。8 和 16 是常见的工程折中值。

结合本项目：

- 你这次两个 LoRA 都用了 `rank=8`
- `router` 的 `eval_loss` 和 benchmark 结果证明这组参数是有效的
- `spot` 的训练收敛也正常，但 benchmark 表现说明“rank 合理”不等于“任何 benchmark 都会涨”

### 4. alpha 为什么常设成 rank 的两倍？

标准回答：

> 因为真正影响 LoRA 更新强度的是 `alpha / rank`。把 `alpha` 设成 `2r` 是常见经验设定，能让更新强度保持在比较稳定的范围，比如我这次是 `r=8, alpha=16`，所以 `alpha/r=2`。

更贴近项目的回答可以这样说：

> 我这次选 `rank=8, alpha=16`，不是因为它在理论上一定最优，而是因为对 4B 模型、小中规模数据和单卡显存约束来说，这是一个很常见的稳定起点。`rank=8` 代表 LoRA 有中等容量，不会太小到学不动，也不会太大到明显增加过拟合风险；`alpha=16` 则让 `alpha/r=2`，保证 LoRA 更新注入原模型时的强度在一个比较稳的范围里。后面我不是靠拍脑袋定它，而是结合 `eval_loss` 和 benchmark 结果来验证这组参数是否有效。

### 5. target_modules 是什么？你这次微调了哪些层？

标准回答：

> target_modules 指的是 LoRA 要挂到模型的哪些线性层上。只挂 q/v 是轻量做法，挂 qkvo 或 all 会更全面。

结合本项目：

- 你这次使用的是 `lora_target=all`
- 实际覆盖了：
  - attention 相关投影层
  - FFN/MLP 层
  - Qwen3.5 模型里的特有投影层

可以这样答：

> 我这次不是只改 qkvo，而是用了 `lora_target=all`，让 LLaMA-Factory 自动给 Qwen3.5-4B 的主要线性层都加上了 LoRA，包括 attention 和 FFN/MLP 相关层。

### 6. 为什么不能只看 train loss？

标准回答：

> 因为 `train loss` 只能说明模型越来越会做训练集里的题，不代表它对新样本也更好。还要看 `eval loss`，防止模型只是把训练集背下来，也就是过拟合。

### 7. train loss 和 eval loss 有什么区别？

标准回答：

> `train loss` 是模型在训练集上的错误程度，`eval loss` 是模型在验证集上的错误程度。前者看收敛，后者看泛化。

结合本项目：

- `router`：中间 checkpoint 最优，所以最后选了 `checkpoint-60`
- `spot`：`eval_loss` 持续下降，所以选了 `final / checkpoint-523`

### 8. 你怎么选 checkpoint？

标准回答：

> 我不是默认 final 最好，而是结合 `eval_loss` 和任务结果来选。router 这类小而结构化的数据，更容易过拟合，所以我选了中间 checkpoint；spot 这次验证集效果持续下降，所以保留 final。

### 9. 你怎么证明 LoRA 有效果，而不是只是 loss 下降？

这是老师最可能继续深挖的问题。

标准回答：

> 我不只看 loss，还做了任务 benchmark。router 用项目内 held-out tool-calling benchmark，对比基座模型和 router LoRA 在工具路由、参数构造和整链成功率上的差异；spot 则做了公开 CrossWOZ benchmark，对比基座模型和 spot LoRA 在事实覆盖和回答风格上的差异。

结合本项目可直接报数：

> router LoRA 在我的 34 条项目内 benchmark 上，`decision tool-name accuracy` 从 `19.57%` 提升到 `100%`，`sample full-chain success` 从 `20.59%` 提升到 `85.29%`。

### 10. 为什么 router 提升这么大？

标准回答：

> 因为 router 的目标是高度结构化的：意图识别、工具选择、参数构造、上下文保存顺序。这类任务和 LoRA 训练数据的一致性很高，所以效果提升非常明显。

### 11. 为什么 spot 没有像 router 那样大幅提升？

标准回答：

> 因为 benchmark 和训练目标不完全一致。我的 `spot_lora` 更偏旅游内容组织和景点表达，而公开 CrossWOZ benchmark 更偏“给定资料后的事实抽取”。所以它在风格指标上更好，但在严格事实型指标上不如基座模型。

这是很重要的结论：

- `router_lora`：明显成功
- `spot_lora`：有取舍，不是全方位提升

### 12. 你的数据集是怎么来的？有没有处理过？

标准回答：

> 我不是直接拿原始数据就训。router 一开始因为格式不对，LLaMA-Factory 直接报 `Cannot find valid samples`。后面我把原来的 `gpt + tool_calls` 样式转换成了训练可接受的 `function_call + observation` 格式，并补上了最后的可学习 assistant 回复。spot 这边则用清洗过的旅游内容数据做普通 SFT。

结合本项目可引用：

- [01_tool_calling.json](/D:/20251224/AI_Study/OpenAgents/data/lora_ready/01_tool_calling.json)
- [01_tool_calling_lf.json](/D:/20251224/AI_Study/OpenAgents/data/lora_ready/01_tool_calling_lf.json)
- [02_spot_cultour_clean.json](/D:/20251224/AI_Study/OpenAgents/data/lora_ready/02_spot_cultour_clean.json)

### 13. 你项目里为什么不做 weather 的 LoRA？

标准回答：

> 因为 weather 的核心价值来自实时天气 API，不来自模型参数。天气 agent 真正要做的是抽城市、调用 API、组织回答，这部分更适合用工具调用和 prompt 控制，而不是 LoRA 注入知识。

### 14. 为什么 plan 现在也没有做 LoRA？

标准回答：

> 因为现阶段路线规划更多是工具调用问题，比如 origin、destination 抽取和 `get_driving_route` 调用，而不是模型知识记忆问题。相比之下，router 和 spot 的 LoRA 收益更高，所以优先做了那两条。

### 15. 你的 function-calling / tool-calling 是什么意思？

标准回答：

> 它的意思是让模型不只是直接回答，而是学会根据任务调用外部函数或工具，并填对参数。在我的项目里，模型需要学会调用天气、景点、路线、记忆以及 agent 转发相关的工具。

结合本项目：

- `router` 的 function-calling 不只是天气查询
- 更重要的是：
  - `get_context`
  - `send_direct_message`
  - `save_context`
  - `send_channel_message`

### 16. 你的 benchmark 是怎么设计的？

标准回答：

> 我没有只用一个 benchmark，而是把评测拆成“项目内 benchmark”和“公开 benchmark”两层。项目内 benchmark 更贴合我的真实任务目标，公开 benchmark 则用于做外部验证。

结合本项目：

- `router`：项目内 `34` 条 held-out tool-calling benchmark
- `spot`：公开 `CrossWOZ` 转换 benchmark，共 `150` 条

### 17. 你这个项目里最成功的部分是什么？

标准回答：

> 最成功的是 router LoRA。因为它的目标最清晰、数据和任务最一致，而且 benchmark 数字提升也最明显。

### 18. 你这个项目里最有分析价值的部分是什么？

标准回答：

> 是 spot LoRA 的 trade-off。它让我看到：LoRA 不一定会在所有 benchmark 上都提升，尤其当 benchmark 和训练目标不完全一致时，会出现“风格变好但事实抽取下降”的现象。这说明 benchmark 设计必须和任务目标匹配。

### 19. 如果老师问：为什么你就选 `rank=8, alpha=16`？是不是只是照着经验值填？

标准回答：

> 我会区分“初始化选择”和“最终结论”。`rank=8, alpha=16` 先是一个有工程依据的稳定起点：对 4B 模型来说，`rank=8` 已经能提供足够的低秩更新容量，而 `alpha=16` 对应 `alpha/r=2`，是常见且稳定的更新强度。真正让我保留这组参数的，不是经验值本身，而是后续的验证：router 这组参数在 `eval_loss` 和 benchmark 上都表现很好，spot 训练也稳定收敛。所以我的选择过程是“经验值起步 + 实验结果验证”，不是盲目照抄。

### 20. 你需要做参数对比试验吗？

标准回答：

> 如果时间允许，做一组小规模消融会更完整，但不一定要把所有参数都穷举。对我这个项目，最值得做的是在 `router` 上做轻量消融，因为 router 的 benchmark 信号最清晰。

建议最小消融方案：

- 固定：
  - 数据集不变
  - 学习率不变
  - epoch 不变
  - `lora_target=all`
- 只比较：
  - `rank = 4 / 8 / 16`
  - `alpha = rank` 或 `alpha = 2 * rank`
- 指标：
  - `eval_loss`
  - `decision tool-name accuracy`
  - `sample full-chain success`

为什么优先选 `router` 做消融：

- 任务更结构化
- benchmark 已经成熟
- 提升信号大，最容易看出参数差异

如果时间不够，可以这样答：

> 我目前已经完成主实验和 benchmark，对 `rank=8, alpha=16` 的有效性有任务结果支持。如果后续补消融，我会优先在 router 任务上做 `rank` 和 `alpha` 的小规模对比，而不是盲目把所有参数都重跑一遍。

## 八、老师追问时可以直接说的总结版

如果老师问：

### “你做这些 LoRA 有什么意义？”

你可以答：

> 我的工作不是简单地把现成框架跑起来，而是把 LoRA 用在旅游多智能体系统里最适合微调的两个子任务上：router 和 spot。router 负责意图识别、工具路由和参数构造，spot 负责景点介绍和旅游表达。我不仅做了训练，还做了数据格式修复、checkpoint 选择和 benchmark 对比，所以最终能说明哪些任务适合 LoRA、哪些任务不适合 LoRA。

### “你有什么明确结果？”

你可以答：

> router LoRA 的结果最明确：在项目内 benchmark 上，`decision tool-name accuracy` 从 `19.57%` 提升到 `100%`，`sample full-chain success` 从 `20.59%` 提升到 `85.29%`。  
> spot LoRA 的结果更有取舍：在公开 CrossWOZ benchmark 上，strict success 从 `98.00%` 降到 `90.67%`，但 `ROUGE-L F1` 从 `2.66%` 升到 `27.36%`，说明它更偏景点表达风格对齐，而不是通用事实抽取增强。

### “你从这个项目里真正学到了什么？”

你可以答：

> 我学到的不只是 LoRA 原理，而是完整的微调闭环：任务拆分、数据清洗、数据格式修复、参数选择、checkpoint 选择、benchmark 设计和结果分析。尤其是通过 router 和 spot 两条线的不同结果，我理解了 benchmark 必须和训练目标一致，不能只看 loss 或只看一个公开分数。

## 九、推荐的下一步顺序

最稳顺序：

1. 先确认你是否坚持“LM Studio 只加载一个模型”
2. 如果是，优先导出 `router` 方向模型做联调
3. 在你当前 OpenAgents 里做真实对话测试
4. 如果 `spot` 表现仍弱，再考虑改成多模型架构
5. 之后再补 `plan_agent` 的专属 LoRA

## 十、如何在 AutoDL 上验证 `router_lora` 是否真的成功

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

真正决定 `router_lora` 成不成功的，不是裸聊，而是接回你当前 OpenAgents：

- [travel_router.yaml](/D:/20251224/AI_Study/OpenAgents/agents/travel_router.yaml)
- [spot_agent.yaml](/D:/20251224/AI_Study/OpenAgents/agents/spot_agent.yaml)
- [weather_agent.yaml](/D:/20251224/AI_Study/OpenAgents/agents/weather_agent.yaml)
- [plan_agent.yaml](/D:/20251224/AI_Study/OpenAgents/agents/plan_agent.yaml)

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

## 十一、当前定版结论

- `router_lora`：用 `checkpoint-60`
- `spot_lora`：用 `final / checkpoint-523`
- `spot_lora` 不适合直接当全局共享模型回答路线问题
- 当前项目如果不改架构，优先测试 `router` 方向模型，而不是 `spot` 方向模型
