# Transformer / LLM 复试面试笔记

日期：2026-03-13

## 1. 一句话先讲清楚 Transformer

Transformer 是一种基于 `self-attention` 的序列建模架构。

它的核心目标是：

- 摆脱 RNN/LSTM 的串行计算
- 更容易并行训练
- 更好地建模长距离依赖

面试里最标准的一句话：

```text
Transformer 用 self-attention 替代循环结构，让序列中任意位置都能直接交互。
```

## 2. 为什么 Transformer 会替代 RNN/LSTM

RNN/LSTM 的主要问题有两个：

- 训练是串行的，难以充分并行
- 长距离依赖传播路径长，容易遗忘早期信息

Transformer 的改进点是：

- 所有 token 可以同时参与计算
- 任意两个位置之间都能直接建立联系

所以它更适合大规模预训练，也更适合扩展成大模型。

## 3. Transformer 的整体结构

原始 Transformer 是 `Encoder-Decoder` 架构。

### 3.1 Encoder

每层 Encoder 包括：

1. Multi-Head Self-Attention
2. Add & Norm
3. Feed Forward Network
4. Add & Norm

### 3.2 Decoder

每层 Decoder 包括：

1. Masked Multi-Head Self-Attention
2. Add & Norm
3. Cross-Attention
4. Add & Norm
5. Feed Forward Network
6. Add & Norm

这里要记住三点：

- Encoder 的 self-attention 可以看全局
- Decoder 的 self-attention 不能看未来 token
- Cross-Attention 是 decoder 去读取 encoder 的输出

## 4. 输入是怎么进入 Transformer 的

输入首先会被转换成词向量，也就是 `Embedding`。

然后再加入位置信息，因为 attention 本身不包含顺序概念。

通常可以写成：

```text
Input = Token Embedding + Positional Encoding
```

如果没有位置编码，模型就只知道有哪些词，不知道谁在前、谁在后。

## 5. Self-Attention 是最核心的知识点

这是面试最常问的部分。

给定输入矩阵 `X`，先通过三组线性映射得到：

```text
Q = XW_Q
K = XW_K
V = XW_V
```

然后计算注意力：

```text
Attention(Q, K, V) = softmax(QK^T / sqrt(d_k)) V
```

### 5.1 Q、K、V 分别代表什么

- `Q`：当前 token 想查询什么信息
- `K`：每个 token 提供什么匹配线索
- `V`：真正要被取出的内容

直观理解：

- `Q` 和 `K` 决定“该关注谁”
- `V` 决定“关注后拿走什么信息”

### 5.2 为什么要除以 `sqrt(d_k)`

如果维度 `d_k` 很大，点积 `QK^T` 容易变得很大。

这会导致：

- softmax 输出过于尖锐
- 梯度变小
- 训练不稳定

所以除以 `sqrt(d_k)` 是为了做数值缩放，让训练更稳。

### 5.3 Self-Attention 的本质

Self-Attention 的本质是：

```text
每个 token 都在从全序列中动态读取自己最需要的信息。
```

## 6. Multi-Head Attention 为什么有效

单头 attention 只能在一个表示子空间中学习关系。

多头 attention 会把 `Q/K/V` 投影到多个不同子空间，分别计算 attention，再拼接起来：

```text
head_i = Attention(QW_i^Q, KW_i^K, VW_i^V)
MultiHead = Concat(head_1, ..., head_h)W^O
```

它的好处是：

- 不同头可以关注不同类型的模式
- 有的头关注局部搭配
- 有的头关注长距离依赖
- 有的头关注语法或实体关系

所以多头机制提升了模型表达能力。

## 7. Position Encoding 为什么必须有

Attention 天然不区分顺序，所以必须额外给位置信息。

原始 Transformer 使用的是正弦余弦位置编码。

核心特点：

- 不引入额外学习参数
- 能表达位置信息
- 对相对位置有一定泛化能力

现代 LLM 常见的位置方案包括：

- Learned Position Embedding
- RoPE

其中 `RoPE` 在大模型里很常见，因为它把位置信息编码进 attention 的旋转操作里，更适合建模相对位置关系。

## 8. Mask 是什么

Transformer 里有两类高频 mask。

