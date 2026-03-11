# 🎓 浙大复试 · RAG 专题面试备考手册
> 基于你的 OpenAgents 旅游助手项目真实代码，针对软件学院 AI 方向整理

---

## 一、关键术语速查表

| 术语 | 一句话解释 |
|---|---|
| **RAG** | 检索增强生成：先从知识库里搜，再把搜到的内容喂给大模型生成答案 |
| **召回（Recall）** | 从大量文档里"捞"出可能相关的候选集，追求不漏掉正确答案 |
| **Hybrid RAG** | 同时用"关键词检索"和"向量语义检索"两路召回，融合排序 |
| **FAISS** | Facebook AI 出品的向量相似度搜索库，支持亿级向量毫秒级检索 |
| **Embedding** | 把文字转成语义浮点向量，让"衡水湖在哪"和"衡水湖怎么去"语义相近 |
| **BM25** | 基于词频的经典信息检索算法，关键词精准匹配的利器 |
| **Rerank** | 对召回候选集做二次精排，用更重量级模型选出最好的 Top-K |
| **意图分发** | 判断用户想干什么（问天气/查景点/规划行程），路由给对应 Agent |

---

## 二、什么是"召回"？

### 直觉解释

想象你在图书馆找书。**召回**就是"把所有可能相关的书先搬到桌子上"这个动作。哪怕搬了 20 本，只有 3 本真正有用，这个"宁可多搬不漏掉"的过程就叫召回。

**召回率（Recall）** = 正确答案里被检索到的比例：

```
Recall = 检索到的相关文档数 / 全部相关文档总数
```

### 你项目里的召回

在你的 `spot_tools.py` 中，`search_knowledge()` 就是召回函数：

```python
# 召回阶段：两路并行
# 路线1：FAISS 向量检索 → top-5 候选
scores, indices = _faiss_index.search(q_vec, min(n, 5))

# 路线2：BM25 关键词检索 → 全库打分
for i, spot in enumerate(_knowledge_docs):
    bm25 = _bm25_score(query, spot)

# 融合 → 取 Top-5 最终结果
top_indices = final_scores.argsort()[::-1][:5]
```

你在 `eval_rag.py` 里还专门评估了**Top-2 召回率**（期望答案出现在返回的前2条结果里的比例）。

> **面试金句**：召回追求高覆盖（不漏），精排追求高精度（不错）。两者是 IR 系统的两阶段 pipeline。

---

## 三、Hybrid RAG 详解

### 3.1 为什么需要 Hybrid？

| 单路检索 | 优点 | 致命缺点 |
|---|---|---|
| 纯向量检索 | 语义理解强，"观鸟"→衡水湖 | 对具体名词（故城县、庆林寺塔）不敏感 |
| 纯关键词(BM25) | 景点名/地名精准命中 | "哪里热闹"这类模糊语义完全无法处理 |
| **Hybrid** | **两者互补** | 需要调权重，工程复杂度稍高 |

### 3.2 你项目的 Hybrid RAG 架构

```
用户 Query："衡水湖适合带小孩去吗？"
        │
        ├─── 路线A: FAISS 向量检索
        │    ├─ bge-small-zh 编码 Query → 512维向量
        │    ├─ IndexFlatIP 内积检索（≈ 余弦相似度）
        │    └─ Top-5 候选，相似度分 × 5.0 权重
        │
        ├─── 路线B: BM25 关键词检索
        │    ├─ 城市词匹配 (+5.0)
        │    ├─ 景点名匹配 (+15.0)
        │    ├─ 标签碰撞 (+2.0/条)
        │    ├─ 内容词频 (+0~2.0)
        │    └─ 独家攻略加权 (+50.0，有碰撞时才加)
        │
        └─── 分数融合：final_score = vec_score + bm25_score
                      Top-5 排序 → 格式化输出给 LLM
```

### 3.3 分数融合策略（你的代码实现）

