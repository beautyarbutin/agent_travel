# 毕设超参数 & 核心技术深度面经

> 基于你论文 PDF 和 PPT 中的**实际实验数据**整理

---

## 一、实验数据总览（来自你的论文）

### 表 4-8：五种预训练模型对比

| 方案 | 参数量 | 训练时间(s) | F1 | EM |
|------|--------|-----------|------|------|
| Chinese-ELECTRA-base | 12M | **1753** | 87.03 | 74.10 |
| BERT-wwm-ext-Chinese | 108M | 1770 | 87.03 | 73.67 |
| nezha-base-Chinese | 108M | 2193 | 86.92 | 73.81 |
| ALBERT-Chinese-xxlarge | 235M | 6438 | 88.51 | 75.42 |
| **ERNIE-3.0-xbase-zh** | **296M** | 7393 | **90.05** | **77.27** |

### 表 4-9：ELECTRA 基线模型 12 组对比实验

| # | 损失函数 | 掩码率 | 对抗训练 | 优化器 | F1 | EM |
|---|---------|-------|---------|-------|------|------|
| 1 | softmax | — | — | AdamW | 87.03 | 74.10 |
| 2 | softmax | 3% | — | AdamW | 86.17 | 72.75 |
| 3 | softmax | 2% | — | AdamW | 86.22 | 73.67 |
| 4 | softmax | 10% | — | AdamW | 86.20 | 72.19 |
| **5** | **softmax** | **5%** | **FGM** | **AdamW** | **87.34** | **74.45** |
| 6 | softmax | — | FGM | Lamb | 81.72 | 67.81 |
| 7 | focal | — | — | AdamW | 84.82 | 71.91 |
| 8 | focal | — | FGM | AdamW | 86.48 | 73.88 |
| 9 | softmax | 5% | — | AdamW | 86.34 | 73.25 |
| 10 | softmax | — | AWP | AdamW | 86.56 | 73.67 |
| 11 | softmax | 5% | AWP | AdamW | 86.65 | 73.18 |
| 12 | focal | 5% | AWP | AdamW | 85.59 | 72.61 |

### ERNIE 消融实验

| 方案 | 消融结构 | F1 | EM |
|------|---------|------|------|
| ERNIE + softmax + 5%mask + FGM | — | **90.55** | **78.61** |
| ERNIE + softmax + FGM | 去掉掩码 | 90.41 | 78.12 |
| ERNIE + softmax + 5%mask | 去掉FGM | 90.10 | 78.04 |
| ERNIE + focal + FGM | 换focal loss | 88.21 | 74.02 |

---

## 二、基础概念（面试必问）

### Q：什么是梯度？什么是梯度下降？

- **梯度**：损失函数对模型参数的偏导数，数学上表示 loss 增长最快的方向
- **梯度下降**：沿着梯度的**反方向**更新参数（因为要**最小化** loss）
- 公式：`theta_new = theta_old - lr * grad(L)`
- 类比：闭着眼站在山上，用脚感受哪个方向最陡（梯度），往反方向（下坡）走一步

### Q：什么是过拟合和欠拟合？

- **过拟合**：训练集表现好，验证集/测试集表现差 = "死记硬背"了训练数据
- **欠拟合**：训练集和验证集上都差 = 模型太简单，没学到规律
- **你实验中防过拟合的手段**：weight decay、FGM 对抗训练、token ID 掩码、warmup + 学习率衰减

### Q：什么是微调（Fine-tune）？和预训练有什么关系？

- **预训练**：在大规模无标注语料上训练，学通用语言知识（如 BERT 在维基百科上学中文理解）
- **微调**：把预训练模型拿来，在**特定任务的小规模标注数据**上继续训练，使其适应具体任务
- 好处：从零训练 BERT 要数百 GPU 天，微调只需 1 块 GPU 几小时
- 核心：微调学习率要**很小**（如 3e-5），以免破坏预训练知识（灾难性遗忘）

---

## 三、超参数设置原理详解

### 1. Batch Size = 12

**Q：batch size 是什么？有什么用？**

- **Batch Size（批次大小）** = 模型每次训练时**同时处理的样本数量**
- 深度学习不是逐个样本训练，而是把多个样本打包成 **mini-batch** 一起送入模型
- **作用**：
  - 提高效率：GPU 擅长并行计算，一次处理多样本比逐个快得多
  - 梯度更稳定：多样本的**平均梯度**比单样本的噪声小
  - 影响泛化：小 batch 有更多梯度噪声 = 隐式正则化 = 可能泛化更好；大 batch 容易陷入 sharp minima

**Q：你为什么设为 12？**

