# LoRA 评测总结

## 1. 项目目标

本项目围绕旅游多智能体系统，对 `Qwen3.5-4B` 做了两条 LoRA 微调：

- `router_lora`
  - 目标：提升意图识别、工具路由、参数构造、上下文记忆顺序
- `spot_lora`
  - 目标：提升景点介绍、推荐表达、旅游助手式回答组织

同时明确区分了不适合当前阶段做 LoRA 的模块：

- `weather_agent`
  - 主要依赖实时天气 API，不适合把能力固化到模型参数里
- `plan_agent`
  - 当前主要依赖工具调用与规则化输出，现阶段优先级低于 `router` 和 `spot`

## 2. 训练设置

### `router_lora`

- 基座模型：`Qwen3.5-4B`
- 数据集：`router_tool_calling`
- 训练方式：LoRA SFT
- 关键参数：
  - `lora_rank = 8`
  - `lora_alpha = 16`
  - `lora_dropout = 0.05`
  - `lora_target = all`
  - `learning_rate = 5e-5`
- checkpoint 选择：
  - 根据 `eval_loss` 下降趋势，最终选用 `checkpoint-60`

### `spot_lora`

- 基座模型：`Qwen3.5-4B`
- 数据集：`spot_cultour`
- 训练方式：LoRA SFT
- 关键参数：
  - `lora_rank = 8`
  - `lora_alpha = 16`
  - `lora_dropout = 0.05`
  - `lora_target = all`
  - `learning_rate = 3e-5`
- checkpoint 选择：
  - `eval_loss` 持续下降，最终采用 `final / checkpoint-523`

## 3. `lora_target=all` 的实际含义

这里的 `all` 不是“整个模型所有参数都训练”，而是：

- 冻结原始模型参数
- 仅对可匹配到的主要线性层挂 LoRA 适配器

在这次 `Qwen3.5-4B` 上，实际命中的模块主要包括：

### Attention 相关层

- `q_proj`
- `k_proj`
- `v_proj`
- `o_proj`
- `qkv`
- `out_proj`
- `attn.proj`
- `in_proj_qkv`

### MLP / FFN 相关层

- `gate_proj`
- `up_proj`
- `down_proj`
- `linear_fc1`
- `linear_fc2`

### 其他实现相关投影层

- `in_proj_a`
- `in_proj_b`
- `in_proj_z`

没有作为 LoRA 主体训练的部分包括：

- `embedding`
- `norm`
- `lm_head`
- 大多数 `bias`

因此它仍然是参数高效微调，而不是全参数微调。

## 4. 评测方案

本项目没有只看 `train loss`，而是采用了“训练收敛 + benchmark 对比”两层验证。

### `router_lora` 评测

- 数据集类型：项目内 held-out router benchmark
- 样本数：`34`
- 核心指标：
  - `Tool-name accuracy`
  - `Argument exact match`
  - `Turn exact match`
  - `Decision tool-name accuracy`
  - `Sample full-chain success`

该 benchmark 主要考察：

- 是否先 `get_context`
- 是否把请求正确转给 `weather_agent / spot_agent / plan_agent`
- 是否正确补 `save_context`
- 是否按多智能体总控逻辑完成整条调用链

### `spot_lora` 评测

采用了两套 benchmark：

#### 1. 公开 benchmark：CrossWOZ

- 样本数：`150`
- 五类各 `30` 条：
  - `名称`
  - `地址`
  - `游玩时间`
  - `评分`
  - `门票`

核心指标：

- `Strict success`
  - 一条样本中所有要求命中的关键事实是否全部命中
- `Fact coverage`
  - 一条样本中关键事实命中的比例
- `ROUGE-L F1`
  - 回答文本与参考答案的文本相似度

#### 2. 项目内 benchmark：spot internal

- 样本数：`80`
- 分类：
  - `城市+景点`
  - `精确景点`
  - `Kaggle`
  - `手写`

该 benchmark 更贴近项目真实需求，重点考察：

- 景点名是否答对
- 景点亮点是否覆盖
- 游玩时长是否回答正确
- 是否更像真实旅游助手回答

## 5. 评测结果

### `router_lora` vs Base

| 指标 | Base | Router LoRA | 结论 |
|---|---:|---:|---|
| Tool-name accuracy | 51.19% | 100.00% | 显著提升 |
| Argument exact match | 19.57% | 89.13% | 显著提升 |
| Turn exact match | 48.81% | 94.05% | 显著提升 |
| Decision tool-name accuracy | 19.57% | 100.00% | 显著提升 |
| Sample full-chain success | 20.59% | 85.29% | 显著提升 |

