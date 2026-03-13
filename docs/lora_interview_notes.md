# LoRA 面试整理

日期：2026-03-13

## 1. LoRA 是什么

LoRA（Low-Rank Adaptation）是一种参数高效微调方法。

核心思想：

- 冻结原始大模型参数
- 不直接更新原权重矩阵
- 只训练一个低秩增量

原始线性层权重记为：

```text
W ∈ R^(d_out × d_in)
```

LoRA 微调后：

```text
W' = W + ΔW
```

其中：

```text
ΔW = B A
```

维度通常设为：

```text
A ∈ R^(r × d_in)
B ∈ R^(d_out × r)
```

如果带缩放项，常写成：

```text
W' = W + (α / r) B A
```

这就是 LoRA 最核心的公式。

## 2. 为什么 LoRA 省参数

全参数微调要训练：

```text
d_out × d_in
```

LoRA 只训练：

```text
r × d_in + d_out × r = r(d_in + d_out)
```

当 `r` 很小时，训练参数量和优化器状态都显著下降，所以：

- 更省显存
- 更省存储
- 训练更快

## 3. LoRA 的核心假设

LoRA 的核心假设是：

- 下游任务需要的权重更新不一定是高自由度的
- 很多有效更新可以落在一个低维子空间中
- 因此可以用低秩矩阵近似完整的权重更新

这就是“低秩更新假设”。

## 4. LoRA 训练时到底更新什么

标准 LoRA 做法：

- 冻结 base model 参数 `W`
- 只训练 `A` 和 `B`
- 前向时使用 `W + (α / r)BA`
- 反向传播时只更新 LoRA 参数

常见初始化：

- `A` 随机初始化
- `B = 0`

这样初始时：

```text
ΔW = B A = 0
```

模型一开始和原模型行为一致，更稳定。

## 5. 面试最常问的 LoRA 参数

### 5.1 rank / r

LoRA 的秩，决定低秩空间大小。

含义：

- `r` 越大，表达能力越强
- 但参数更多、显存更高、过拟合风险更高

常见值：

- `4`
- `8`
- `16`
- `32`

项目里如果数据量不大，`r=8` 往往是很稳的起点。

### 5.2 lora_alpha / alpha

LoRA 更新项的缩放系数。

在公式里：

```text
W' = W + (α / r) B A
```

直观理解：

- `rank` 决定容量
- `alpha` 决定更新强度

常见经验：

```text
alpha ≈ 2r
```

例如：

- `r=8`
- `alpha=16`

### 5.3 lora_dropout

LoRA 分支上的 dropout，用于正则化。

作用：

- 降低过拟合
- 让小数据微调更稳

常见值：

- `0`
- `0.05`
- `0.1`

### 5.4 target_modules / lora_target

LoRA 要挂到哪些层上。

常见目标模块：

- `q_proj`
- `k_proj`
- `v_proj`
- `o_proj`
- MLP 中的线性层
- 或者直接 `all`

为什么常挂 attention 投影层：

- 对模型行为影响大
- 参数开销相对可控

### 5.5 learning_rate

LoRA 的学习率通常会比全参数微调大一些，但不能太激进。

常见范围：

- `1e-4`
- `5e-5`
- `3e-5`

经验：

- 工具调用、模板化任务：可以稍高
- 开放式生成任务：更保守一些

### 5.6 num_train_epochs

训练轮数。

LoRA 也会过拟合，尤其是：

- 数据量小
- 样本高度模板化
- 输出格式固定

因此不能只看 `train loss`，必须看：

- `eval_loss`
- 真实样例表现

### 5.7 batch size 和 gradient accumulation

有效 batch 常用公式：

```text
effective_batch_size = per_device_batch_size × gradient_accumulation_steps × GPU数
```

面试时常会问你如何估算训练步数和训练稳定性，这个公式很常用。

### 5.8 warmup_steps

学习率预热步数。

作用：

- 防止训练初期更新过猛
- 让训练曲线更稳

### 5.9 bf16 / fp16

混合精度训练选项。

作用：

- 降显存占用
- 加快训练

## 6. LoRA 推理怎么用

LoRA 推理有两种主流方式。

### 6.1 运行时挂 adapter

形式：

```text
base model + LoRA adapter
```

优点：

- 灵活
- 多个任务可共用一个基座模型

缺点：

- 部署和切换链路更复杂

### 6.2 merge 后推理

把 LoRA 合并回原始权重：

```text
W_merge = W + (α / r) B A
```

优点：

- 推理时像普通模型一样使用
- 更适合 GGUF / 本地部署

缺点：

- 每个 adapter 常常都要单独导出一份模型

## 7. LoRA 和 QLoRA 的区别

### LoRA

- 基座模型正常精度加载
- 只训练 LoRA 参数

### QLoRA

