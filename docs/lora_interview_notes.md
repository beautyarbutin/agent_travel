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
