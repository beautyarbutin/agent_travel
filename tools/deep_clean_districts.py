"""
终极清洗脚本：district 字段只允许合法的中国行政区划格式。
合法格式：XX区、XX县、XX旗、XX市（县级市）
其他一律清空。
"""
import json
import os
import re

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
FILE_PATH = os.path.join(DATA_DIR, 'spots_knowledge.json')

# 合法的 district 必须满足：2-6个汉字 + 区/县/旗/市
VALID_DISTRICT_PATTERN = re.compile(r'^[\u4e00-\u9fff]{1,6}(?:区|县|旗)$')
# 县级市也合法：如 "义乌市"、"五指山市"
VALID_COUNTY_CITY_PATTERN = re.compile(r'^[\u4e00-\u9fff]{2,5}市$')

# 但这些是地级市不是县级市，排除掉
PREFECTURE_CITIES = {
    "北京市","天津市","上海市","重庆市","广州市","深圳市","武汉市","成都市","杭州市",
    "南京市","长沙市","郑州市","西安市","沈阳市","大连市","青岛市","济南市","福州市",
    "厦门市","昆明市","贵阳市","南宁市","太原市","合肥市","石家庄市","哈尔滨市",
    "长春市","兰州市","西宁市","银川市","呼和浩特市","乌鲁木齐市","拉萨市","海口市",
    "三亚市","衡水市","德州市","保定市","邢台市","邯郸市","廊坊市","唐山市","秦皇岛市",
    "张家口市","承德市","沧州市","泰安市","烟台市","威海市","潍坊市","淄博市","临沂市",
    "东营市","日照市","滨州市","菏泽市","枣庄市","聊城市","德阳市","绵阳市","泸州市",
    "宜宾市","自贡市","乐山市","南充市","达州市","广安市","遂宁市","内江市","资阳市",
    "眉山市","雅安市","巴中市","攀枝花市","广元市","苏州市","无锡市","常州市","南通市",
    "徐州市","连云港市","盐城市","扬州市","镇江市","泰州市","宿迁市","淮安市",
    "宁波市","温州市","嘉兴市","湖州市","绍兴市","金华市","衢州市","台州市","舟山市",
    "丽水市","珠海市","佛山市","东莞市","中山市","惠州市","江门市","汕头市","湛江市",
    "茂名市","肇庆市","梅州市","汕尾市","河源市","阳江市","清远市","韶关市","揭阳市",
    "潮州市","云浮市","株洲市","湘潭市","衡阳市","邵阳市","岳阳市","常德市","张家界市",
    "益阳市","娄底市","郴州市","永州市","怀化市","洛阳市","开封市","安阳市","新乡市",
    "焦作市","濮阳市","许昌市","漯河市","三门峡市","南阳市","商丘市","信阳市",
    "周口市","驻马店市","平顶山市","鹤壁市","十堰市","宜昌市","襄阳市","荆州市",
    "荆门市","黄冈市","孝感市","黄石市","咸宁市","随州市","鄂州市","南昌市","九江市",
    "景德镇市","萍乡市","新余市","鹰潭市","赣州市","吉安市","宜春市","抚州市","上饶市",
    "芜湖市","蚌埠市","淮南市","马鞍山市","淮北市","铜陵市","安庆市","黄山市","阜阳市",
    "宿州市","亳州市","滁州市","六安市","宣城市","池州市","漳州市","泉州市","三明市",
    "莆田市","南平市","龙岩市","宁德市","桂林市","柳州市","来宾市","梧州市","贺州市",
    "玉林市","百色市","钦州市","防城港市","北海市","崇左市","河池市","贵港市",
    "曲靖市","玉溪市","保山市","昭通市","丽江市","普洱市","临沧市","遵义市","六盘水市",
    "安顺市","毕节市","铜仁市","咸阳市","宝鸡市","渭南市","延安市","汉中市","榆林市",
    "安康市","商洛市","天水市","白银市","定西市","陇南市","平凉市","庆阳市","武威市",
    "张掖市","酒泉市","嘉峪关市","金昌市","吴忠市","固原市","石嘴山市","中卫市",
    "包头市","赤峰市","通辽市","鄂尔多斯市","巴彦淖尔市","乌兰察布市","锡林郭勒盟",
    "伊犁市","克拉玛依市","西双版纳市","大理市","万宁市","文昌市","琼海市","儋州市",
    "四平市","辽源市","白城市","松原市","白山市","通化市","延边市",
    "鞍山市","本溪市","丹东市","锦州市","营口市","阜新市","辽阳市","盘锦市","铁岭市",
    "朝阳市","葫芦岛市","抚顺市","齐齐哈尔市","牡丹江市","佳木斯市","大庆市",
    "鸡西市","鹤岗市","双鸭山市","伊春市","七台河市","黑河市","绥化市",
    "吴忠市","泉州市",
}