- 基座模型先量化到 4bit
- 仍然只训练 LoRA 参数
- 显存需求更低

一句话：

```text
QLoRA = 量化基座模型后的 LoRA
```

## 8. LoRA 的优缺点

### 优点

- 显存占用小
- 训练快
- 适合小样本定向微调
- 便于一个基座对应多个任务 adapter
- 保存和分发成本低

### 缺点

- 能力上限通常不如高质量全参数微调
- 更容易学到“风格”而不是“新知识”
- 小数据下很容易过拟合
- 部署时可能面临 adapter / merge / 量化链路问题

## 9. 结合本项目怎么答最合适

这个项目最适合把 LoRA 用在：

- `travel_router`
- `spot_agent`

不太适合现在就做 LoRA 的：

- `weather_agent`
- `plan_agent` 的纯路线查询部分

原因：

### weather_agent

天气是强实时信息，核心依赖 API。

模型主要负责：

- 识别天气意图
- 抽城市
- 调工具
- 整理返回格式

这更适合靠：

- prompt
- tool schema
- few-shot

而不是靠 LoRA 固化能力。

### plan_agent

如果只是：

- 两地路线
- 驾车时长
- 路径查询

这本质上也是工具型任务，LoRA 收益不大。

如果以后要做的是：

- 多日游规划
- 多约束行程安排
- 稳定结构化输出

那时再考虑 `plan_lora` 更合理。

## 10. 项目里的参数案例

### router LoRA

项目里 router 方向采用了：

- `r = 8`
- `alpha = 16`
- `dropout = 0.05`
- `lr = 5e-5`

原因：

- 数据量不大
- 样本偏工具调用和模板化
- 需要较稳定地学习路由和参数构造

最终通过 `eval_loss` 选择中间 checkpoint，而不是 final。

### spot LoRA

项目里 spot 方向采用了：

- `r = 8`
- `alpha = 16`
- `dropout = 0.05`
- `lr = 3e-5`

原因：

- `spot` 是开放式生成任务
- 比 router 更容易出现文风漂移
- 所以学习率更保守

最终 `eval_loss` 持续下降，因此用 final checkpoint。

## 11. 面试高频问题速答

### 问：LoRA 的核心公式是什么？

答：

```text
W' = W + (α / r) B A
```

其中 `W` 冻结，`A` 和 `B` 是可训练的低秩矩阵。

### 问：为什么 LoRA 比全参数微调省显存？

答：

因为全参数微调训练的是整个权重矩阵，而 LoRA 只训练低秩增量矩阵，参数量从：

```text
d_out × d_in
```

降到：

```text
r(d_out + d_in)
```

所以显存和优化器状态都显著减少。

### 问：rank 越大越好吗？

答：

不是。`rank` 越大，表达能力越强，但参数更多、显存更高、也更容易过拟合。要在表达能力和稳定性之间平衡。

### 问：alpha 是做什么的？

答：

`alpha` 是 LoRA 更新项的缩放系数，用来控制低秩增量注入原模型的强度。

### 问：LoRA 为什么适合你的项目？

答：

因为这个项目的核心不是重塑整个模型，而是对不同 agent 做任务定向微调：

- router 学路由和参数构造
- spot 学景点介绍和推荐表达

这类“行为定向”任务非常适合 LoRA。

### 问：为什么你没给 weather 做 LoRA？

答：

天气依赖实时 API，模型不应该记忆天气事实。weather agent 更重要的是意图识别、参数抽取和调用工具，这些问题用 prompt 和工具约束更划算。

### 问：为什么你现在也没急着给 plan 做 LoRA？

答：

因为当前 plan 里的“路线查询”主要是工具型任务，收益不如先把工具调用和模板做好。只有等到以后要做高质量多日游规划时，LoRA 的价值才会更明显。

## 12. 面试速记版

最后只记这 6 句也够用：

1. `LoRA 冻结原模型，只学习低秩增量。`
2. `核心公式是 W' = W + (α/r)BA。`
3. `参数量从 d_out*d_in 降到 r(d_out+d_in)。`
4. `rank 控制容量，alpha 控制更新强度，dropout 控制正则化。`
5. `LoRA 适合任务定向微调，不适合替代实时工具和最新知识。`
6. `在我的项目里 router 和 spot 适合 LoRA，weather 不适合，plan 现阶段也不急。`

## 13. 面试追问版：rank、alpha 和 target_module

这一节是老师最容易继续往下追问的地方。

### 13.1 为什么 rank 常见是 8、16？

`rank` 不只是影响显存，它也直接影响 LoRA 更新的表达能力。

可以把 LoRA 理解成给原模型贴一个“小补丁”：

- `rank` 小：补丁更薄，更省显存，但容量更小
- `rank` 大：补丁更厚，能学到更复杂的变化，但参数更多，也更容易过拟合