```python
# 这是你 spot_tools.py 里的核心逻辑
final_scores = np.zeros(n, dtype=np.float32)

# 向量召回得分
for rank, (idx, score) in enumerate(zip(indices[0], scores[0])):
    final_scores[idx] += score * 5.0  # 向量相似度 × 权重

# BM25 得分叠加
for i, spot in enumerate(_knowledge_docs):
    bm25 = _bm25_score(query, spot)
    if spot.get('source') == '独家手写攻略' and bm25 > 0:
        bm25 += 50.0  # 独家攻略特权分（仅有关键词碰撞才激活）
    final_scores[i] += bm25
```

> **设计亮点**：独家攻略的 `+50.0` 只在 `bm25 > 0` 时才加，避免"搜故宫时手写的衡水湖攻略因为特权分挤掉故宫条目"。这是很有工程经验的设计！

---

## 四、FAISS + bge-small 稠密语义检索

### 4.1 核心概念

**稠密检索（Dense Retrieval）** = 把文本编码成**稠密向量**（每个维度都有值），然后计算向量间的距离/相似度。

```
"衡水湖怎么去" → [0.12, -0.87, 0.34, ...] (512维)
"衡水湖在哪里" → [0.11, -0.85, 0.36, ...] (512维)
内积（余弦相似度） ≈ 0.99  → 很相关！
```

### 4.2 FAISS 算法详解

**FAISS（Facebook AI Similarity Search）** 的核心是解决：  
> 在 N 个向量中，找到距离 query 向量最近的 K 个向量（K-NN 问题）

你项目用的是 **`IndexFlatIP`**（暴力精确检索，内积）：

| FAISS 索引类型 | 原理 | 速度 | 精度 | 适合规模 |
|---|---|---|---|---|
| `IndexFlatIP` | 暴力全量内积计算 | 慢 | 100% 精确 | < 10万（你的场景✅）|
| `IndexIVFFlat` | 先聚类分桶，只搜桶内 | 快 | 略有损失 | 百万级 |
| `IndexHNSW` | 图结构近邻搜索 | 极快 | ~99% | 千万级 |

**为什么你用 `IndexFlatIP` 是合理的？**：你的知识库只有 1840 个向量，暴力检索毫秒级，无需近似算法。

**为什么用内积(IP)而不是L2距离？**：因为你做了 `normalize_embeddings=True`——归一化后向量长度均为1，此时 `内积 = 余弦相似度`，计算语义相似性更准确。

### 4.3 bge-small-zh-v1.5 模型

- **全称**：BAAI (北京智源) General Embedding，中文小参数版
- **参数量**：~33M（很轻量，纯CPU可跑）
- **向量维度**：512维
- **训练方式**：对比学习（Contrastive Learning）——让语义相似的句子向量靠近，不相似的推远

### 4.4 构建索引的完整流程（你的 build_spot_vectors.py）

```python
# Step 1: 拼接检索文本（字段融合，覆盖更多语义）
text = f"{spot['city']} {spot['district']} {spot['spot_name']} {tags_str} {spot['content']}"

# Step 2: 加载 bge 模型，生成归一化 embedding
model = SentenceTransformer("BAAI/bge-small-zh-v1.5")
embeddings = model.encode(texts, normalize_embeddings=True)
embeddings = np.array(embeddings, dtype=np.float32)  # FAISS 要求 float32

# Step 3: 构建 IndexFlatIP 索引
dimension = embeddings.shape[1]  # 512
index = faiss.IndexFlatIP(dimension)
index.add(embeddings)  # 批量添加向量

# Step 4: 持久化
faiss.write_index(index, "faiss_index.bin")
```

### 4.5 ⚡ 手撕代码：从零实现简化版 FAISS 向量检索

面试官可能让你不用 FAISS 库，手写一个向量相似度检索：

