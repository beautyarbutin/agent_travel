"""
重装向量库脚本 (无损重组版)
由于之前已经具备了 5 条对应的景点向量数据，本脚本直接读取新的 JSON 配置将它们映射合并，不需要通过网络调用 Embedding API。
"""
import os
import json

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    storage_dir = os.path.join(base_dir, 'storage')
    data_file = os.path.join(base_dir, 'data', 'spots_knowledge.json')
    vectors_file = os.path.join(storage_dir, 'vectors.json')
    doc_file = os.path.join(storage_dir, 'doecment.json')
    
    print("1. 读取最新的结构化 JSON 数据...")
    with open(data_file, 'r', encoding='utf-8') as f:
        spots_data = json.load(f)
        
    print("2. 读取旧的纯张量列表 vectors.json ...")
    with open(vectors_file, 'r', encoding='utf-8') as f:
        raw_vectors = json.load(f)
        
    if len(spots_data) != len(raw_vectors):
        print(f"数量不匹配！JSON 有 {len(spots_data)} 个，但是向量有 {len(raw_vectors)} 个！无法合并。如果原格式已经是dict则跳过")
        if len(raw_vectors) > 0 and isinstance(raw_vectors[0], dict):
            print("看起来已经是包含 ID 的新版向量了。")
        return
        
    # 第一层是合并出含有 ID 的 vectors
    new_vectors_data = []
    for spot, vec in zip(spots_data, raw_vectors):
        new_vectors_data.append({
            "id": spot["id"],
            "vector": vec
        })
        
    try:
        print("3. 正式覆盖保存新格式...")
        # doecment.json 现在存的是结构化字典的 list
        with open(doc_file, 'w', encoding='utf-8') as f:
            json.dump(spots_data, f, ensure_ascii=False, indent=2)
            
        # vectors.json 现在存的是带 id 的字典 list，避免仅仅是浮点数组
        with open(vectors_file, 'w', encoding='utf-8') as f:
            json.dump(new_vectors_data, f, ensure_ascii=False, indent=2)
        print("✅ 组合成功！已完美在不消耗 API 的情况下完成 RAG 数据的升维挂载！")
    except Exception as e:
        print(f"❌ 保存失败: {e}")

if __name__ == "__main__":
    main()
