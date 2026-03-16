# 2026-03-15 RAG 数据集增补记录

## 目标

在不推翻现有 RAG 结构的前提下，为景点知识库新增 2 个公开数据源，并重新构建 FAISS 索引。

本次新增来源：

1. `ConvLab/crosswoz`
2. `Kakuluk/Hong_Kong_Tour_Guide`

## 选择原因

### 1. `ConvLab/crosswoz`

- 中文旅游对话领域常用公开数据集
- 内含结构化景点库 `attraction_db.json`
- 数据字段较完整，包含地址、门票、游玩时长、周边景点、周边餐馆、周边酒店、地铁信息
- 能较自然地映射到当前项目的结构化 schema

### 2. `Kakuluk/Hong_Kong_Tour_Guide`

- 中文旅游问答数据
- 可补充当前库中较弱的“问答式攻略/交通说明/拍摄建议”表达
- 对香港场景形成补充，和现有大陆景点 CSV 数据源互补

## 为什么没有选之前提到的另一个 Kaggle 中国景点集

这次没有再导入 `China City Attraction Details` 一类的 Kaggle 景点表，是因为当前库里的 `Kaggle/去哪儿网` 主体数据已经与该类中国城市景点明细源高度重合。继续重复导入，重复样本会显著增多，但对实际召回提升有限。

## 新增脚本

新增导入脚本：

- [import_additional_rag_sources.py](/d:/20251224/AI_Study/OpenAgents/tools/import_additional_rag_sources.py)

它负责：

- 下载 `ConvLab/crosswoz`
- 读取 `data/attraction_db.json`
- 转换为当前统一 schema
- 下载 `Kakuluk/Hong_Kong_Tour_Guide`
- 过滤明显偏餐饮/泛区域问答
- 提取可落入景点知识库的条目
- 合并回 [spots_knowledge.json](/d:/20251224/AI_Study/OpenAgents/data/spots_knowledge.json)

## 统一后的 schema

两个新数据源都被转换为当前项目既有格式：

```json
{
  "id": "...",
  "city": "...",
  "district": "...",
  "spot_name": "...",
  "content": "...",
  "tags": ["..."],
  "duration": "...",
  "budget": "...",
  "rating": 4.0,
  "source": "..."
}
```

## 处理结果

处理后的中间文件：

- [crosswoz_attractions_processed.json](/d:/20251224/AI_Study/OpenAgents/data/datasets_rag/crosswoz_attractions_processed.json)
- [hongkong_tour_guide_processed.json](/d:/20251224/AI_Study/OpenAgents/data/datasets_rag/hongkong_tour_guide_processed.json)

最终合并后的知识库：

- [spots_knowledge.json](/d:/20251224/AI_Study/OpenAgents/data/spots_knowledge.json)

重新构建后的索引：

- [faiss_index.bin](/d:/20251224/AI_Study/OpenAgents/storage/faiss_index.bin)
- [doecment.json](/d:/20251224/AI_Study/OpenAgents/storage/doecment.json)

## 数量变化

本次新增：

- `CrossWOZ景点库`：465 条
- `香港旅游指南QA`：18 条

重建后总量：

- 总条目数：15723

来源分布：

- `Kaggle/去哪儿网`：14581
- `CrossWOZ景点库`：465
- `独家手写攻略`：347
- `China312地理数据集`：312
- `香港旅游指南QA`：18

## 样例

### CrossWOZ 样例

```json
{
  "city": "北京市",
  "district": "东城区",
  "spot_name": "故宫",
  "source": "CrossWOZ景点库"
}
```

### 香港旅游指南 QA 样例

```json
{
  "city": "香港特别行政区",
  "district": "",
  "spot_name": "太平山頂纜車",
  "source": "香港旅游指南QA"
}
```

## 实际执行

执行导入：

```powershell
python tools\import_additional_rag_sources.py
```

执行向量重建：

```powershell
python tools\build_spot_vectors.py
```

## 冒烟验证

已确认：

- 两个新来源都已写入 [spots_knowledge.json](/d:/20251224/AI_Study/OpenAgents/data/spots_knowledge.json)
- 两个新来源都已写入 [doecment.json](/d:/20251224/AI_Study/OpenAgents/storage/doecment.json)
- FAISS 索引已按新总量重建完成

## 当前残留问题

虽然新数据已经接入成功，但当前检索排序仍明显偏向 `独家手写攻略`。原因主要有两点：

1. [spot_tools.py](/d:/20251224/AI_Study/OpenAgents/tools/spot_tools.py) 中 `HANDWRITTEN_BONUS = 35.0` 偏重
2. 当前 BM25 风格打分仍较粗糙，不是严格标准 BM25

因此，新增数据已经“进库并进索引”，但在一些查询下未必能排到最前面。

例如冒烟查询：

- `海洋公园怎么玩`
- `蓝屋建筑群`
- `故宫 地铁 地址`

当前 top 结果仍常被 `独家手写攻略` 抢占。这说明下一步如果想让新增数据更容易被命中，重点不再是“加数据”，而是“调排序和拆源”。

## 后续建议

1. 降低 `HANDWRITTEN_BONUS`
2. 将 `独家手写攻略` 与公域景点库拆分排序
3. 对香港/北京等新来源增加按城市过滤的优先级
4. 后续再补 1 份区县级高质量中文景点攻略数据

## 注意

运行中的 agent 如果已经懒加载过旧索引，需要重启相关进程，才能读取新版本的 [faiss_index.bin](/d:/20251224/AI_Study/OpenAgents/storage/faiss_index.bin) 和 [doecment.json](/d:/20251224/AI_Study/OpenAgents/storage/doecment.json)。