```python
import numpy as np

class SimpleDenseRetriever:
    """
    简化版稠密检索器（纯 numpy 实现）
    等价于 FAISS IndexFlatIP
    """
    def __init__(self):
        self.vectors = None   # shape: (N, D)
        self.docs = []
    
    def add(self, texts: list[str], encoder):
        """建库：编码文本，存储向量"""
        embeddings = encoder.encode(texts, normalize_embeddings=True)
        self.vectors = np.array(embeddings, dtype=np.float32)
        self.docs = texts
    
    def search(self, query: str, encoder, top_k: int = 5):
        """检索：返回 top_k 个最相似结果"""
        # 1. 编码 query
        q_vec = encoder.encode([query], normalize_embeddings=True)
        q_vec = np.array(q_vec, dtype=np.float32)  # shape: (1, D)
        
        # 2. 计算余弦相似度（已归一化，内积 = 余弦）
        # self.vectors: (N, D), q_vec.T: (D, 1) → scores: (N, 1)
        scores = self.vectors @ q_vec.T  # 矩阵乘法，广播
        scores = scores.squeeze()        # (N,)
        
        # 3. argsort 降序取 top_k
        top_indices = np.argsort(scores)[::-1][:top_k]
        
        return [(self.docs[i], float(scores[i])) for i in top_indices]


# ---- 使用示例 ----
from sentence_transformers import SentenceTransformer

encoder = SentenceTransformer("BAAI/bge-small-zh-v1.5")
retriever = SimpleDenseRetriever()

corpus = ["衡水湖是著名湿地公园", "故宫博物院位于北京", "西湖是杭州的名片"]
retriever.add(corpus, encoder)

results = retriever.search("衡水有什么湖", encoder, top_k=2)
for doc, score in results:
    print(f"[{score:.4f}] {doc}")
```

**关键数学：余弦相似度**

```
cos(A, B) = (A · B) / (‖A‖ × ‖B‖)

归一化后 ‖A‖ = ‖B‖ = 1，所以：
cos(A, B) = A · B  ←  就是内积！
```

---

## 五、BM25 算法详解

### 5.1 BM25 来自哪里？

BM25 是 **Best Match 25** 的缩写，是 TF-IDF 的进化版，由 Robertson 等人在 1994 年提出，是传统信息检索的"压箱底"算法，至今仍是很多搜索引擎的基础。

### 5.2 完整数学公式

$$\text{Score}(D, Q) = \sum_{t \in Q} \text{IDF}(t) \cdot \frac{f(t,D) \cdot (k_1+1)}{f(t,D) + k_1 \cdot (1 - b + b \cdot \frac{|D|}{\text{avgdl}})}$$

| 符号 | 含义 |
|---|---|
| `f(t, D)` | 词 t 在文档 D 中的词频（TF）|
| `\|D\|` | 文档长度（词数）|
| `avgdl` | 语料库平均文档长度 |
| `k1` | 词频饱和参数，通常 1.2~2.0 |
| `b` | 长度惩罚参数，通常 0.75 |
| `IDF(t)` | 逆文档频率，稀有词权重更高 |

**直觉理解**：
- 词频越高分越高，但有**上限**（`k1`控制饱和）→ 一篇文章里出现100次"故宫"不会比10次好太多
- 文档越长**打折**（`b`控制）→ 长文章因为词多命中多，要惩罚一下
- 稀有词（IDF高）权重更大 → "庆林寺塔"比"景点"更能区分文档

### 5.3 你项目的 BM25 实现

你的 `_bm25_score()` 是一个**轻量化的手写版 BM25 变体**（没有算 IDF 和文档长度归一化，但思路相通）：

```python
def _bm25_score(query: str, spot: dict) -> float:
    score = 0.0
    
    # 等价 TF 匹配（不同字段权重不同）
    if city_core in query:      score += 5.0   # 城市命中
    if dist_core in query:      score += 5.0   # 区县命中
    if spot_name in query:      score += 15.0  # 景点名完整命中（最强信号）
    elif partial_match:         score += 8.0   # 景点名部分匹配
    for tag in spot['tags']:
        if tag in query:        score += 2.0   # 标签碰撞
    
    # 内容词频（简化版 TF）
    matched = sum(1 for ch in query if ch in content)
    score += float(matched / max(len(query), 1)) * 2.0
    
    return score
```