所以 `rank=8`、`rank=16` 常见，不是因为这两个数字神秘，而是因为它们通常是：

- 表达能力
- 显存成本
- 训练稳定性

之间比较均衡的折中。

实际经验上：

- `4 -> 8` 有时提升比较明显
- `8 -> 16` 可能还有提升，但不一定大
- `16 -> 32` 往往开始收益递减

一句话面试回答：

> rank 决定 LoRA 低秩更新的容量，不只是影响显存，也会影响模型能学到多复杂的任务变化。8 和 16 是工程上常见的折中值。

### 13.2 为什么 alpha 常常设成 rank 的两倍？

LoRA 常见公式是：

```text
W' = W + (alpha / r)BA
```

真正控制 LoRA 更新强度的，关键不只是 `alpha`，而是：

```text
alpha / r
```

所以很多人喜欢设：

- `r=8, alpha=16`
- `r=16, alpha=32`

这样做的直觉是：

- 当你改动 `rank` 时，更新强度不会乱掉太多
- 因为 `alpha / r` 保持在一个相对稳定的比例

你这次项目里：

```text
r = 8
alpha = 16
alpha / r = 2
```

这就是很常见的经验设定。

重点要会说：

> `alpha = 2r` 不是数学定理，只是常见经验值。它的目的，是让 `alpha / r` 落在一个比较稳的范围里。

### 13.3 target_module 到底是什么？

`target_module` 指的是：

> LoRA 要挂到模型的哪些层上。

LoRA 不是给整个模型所有参数都加补丁，而是只给一部分关键线性层加低秩更新。

常见目标层包括：

- 注意力相关层：`q_proj`、`k_proj`、`v_proj`、`o_proj`
- 前馈网络层：`up_proj`、`down_proj`、`gate_proj`
- 或者直接用 `all`

### 13.4 q / k / v / o 分别起什么作用？

可以用特别白话的话记：

- `q`：我现在想找什么
- `k`：我这里有什么可被匹配
- `v`：真正被取出来传过去的内容
- `o`：把多个注意力头的结果整合回主干

更接近技术表达的理解：

- `q_proj`：更影响模型“关注哪里”
- `k_proj`：更影响匹配关系
- `v_proj`：更影响传递出来的内容
- `o_proj`：更影响注意力结果如何重新投影回隐藏状态

所以：

- 只改 `q`：更偏改变注意力方向
- 改 `q + v`：是很常见的轻量方案
- 改 `q + k + v + o`：更全面，但也更重

### 13.5 只加 qv 和加 qkvo 有什么区别？

可以这么理解：

- `qv`：够轻量，常常已经能明显改变模型行为
- `qkvo`：改得更全面，表达更强，但参数也更多

很多时候：

- 工具调用
- 指令遵循
- 路由行为

用 attention 相关层就已经很有效。

如果任务更偏：

- 内容生成
- 领域表达
- 风格迁移

那 FFN/MLP 层也常常很重要。

### 13.6 为什么有人说“知识更多在 FFN”？

这是一种很常见的经验说法，不是严格定理。

直觉上：

- 注意力层更像在做“信息交互、对齐、检索”
- FFN/MLP 更像在做“非线性变换、模式加工、知识表达”

所以：

- 如果你想改行为、改工具调用方式，attention 层常常很关键
- 如果你想做知识注入、领域表达、风格生成，FFN/MLP 层也很重要

## 14. 你这个项目里的两个 LoRA，实际打到了哪些层

这部分不是概念，而是你本地配置文件里的真实结果。

我查看了：

- [router adapter_config.json](/D:/20251224/AI_Study/OpenAgents/models/router_lora_2026-03-12/adapter_config.json)
- [spot adapter_config.json](/D:/20251224/AI_Study/OpenAgents/models/spot_lora_2026-03-12/adapter_config.json)

你的两个 LoRA 都是：

- `r = 8`
- `alpha = 16`
- `dropout = 0.05`
- `lora_target = all`

这意味着它们并不是只打在 `qkvo` 上，而是挂到了模型里大多数关键线性层。

### 14.1 router LoRA 实际 target_modules

包括：

- 注意力相关：
  - `q_proj`
  - `k_proj`
  - `v_proj`
  - `o_proj`
  - `qkv`
  - `out_proj`
  - `attn.proj`
- FFN / MLP 相关：
  - `gate_proj`
  - `up_proj`
  - `down_proj`
  - `linear_fc1`
  - `linear_fc2`
- Qwen3.5 模型特有的一些投影层：
  - `in_proj_a`
  - `in_proj_b`
  - `in_proj_qkv`
  - `in_proj_z`

### 14.2 spot LoRA 实际 target_modules

spot LoRA 的模块集合和 router 非常接近，也覆盖了：