# 省名的残片列表（原始正则切割后可能残留为 district 的垃圾词）
PROVINCE_FRAGMENTS = {
    "东省", "南省", "北省", "西省", "建省", "江省", "湾省", "徽省",
    "海市", "津市", "门市",
    "蒙古", "蒙古自治区",
    "吾尔自治区", "吾尔",
    "壮族自治区",
    "回族自治区",
    "治州", "理州",  # 自治州残片
    "兴安岭地区",
    "古阿尔山市", "古阿尔山",
    "跨于",
    "沙市",  # 荆州沙市区特殊处理——"沙市"不是合法区县名
}

def is_valid_district(dist: str, city: str) -> bool:
    """判断 district 是否合法"""
    if not dist:
        return True  # 空的也合法（表示未知）
    
    # 黑名单：已知的残片垃圾词
    if dist in PROVINCE_FRAGMENTS:
        return False
    
    # 包含 "自治区" 或 "自治州" 的一律不合法（但"自治县"和"自治旗"是合法的）
    if "自治区" in dist or "自治州" in dist:
        return False
    
    # 包含 "省" 的一律不合法
    if "省" in dist:
        return False
    
    # district 里出现了城市名（跨城错误，如 district="丽江市" 但 city="凉山市"）
    if dist in PREFECTURE_CITIES:
        return False
    
    # 以"位于"开头（如"位于玉田县"）-> 尝试修正
    if dist.startswith("位于") and len(dist) > 3:
        remainder = dist[2:]
        if remainder.endswith("县") or remainder.endswith("区") or remainder.endswith("旗"):
            return remainder  # 修正为去掉"位于"
        return False
    
    # 以"州"开头的残片（如"州特克斯县"是"伊犁哈萨克自治州特克斯县"的残片）
    if dist.startswith("州") and len(dist) > 2:
        remainder = dist[1:]
        if remainder.endswith("县") or remainder.endswith("区") or remainder.endswith("市"):
            return remainder  # 修正
        return False
    
    # district 包含 city 的名字（如 city="丽水市", dist="丽水遂昌县" -> 应该是 "遂昌县"）
    city_core = city.replace("市", "")
    if len(city_core) >= 2 and dist.startswith(city_core) and len(dist) > len(city_core):
        # 尝试修正：去掉 city 前缀
        remainder = dist[len(city_core):]
        # remainder 至少 2 个字才算合法修正（否则就是 "东营区" -> "区" 这种 bug）
        if len(remainder) >= 2 and (remainder.endswith("县") or remainder.endswith("区") or remainder.endswith("旗") or remainder.endswith("市")):
            return remainder  # 返回修正后的值
        # 如果 remainder 太短，说明 district 就是 city+区 的格式（如"东营区"），这是合法的
        if remainder in ["区", "县", "旗"]:
            return True  # "东营区"完全合法，不修改
        return False
    
    # district 里包含"景区"、"地区"、"市区"
    if "景区" in dist or "地区" in dist or dist.endswith("市区"):
        return False
    
    # 含 "族" 但不含 "县/旗"（如 "畲族自治县" 是合法的，但 "苗族自治县" 需检查）
    # 自治县和自治旗是合法的
    if "族" in dist and not (dist.endswith("县") or dist.endswith("旗")):
        return False
    if VALID_DISTRICT_PATTERN.match(dist):
        return True
    
    # 县级市格式（XX市），但不能是地级市
    if VALID_COUNTY_CITY_PATTERN.match(dist) and dist not in PREFECTURE_CITIES:
        return True
    
    return False

def clean():
    with open(FILE_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    fixes = 0
    invalid_examples = []
    
    for spot in data:
        if spot.get('source') == '独家手写攻略':
            continue
        
        dist = spot.get('district', '')
        city = spot.get('city', '')
        
        if not dist:
            continue
        
        result = is_valid_district(dist, city)
        if result is True:
            continue  # 合法
        elif isinstance(result, str):
            # 返回了修正后的值
            invalid_examples.append(f"  [{city}] district=\"{dist}\" (景点:{spot.get('spot_name','')}) -> 修正为 \"{result}\"")
            spot['district'] = result
            fixes += 1
        else:
            invalid_examples.append(f"  [{city}] district=\"{dist}\" (景点:{spot.get('spot_name','')}) -> 清空")
            spot['district'] = ""
            fixes += 1
    
    print(f"✅ 终极清洗：修复了 {fixes} 条不合法的 district")
    print(f"\n不合法的 district 示例（前30个）：")
    for ex in invalid_examples[:30]:
        print(ex)
    
    # 统计清洗后还剩多少有效 district
    valid_count = sum(1 for s in data if s.get('district', ''))
    print(f"\n📊 清洗后：{valid_count} 条有有效 district，{len(data) - valid_count} 条 district 为空")
    
    with open(FILE_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    # 抽查有效的 district
    print(f"\n✅ 抽查清洗后保留的有效 district（前20个不同的）：")
    seen = set()
    count = 0
    for spot in data:
        d = spot.get('district', '')
        if d and d not in seen:
            seen.add(d)
            print(f"  [{spot['city']}] -> {d}")
            count += 1
            if count >= 20:
                break

if __name__ == "__main__":
    clean()