> **面试角度**：这是工程化的 BM25，通过人工赋权替代了 IDF（景点名比标签更稀有，所以权重更高），适合领域知识突出的垂直场景。

### 5.4 ⚡ 手撕代码：标准 BM25

```python
import math
from collections import Counter

class BM25:
    def __init__(self, corpus: list[list[str]], k1=1.5, b=0.75):
        """
        corpus: 已分词的文档列表，例如 [["故宫", "博物院"], ["西湖", "杭州"]]
        """
        self.k1 = k1
        self.b = b
        self.corpus = corpus
        self.N = len(corpus)
        self.avgdl = sum(len(d) for d in corpus) / self.N
        
        # 统计每个词出现在多少篇文档中（用于 IDF）
        self.df = {}
        for doc in corpus:
            for word in set(doc):
                self.df[word] = self.df.get(word, 0) + 1
    
    def idf(self, word: str) -> float:
        """计算 IDF（Robertson 版本）"""
        df = self.df.get(word, 0)
        return math.log((self.N - df + 0.5) / (df + 0.5) + 1)
    
    def score(self, doc: list[str], query: list[str]) -> float:
        """计算单个文档对 query 的 BM25 分数"""
        tf_map = Counter(doc)
        dl = len(doc)
        score = 0.0
        for word in query:
            if word not in tf_map:
                continue
            tf = tf_map[word]
            numerator = tf * (self.k1 + 1)
            denominator = tf + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
            score += self.idf(word) * numerator / denominator
        return score
    
    def search(self, query: list[str], top_k: int = 5) -> list[tuple]:
        """检索 top_k 个最相关文档"""
        scores = [(i, self.score(doc, query)) for i, doc in enumerate(self.corpus)]
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]


# ---- 使用示例 ----
corpus = [
    ["故宫", "博物院", "北京", "历史", "文化"],
    ["西湖", "杭州", "景点", "自然", "风景"],
    ["衡水湖", "湿地", "观鸟", "自然", "保护区"],
]

bm25 = BM25(corpus)
query = ["衡水", "湖", "自然"]
results = bm25.search(query, top_k=2)
for idx, score in results:
    print(f"[{score:.4f}] 文档{idx}: {corpus[idx]}")
```

---

## 六、意图分发（Intent Routing）

### 6.1 概念解释

**意图分发**就是让系统理解用户在说什么、想要什么，然后把请求转给最合适的处理模块。

类比：打客服电话 → "请按1查询账单，请按2办理业务" → 这就是规则式意图分发。你的项目用的是 **LLM 驱动的智能分发**。

### 6.2 你项目的意图分发架构

```
用户消息
    │
    ▼
travel_router（总控网关 Agent）
    │
    ├─ Step1: get_context() ← 读取对话记忆（城市/景点/偏好）
    │
    ├─ Step2: 意图识别 + 指代消解
    │    ├─ "那里的天气" → current_city="北京" → "北京的天气"
    │    └─ 判断意图类型：天气/景点/行程/闲聊
    │
    ├─ Step3: 路由转发（Tool Calling）
    │    ├─ 天气意图 → send_direct_message(target="weather_agent")
    │    ├─ 景点意图 → send_direct_message(target="spot_agent")
    │    ├─ 行程意图 → send_direct_message(target="plan_agent")
    │    └─ 闲聊 → send_channel_message(直接回复)
    │
    └─ Step4: save_context() ← 保存新提取的上下文信息
```

**关键词触发（早期版本）** vs **LLM意图识别（当前版本）**：

| 方式 | 实现 | 优点 | 缺点 |
|---|---|---|---|
| 关键词触发 | `if "天气" in query` | 无需大模型，极快 | 覆盖率低，易误触发 |
| LLM路由 | Prompt让模型判断意图并调用工具 | 泛化强，理解自然语言 | 需要大模型推理 |

你当前的 `travel_router.yaml` 中通过 **CoT（Chain-of-Thought）Prompt** 让 Qwen3.5-4B 自己判断意图并分发：