- 注意力相关层
- FFN / MLP 相关层
- Qwen3.5 特有的一些 `in_proj_*` 结构

这也说明你这两个 LoRA 都不是“只改一点点 qv”，而是使用了比较全面的 `all` 策略。

### 14.3 这对你的两个任务意味着什么

#### router LoRA

router 的目标是：

- 意图识别
- 工具路由
- 参数构造

这更偏“行为变化”，所以 attention 相关层非常重要；而 `all` 又让它连 FFN 一起调，适配会更全面。

#### spot LoRA

spot 的目标是：

- 景点介绍
- 推荐表达
- 内容组织

这比 router 更偏内容生成，所以同时覆盖 attention 和 FFN/MLP 是合理的。

一句话可以这样答：

> 我的两个 LoRA 都不是只挂在 qkvo 上，而是用了 `lora_target=all`，因此实际覆盖了 attention 投影层、FFN/MLP 层，以及 Qwen3.5 的一些模型特有投影层。

## 15. train loss 和 eval loss 的区别

这个问题面试也很容易问，而且你项目里正好真做过。

### 15.1 train loss 是什么

`train loss` 就是：

> 模型在训练集上的错误程度。

训练时模型看的是“已经拿来学习的数据”，所以：

- `train loss` 下降
- 说明模型越来越会做训练里见过的题

### 15.2 eval loss 是什么

`eval loss` 就是：

> 模型在验证集上的错误程度。

验证集不参与训练，只拿来考模型，所以它更接近“模型对新样本的泛化能力”。

### 15.3 为什么不能只看 train loss

因为模型可能只是把训练集背下来了。

典型过拟合现象：

- `train loss` 继续下降
- `eval loss` 不再下降，甚至升高

这就说明：

- 模型越来越会做训练题
- 但不一定越来越会做新题

### 15.4 结合你自己的项目怎么说

你的项目里：

- `router_lora` 最终不是选 final，而是根据 `eval_loss` 选了更优 checkpoint
- `spot_lora` 则是因为 `eval_loss` 持续下降，所以最终选了 final

这正好说明你不是只看训练曲线，而是在用验证集做 checkpoint 选择。

## 16. function-calling 和 tool-calling 是什么

这两个词在你的项目里非常重要。

### 16.1 最白话的理解

它们的核心意思是：

> 模型不只是直接说话，而是先决定调用哪个函数/工具，再根据工具返回结果继续回答。

比如用户问：

`帮我查一下衡水天气`

模型不应该直接瞎编天气，而应该先决定：

```json
{
  "name": "get_weather",
  "arguments": {
    "city": "衡水"
  }
}
```

这就是 function-calling / tool-calling。

### 16.2 两个词的区别

- `function-calling`：更偏“函数调用”这个说法
- `tool-calling`：更偏“工具调用”这个说法

在你的项目里，它们基本可以理解成一回事。

### 16.3 你项目里的 function-calling 是什么

你的旅游助手里会调用这些能力：

- 天气查询
- 景点检索
- 驾车路线
- 本地知识库查询
- 读取上下文记忆
- 保存上下文记忆
- 转发给子 Agent

所以你简历里写 `Function Calling` 是说得通的。

更准确一点也可以说：

> 基于 Tool Calling / Function Calling 的多工具调度与参数构造。

### 16.4 router 为什么特别像 function-calling 任务

因为 router 的核心不是“生成很漂亮的自然语言”，而是：

- 识别用户意图
- 决定调用哪个工具或子 Agent
- 正确构造参数
- 必要时读写上下文

这本质上就是函数调用链路学习。

## 17. 你可以直接背的几句面试话术

### 17.1 关于 rank

> rank 不只是影响显存，也决定 LoRA 更新的容量。太小可能学不够，太大又容易增加成本和过拟合，所以 8 和 16 是工程上比较常见的折中值。

### 17.2 关于 alpha

> alpha 控制 LoRA 更新的缩放强度，真正关键的是 `alpha / rank` 这个比例。把 alpha 设成 rank 的两倍是一种常见经验做法，不是理论硬规定。

### 17.3 关于 target_module

> target_module 表示 LoRA 挂到哪些层上。attention 投影层更偏行为和信息交互，FFN/MLP 层更偏内容加工和知识表达。不同任务适合的挂法不一样。

### 17.4 关于你自己的 LoRA

> 我这两个 LoRA 不是只改 qkvo，而是使用了 `lora_target=all`，实际覆盖了 attention、FFN/MLP 以及 Qwen3.5 模型特有的一些投影层。router 更偏行为定向，spot 更偏内容生成。

### 17.5 关于 train/eval loss

> train loss 反映模型对训练集的拟合程度，eval loss 更能反映泛化能力。我的 router 和 spot 两个 LoRA 都是结合 eval loss 来做 checkpoint 判断，而不是只看 train loss。
