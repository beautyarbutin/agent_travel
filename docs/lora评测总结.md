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

## 6. Badcase 分析

### `router_lora` 的 badcase

`router` 这条线最适合做 badcase 分析，因为它的评测是逐 turn、逐工具、逐参数比较，错误类型非常清楚。

#### 6.1 Base 的 badcase

先看基座模型的坏例子分布。

- turn 级总 miss：`43`
- 主要错在三类期望工具：
  - `send_direct_message`：`21`
  - `save_context`：`16`
  - `get_context`：`6`

最常见的错误映射是：

- `save_context -> get_context`：`6`
- `send_direct_message -> save_context`：`6`
- `send_direct_message -> get_weather`：`5`
- `send_direct_message -> search_spots`：`5`
- `send_direct_message -> get_driving_route`：`3`
- `save_context -> reply_channel_message`：`3`
- `save_context -> send_channel_message`：`3`

代表性坏例子：

1. 该转发给 `weather_agent`，却直接调用底层天气工具
   - 期望：
     - `send_direct_message(target_agent_id="weather_agent", text="帮我看下苏州今天冷不冷")`
   - 实际：
     - `get_weather(city="苏州")`

2. 该补记忆，结果又去读记忆
   - 期望：
     - `save_context(current_city="成都")`
   - 实际：
     - `get_context()`

3. 第一轮本该先读上下文，结果一上来就猜城市并直接调工具
   - 期望：
     - `get_context()`
   - 实际：
     - `get_weather(city="昆明")`

#### 6.2 Base 的共性错误

基座模型的错误很有代表性，说明它没有真正学会“多智能体总控”的行为约束。

- 它经常绕过 router 设计，直接调用底层业务工具
- 它知道“用户在问天气/景点/路线”，但不知道“应该先转给哪个子 agent”
- 它对记忆读写顺序理解不稳，容易把 `save_context` 和 `get_context` 混掉

也就是说，base 更像一个“会用工具的单体助手”，而不是“按规则调度多个 agent 的总控”。

#### 6.3 `router_lora` 的 badcase

`router_lora` 的 badcase 很集中，说明模型主体行为已经学对了，剩下的问题不是“路由到错 agent”，而是“上下文字段提取不完整”。

- turn 级总 miss：`5`
- 5 个 miss 全部来自：
  - `save_context -> save_context`
- 也就是说：
  - 工具名已经对了
  - 错误只发生在参数不完整

代表性坏例子：

1. 少存 `travel_party`
   - 期望：
     - `current_city = 西安`
     - `travel_party = 带父母`
   - 实际：
     - `current_city = 西安`

2. 把 `notes` 错替成默认化的人数信息
   - 期望：
     - `current_city = 上海`
     - `notes = 两日游`
   - 实际：
     - `current_city = 上海`
     - `travel_party = 2人`

3. 多字段场景下只保留“最显眼字段”
   - 期望：
     - `current_city = 重庆`
     - `travel_party = 和朋友`
     - `notes = 三天行程`
   - 实际：
     - `current_city = 重庆`
     - `travel_party = 和朋友`

#### 6.4 `router_lora` 的共性原因

- `router_lora` 已经学会了：
  - 先 `get_context`
  - 再转给正确子 agent
  - 工具名选对
- 但对 `save_context` 这种“多槽位联合抽取”工具，还会优先保留最核心字段
- 所以它更像是：
  - “路由正确”
  - 但“记忆补全不完全”

#### 6.5 你在答辩时怎么说

> `router_lora` 的 badcase 并不是路由错了，而主要是 `save_context` 字段抽取不完整。也就是说，它已经能判断该转给哪个子 agent，但在补记忆时偶尔会漏掉 `travel_party` 或 `notes` 这类次级槽位。相对地，base 的核心问题是根本没有学会多智能体总控逻辑，经常直接绕过 router 去调用底层工具。

### `spot_lora` 的 badcase

`spot_lora` 的 badcase 要分成两类看：

- 公开 `CrossWOZ`
- 项目内 `spot internal`

因为两套 benchmark 的关注点不完全一样。

#### A. 公开 `CrossWOZ` 上的 badcase

先看公开 benchmark 的坏例子分布。

- 总 miss：`33`
- 按类别分布：
  - `CrossWOZ-游玩时间`：`17`
  - `CrossWOZ-门票`：`9`
  - `CrossWOZ-评分`：`6`
  - `CrossWOZ-地址`：`1`

按缺失事实类型分布：

- 只缺 `duration`：`18`
- 只缺 `budget`：`9`
- 只缺 `spot_name`：`6`

##### 最常见错误类型

1. `duration` 错误最多
   - 这是最主要的 badcase 来源
   - 常见现象：
     - 回答了时长
     - 但答错了具体数值
     - 或者答成了不在 gold 候选里的时间

2. `budget` / `门票` 错误次之
   - 有时没有明确答门票
   - 有时把门票说成泛化描述，没落到正确数值

3. 少量 `spot_name` 错误
   - 个别样本会出现景点名未精确命中

##### 典型 badcase 现象

- 用户问：
  - `游玩时间是多久`
- 模型回答：
  - 先展开一大段景点介绍
  - 甚至补了电话、地址、推荐语
  - 但核心的 `duration` 没答准