```yaml
# 摘自 travel_router.yaml
instruction: |
  结合记忆和对话历史，执行指代消解，然后转发给对应的子助手：
  - 天气相关 → send_direct_message(target_agent_id="weather_agent", ...)
  - 景点相关 → send_direct_message(target_agent_id="spot_agent", ...)
  - 行程相关 → send_direct_message(target_agent_id="plan_agent", ...)
```

---

## 七、面试题精选 & 标准答案

---

### Q1：什么是 RAG？它解决了什么问题？

**答**：RAG（Retrieval-Augmented Generation，检索增强生成）是将信息检索系统与大语言模型结合的框架。它解决两个核心问题：
1. **知识时效性**：LLM 训练数据有截止日期，RAG 通过检索实时/领域知识弥补
2. **幻觉问题（Hallucination）**：LLM 有时会"一本正经地胡说八道"，RAG 给模型提供真实的上下文来源，相当于给模型"开卷考试"

在我项目里，用户问"衡水湖适合带小孩吗"——如果纯靠 LLM，它可能编造答案。RAG 先从我的知识库里检索出独家手写攻略，再把真实内容喂给模型生成回答，答案更可靠。

---

### Q2：BM25 和 TF-IDF 的区别？

**答**：BM25 是 TF-IDF 的改进版，主要改进两点：
1. **词频饱和**：TF 是线性的，出现100次和10次差距很大；BM25 加了 k1 参数做饱和截断，词频到一定程度就不再有显著增益
2. **文档长度归一化**：长文档命中词多是"正常的"，BM25 用 b 参数对长文档打折；TF-IDF 没有这个机制

数学上：BM25 的 TF 部分 = `tf*(k1+1) / (tf + k1*(1-b+b*|D|/avgdl))`

---

### Q3：为什么向量检索要归一化？

**答**：归一化（L2 Norm）使所有向量长度为 1，这时**内积（点积）等价于余弦相似度**。
- 内积 = A·B，受向量长度影响大（长向量内积自然大）
- 余弦 = A·B / (|A|×|B|)，只关注方向，不关注长度，更适合衡量语义相似性
- 归一化后 |A|=|B|=1，直接算内积就等于余弦，计算更快

在我项目里：`model.encode(texts, normalize_embeddings=True)` + `faiss.IndexFlatIP` 实现的就是归一化内积=余弦相似度检索。

---

### Q4：FAISS IndexFlatIP 和 IndexIVFFlat 有什么区别？何时选哪个？

**答**：
- `IndexFlatIP`：暴力精确搜索，把 query 向量和库中**每一个**向量都算一遍内积，100% 精确，时间复杂度 O(N×D)
- `IndexIVFFlat`：先用 K-means 把向量聚成 n 个簇，检索时只在最近的几个簇里搜，速度快但可能漏掉边界向量（近似），时间复杂度 O(n×(N/n)×D)

**选择原则**：
- N < 10 万 → `IndexFlatIP`（我的项目 1840 条，毫秒级，用这个完全合理）
- N > 100 万 → `IndexIVFFlat` 或 `IndexHNSWFlat`

---

### Q5：Hybrid RAG 中如何融合两路分数？有哪些策略？

**答**：主要有三种策略：
1. **线性加权**（我项目用的）：`final = α × vec_score + β × bm25_score`，实现简单，可解释性强
2. **RRF（Reciprocal Rank Fusion）**：对两路各自排名取倒数加和 `score = 1/(k+rank_vec) + 1/(k+rank_bm25)`，对绝对分值不敏感，鲁棒性更好
3. **Learn-to-Rank**：训练一个小模型学习如何融合，效果最好但需要标注数据

我项目用的是线性加权，并且对独家攻略加了领域先验权重 (+50)，兼顾了召回效果和业务需求。

---

### Q6：你是如何评估 RAG 效果的？有哪些评估指标？