- **硬件限制**：V100（32GB），ERNIE-3.0-xbase 有 296M 参数 + 20 层 + seq_len=512，batch=12 已接近显存上限
- **显存估算**：模型参数(FP32) 约 1.1GB + AdamW 状态 x3 + 中间激活值 + 输入数据
- **经验法则**：预训练微调 batch 通常 **8~32**

> [!TIP]
> **追问**："为什么不用梯度累积模拟更大 batch？" 回答：可以，但 batch=12 已够用，epoch=2 的训练步数足够收敛。

---

### 2. Learning Rate = 3e-5

**Q：学习率是什么？有什么用？**

- **学习率（lr）** = 每次参数更新的**步长大小**
- 公式：`theta = theta - lr * grad`，梯度指方向，lr 控制走多远
- 太大：跳过最优解，loss 震荡/发散
- 太小：收敛极慢
- 需要在"收敛速度"和"稳定性"之间平衡

**Q：为什么设 3e-5？这么小？**

- **微调核心原则**：预训练模型已学到丰富语言知识，太大的 lr 会**破坏预训练权重**（灾难性遗忘）
- **BERT 论文推荐**：微调 lr 为 {2e-5, 3e-5, 5e-5}，3e-5 是中间值
- **配合 warmup**：lr 从 0 增长到 3e-5 再衰减，避免训练初期震荡

**追问：如果 lr 设为 1e-4？**
- 大概率 loss 震荡/发散，预训练权重被破坏，F1 可能只有 70+

---

### 3. Epoch = 2

**Q：epoch 是什么？和 step 有什么区别？**

- **Epoch**：模型把**整个训练集**过一遍 = 1 个 epoch
- **Step/Iteration**：处理 1 个 mini-batch = 1 个 step
- **关系**：`1 epoch = 总样本数 / batch_size 个 steps`
- 你的实验：约 15000 样本，batch=12，1 epoch 约 1250 steps，2 epoch 约 2500 steps

**Q：为什么只训练 2 个 epoch？**

- 预训练模型微调**收敛极快**，通常 2~4 epoch 足够
- DuReader-robust 训练集约 1.5w 样本，epoch 太多易过拟合
- Loss 曲线显示 2 epoch 后已趋于平稳
- BERT 论文建议微调 2~4 epoch

---

### 4. Warmup Proportion = 0.1

**Q：warmup 是什么？为什么需要？**

学习率调度为 **Linear Decay with Warmup**：

```
阶段1（前10%步数）：lr 从 0 线性增长到 3e-5
阶段2（后90%步数）：lr 从 3e-5 线性衰减到 0
```

**为什么需要 warmup**：
- 训练初期，分类头是随机初始化的，梯度方差很大
- 一开始就用大 lr 可能把预训练权重带偏
- 先用小 lr "热身"，逐步适应下游任务

**0.1 的含义**：前 10% steps 用于 warmup，BERT 微调的标准配置。

---

### 5. Weight Decay = 0.01

**Q：权重衰减是什么？有什么用？**

- **Weight Decay** = 正则化技术，每次更新时让权重乘以略小于 1 的系数，防止权重过大
- 本质：惩罚大权重，迫使模型学到更小、更分散的参数
- 作用：防止**过拟合**
- 与 L2 正则化关系：在 SGD 中等价，但在 AdamW 中使用**解耦 weight decay**，效果更好
- **0.01 是标准值**：预训练领域几乎都用 0.01

**Q：为什么 layer_norm 和 bias 不做衰减？**

- **layer_norm 参数**控制归一化的尺度和偏移，惩罚它们会影响网络稳定性
- **bias** 提供偏移量，大小不代表过拟合，惩罚反而限制表达能力
- 这是 BERT/ERNIE 微调的标准做法

```python
decay_params = [
    p.name for n, p in model.named_parameters()
    if not any(nd in n for nd in ["bias", "norm"])
]
```

---

## 四、损失函数对比详解

**Q：损失函数是什么？有什么用？**

- **Loss Function** = 衡量模型预测值与真实值的**差距**
- 训练目标就是**最小化 loss**：loss 越小 = 预测越准
- 你的 MRC 任务中，答案位置预测本质是**分类问题**（从 512 个位置中选 1 个）

### Softmax Cross-Entropy ✅（最终选用）

**原理**：
1. 模型对序列每个位置输出一个 logit 分数
2. **softmax** 转为概率分布：`P(i) = exp(logit_i) / sum(exp(logit_j))`，所有位置概率和为 1
3. **交叉熵**：`loss = -log(P(label))`，正确位置概率越高 loss 越小

**在 MRC 中**：起始/结束位置各一个 CE loss，最终 `loss = (start_loss + end_loss) / 2`

