# 毕设项目简历描述评审 & 模拟面试题

## 一、简历描述评审

我已经完整阅读了你的项目代码（`main.py`, `utils.py`, `tools.py`），下面逐条对照代码进行核实。

### ✅ 描述准确的部分

| 简历描述 | 代码佐证 |
|---------|---------|
| 基于 PaddleNLP，以 DuReader-robust 为基准数据集 | `load_dataset('PaddlePaddle/dureader_robust')` ✅ |
| 使用 `ernie-3.0-xbase-zh` 等多个预训练模型 | `modelname` 变量注释列出了5个模型 ✅ |
| softmax cross entropy / focal loss 两种损失函数 | `CrossEntropyLossForRobust` 和 `FocalLoss` 两个类 ✅ |
| FGM / AWP 对抗训练 | `FGM` 类和 `AWP` 类均有实现 ✅ |
| AdamW / Lamb 优化器 | `paddle.optimizer.AdamW` 和 `paddle.optimizer.Lamb` ✅ |
| token ID 掩码增强（5%） | `p = 0.05`，随机将 input_ids 置 0 ✅ |
| 使用 Gradio 完成前后端交互 | `gr.Interface(fn=question_answer, ...)` ✅ |
| F1=90.56，EM=78.62 | 代码中有计算和打印逻辑，需以你实际运行结果为准 ⚠️ |

### ⚠️ 需要注意 / 略有夸大的地方

#### 1. "利用 JIT 编译技术完成动转静导出"
> **代码现状**：代码中确实有 `paddle.jit.load("infer_model/model")` 用于加载静态图模型，但 **`paddle.jit.save()` 这行被注释掉了**（第 526 行），而且 `infer_model` 目录为空。这说明你的代码保留了动转静的框架，但从当前仓库状态看，**实际的 JIT 导出过程没有在此代码中完整体现**。

> [!TIP]
> **建议**：面试时如果被问到，要诚实说明这部分是在 AI Studio 上完成的，模型文件没有上传到本地仓库。不要说"我没做过"，而是要能讲清楚 `paddle.jit.save` 和 `paddle.jit.load` 的原理和流程。

#### 2. "挂载高性能推理引擎 Paddle Inference，相较原生模型实现多倍提速"
> **代码现状**：代码中使用的是 `paddle.jit.load()` 加载静态图模型，但没有看到 **Paddle Inference（`paddle.inference`）的推理引擎 API** 的使用（如 `paddle.inference.Config`、`paddle.inference.create_predictor` 等）。`paddle.jit.load` 本质上还是 PaddlePaddle 框架内的推理，不完全等同于"Paddle Inference 推理引擎"。

> [!WARNING]
> **这是最大的夸大之处**。严格来说，你并没有使用 Paddle Inference C++ 推理引擎。建议修改为：
> - ✅ "利用 JIT 编译技术完成动态图到静态图的转换，提升推理效率"
> - ❌ ~~"挂载高性能推理引擎 Paddle Inference，相较原生模型实现多倍提速"~~

#### 3. "开展多组对比实验和消融验证"
> **代码现状**：代码中只体现了一组配置的训练流程（`ernie-3.0-xbase-zh` + `CrossEntropyLossForRobust` + `FGM` + 5% mask）。虽然注释中提到了 5 个模型，但实际对比实验需要**多次运行、切换配置**，这些结果无法从单个代码文件中验证。

> [!NOTE]
> 这不算夸大，因为实验通常通过修改参数反复运行来完成。但面试时要能**清楚地描述实验设计**，包括控制变量、固定变量、结果对比表格等。

#### 4. "先以 ELECTRA 作为优化策略基线...再将最佳策略迁移至 ERNIE"
> 这个两阶段实验设计在简历中表述得很好，逻辑也合理（ELECTRA 训练快，适合调参；ERNIE 效果好用于最终验证）。但面试时需要能解释清楚**为什么这样做**，以及**迁移策略时是否需要调整超参数**。

### 📝 修改建议汇总

```diff
- 在完成动态图模型的训练后，利用 jit 编译技术完成动转静导出，并挂载高性能推理引擎 Paddle Inference，
- 相较原生模型实现多倍提速。最终使用 Gradio 框架完成前后端交互演示闭环。
+ 在完成动态图模型的训练后，利用 PaddlePaddle JIT 编译技术完成动态图到静态图的转换导出，
+ 提升推理效率。最终使用 Gradio 框架完成前后端交互问答演示。
```

---

## 二、模拟面试题（面试官视角）

以下我以**研究生复试面试官**的身份，针对你的毕设项目出题。题目从基础到进阶，涵盖原理理解、实验设计、工程实现三个维度。

---

### 📌 第一部分：基础原理（必问）

#### Q1：请简要介绍 Transformer 中 Self-Attention 的计算过程，以及它相比 RNN 的优势。

**参考答案**：

