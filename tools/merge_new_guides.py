import json
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
NEW_GUIDES_FILE = os.path.join(DATA_DIR, 'new_guides.json')
SPOTS_FILE = os.path.join(DATA_DIR, 'spots_knowledge.json')

def merge_new_guides():
    # 1. 加载新攻略
    with open(NEW_GUIDES_FILE, 'r', encoding='utf-8') as f:
        new_guides = json.load(f)
    
    # 2. 为新攻略添加 source 标签，确保它们能享受 BM25 特权分
    for guide in new_guides:
        guide['source'] = '独家手写攻略'
        
    print(f"✅ 成功加载 {len(new_guides)} 条新的独家手写攻略。")
    
    # 3. 加载现有的全部知识库
    with open(SPOTS_FILE, 'r', encoding='utf-8') as f:
        existing_spots = json.load(f)
        
    # 4. 查重：移除现有知识库中可能和新攻略 ID 重复的数据
    new_ids = {g['id'] for g in new_guides}
    existing_spots = [s for s in existing_spots if s.get('id') not in new_ids]
    
    # 5. 将新攻略放在最前面（或者和之前的5条独家攻略放在一起，总之放在前面）
    # 其实只要有 "source": "独家手写攻略"，无论放哪都会被特别提权。这里为了清晰，我们全都放在开头。
    
    # 把已有的独家手写攻略提出来
    existing_exclusives = [s for s in existing_spots if s.get('source') == '独家手写攻略']
    others = [s for s in existing_spots if s.get('source') != '独家手写攻略']
    
    # 合并：旧的独家 + 新的独家 + 其他Kaggle数据
    final_spots = existing_exclusives + new_guides + others
    
    print(f"📊 合并后：独家手写攻略共 {len(existing_exclusives) + len(new_guides)} 条，Kaggle等其他数据 {len(others)} 条。总计 {len(final_spots)} 条。")
    
    # 6. 写回 JSON
    with open(SPOTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(final_spots, f, ensure_ascii=False, indent=2)
        
    print("✅ spots_knowledge.json 已更新完成！")

if __name__ == '__main__':
    merge_new_guides()