```python
start_loss = paddle.nn.functional.softmax_with_cross_entropy(
    logits=start_logits, label=start_position, soft_label=False)
end_loss = paddle.nn.functional.softmax_with_cross_entropy(
    logits=end_logits, label=end_position, soft_label=False)
loss = (start_loss + end_loss) / 2
```

### Focal Loss ❌（效果差）

**原理**：Kaiming He 为解决目标检测中**正负样本不平衡**提出

`Loss = -alpha * (1-sigma(y))^gamma * log(sigma(y))`

- **alpha=0.25**：平衡正负样本权重
- **gamma=2.0**：降低**易分样本**权重，聚焦于**难分样本**
- 样本被正确分类且置信度高时，`(1-sigma(y))^gamma` 趋近于 0，贡献极小

**实现差异**：需先将 position 转 **one-hot 编码**，用 `sigmoid_focal_loss` 而非 softmax

### 对比结果

| 对比 | F1 | 差异 |
|------|------|------|
| softmax vs focal（无FGM） | 87.03 vs 84.82 | **softmax 高 2.21** |
| softmax+FGM vs focal+FGM | 87.34 vs 86.48 | **softmax 高 0.86** |
| ERNIE 消融 | 90.55 vs 88.21 | **softmax 高 2.34** |

**为什么 softmax 更好？**
1. **focal loss 的 alpha/gamma 难调**：论文原话"focal loss 的权重十分难调，所以还不如交叉熵效果好"
2. **任务不匹配**：focal loss 解决 CV 中极端不平衡（背景:前景=1000:1），MRC 的不平衡没那么极端
3. **softmax 的互斥假设更适合 MRC**：答案位置是**唯一的**，softmax 天然建模"512 选 1"的互斥关系；focal loss 用 sigmoid 对每位置独立二分类，丢失了位置间竞争

---

## 五、优化器对比详解

**Q：优化器是什么？有什么用？**

- **Optimizer** = 决定参数**如何更新**
- 最基础的 **SGD**：`theta = theta - lr * grad`，所有参数同一学习率，收敛慢
- **Adam 系列**改进：为每个参数**自适应调整**学习率
  - 梯度大的参数自动减小步长，梯度小的自动增大
- 优化器选择直接影响训练速度和最终效果

### AdamW ✅（最终选用）

**核心公式**：
```
m_t = beta1 * m_{t-1} + (1-beta1) * g_t          # 一阶动量（梯度均值）
v_t = beta2 * v_{t-1} + (1-beta2) * g_t^2         # 二阶动量（梯度方差）
m_hat = m_t / (1-beta1^t)                          # 偏差校正
v_hat = v_t / (1-beta2^t)                          # 偏差校正
theta = theta - lr * m_hat/(sqrt(v_hat)+eps) - lr*tau*theta  # 解耦权重衰减
```

**与 Adam 关键区别**：
- Adam：L2 正则化耦合在梯度中，正则化被自适应学习率削弱
- **AdamW**：**解耦权重衰减**，直接减去 `lr*tau*theta`，正则化更稳定

### Lamb ❌（效果极差）

**核心**：在 AdamW 基础上加**逐层自适应信任比率**：
```
theta = theta - lr * (||theta|| / ||update||) * update
```

**设计目的**：专为**大 batch（数千~数万）** 训练设计。

### 对比结果

| 优化器 | F1 | EM |
|-------|------|------|
| AdamW | **87.34** | **74.45** |
| Lamb | 81.72 | 67.81 |

**Lamb 为什么惨败？**
1. Lamb 为大 batch 设计，你的 batch=12 属于小 batch，逐层自适应在小 batch 时引入噪声
2. 论文："Lamb 更适合较大规模的数据集"
3. 经验：小数据+小batch = **AdamW**；大数据+大batch（预训练阶段） = Lamb

---

## 六、对抗训练详解

**Q：对抗训练是什么？**

- 在训练时故意往输入/权重上**加微小扰动**，让模型在更困难的条件下学习
- 提升**鲁棒性**和**泛化能力**，是 NLP 榜单的提分利器
- NLP 中文本是离散的，不能直接在文字上加噪声，所以在连续的 **Embedding 空间**加扰动

**数学表达**：
```
min_theta E_{(x,y)} [ max_{delta} L(x+delta, y; theta) ]
```
- 内层 max：找让 loss 最大的扰动（攻击）
- 外层 min：在对抗样本上最小化 loss（防御）

### FGM ✅（最终选用）

**扰动对象**：Embedding 层输入 x

**扰动公式**：`delta_x = eps * grad_x / ||grad_x||`

**训练流程**：
```
1. 正常前向 -> 计算loss -> 反向传播（得梯度）
2. fgm.attack()  -> 沿梯度方向扰动 embedding
3. 扰动后再次前向+反向（累积梯度）
4. fgm.restore() -> 还原 embedding
5. optimizer.step() -> 用累积梯度更新参数
```