**答**：我在 `eval_rag.py` 里设计了自动化评估流程：
- **指标**：Top-1 准确率（第一条命中）和 Top-2 召回率（前两条命中一条即可）
- **测试集**：40+ 手工标注用例 + 200+ 大模型（Qwen3.5-4B）自动合成的测试用例（LLM-as-a-Judge 范式）
- **分类测试**：独家手写攻略命中、热门城市景点命中、语义模糊查询命中，分别统计覆盖不同场景

工业界还常用 **NDCG（归一化折损累计增益）**、**MRR（平均倒数排名）** 等指标。召回率 ≥ 80% 为我的 pass 标准。

---

### Q7：意图识别有哪些方法？你的项目用的是哪种？

**答**：
1. **规则/关键词分类**：if "天气" in text → 天气意图，简单快速，覆盖率低
2. **传统 ML 分类**：词袋 + SVM/朴素贝叶斯，需要标注数据
3. **预训练模型 Fine-tune**：BERT+分类头，效果好但资源重
4. **LLM Prompt 直接推理**（我的项目）：把意图识别任务写进 System Prompt，让模型输出对应的 Tool Call

我的 `travel_router.yaml` 用 CoT Prompt 让 Qwen3.5-4B 做意图识别 + 指代消解 + 路由，优点是泛化极强（用户说"那边天气咋样"，传统关键词法无法处理"那边"这个指代，LLM 可以结合记忆消解），缺点是多一次大模型调用，有延迟。

---

### Q8（进阶）：如果知识库有100万条数据，你会如何优化现在的架构？

**答**：
1. **向量检索**：从 `IndexFlatIP` 换成 `IndexIVFFlat` 或 `IndexHNSWFlat`，并配置 GPU 加速
2. **BM25 方面**：放弃全量遍历，改用 `Elasticsearch` 或 `whoosh` 等倒排索引引擎
3. **二阶段架构**：召回粗排（100条）→ 精排 Rerank 模型（Top-5）→ 生成
4. **缓存**：对热门 query 结果缓存，避免重复检索
5. **离线预计算**：常见 query 的检索结果异步预计算

---

*💡 Tips: 面试时结合项目代码来讲，比如直接说"我在 `spot_tools.py` 的 `_bm25_score` 函数里..."，会显得非常有实战底气。*

---

## 八、RAG 知识库 + 高德 POI 融合检索

### 8.1 为什么要融合？两类数据源的本质差异

| 维度 | 本地 RAG 知识库 | 高德地图 POI API |
|---|---|---|
| **数据类型** | 非结构化深度文本（攻略/避坑/美食）| 结构化实时数据（地址/评分/电话）|
| **实时性** | 静态（上次更新时的内容）| 实时（高德官方数据库持续更新）|
| **覆盖范围** | 1840 条精选景点 | 全国所有 POI |
| **内容深度** | 深度：游玩时长、预算细节、独家体验 | 浅：名称、位置、联系方式 |
| **擅长场景** | "衡水湖避坑指南"、"故城特色小吃" | "故城县有哪些景点"、"西湖电话多少" |

**核心互补逻辑**：
- 高德 API 知道你不知道的景点（新开、小众）
- RAG 知道高德 API 不会告诉你的内容（攻略、体验、避坑）

### 8.2 融合架构图

```
用户 Query: "故城县有什么好玩的？"
        │
        ├──── 并行发起两路请求 ────┐
        │                         │
        ▼                         ▼
📚 RAG 本地知识库              🗺️ 高德地图 POI API
(FAISS+BM25 混合检索)          (restapi.amap.com)
    │                              │
    │ 返回深度攻略                 │ 返回实时 POI 列表
    │ (含游玩时长/预算/避坑)       │ (含地址/评分/电话)
    │                              │
    └────────── 融合层 ────────────┘
                   │
                   ▼
        跨来源互补分析
        (检查高德 POI 名在 RAG 里有无攻略)
                   │
                   ▼
        🤖 LLM 生成最终回答
        (深度攻略 + 实时信息 双层结构)
```

### 8.3 实现代码（search_combined 核心逻辑）

这个函数已经实现在你的 `spot_tools.py` 里，并通过 `mcp_server.py` 注册为第 7 个 MCP tool：

