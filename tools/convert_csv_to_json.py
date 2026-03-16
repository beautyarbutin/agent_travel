"""
将 Kaggle 中国城市旅游景点 CSV 数据集转换为 RAG 知识库 JSON 格式
过滤条件：必须有"介绍"内容 且 评分 >= 3.5
"""
import os
import csv
import json
import re

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
CSV_DIR = os.path.join(DATA_DIR, 'archive', 'citydata')
OUTPUT_FILE = os.path.join(DATA_DIR, 'spots_knowledge.json')

# 从景点介绍中自动提取标签关键词
TAG_KEYWORDS = {
    "自然风景": ["湖", "山", "瀑布", "峡谷", "湿地", "森林", "草原", "花海", "溪", "泉"],
    "历史": ["古", "遗址", "历史", "朝", "年间", "纪念", "文物", "遗迹"],
    "寺庙": ["寺", "庙", "祠", "塔", "佛", "道观", "禅"],
    "古建筑": ["古城", "古镇", "古街", "古建", "城墙", "城楼", "牌坊"],
    "博物馆": ["博物馆", "展馆", "纪念馆", "展览"],
    "公园": ["公园", "广场", "花园", "植物园"],
    "美食": ["美食", "小吃", "特产", "餐厅", "饭店", "烧烤"],
    "夜景": ["夜景", "灯光", "夜市", "夜"],
    "亲子": ["亲子", "儿童", "孩子", "游乐", "乐园", "动物园", "水上"],
    "拍照": ["拍照", "拍摄", "打卡", "摄影", "机位"],
    "观鸟": ["鸟", "观鸟", "候鸟"],
    "古塔": ["塔"],
    "运河文化": ["运河", "大运河"],
    "免费": ["免费", "免门票", "不收费"],
    "红色旅游": ["革命", "烈士", "红色", "纪念"],
    "温泉": ["温泉", "泡汤"],
    "漂流": ["漂流", "水上"],
    "登山": ["登山", "爬山", "徒步", "攀登"],
    "海滨": ["海", "沙滩", "海滨", "海岸"],
    "古街": ["古街", "步行街", "老街"],
    "乘船": ["游船", "乘船", "坐船", "船游"],
}

def extract_tags(name: str, intro: str, tips: str) -> list:
    """从景点名称、介绍和小贴士中自动提取标签"""
    full_text = f"{name} {intro} {tips}"
    tags = set()
    for tag, keywords in TAG_KEYWORDS.items():
        for kw in keywords:
            if kw in full_text:
                tags.add(tag)
                break
    return sorted(list(tags))

def parse_budget(ticket_info: str) -> str:
    """从门票信息推算消费水平"""
    if not ticket_info or ticket_info.strip() in ['', '具体收费情况以现场公示为主']:
        return "未知"
    if "免费" in ticket_info:
        return "免费"
    # 尝试提取价格数字
    prices = re.findall(r'¥(\d+\.?\d*)', ticket_info)
    if prices:
        max_price = max(float(p) for p in prices)
        if max_price <= 30:
            return "低"
        elif max_price <= 100:
            return "中"
        else:
            return "高"
    return "未知"

def clean_address(addr_raw: str) -> tuple:
    """从地址字段提取纯地址和电话"""
    if not addr_raw:
        return "", ""
    # 去掉 "地址:" "电话:" 等标签
    addr = addr_raw.replace('\n', ' ').strip()
    addr = re.sub(r'地址[:：]', '', addr)
    addr = re.sub(r'电话[:：].*', '', addr)
    addr = re.sub(r'官网[:：].*', '', addr)
    return addr.strip(), ""