### AWP ❌（效果不稳定）

**扰动对象**：模型权重 theta（而非输入）

**扰动公式**：`delta_theta = eps * grad_theta / ||grad_theta|| * (||w|| + tau)`

### FGM vs AWP 对比

| | FGM | AWP |
|---|-----|-----|
| 扰动对象 | Embedding 输入 | 模型权重 |
| 扰动范围 | 仅 Embedding 层 | 所有 weight 参数 |
| 超参数 | eps=1（简单） | adv_lr=1, adv_eps=0.0001（难调） |

| 对比 | 对抗训练 | F1 |
|------|---------|------|
| 实验1 vs 5 | 无 vs FGM | 87.03 -> **87.34** |
| 实验1 vs 10 | 无 vs AWP | 87.03 -> 86.56 |
| ERNIE消融 | 有FGM vs 无FGM | **90.55** vs 90.10 |

**FGM 为什么更好？**
1. AWP 超参难调，默认值效果不理想
2. AWP 扰动范围太广，微调任务中可能过度正则化
3. FGM 只扰动 embedding，eps=1 是通用配置，几乎不需要调参

---

## 七、Token ID 掩码增强详解

**Q：数据增强是什么？**

- 通过对训练数据做变换，"创造"更多样本，提高泛化能力
- CV 中常用旋转、翻转、裁剪；NLP 中可用同义词替换、回译、掩码等

**你的做法**：以概率 p 将 input_ids 中的 token ID 随机置 0（PAD token）

### 不同掩码率的实验结果

| 掩码率 | F1 | 对比基线(87.03) |
|--------|------|---------|
| 0% | 87.03 | — |
| 2% | 86.22 | -0.81 |
| 3% | 86.17 | -0.86 |
| **5%+FGM** | **87.34** | **+0.31** |
| 5% (无FGM) | 86.34 | -0.69 |
| 10% | 86.20 | -0.83 |

**关键结论**：
1. 单独用掩码效果反而下降（实验9 vs 实验1），信息损失太多
2. **掩码+FGM 配合才有提升**，两种正则化互补
3. 掩码率过高（10%）明显有害
4. 5% 是最优平衡点

---

## 八、JIT 编译与动转静详解

**Q：动态图和静态图有什么区别？**

| | 动态图 | 静态图 |
|---|---|---|
| 执行方式 | 逐行执行 Python | 先编译计算图再执行 |
| 调试 | 方便 | 难调试 |
| 推理速度 | 较慢 | **快**（图优化+C++执行） |
| 适用 | 训练开发 | **部署推理** |

**Q：JIT 是什么？**

- **JIT（Just-In-Time）编译**：在运行时将动态图模型"追踪"一次前向计算，转换为静态计算图
- `paddle.jit.save(model)` 输出：
  - `.pdmodel`：网络结构
  - `.pdiparams`：参数权重
  - `.pdiparams.info`：参数元信息
- `paddle.jit.load()` 加载静态图，返回 TranslatedLayer 对象

**静态图为什么快**：算子融合、常量折叠、内存优化、C++ 执行绕过 Python GIL

**追问：Paddle Inference vs paddle.jit.load？**
> `paddle.jit.load` 在 Python 框架内加载。Paddle Inference 是独立 C++ 推理引擎，支持 TensorRT 和 INT8 量化。我实际用的是 `paddle.jit.load`。

---

## 九、高频追问 Q&A

### Q：为什么 max_seq_length = 512？

BERT 系模型位置编码最大支持 512 token，预训练时就固定了。超过 512 必须滑动窗口切割。

### Q：为什么 doc_stride = 128？

512 窗口以 128 步长滑动，相邻窗口重叠 384 token，确保答案不在边界被切断。这是 SQuAD 的标准设置。

### Q：ELECTRA 12M 参数为何和 BERT 108M 效果差不多？

ELECTRA 用 RTD（Replaced Token Detection）在**所有 token** 上计算损失，BERT MLM 只在 15% 的 mask 位置上算。同等计算量下 ELECTRA 学到更多，小模型也能达到大模型效果。

### Q：为什么用 ELECTRA 做基线调参而不是直接在 ERNIE 上调？

1. ELECTRA 训练 1753s（30分钟），ERNIE 要 7393s（2小时），**省 4 倍时间**
2. 12 组对比实验，都在 ERNIE 上做要 24+ 小时
3. 优化策略的相对优劣在不同模型上通常一致
4. ERNIE 消融实验验证了策略迁移有效

### Q：F1=90.55 是什么水平？

- 官方 ERNIE-1.0 基线约 F1=85
- 你的结果高出 5.5 个点
- 顶尖方案约 F1=92+
- 属于**中上水平**，本科毕设很不错
