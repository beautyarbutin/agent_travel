"""
一步到位：将用户提供的所有手写攻略合并到 spots_knowledge.json
"""
import json
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
SPOTS_FILE = os.path.join(DATA_DIR, 'spots_knowledge.json')

def load_batch_files():
    """加载 data/ 下所有 batch*_guides.json 文件"""
    all_new = []
    for fn in sorted(os.listdir(DATA_DIR)):
        if fn.startswith('batch') and fn.endswith('.json'):
            fp = os.path.join(DATA_DIR, fn)
            with open(fp, 'r', encoding='utf-8') as f:
                batch = json.load(f)
            # 标记来源 + 修复 tags
            for g in batch:
                g['source'] = '独家手写攻略'
                if not g.get('tags') or not isinstance(g.get('tags'), list):
                    g['tags'] = []
            print(f"  📄 {fn}: {len(batch)} 条")
            all_new.extend(batch)
    return all_new

def main():
    # 1. 加载现有数据
    with open(SPOTS_FILE, 'r', encoding='utf-8') as f:
        all_data = json.load(f)
    
    old_exc = [s for s in all_data if s.get('source') == '独家手写攻略']
    kaggle = [s for s in all_data if s.get('source') != '独家手写攻略']
    print(f"📦 现有: {len(old_exc)} 条独家 + {len(kaggle)} 条 Kaggle = {len(all_data)} 总计")
    
    # 2. 加载所有批次文件
    print(f"\n📥 加载新批次:")
    new_guides = load_batch_files()
    if not new_guides:
        print("❌ data/ 下无 batch*_guides.json 文件！")
        return
    print(f"  共计: {len(new_guides)} 条新攻略")
    
    # 3. 去重
    new_ids = {g['id'] for g in new_guides}
    old_exc = [s for s in old_exc if s['id'] not in new_ids]
    kaggle = [s for s in kaggle if s.get('id','') not in new_ids]
    
    # 4. 合并：旧独家 + 新独家 + Kaggle
    final = old_exc + new_guides + kaggle
    exc_total = len([s for s in final if s.get('source') == '独家手写攻略'])
    
    print(f"\n📊 合并结果:")
    print(f"  独家手写攻略: {exc_total} 条")
    print(f"  Kaggle 数据:  {len(final) - exc_total} 条")
    print(f"  总计: {len(final)} 条")
    
    # 5. 写回
    with open(SPOTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(final, f, ensure_ascii=False, indent=2)
    print(f"\n✅ spots_knowledge.json 更新完成！")

if __name__ == '__main__':
    main()