def process_all_csvs():
    """处理所有城市 CSV 文件"""
    all_spots = []
    city_count = 0
    skipped = 0
    
    csv_files = sorted([f for f in os.listdir(CSV_DIR) if f.endswith('.csv')])
    print(f"📂 发现 {len(csv_files)} 个城市 CSV 文件")
    
    for csv_file in csv_files:
        city_name = csv_file.replace('.csv', '')
        csv_path = os.path.join(CSV_DIR, csv_file)
        
        try:
            with open(csv_path, 'r', encoding='utf-8', errors='ignore') as f:
                reader = csv.DictReader(f)
                city_spots = 0
                
                for row in reader:
                    name = (row.get('名字') or '').strip()
                    intro = (row.get('介绍') or '').strip()
                    rating_str = (row.get('评分') or '').strip()
                    duration = (row.get('建议游玩时间') or '').strip()
                    tips = (row.get('小贴士') or '').strip()
                    ticket = (row.get('门票') or '').strip()
                    open_time = (row.get('开放时间') or '').strip()
                    address_raw = (row.get('地址') or '').strip()
                    
                    # === 过滤条件 ===
                    # 1. 必须有景点名
                    if not name:
                        skipped += 1
                        continue
                    # 2. 必须有介绍内容（至少50字才有价值）
                    if len(intro) < 50:
                        skipped += 1
                        continue
                    # 3. 评分 >= 3.5（过滤低质量景点）
                    try:
                        rating = float(rating_str) if rating_str and rating_str != '--' else 0
                    except ValueError:
                        rating = 0
                    if rating > 0 and rating < 3.5:
                        skipped += 1
                        continue
                    
                    # 去掉英文名（括号前的部分就是中文名）
                    cn_name = re.split(r'[A-Z]', name)[0].strip() if re.search(r'[A-Z]', name) else name
                    
                    # 拼接内容
                    content_parts = [intro]
                    if tips:
                        content_parts.append(f"小贴士：{tips}")
                    if open_time:
                        content_parts.append(f"开放时间：{open_time}")
                    content = " ".join(content_parts)
                    
                    # 提取标签
                    tags = extract_tags(cn_name, intro, tips)
                    if not tags:
                        tags = ["景点"]
                    
                    # 提取地址
                    addr, _ = clean_address(address_raw)
                    
                    # 推断区县（从地址中提取）
                    district = ""
                    dist_match = re.search(r'([\u4e00-\u9fff]{2,4}(?:县|区|市))', addr)
                    if dist_match:
                        district = dist_match.group(1)
                    
                    spot_id = f"kaggle_{city_name}_{city_spots+1:03d}"
                    
                    spot = {
                        "id": spot_id,
                        "city": city_name if city_name.endswith("市") else f"{city_name}市",
                        "district": district,
                        "spot_name": cn_name,
                        "content": content,
                        "tags": tags,
                        "duration": duration if duration else "未知",
                        "budget": parse_budget(ticket),
                        "rating": rating,
                        "source": "Kaggle/去哪儿网"
                    }
                    
                    all_spots.append(spot)
                    city_spots += 1
                
                if city_spots > 0:
                    city_count += 1
                    
        except Exception as e:
            print(f"  ⚠️ 处理 {csv_file} 出错: {e}")
            continue
    
    print(f"\n📊 处理结果:")
    print(f"   城市数: {city_count}")
    print(f"   有效景点数: {len(all_spots)}")
    print(f"   过滤掉的低质量条目: {skipped}")
    
    # 按评分排序，高分在前
    all_spots.sort(key=lambda x: x.get('rating', 0), reverse=True)
    
    # === 合并原始手写独家攻略（保留在最前面，优先级最高）===
    ORIGINAL_SPOTS = [
        {"id":"spot_gucheng_001","city":"衡水市","district":"故城县","spot_name":"运河街区二道街","content":"运河街区二道街详细攻略：不仅是历史街区，而且是最具运河风情的地方。独家避坑指南：周末下午人最多，建议傍晚时分（18:00左右）去可以拍到绝佳的夕阳，晚上灯光亮起后别有一番风味。必吃美食：街角的'老树皮烤肉'非常地道，还有不能错过的故城熏肉，建议去当地人常去的老字号购买。最佳游玩路线：从南入口进，沿石板路顺时针游览，中途可以在老茶馆歇脚。","tags":["古街","历史","拍照","夜景","小吃","运河文化","夕阳"],"duration":"2-3小时","budget":"低","rating":5.0,"source":"独家手写攻略"},
        {"id":"spot_gucheng_002","city":"衡水市","district":"故城县","spot_name":"庆林寺塔","content":"庆林寺塔考古探险：全国重点文物保护单位。深度知识点：始建于北宋，这座八角形密檐式砖塔最独特的地方在于其内部中空，而且没有任何木制结构，全靠青砖错缝叠砌。拍摄机位建议：下午3点左右阳光侧方照射时，塔雕的轮廓最立体。村里周边没什么商业，所以建议自带水和干粮。","tags":["古建筑","历史","文物","北宋","拍照","探险","古塔"],"duration":"1小时","budget":"免费","rating":5.0,"source":"独家手写攻略"},
        {"id":"spot_hengshui_001","city":"衡水市","district":"桃城区","spot_name":"衡水湖","content":"衡水湖深度观鸟指南：'京津冀最美湿地'。只坐船游湖是外行玩法！资深玩法推荐：早上6点是最佳观鸟时间（特别是10月至次年3月候鸟迁徙季），带上望远镜，去湖的东北角的芦苇荡，能看到极其珍稀的青头潜鸭。美食推荐：衡水湖的'全鱼宴'非常出名，一定要试试'凉拌鱼丝'和'红烧带鱼'，但湖边的饭店价格偏高，建议往市区方向走一两公里找当地馆子。","tags":["自然风景","湖泊","观鸟","湿地","乘船","美食","全鱼宴","自然摄影"],"duration":"半天","budget":"中","rating":5.0,"source":"独家手写攻略"},
        {"id":"spot_shijiazhuang_001","city":"石家庄市","district":"正定县","spot_name":"正定古城","content":"正定古城特种兵路线：本地人推荐路线：隆兴寺（大佛寺） -> 旺泉古街吃午饭 -> 临济寺 -> 开元寺 -> 晚上去南门看夜景。绝佳看点：隆兴寺的'倒座观音'被鲁迅称为东方美神，不要只在正面拍照，一定要走到背面欣赏。免费福利：正定古城所有停车场目前全部免费，绝对对自驾游非常友好！美食必吃：正定八大碗（推荐宋记八大碗）、崩肝、烧麦。","tags":["古城","寺庙","古建","历史","夜景","步行街","免停车费","自驾","美食"],"duration":"1天","budget":"中","rating":5.0,"source":"独家手写攻略"},
        {"id":"spot_qingyun_001","city":"德州市","district":"庆云县","spot_name":"海岛金山寺","content":"海岛金山寺静心之旅：深度体验：虽然是重建的寺庙，但地下有一个规模庞大的地宫，非常震撼，里面有无数佛像和壁画，夏天进去非常凉快。上香礼仪：门口有免费领香点，不用在外面买高价香！周边配套：逛完可以去旁边的紫金湖湿地公园散步，生态非常好。如果不喜欢寺庙，也可以去附近的侏罗纪乐园月亮城堡，适合带小孩的家庭。","tags":["寺庙","祈福","地宫","壁画","公园散步","亲子"],"duration":"2-3小时","budget":"免费","rating":5.0,"source":"独家手写攻略"},
    ]
    
    # 手写攻略插入到最前面（最高优先级）
    all_spots = ORIGINAL_SPOTS + all_spots
    
    print(f"\n📎 合并 {len(ORIGINAL_SPOTS)} 条独家手写攻略（优先级最高）")
    
    # 保存
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(all_spots, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 已保存到: {OUTPUT_FILE}")
    print(f"   文件大小: {os.path.getsize(OUTPUT_FILE) / 1024:.1f} KB")
    print(f"   总条目数: {len(all_spots)} (手写:{len(ORIGINAL_SPOTS)} + Kaggle:{len(all_spots)-len(ORIGINAL_SPOTS)})")
    
    # 打印前10条预览
    print(f"\n📋 前10条预览:")
    for i, s in enumerate(all_spots[:10]):
        src = s.get('source', '')
        print(f"   {i+1}. [{s['city']}] {s['spot_name']} ({src}, 标签:{','.join(s['tags'][:3])})")

if __name__ == "__main__":
    process_all_csvs()