结论：

- `router_lora` 明确成功
- 它显著提升了多智能体系统中的：
  - 意图识别
  - 子 agent 路由
  - 参数构造
  - 整条工具调用链稳定性

### `spot_lora` vs Base：公开 CrossWOZ

| 指标 | Base | Spot LoRA | 结论 |
|---|---:|---:|---|
| Strict success | 98.00% | 90.67% | 下降 |
| Fact coverage | 99.00% | 94.33% | 下降 |
| ROUGE-L F1 | 2.66% | 27.36% | 显著上升 |

结论：

- 在偏“事实抽取”的公开 benchmark 上，`spot_lora` 不如 base
- 但 `ROUGE-L F1` 大幅上升，说明回答风格更接近旅游助手式参考答案

### `spot_lora` vs Base：项目内 internal benchmark

| 指标 | Base | Spot LoRA | 结论 |
|---|---:|---:|---|
| Strict success | 60.00% | 40.00% | 下降 |
| Fact coverage | 78.33% | 73.75% | 下降 |
| ROUGE-L F1 | 5.96% | 48.33% | 显著上升 |

进一步拆分可见：

- `highlight`
  - `66.23% -> 80.52%`
  - 提升
- `duration`
  - `57.69% -> 23.08%`
  - 明显下降

结论：

- `spot_lora` 的主要收益在“表达风格和回答组织”
- 并没有提升严格事实命中
- 尤其在“游玩时长”这类精确事实槽位上更弱

## 6. 最终实验结论

### `router_lora`

这是本项目最明确成功的一条线。

可以直接下结论：

- LoRA 对结构化 router 任务非常有效
- 它显著提升了：
  - 路由准确率
  - 参数匹配率
  - 全链路成功率

### `spot_lora`

这是“有 trade-off”的一条线。

可以更准确地说：

- 它让模型更像旅游助手、更像参考答案的表达风格
- 但没有提升严格事实问答能力
- 因此它更像“风格对齐 / 回答组织优化”
- 而不是“通用事实抽取增强”

## 7. 为什么会出现这种结果

### 为什么 `router_lora` 提升很大

因为 `router` 任务本身高度结构化：

- 用户意图有限
- 工具集合固定
- 输出格式明确
- benchmark 和训练目标高度一致

所以 LoRA 很容易在这个任务上学到稳定行为。

### 为什么 `spot_lora` 没有提升事实指标

因为这版 `spot_lora` 学到的更偏：

- 景点介绍
- 推荐表达
- 旅游话术
- 回答组织

而 benchmark 更看重：

- 景点名
- 时长
- 预算
- 评分
- 地址

也就是严格事实槽位是否命中。

所以它更像是“生成风格更好了”，但“事实抽取更严格”这件事没有变强。

## 8. 面试时最推荐的总结说法

可以直接这样说：

> 我的项目不是简单做一个通用 LoRA，而是把任务拆成 router 和 spot 两类。  
> router LoRA 结果最明确，在项目内 tool-calling benchmark 上，`decision tool-name accuracy` 从 `19.57%` 提升到 `100%`，`sample full-chain success` 从 `20.59%` 提升到 `85.29%`，说明它显著提升了多智能体路由和参数构造能力。  
> spot LoRA 的结果更有取舍：在公开 CrossWOZ 和项目内景点问答 benchmark 上，它的严格事实指标低于基座模型，但 `ROUGE-L` 显著更高，说明它更偏旅游助手式表达和回答组织，而不是通用事实抽取增强。

## 9. 当前最稳的项目结论

- `router_lora`：成功，值得保留
- `spot_lora`：存在 trade-off，可作为“风格优化”实验结论
- `weather_agent`：不需要做 LoRA
- `plan_agent`：当前阶段不优先做 LoRA

## 10. 面试时如果被追问

### “LoRA 到底有没有用？”

最稳回答：

> 有用，但要看任务。  
> 在 router 这种结构化、工具驱动任务上，LoRA 的收益非常明显；在 spot 这种开放式生成任务上，LoRA 更容易带来风格对齐收益，但不一定提升严格事实指标。

### “为什么你还保留 spot 这条实验？”

最稳回答：

> 因为它提供了一个真实的实验结论：LoRA 不一定在所有 benchmark 上都提升分数，但它可能改变模型优化方向。我的 spot LoRA 更偏旅游话术和回答组织，而不是精确事实抽取，这说明 benchmark 和训练目标必须匹配。