### 8.1 Padding Mask

作用：

- 屏蔽补齐出来的 PAD 位置
- 避免模型把无效 token 当作真实信息

### 8.2 Causal Mask

作用：

- 保证当前位置不能看到未来 token
- 符合自回归生成要求

因此：

- Encoder 主要用 padding mask
- Decoder 既要用 padding mask，也要用 causal mask

## 9. FFN、残差连接、LayerNorm 各自干什么

### 9.1 FFN

每层 attention 后面都会接一个逐位置的前馈网络：

```text
FFN(x) = W_2 sigma(W_1 x + b_1) + b_2
```

它的作用是：

- 对每个 token 的表示做非线性变换
- 提升特征表达能力

可以理解为：

- attention 负责 token 之间的信息交互
- FFN 负责每个 token 自身的特征加工

### 9.2 Residual Connection

残差连接的作用是：

- 缓解深层网络退化问题
- 让梯度传播更稳定

### 9.3 LayerNorm

LayerNorm 的作用是：

- 稳定不同层的特征分布
- 提高训练稳定性

很多现代 LLM 还会使用 `RMSNorm` 作为替代。

## 10. Encoder-only、Decoder-only、Encoder-Decoder 的区别

这是复试里很高频的对比题。

### 10.1 Encoder-only

代表模型：

- BERT

特点：

- 可以看双向上下文
- 更适合理解类任务

典型任务：

- 分类
- 匹配
- 抽取

### 10.2 Decoder-only

代表模型：

- GPT 系列

特点：

- 使用因果 mask
- 只看前文
- 非常适合做文本生成

现代 LLM 基本都采用这一路线。

### 10.3 Encoder-Decoder

代表模型：

- T5

特点：

- 输入先编码
- 输出端再条件生成

适合：

- 翻译
- 摘要
- 问答

一句话速记：

```text
BERT 偏理解，GPT 偏生成，T5 偏条件生成。
```

## 11. Transformer 的优点和缺点

### 11.1 优点

- 并行性强
- 长距离依赖建模更直接
- 表达能力强
- 易于扩展成大规模模型

### 11.2 缺点

- Attention 复杂度通常是 `O(n^2)`
- 长文本下显存和计算开销很大
- 生成阶段要逐 token 解码，推理慢

这也是后续很多改进工作的出发点。

## 12. Transformer 和 LLM 的关系

现代 LLM 并不是脱离 Transformer 的全新体系。

更准确地说：

```text
LLM 是以 Transformer，尤其是 decoder-only Transformer 为核心骨架扩展出来的。
```

LLM 相比原始 Transformer 的主要演化方向有：

- 更大的参数规模
- 更大的训练数据
- 更长的上下文窗口
- 更稳定的训练策略
- 更高效的推理实现

## 13. LLM 最常被问到的几个知识点

### 13.1 预训练目标是什么

主流生成式大模型使用的是：

```text
Next Token Prediction
```

也就是根据前文预测下一个 token。

形式上可以理解为最大化：

```text
P(x_t | x_<t)
```

### 13.2 为什么现在大模型多用 decoder-only

原因主要有：

- 训练目标统一，直接做自回归语言建模
- 架构简单，易扩展
- 对生成任务天然友好
- 预训练和推理链路更统一

### 13.3 什么是 SFT、RLHF、DPO

- `SFT`：监督微调，让模型学会按指令回答
- `RLHF`：基于人类偏好做强化学习对齐
- `DPO`：不用显式强化学习，直接通过偏好对做优化

如果老师问“预训练之后还需要什么”，通常就答这三个阶段。

### 13.4 为什么大模型会出现幻觉

因为模型本质上是在生成“最可能出现的下一个 token”，并不是在直接检索真实知识。

所以当：

- 训练中见过类似模式
- 但缺少准确事实支撑

模型就可能生成流畅但错误的内容。

### 13.5 怎么缓解幻觉

常见方法：

- RAG
- 工具调用
- 更高质量的数据
- 指令约束
- 后验校验

### 13.6 为什么 LLM 推理慢

训练时可以并行。

但生成时通常要一个 token 一个 token 地解码，所以速度会慢很多。

这里最好顺带提一下：