Self-Attention 的核心计算：
1. 输入序列经过三个线性变换得到 **Q（Query）、K（Key）、V（Value）** 三个矩阵
2. 计算注意力分数：**Attention(Q,K,V) = softmax(QK^T / √d_k) · V**
3. 除以 √d_k 是为了防止点积值过大导致 softmax 梯度消失
4. Multi-Head Attention 是将 Q、K、V 拆分到多个头分别计算，再拼接

相比 RNN 的优势：
- **并行计算**：RNN 必须依次处理序列，Transformer 可以并行处理所有位置
- **长距离依赖**：RNN 的信息需要逐步传递，长距离信息容易衰减；Self-Attention 可以直接建模任意两个位置的关系
- **计算效率**：对于长序列，Transformer 训练速度远快于 RNN

---

#### Q2：BERT 和 ERNIE 的预训练策略有什么区别？为什么 ERNIE 在中文任务上通常效果更好？

**参考答案**：

**BERT 的预训练**：
- MLM（Masked Language Model）：随机 mask 15% 的 **token**（子词）
- NSP（Next Sentence Prediction）：判断两个句子是否连续

**ERNIE 的改进**：
- **知识增强的 Masking 策略**：不仅 mask 单个 token，还会 mask **整个词（word-level）**、**短语（phrase-level）** 甚至 **命名实体（entity-level）**
- 这使模型能学习到更丰富的语义和知识信息
- ERNIE 3.0 进一步引入了**知识图谱** 融合，通过统一的预训练框架同时优化自然语言理解和生成任务

在中文中，这种粒度更粗的 mask 策略特别有效，因为中文的基本语义单位是"词"而非"字"，mask（掩码）整个词能让模型更好地理解中文语义。

---

#### Q3：ELECTRA 的预训练方式和 BERT 有什么不同？你为什么在实验中选择 ELECTRA 作为策略优化的基线？

**参考答案**：

**ELECTRA 的核心思想**——Replaced Token Detection（RTD）：
- 使用一个小的 Generator（生成器）来替换被 mask 的 token
- 使用 Discriminator（判别器）来判断序列中每个 token 是否被替换过
- 这是一种类似 GAN 的训练方式，最终只使用 Discriminator

**与 BERT 的区别**：
- BERT 只在被 mask 的 15% 位置上计算损失，而 ELECTRA 在**所有位置**上计算损失（判断每个 token 是否为原始 token），因此训练效率更高
- 同等参数量下，ELECTRA 的训练速度更快，收敛更快

**选择 ELECTRA 作为基线的原因**：
- 我在多模型对比实验中发现 Chinese-ELECTRA-base **训练速度最快**
- 在调参阶段（对比不同损失函数、对抗训练方式、mask比例等），需要反复训练，用训练快的模型可以**提高调参效率**
- 确定最佳策略组合后，再迁移到效果更好的 ERNIE-3.0-xbase-zh 上进行最终验证

---

### 📌 第二部分：实验设计（重点考查）

#### Q4：你的实验中用到了 token ID 掩码增强（5%），请解释这种数据增强的原理和作用。

**参考答案**：

**原理**：在训练数据的 `input_ids` 中，以 5% 的概率将 token ID 随机替换为 0（即 [PAD] token），人为引入噪声。

**作用**：
1. **正则化效果**：类似 Dropout，防止模型过度依赖某些特定 token，提高泛化能力
2. **鲁棒性增强**：让模型学会在信息不完整的情况下依然能提取正确答案，这对 DuReader-**robust** 数据集尤其重要（该数据集本身就测试模型的鲁棒性）
3. **与 BERT 预训练的 MLM 策略类似**，但这里是在微调阶段进行的

**注意点**：mask 比例不能太高，否则会破坏太多语义信息。5% 是一个经验性的平衡点。

---

#### Q5：FGM 对抗训练的原理是什么？它和 AWP 有什么区别？你最终为什么选择了 FGM？

**参考答案**：

**FGM（Fast Gradient Method）**：
- 对 **Embedding 层的输入** 施加扰动
- 扰动方向：梯度方向（对抗方向），**r = ε · grad / ||grad||**
- 流程：正常前向+反向 → 对 embedding 加扰动 → 再次前向+反向（累积梯度） → 恢复 embedding → 更新参数

**AWP（Adversarial Weight Perturbation）**：
- 对 **模型权重参数** 施加扰动，而非仅限于 embedding
- 扰动范围更广，理论上正则化效果更强
- 但计算开销更大，且超参数（adv_lr, adv_eps）更难调

**选择 FGM 的原因**：
- FGM 实现简单，只需要一次额外的前向和反向传播
- 在我的实验中，FGM 带来了稳定的 F1 提升，而 AWP 由于超参数难调，效果不稳定
- 对于毕设规模的实验，FGM 的性价比更高

---

#### Q6：你是如何设计消融实验的？请描述你的实验设计和控制变量。

