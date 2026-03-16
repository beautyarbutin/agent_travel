"""
构建景点知识库 FAISS 向量索引
使用 bge-small-zh-v1.5 本地 Embedding 模型（纯 CPU，无需 GPU）
"""
import os
import sys
import json
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_file = os.path.join(base_dir, 'data', 'spots_knowledge.json')
    storage_dir = os.path.join(base_dir, 'storage')
    os.makedirs(storage_dir, exist_ok=True)

    # 1. 读取结构化知识库
    print("📖 第1步：读取结构化 JSON 知识库...")
    with open(data_file, 'r', encoding='utf-8') as f:
        spots = json.load(f)
    print(f"   共 {len(spots)} 个景点条目")

    # 2. 拼接检索文本（把关键字段合并，让 embedding 能覆盖更多语义）
    print("📝 第2步：拼接检索文本...")
    texts = []
    for spot in spots:
        tags_str = " ".join(spot.get("tags", []))
        text = f"{spot['city']} {spot['district']} {spot['spot_name']} {tags_str} {spot['content']}"
        texts.append(text)

    # 3. 加载 bge-small-zh-v1.5 模型并生成 embedding
    print("\n🤖 第3步：加载 bge-small-zh-v1.5 本地 Embedding 模型...")
    print("   （首次运行会自动下载模型，约 90MB，请稍等）")
    model = SentenceTransformer("BAAI/bge-small-zh-v1.5")
    
    print("🧮 第4步：生成向量 embeddings...")
    embeddings = model.encode(texts, show_progress_bar=True, normalize_embeddings=True)
    embeddings = np.array(embeddings, dtype=np.float32)
    print(f"   向量维度: {embeddings.shape}")

    # 4. 构建 FAISS 索引
    print("🗂️ 第5步：构建 FAISS 向量索引...")
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatIP(dimension)  # 内积（因为已归一化，等价于余弦相似度）
    index.add(embeddings)
    print(f"   索引中共 {index.ntotal} 个向量")

    # 5. 保存
    faiss_path = os.path.join(storage_dir, 'faiss_index.bin')
    doc_path = os.path.join(storage_dir, 'doecment.json')
    
    faiss.write_index(index, faiss_path)
    with open(doc_path, 'w', encoding='utf-8') as f:
        json.dump(spots, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 构建完成！")
    print(f"   FAISS 索引: {faiss_path}")
    print(f"   结构化文档: {doc_path}")
    print(f"   向量维度: {dimension}, 条目数: {len(spots)}")

if __name__ == "__main__":
    main()