- `Prefill`：先把已有上下文跑一遍
- `Decode`：再逐 token 生成
- `KV Cache`：缓存历史 key/value，避免每步重复计算

### 13.7 什么是 LoRA

LoRA 是参数高效微调方法。

核心思想：

- 冻结原模型参数
- 只学习一个低秩增量矩阵

如果老师继续追问公式，可以接：

```text
W' = W + (alpha / r)BA
```

本仓库里已经有更详细的 LoRA 笔记，可结合 `lora_interview_notes.md` 一起准备。

## 14. 面试高频问答

### 问：为什么 Transformer 比 RNN 更适合做大模型？

答：

因为 Transformer 计算并行性更强，且任意两个 token 之间都能直接交互，更容易建模长距离依赖，所以更适合大规模数据和大参数训练。

### 问：Self-Attention 的核心公式是什么？

答：

```text
Attention(Q, K, V) = softmax(QK^T / sqrt(d_k)) V
```

其中 `Q` 是查询，`K` 是键，`V` 是值。

### 问：为什么 attention 要缩放？

答：

因为高维点积容易导致数值过大，使 softmax 过于尖锐，梯度变小。除以 `sqrt(d_k)` 可以让训练更稳定。

### 问：为什么 Transformer 一定需要位置编码？

答：

因为 attention 本身不感知顺序。如果不加入位置信息，模型只知道 token 集合，不知道序列顺序。

### 问：Multi-Head Attention 比单头好在哪里？

答：

因为不同头可以在不同表示子空间中学习不同关系模式，从而增强表达能力。

### 问：BERT 和 GPT 的本质区别是什么？

答：

BERT 是 encoder-only，采用双向上下文建模，偏理解任务；GPT 是 decoder-only，采用自回归建模，偏生成任务。

### 问：为什么主流 LLM 用 decoder-only，而不是 BERT 那种结构？

答：

因为 decoder-only 更适合统一成“预测下一个 token”的预训练目标，生成链路简单，扩展性强。

### 问：什么是 causal mask？

答：

causal mask 是一种上三角屏蔽机制，保证当前 token 只能看见自己之前的位置，不能看到未来信息。

### 问：Transformer 的缺点是什么？

答：

主要是长序列时 attention 的计算和显存开销大，复杂度通常为 `O(n^2)`，另外生成时逐 token 解码导致推理速度慢。

### 问：为什么大模型会幻觉？

答：

因为它是在做概率生成，不是在做事实检索。当缺乏可靠外部依据时，容易生成流畅但不真实的内容。

### 问：怎么缓解幻觉？

答：

可以通过 RAG、工具调用、指令约束、检索校验等方法降低幻觉风险。

### 问：为什么 LLM 推理时要用 KV Cache？

答：

因为生成时历史 token 不变，如果每一步都重新计算全部历史 attention 会很浪费。KV Cache 把历史 key/value 缓存起来，可以显著降低重复计算。

## 15. 复试里的推荐回答顺序

如果老师让你讲 Transformer，最稳的回答顺序是：

1. 先说提出动机：解决 RNN 串行和长依赖问题
2. 再说整体结构：Encoder、Decoder、Attention、FFN
3. 再说核心公式：`softmax(QK^T / sqrt(d_k))V`
4. 再说关键设计：多头、位置编码、mask、残差、归一化
5. 最后联系 LLM：主流是 decoder-only，自回归生成

这个顺序比零散堆术语更像真正理解过。

## 16. 面试前最后速记版

最后至少记住下面这 8 句话：

1. `Transformer 用 self-attention 替代循环结构。`
2. `核心公式是 Attention(Q,K,V)=softmax(QK^T/sqrt(d_k))V。`
3. `Q 决定查什么，K 决定匹配谁，V 决定取什么信息。`
4. `多头注意力让模型在不同子空间中学习不同关系。`
5. `位置编码解决 attention 不感知顺序的问题。`
6. `BERT 是 encoder-only，GPT 是 decoder-only，T5 是 encoder-decoder。`
7. `Transformer 的主要缺点是长序列计算复杂度高。`
8. `现代 LLM 本质上是 Transformer，尤其是 decoder-only Transformer 的扩展。`