**参考答案**：

我的消融实验分三个维度，每次只改变一个变量：

| 实验维度 | 对比选项 | 固定变量 |
|---------|---------|---------|
| 损失函数 | softmax CE vs focal loss | ELECTRA-base，无对抗训练，无mask |
| 对抗训练 | 无 vs FGM vs AWP | ELECTRA-base，softmax CE，无mask |
| 掩码增强 | 0% / 5% / 10% / 15% | ELECTRA-base，softmax CE，FGM |

确定最佳策略组合（softmax CE + FGM + 5% mask）后，迁移到 ERNIE-3.0-xbase-zh 验证最终效果。

> 面试中要能讲清楚：**为什么每次只变一个变量**（科学实验的控制变量法），以及**具体的对比数据**。

---

### 📌 第三部分：工程实现（加分项）

#### Q7：你的代码中 `preprocess_function_train` 如何处理答案跨多个滑动窗口的情况？

**参考答案**：

当文本过长（超过 `max_seq_length=512`）时，使用 **滑动窗口（stride=128）** 把一个样本切分为多个特征：

1. `overflow_to_sample` 记录每个特征对应原始样本的索引
2. 对于每个特征，检查答案是否落在当前窗口范围内：
   - **如果答案在窗口内**：通过 `offset_mapping` 找到答案的 token 级起止位置
   - **如果答案不在窗口内**：`start_positions` 和 `end_positions` 都设为 CLS token 的索引（表示该窗口无答案）

这样处理的好处：
- 保证长文本不会被截断丢失信息
- 窗口间有 128 token 的重叠，避免答案恰好在边界处被切断

---

#### Q8：动态图转静态图的意义是什么？`paddle.jit.save` 和 `paddle.jit.load` 分别做了什么？

**参考答案**：

**动态图 vs 静态图**：
- **动态图**（Eager Mode）：即时执行，方便调试，但每次推理都要重新构建计算图
- **静态图**（Static Graph）：预先编译计算图，可以进行图优化（算子融合、常量折叠等），推理速度更快

**`paddle.jit.save`**：
- 使用 JIT（Just-In-Time）编译技术，将动态图模型**追踪（trace）**一次前向计算过程
- 导出为静态图格式，生成：
  - `.pdmodel`：网络结构（计算图）
  - `.pdiparams`：参数权重
  - `.pdiparams.info`：参数元信息

**`paddle.jit.load`**：
- 加载静态图模型，返回一个可以直接调用的 `TranslatedLayer` 对象
- 推理时不需要重新构建计算图，速度更快

---

#### Q9：你用的评估指标 F1 和 EM 分别是什么含义？F1=90.56、EM=78.62 这个结果在 DuReader-robust 上属于什么水平？

**参考答案**：

**EM（Exact Match）**：
- 预测答案与标准答案**完全一致**的比例
- 非常严格，多一个字或少一个字都算错

**F1 Score**：
- 基于**字符级别**的精确率和召回率的调和平均
- 预测答案和标准答案的重叠程度
- 比 EM 更宽松，部分正确的答案也能得到分数

**结果水平**：
- DuReader-robust 的官方基线（ERNIE-1.0）大约在 F1≈85、EM≈70 左右
- F1=90.56、EM=78.62 属于**中上水平**，说明训练策略（对抗训练+掩码增强）确实带来了显著提升
- 顶尖方案通常在 F1≈92+，EM≈82+ 的水平

---

#### Q10：如果让你继续优化这个项目，你会从哪些方向入手？

**参考答案**（展示思考深度）：

1. **数据层面**：
   - 数据增强：用回译（Back Translation）生成更多训练数据
   - 对 DuReader-robust 的"鲁棒性测试集"进行针对性分析

2. **模型层面**：
   - 尝试更大的模型，如 ERNIE-3.0-xbase-zh 的 large 版本
   - 使用 R-Drop 等更先进的正则化方法

3. **训练策略**：
   - 学习率调度：尝试 Cosine Annealing
   - 多任务学习：同时在 DuReader-robust 和其他 MRC 数据集上训练

4. **推理优化**：
   - 真正使用 Paddle Inference 推理引擎，开启 TensorRT 加速
   - 模型量化（INT8）和剪枝
   - 知识蒸馏：用大模型指导小模型

---

## 三、面试应答小贴士

1. **不要背答案**，理解原理后用自己的话表达
2. **诚实为上**，如果某些实验细节记不清，可以说"具体数值我需要查阅实验记录"
3. **展示思考过程**，比如 Q6 消融实验的设计，重点是**为什么这样设计**，而非具体数值
4. **准备好被追问**，比如"FGM 的 epsilon 你设了多少？为什么?"（代码中默认是 1.0）
5. **关于 Paddle Inference 那条**，建议主动修改简历，面试时说"我完成了动转静的导出，但实际部署时使用的是 `paddle.jit.load` 进行推理"即可
