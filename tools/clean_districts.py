import json
import os
import re

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
FILE_PATH = os.path.join(DATA_DIR, 'spots_knowledge.json')

def clean_districts():
    print(f"Reading from: {FILE_PATH}")
    with open(FILE_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    fixes = 0
    for spot in data:
        # 手写攻略不受影响
        if spot.get('source') == '独家手写攻略':
            continue
            
        city = spot.get('city', '')
        dist = spot.get('district', '')
        old_dist = dist
        old_city = city
        
        # 1. 修复海南省特例（五指山市是省直辖县级市，但在三亚或海口的CSV里）
        if "五指山" in dist or "五指山" in spot.get('spot_name', ''):
            if city in ["三亚市", "海口市", "海南省五指山"]:
                spot['city'] = "五指山市"
                spot['district'] = ""
                fixes += 1
                continue
                
        # 2. 修复带有"省"的 district（如 "南省三沙市", "省直辖县级行政单位"）
        if "省" in dist:
            # 提取省后面的真实地名
            match = re.search(r'省(?:级|直辖)?(.+)', dist)
            if match:
                dist = match.group(1).strip()
            
            if "三沙" in dist:
                spot['city'] = "三沙市"
                spot['district'] = ""
                fixes += 1
                continue
            
        # 3. 修复 district 和 city 相同或包含 city 的情况
        if dist and city:
            # 如果 district 是 "三沙市"，city 是 "三沙市" -> 清空 district
            if city in dist and len(dist.replace(city, '')) < 2:
                spot['district'] = ""
                fixes += 1
            # 如果 district 是 "张家界市武陵源区"，city 是 "张家界市" -> 改为 "武陵源区"
            elif city in dist:
                spot['district'] = dist.replace(city, '')
                fixes += 1

        # 4. 修复乱码或过长、包含特殊字符的无效 district (比如一段地址)
        if len(dist) > 10 or any(c in dist for c in ['路', '街', '号', '交汇']):
            spot['district'] = ""
            fixes += 1
            
        # 5. 特殊处理"三沙市"
        if city == "三沙市":
            spot['district'] = ""
            if old_dist != "":  # 只有真正改了才算一次
                fixes += 1

    print(f"✅ 成功清洗和修正了 {fixes} 条行政区划错误数据。")
    
    with open(FILE_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        
    print(f"✅ 重新保存成功。")

if __name__ == "__main__":
    clean_districts()