```python
def search_combined(query: str) -> str:
    sections = []

    # ---- Part 1: RAG 本地知识库 ----
    rag_result = search_knowledge(query)
    if rag_result and "未找到" not in rag_result:
        sections.append("📚【本地深度攻略（RAG 知识库）】\n" + rag_result)

    # ---- Part 2: 高德 POI 实时数据 ----
    raw_poi_names = []
    resp = requests.get("https://restapi.amap.com/v3/place/text", params={...})
    pois = resp.json().get("pois", [])
    for poi in pois:
        raw_poi_names.append(poi["name"])
        # 格式化：名称、位置、评分、人均消费、电话
    sections.append("🗺️【实时景点数据（高德地图 POI）】\n" + poi_text)

    # ---- Part 3: 跨来源互补提示 ----
    # 检查高德返回的 POI 在 RAG 里有没有对应攻略
    for poi_name in raw_poi_names[:3]:
        matched = any(poi_name in d["spot_name"] for d in _knowledge_docs)
        if not matched:
            # 提示该景点暂无本地深度攻略，参考高德实时数据
            ...

    return "深度攻略 + 实时信息" 的融合结果
```

### 8.4 数据融合的三种工程策略

| 策略 | 说明 | 你的项目 |
|---|---|---|
| **串行查询** | 先查API，用API结果增强RAG的查询词 | 未实现（可扩展）|
| **并行查询 + 分区展示** | 同时查两路，各自独立展示 | ✅ `search_combined` 采用此策略 |
| **深度融合排序** | 把POI名注入BM25，做统一排序 | 部分实现（互补分析层）|

**并行 + 分区展示的优点**：
1. 来源可追溯（用户知道哪条是攻略、哪条是官方数据）
2. 延迟取决于更慢的那路，但两路同时发出
3. 信息量最大，不丢失任何信息

### 8.5 高德 POI API 技术细节

- **接口**：`GET /v3/place/text`，关键字 + 类型码检索
- **类型码 `110000`**：景点/旅游景区分类
- **`extensions=all`**：返回扩展信息，包含 `biz_ext.rating`（评分）和 `biz_ext.cost`（人均消费）
- **区县/城市自动识别**：query 中含"县/市/区"时，切换为"以地名为城市范围"的区域搜索

---

## 九、补充面试题（融合检索场景）

### Q9：你的系统里 RAG 和外部 API 是如何配合的？

**答**：项目里实现了三种使用模式：

1. **独立调用**：`search_local_knowledge`（纯RAG）和 `search_spots`（纯高德）是两个独立 MCP tool，LLM 根据需要自己判断用哪个
2. **融合调用**：`search_combined` 是新实现的融合工具，并行查两路，按"深度攻略 + 实时信息"双层结构呈现
3. **互补分析**：融合层还会检查高德返回的 POI 名称是否在本地 RAG 知识库里有对应攻略，没有的话标注"参考高德实时数据"

这个设计思路来自工业界的"在线+离线"混合知识库架构：离线知识库提供深度，在线 API 提供时效性。

---

### Q10：如何保证两路信息不冲突、不重复？

**答**：这是融合检索的核心工程挑战。我采用了**分区展示**策略（而非混合排序），原因如下：
1. **来源不同，不可比**：RAG 是文字攻略（有观点），高德是结构化数据（有评分），两者无法用同一分数排序
2. **避免"浓度稀释"**：如果混排，可能 5 条攻略被高德的 5 条地址信息稀释，用户反而找不到深度内容
3. **溯源透明**：每一层都有清晰的来源标注（📚本地知识库 / 🗺️高德地图），利于用户判断可信度

在需要统一排序的场景（如搜索引擎），可以用 RRF（倒数排名融合）来整合两路排名，不需要比较绝对分数。

---

*📌 更新记录：2026-03-11 新增"RAG + 高德 POI 融合检索"章节，对应代码实现：`spot_tools.py::search_combined` + `mcp_server.py::Tool 4b`*