还有一种情况：

- 用户同时问：
  - `地址在哪`
  - `可以玩多久`
- 模型把地址答对了
- 但时长答错了
- 于是 `strict success` 仍然算失败

更具体的公开 badcase 例子：

1. `duration` 被答成错误数值
   - 问：
     - `北京古代建筑博物馆游玩多长时间好呢？`
   - 模型答：
     - `0.3小时到0.5小时`
   - 现象：
     - 看起来像一个完整回答
     - 但严格 fact 命中失败

2. 把“游玩时间”答成了“营业时间”
   - 问：
     - `中国儿童中心剧院的游玩时间是多久？`
   - 模型答：
     - 营业时间相关信息
   - 现象：
     - 说明模型抓住了“时间”这个话题
     - 但没抓住“游玩时长”这个槽位

3. 回答非常像旅游助手，但没命中 gold 槽位
   - 问：
     - `宋庆龄故居能玩多久，周边还有其他景点吗？`
   - 模型答：
     - 时长 + 周边景点一大段介绍
   - 现象：
     - 文风更自然
     - 但严格匹配时仍然判错

##### 普遍原因

- `spot_lora` 更偏旅游助手式表达
- 它喜欢：
  - 展开介绍
  - 加描述性语言
  - 做推荐式回答
- 但 `CrossWOZ` 这一套更像“严格事实抽取”
- 所以它在：
  - `duration`
  - `budget`
  - `rating`
  这类槽位上不如 base 稳

#### B. 项目内 `spot internal` 上的 badcase

##### 最关键现象

分项已经很清楚：

- `highlight`
  - `66.23% -> 80.52%`
  - 变好了
- `duration`
  - `57.69% -> 23.08%`
  - 明显变差
- `spot_name`
  - 略降
- `budget`
  - 样本很少，但没有命中

按类别看，内部 benchmark 上下降最明显的是：

- `精确景点`
  - `45.16% -> 29.03%`
- `城市+景点`
  - `74.29% -> 42.86%`

这两类正好是你项目里最常见的真实问法。

##### 普遍原因

1. 更会说“亮点”，但不爱先答“硬事实”
   - 它会回答：
     - 适合拍照
     - 历史气息浓厚
     - 适合亲子
   - 但未必先把：
     - 游玩时长
     - 预算
     - 地址
     这种硬信息答清楚

2. 更像旅游助手，但更不“槽位化”
   - 参考答案风格更像它
   - 所以 `ROUGE-L` 大幅上升
   - 但严格 fact 命中下降

3. 越开放的问题越容易往“介绍型回答”漂
   - 尤其在：
     - `精确景点`
     - `城市+景点`
   这种场景里，模型容易把重点放到描述，而不是精确事实抽取

可以把内部 benchmark 的共性理解成：

- `spot_lora` 更擅长回答：
  - 为什么值得去
  - 有什么特色
  - 适合谁去
- 但更不擅长回答：
  - 能玩多久
  - 多少钱
  - 具体数值是多少

#### 你在答辩时怎么说

> `spot_lora` 的 badcase 主要不是完全答错景点，而是更偏描述性、推荐式回答，导致 `duration`、`budget`、`rating` 这类严格事实槽位命中率下降。公开 CrossWOZ 上最典型的是“把游玩时间答错或答成营业时间”，内部 benchmark 上最典型的是“亮点讲得更好了，但时长这类硬事实答得更差了”。换句话说，它更像旅游助手了，但更不像一个严格的事实抽取器。

## 7. 最终实验结论

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

## 8. 为什么会出现这种结果

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

## 9. 面试时最推荐的总结说法

可以直接这样说：

> 我的项目不是简单做一个通用 LoRA，而是把任务拆成 router 和 spot 两类。  
> router LoRA 结果最明确，在项目内 tool-calling benchmark 上，`decision tool-name accuracy` 从 `19.57%` 提升到 `100%`，`sample full-chain success` 从 `20.59%` 提升到 `85.29%`，说明它显著提升了多智能体路由和参数构造能力。  
> spot LoRA 的结果更有取舍：在公开 CrossWOZ 和项目内景点问答 benchmark 上，它的严格事实指标低于基座模型，但 `ROUGE-L` 显著更高，说明它更偏旅游助手式表达和回答组织，而不是通用事实抽取增强。

## 10. 当前最稳的项目结论

- `router_lora`：成功，值得保留
- `spot_lora`：存在 trade-off，可作为“风格优化”实验结论
- `weather_agent`：不需要做 LoRA
- `plan_agent`：当前阶段不优先做 LoRA

## 11. 面试时如果被追问

### “LoRA 到底有没有用？”

最稳回答：

> 有用，但要看任务。  
> 在 router 这种结构化、工具驱动任务上，LoRA 的收益非常明显；在 spot 这种开放式生成任务上，LoRA 更容易带来风格对齐收益，但不一定提升严格事实指标。

### “为什么你还保留 spot 这条实验？”

最稳回答：

> 因为它提供了一个真实的实验结论：LoRA 不一定在所有 benchmark 上都提升分数，但它可能改变模型优化方向。我的 spot LoRA 更偏旅游话术和回答组织，而不是精确事实抽取，这说明 benchmark 和训练目标必须匹配。
