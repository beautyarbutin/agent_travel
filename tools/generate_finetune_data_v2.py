"""
OpenAgents 旅游助手 - 高质量 Tool-Calling 训练数据生成器 v2
目标：生成 1500+ 条多样化、高质量的工具调用训练数据

改进点（对比 v1）：
1. 更多调用链模式（20+种，不是8种）
2. 多轮追问场景
3. 异常/边界场景
4. 灵活的对话长度（3-11轮）
5. 更丰富的问题模板和城市覆盖
6. 输出格式：LLaMA-Factory ShareGPT (gpt + tool_calls)
"""
import json
import random
import os

random.seed(42)

# =====================================================================
# 工具定义
# =====================================================================
TOOLS = json.dumps([
    {"name": "get_weather", "description": "获取指定城市的实时天气信息", "parameters": {"type": "object", "properties": {"city": {"type": "string", "description": "城市名称"}}, "required": ["city"]}},
    {"name": "search_spots", "description": "搜索指定城市或地区的景点信息（高德地图POI）", "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "地名或景点名"}}, "required": ["query"]}},
    {"name": "get_driving_route", "description": "获取两地之间的驾车路线规划", "parameters": {"type": "object", "properties": {"origin": {"type": "string", "description": "出发地"}, "destination": {"type": "string", "description": "目的地"}}, "required": ["origin", "destination"]}},
    {"name": "search_local_knowledge", "description": "搜索本地RAG知识库的深度攻略", "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "景点名或问题"}}, "required": ["query"]}},
    {"name": "search_combined", "description": "融合检索：同时查RAG知识库和高德POI", "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "用户问题"}}, "required": ["query"]}},
    {"name": "save_context", "description": "保存用户对话上下文到记忆", "parameters": {"type": "object", "properties": {"current_city": {"type": "string"}, "current_spot": {"type": "string"}, "travel_party": {"type": "string"}, "preferences": {"type": "string"}, "notes": {"type": "string"}}}},
    {"name": "get_context", "description": "读取对话上下文记忆", "parameters": {"type": "object", "properties": {}}},
    {"name": "send_direct_message", "description": "转发给指定子Agent处理", "parameters": {"type": "object", "properties": {"target_agent_id": {"type": "string"}, "text": {"type": "string"}}, "required": ["target_agent_id", "text"]}},
    {"name": "send_channel_message", "description": "发送消息到公共频道", "parameters": {"type": "object", "properties": {"channel": {"type": "string"}, "text": {"type": "string"}}, "required": ["channel", "text"]}},
    {"name": "reply_channel_message", "description": "回复频道消息", "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
], ensure_ascii=False)

# =====================================================================
# System Prompts
# =====================================================================
ROUTER_SYSTEM = (
    "# 最高优先级规则（违反=失败）\n"
    "你必须通过调用工具来完成任务！禁止输出纯文本！禁止调用finish工具！\n\n"
    "你是旅游小助手的总控网关。收到用户消息后，判断意图并执行对应操作。\n\n"
    "## 记忆系统操作流程\n"
    "第一步：调用 get_context 读取上下文记忆。\n"
    "第二步：指代消解+意图识别+转发（天气→weather_agent，景点→spot_agent，行程→plan_agent，闲聊→send_channel_message）。\n"
    "第三步：如果出现新信息，调用 save_context 保存。"
)

WEATHER_SYSTEM = (
    "你是\"天气助手\"，专门回答天气相关问题。\n"
    "你必须使用 get_weather 工具获取真实天气数据，绝对不要自己编造天气信息！\n"
    "步骤：1.调用get_context获取记忆 2.调用get_weather获取天气 3.调用reply_channel_message回复用户\n"
    "绝对不要直接输出纯文本回答！"
)

SPOT_SYSTEM = (
    "你是\"景点助手\"，专门负责景点推荐和深度知识解答。\n"
    "你必须调用工具获取真实数据，绝对不要自己编造！\n"
    "步骤：1.调用get_context 2.调用search_spots或search_local_knowledge 3.调用reply_channel_message回复\n"
    "绝对不要直接输出纯文本回答！"
)

PLAN_SYSTEM = (
    "你是\"行程助手\"，专门负责行程规划。\n"
    "必须调用 get_driving_route 工具获取真实路线数据，禁止自行编造任何距离或耗时信息。\n"
    "步骤：1.调用get_context 2.调用get_driving_route 3.调用reply_channel_message回复\n"
    "绝对不要直接输出纯文本回答！"
)

# =====================================================================
# 素材库（大幅扩充）
# =====================================================================
CITIES = [
    "北京", "上海", "广州", "深圳", "成都", "杭州", "南京", "西安",
    "重庆", "武汉", "长沙", "青岛", "大连", "厦门", "桂林", "丽江",
    "三亚", "苏州", "天津", "昆明", "贵阳", "兰州", "太原", "合肥",
    "南昌", "福州", "哈尔滨", "长春", "沈阳", "郑州", "济南", "石家庄",
    "衡水", "故城县", "如皋市", "庆云县", "德州", "南通", "拉萨",
    "敦煌", "洛阳", "开封", "黄山", "张家界", "九寨沟", "乌镇",
]

SPOTS = {
    "北京": ["故宫", "长城", "颐和园", "天坛", "圆明园", "南锣鼓巷", "798艺术区"],
    "上海": ["外滩", "东方明珠", "豫园", "迪士尼", "城隍庙", "田子坊"],
    "成都": ["大熊猫基地", "宽窄巷子", "锦里", "都江堰", "武侯祠", "春熙路"],
    "杭州": ["西湖", "灵隐寺", "千岛湖", "宋城", "西溪湿地"],
    "西安": ["兵马俑", "大雁塔", "华清宫", "钟楼", "回民街", "城墙"],
    "重庆": ["洪崖洞", "解放碑", "磁器口", "长江索道", "武隆天坑"],
    "南京": ["中山陵", "夫子庙", "玄武湖", "明孝陵", "总统府"],
    "厦门": ["鼓浪屿", "南普陀寺", "曾厝垵", "环岛路", "厦门大学"],
    "桂林": ["漓江", "阳朔", "象鼻山", "龙脊梯田"],
    "丽江": ["丽江古城", "玉龙雪山", "泸沽湖", "束河古镇"],
    "衡水": ["衡水湖", "武强年画博物馆", "冀州古城"],
    "故城县": ["故城大运河", "庆林寺塔"],
    "庆云县": ["庆云海岛金山寺", "月亮湾"],
    "洛阳": ["龙门石窟", "白马寺", "洛阳博物馆"],
    "黄山": ["黄山风景区", "宏村", "西递"],
}

PARTIES = ["一个人", "带小孩", "情侣", "和朋友", "带老人", "全家", "带父母", "闺蜜团", "同事团建"]
PREFERENCES = ["喜欢历史古迹", "喜欢自然风光", "不喜欢爬山", "喜欢美食", "喜欢拍照打卡", "预算有限", "喜欢安静", "想体验当地文化", "想看夜景", "喜欢户外运动"]
BUDGETS = ["500以内", "1000左右", "不限预算", "2000以内", "学生党穷游"]
DAYS = [1, 2, 3, 4, 5, 7]

# 问题模板（大幅扩充）
WEATHER_QS = [
    "{city}天气怎么样", "{city}今天天气如何", "{city}现在多少度",
    "{city}会不会下雨", "帮我查一下{city}的天气", "{city}冷不冷",
    "明天去{city}穿什么衣服好", "{city}天气好吗", "查看{city}今日天气",
    "{city}这个周末天气如何", "去{city}需要带伞吗", "{city}风大不大",
    "{city}最近天气怎么样", "{city}适合出行吗", "{city}温度高不高",
    "想去{city}，天气配合吗", "{city}紫外线强吗", "{city}有没有雾霾",
    "帮看看{city}明天天气", "{city}今天适合户外吗",
]

SPOT_QS = [
    "{city}有什么好玩的", "{city}有哪些景点", "{city}旅游推荐",
    "推荐一下{city}的景点", "{city}有什么值得去的地方", "{city}哪里好玩",
    "{city}必去的景点有哪些", "去{city}玩去哪些地方",
    "{city}有什么适合{party}的景点", "{city}最值得去的三个地方",
    "第一次去{city}该去哪", "{city}有什么免费的景点", "{city}小众景点推荐",
    "{city}哪个景点最值得去", "{city}有什么网红打卡地", "去{city}必打卡的地方",
    "{city}有适合老人去的景点吗", "{city}周边有什么好玩的",
]

DEEP_SPOT_QS = [
    "{spot}怎么玩", "{spot}攻略", "{spot}有什么好吃的",
    "{spot}值得去吗", "{spot}门票多少钱", "去{spot}要注意什么",
    "{spot}有什么特色", "{spot}避坑指南", "{spot}最佳游览时间",
    "{spot}停车方便吗", "{spot}附近有什么酒店", "{spot}需要预约吗",
    "{spot}适合带孩子去吗", "{spot}有什么纪念品", "{spot}逛多久合适",
    "{spot}附近美食推荐", "{spot}和{spot2}哪个更值得去",
]

ROUTE_QS = [
    "从{a}到{b}怎么走", "从{a}开车到{b}多远", "{a}到{b}的驾车路线",
    "从{a}去{b}怎么去", "{a}自驾到{b}要多久", "帮我规划从{a}到{b}的路线",
    "{a}到{b}自驾路线", "从{a}出发到{b}走高速多远",
    "{a}到{b}怎么走最快", "自驾从{a}到{b}过路费多少",
]

PLAN_QS = [
    "帮我规划{city}{n}天行程", "{city}{n}日游怎么安排",
    "去{city}玩{n}天怎么安排", "{city}{n}天旅游攻略",
    "{city}周末两天怎么玩", "国庆去{city}怎么安排",
    "{party}去{city}玩{n}天，帮我规划一下",
    "预算{budget}，去{city}{n}天怎么安排",
]

CHAT_QS = [
    "你好", "谢谢你", "帮了大忙", "你是谁", "能帮我什么",
    "今天心情不错", "旅途愉快", "你真棒", "辛苦了",
    "你好厉害", "太感谢了", "下次再来找你", "晚安",
    "早上好", "有你真好", "能推荐个好去处吗",
]

PRONOUN_QS = [
    "这个城市天气怎么样", "那里有什么好玩的", "帮我规划那边的行程",
    "这个地方冷不冷", "那个城市有什么景点", "就那个地方怎么去",
    "它的门票多少钱", "那边有什么美食", "这附近还有啥景点",
    "那周边有酒店吗", "这地方适合带小孩吗",
]

MULTI_INTENT_QS = [
    "{city}天气怎么样，顺便推荐几个景点",
    "我想去{city}，先查下天气再推荐景点",
    "帮我看看{city}天气，还有从{a}怎么过去",
    "{city}有什么好玩的，帮我规划个{n}天行程",
]

# =====================================================================
# 辅助函数
# =====================================================================
def tc(name, arguments):
    """生成 gpt 消息（带 tool_calls）"""
    return {"from": "gpt", "value": "", "tool_calls": [{"name": name, "arguments": arguments}]}

def obs(value):
    """生成 observation 消息"""
    return {"from": "observation", "value": value}

def human(value):
    return {"from": "human", "value": value}

def fake_weather(city):
    temp = random.randint(-5, 38)
    descs = ["晴朗", "多云", "阴天", "小雨", "大雨", "小雪", "雾", "多云转晴", "阵雨"]
    return json.dumps({"city": city, "temp": temp, "feels_like": temp - random.randint(1, 4), "desc": random.choice(descs), "humidity": random.randint(30, 95), "wind_speed": round(random.uniform(1, 25), 1)}, ensure_ascii=False)

def fake_route(a, b):
    dist = random.randint(30, 1200)
    roads = random.sample(["G2京沪高速", "G3京台高速", "G15沈海高速", "G20青银高速", "G1京哈高速", "G30连霍高速", "G4京港澳高速", "G50沪渝高速", "G60沪昆高速", "G5京昆高速"], k=random.randint(2, 4))
    return json.dumps({"distance_km": dist, "duration_min": int(dist / 80 * 60), "roads": " → ".join(roads)}, ensure_ascii=False)

def fake_spots_result(city):
    spots = SPOTS.get(city, [f"{city}公园", f"{city}博物馆", f"{city}古镇"])
    return json.dumps({"count": len(spots), "spots": spots}, ensure_ascii=False)

def get_city_spots(city):
    return SPOTS.get(city, [f"{city}公园", f"{city}博物馆"])

def make_weather_reply(city, wd):
    if wd["temp"] < 5: advice = "🧥 天气寒冷，建议穿着羽绒服"
    elif wd["temp"] < 15: advice = "🧶 天气较凉，建议穿着外套"
    elif wd["temp"] < 25: advice = "👕 天气舒适，建议穿着长袖"
    else: advice = "☀️ 天气炎热，建议穿着短袖"
    return f"🌡️ {city}天气：{wd['desc']}，{wd['temp']}°C（体感{wd['feels_like']}°C），湿度{wd['humidity']}%，风速{wd['wind_speed']}km/h\n{advice}"

CHAT_REPLIES = {
    "你好": "你好呀！我是你的旅游小助手 🌟 有什么可以帮你的吗？",
    "谢谢你": "不客气～祝你旅途愉快！🎒✨", "帮了大忙": "能帮到你真开心！😊",
    "你是谁": "我是旅游小助手，可以帮你查天气、推荐景点、规划行程哦！🗺️",
    "能帮我什么": "我可以帮你查天气☀️、推荐景点🏛️、规划行程🗺️、查驾车路线🚗！",
    "今天心情不错": "心情好就该出去玩！要不要我帮你推荐个好去处？🌈",
    "旅途愉快": "谢谢～也祝你一路顺风！🎉", "你真棒": "谢谢夸奖！继续为你服务💪",
    "辛苦了": "为你服务是我的荣幸！😄", "你好厉害": "过奖了～有旅游问题随时问我！",
    "太感谢了": "能帮到你就好！祝玩得开心～🎊", "下次再来找你": "随时欢迎！一路顺风～🌟",
    "晚安": "晚安！明天有旅行计划记得找我哦～🌙", "早上好": "早上好！新的一天要去哪里玩呢？☀️",
    "有你真好": "你也很棒！有问题随时找我～❤️", "能推荐个好去处吗": "当然可以！你想去哪个城市或者什么类型的地方呢？🗺️",
}

dataset = []

def add(system, convs):
    dataset.append({"conversations": convs, "system": system, "tools": TOOLS})

# =====================================================================
# 1. Router 数据 (~500条)
# =====================================================================
print("生成 Router 数据...")

# 1a. 天气意图转发（有记忆 / 无记忆变化）
for _ in range(80):
    city = random.choice(CITIES)
    q = random.choice(WEATHER_QS).format(city=city)
    add(ROUTER_SYSTEM, [
        human(q),
        tc("get_context", {}), obs("暂无上下文记忆"),
        tc("send_direct_message", {"target_agent_id": "weather_agent", "text": q}), obs("消息已发送给weather_agent"),
        tc("save_context", {"current_city": city}), obs("上下文已保存"),
    ])

# 1a-2. 天气意图，已有记忆（不需要save）
for _ in range(30):
    city = random.choice(CITIES)
    q = random.choice(WEATHER_QS).format(city=city)
    memory = json.dumps({"current_city": city}, ensure_ascii=False)
    add(ROUTER_SYSTEM, [
        human(q),
        tc("get_context", {}), obs(memory),
        tc("send_direct_message", {"target_agent_id": "weather_agent", "text": q}), obs("消息已发送给weather_agent"),
    ])

# 1b. 景点意图转发
for _ in range(70):
    city = random.choice(CITIES)
    party = random.choice(PARTIES)
    templates = SPOT_QS.copy()
    q = random.choice(templates).format(city=city, party=party)
    add(ROUTER_SYSTEM, [
        human(q),
        tc("get_context", {}), obs("暂无上下文记忆"),
        tc("send_direct_message", {"target_agent_id": "spot_agent", "text": q}), obs("消息已发送给spot_agent"),
        tc("save_context", {"current_city": city}), obs("上下文已保存"),
    ])

# 1b-2. 深度景点问题（直接问某景点）
for _ in range(40):
    city = random.choice(list(SPOTS.keys()))
    spots_list = SPOTS[city]
    spot = random.choice(spots_list)
    spot2 = random.choice([s for s in spots_list if s != spot]) if len(spots_list) > 1 else spot
    q = random.choice(DEEP_SPOT_QS).format(spot=spot, spot2=spot2)
    add(ROUTER_SYSTEM, [
        human(q),
        tc("get_context", {}), obs("暂无上下文记忆"),
        tc("send_direct_message", {"target_agent_id": "spot_agent", "text": q}), obs("消息已发送给spot_agent"),
        tc("save_context", {"current_spot": spot}), obs("上下文已保存"),
    ])

# 1c. 路线意图转发
for _ in range(60):
    a, b = random.sample(CITIES, 2)
    q = random.choice(ROUTE_QS).format(a=a, b=b)
    add(ROUTER_SYSTEM, [
        human(q),
        tc("get_context", {}), obs("暂无上下文记忆"),
        tc("send_direct_message", {"target_agent_id": "plan_agent", "text": q}), obs("消息已发送给plan_agent"),
        tc("save_context", {"current_city": b}), obs("上下文已保存"),
    ])

# 1d. 行程规划转发（带偏好/预算等复杂信息）
for _ in range(50):
    city = random.choice(CITIES)
    n = random.choice(DAYS)
    party = random.choice(PARTIES)
    q = random.choice(PLAN_QS).format(city=city, n=n, party=party, budget=random.choice(BUDGETS))
    ctx = {"current_city": city, "travel_party": party}
    if random.random() > 0.5:
        pref = random.choice(PREFERENCES)
        q += f"，{pref}"
        ctx["preferences"] = pref
    add(ROUTER_SYSTEM, [
        human(q),
        tc("get_context", {}), obs("暂无上下文记忆"),
        tc("send_direct_message", {"target_agent_id": "plan_agent", "text": q}), obs("消息已发送给plan_agent"),
        tc("save_context", ctx), obs("上下文已保存"),
    ])

# 1e. 指代消解（需要从记忆中恢复信息）
for _ in range(60):
    city = random.choice(CITIES)
    pq = random.choice(PRONOUN_QS)
    memory = json.dumps({"current_city": city}, ensure_ascii=False)
    if "天气" in pq or "冷" in pq:
        target, resolved = "weather_agent", f"{city}天气怎么样"
    elif "好玩" in pq or "景点" in pq or "啥景点" in pq:
        target, resolved = "spot_agent", f"{city}有什么好玩的"
    elif "行程" in pq:
        target, resolved = "plan_agent", f"规划{city}的行程"
    elif "门票" in pq or "美食" in pq or "酒店" in pq or "小孩" in pq:
        target, resolved = "spot_agent", f"{city}" + pq.replace("那", "").replace("这", "").replace("它的", "")
    else:
        target, resolved = "plan_agent", f"从当前位置到{city}怎么去"
    add(ROUTER_SYSTEM, [
        human(pq),
        tc("get_context", {}), obs(memory),
        tc("send_direct_message", {"target_agent_id": target, "text": resolved}), obs(f"消息已发送给{target}"),
    ])

# 1f. 闲聊（直接回复，不转发）
for q_text, reply in CHAT_REPLIES.items():
    # 每个闲聊问题生成2条（有记忆和无记忆）
    add(ROUTER_SYSTEM, [
        human(q_text),
        tc("get_context", {}), obs("暂无上下文记忆"),
        tc("send_channel_message", {"channel": "general", "text": reply}), obs("消息已发送"),
    ])
    city = random.choice(CITIES)
    add(ROUTER_SYSTEM, [
        human(q_text),
        tc("get_context", {}), obs(json.dumps({"current_city": city}, ensure_ascii=False)),
        tc("send_channel_message", {"channel": "general", "text": reply}), obs("消息已发送"),
    ])

# 1g. 多意图（天气+景点 → 转发两个agent）
for _ in range(40):
    city = random.choice(CITIES)
    a = random.choice([c for c in CITIES if c != city])
    n = random.choice(DAYS)
    q = random.choice(MULTI_INTENT_QS).format(city=city, a=a, n=n)
    
    if "天气" in q and "景点" in q:
        add(ROUTER_SYSTEM, [
            human(q),
            tc("get_context", {}), obs("暂无上下文记忆"),
            tc("send_direct_message", {"target_agent_id": "weather_agent", "text": f"{city}天气怎么样"}), obs("消息已发送给weather_agent"),
            tc("send_direct_message", {"target_agent_id": "spot_agent", "text": f"推荐{city}的景点"}), obs("消息已发送给spot_agent"),
            tc("save_context", {"current_city": city}), obs("上下文已保存"),
        ])
    elif "天气" in q and "过去" in q:
        add(ROUTER_SYSTEM, [
            human(q),
            tc("get_context", {}), obs("暂无上下文记忆"),
            tc("send_direct_message", {"target_agent_id": "weather_agent", "text": f"{city}天气怎么样"}), obs("消息已发送给weather_agent"),
            tc("send_direct_message", {"target_agent_id": "plan_agent", "text": f"从{a}到{city}怎么走"}), obs("消息已发送给plan_agent"),
            tc("save_context", {"current_city": city}), obs("上下文已保存"),
        ])
    else:
        add(ROUTER_SYSTEM, [
            human(q),
            tc("get_context", {}), obs("暂无上下文记忆"),
            tc("send_direct_message", {"target_agent_id": "spot_agent", "text": f"{city}有什么好玩的"}), obs("消息已发送给spot_agent"),
            tc("send_direct_message", {"target_agent_id": "plan_agent", "text": f"帮我规划{city}{n}天行程"}), obs("消息已发送给plan_agent"),
            tc("save_context", {"current_city": city}), obs("上下文已保存"),
        ])

# 1h. 只需save_context不需要转发的场景
for _ in range(30):
    city = random.choice(CITIES)
    party = random.choice(PARTIES)
    pref = random.choice(PREFERENCES)
    info_qs = [
        f"我{party}，准备去{city}",
        f"我们打算去{city}，{pref}",
        f"下周要和{party}去{city}",
        f"计划去{city}玩，预算{random.choice(BUDGETS)}",
    ]
    q = random.choice(info_qs)
    ctx = {"current_city": city}
    if party != "一个人":
        ctx["travel_party"] = party
    if pref in q:
        ctx["preferences"] = pref
    add(ROUTER_SYSTEM, [
        human(q),
        tc("get_context", {}), obs("暂无上下文记忆"),
        tc("save_context", ctx), obs("上下文已保存"),
        tc("send_channel_message", {"channel": "general", "text": f"好的，已记录！需要我帮你查{city}的天气、景点还是规划行程呢？"}), obs("消息已发送"),
    ])

router_count = len(dataset)
print(f"  Router: {router_count} 条")

# =====================================================================
# 2. Weather Agent 数据 (~200条)
# =====================================================================
print("生成 Weather Agent 数据...")
before = len(dataset)

# 2a. 正常天气查询
for _ in range(100):
    city = random.choice(CITIES)
    q = random.choice(WEATHER_QS).format(city=city)
    wd_str = fake_weather(city)
    wd = json.loads(wd_str)
    reply = make_weather_reply(city, wd)
    add(WEATHER_SYSTEM, [
        human(q),
        tc("get_context", {}), obs("暂无上下文记忆"),
        tc("get_weather", {"city": city}), obs(wd_str),
        tc("reply_channel_message", {"text": reply}), obs("消息已发送"),
    ])

# 2b. 从记忆获取城市（模糊查询）
for _ in range(50):
    city = random.choice(CITIES)
    vague_qs = ["天气怎么样", "今天冷不冷", "需要带伞吗", "穿什么衣服好", "出门要防晒吗", "下雨了吗"]
    q = random.choice(vague_qs)
    memory = json.dumps({"current_city": city}, ensure_ascii=False)
    wd_str = fake_weather(city)
    wd = json.loads(wd_str)
    reply = make_weather_reply(city, wd)
    add(WEATHER_SYSTEM, [
        human(q),
        tc("get_context", {}), obs(memory),
        tc("get_weather", {"city": city}), obs(wd_str),
        tc("reply_channel_message", {"text": reply}), obs("消息已发送"),
    ])

# 2c. 天气工具返回异常
for _ in range(20):
    city = random.choice(CITIES)
    q = random.choice(WEATHER_QS).format(city=city)
    add(WEATHER_SYSTEM, [
        human(q),
        tc("get_context", {}), obs("暂无上下文记忆"),
        tc("get_weather", {"city": city}), obs("API请求失败，请稍后重试"),
        tc("reply_channel_message", {"text": f"抱歉，{city}的天气数据暂时获取失败，请稍后再试 🙏"}), obs("消息已发送"),
    ])

weather_count = len(dataset) - before
print(f"  Weather: {weather_count} 条")

# =====================================================================
# 3. Spot Agent 数据 (~200条)
# =====================================================================
print("生成 Spot Agent 数据...")
before = len(dataset)

# 3a. 搜索景点（search_spots）
for _ in range(70):
    city = random.choice(CITIES)
    q = random.choice(SPOT_QS).format(city=city, party=random.choice(PARTIES))
    spots_data = fake_spots_result(city)
    sd = json.loads(spots_data)
    spots_text = "\n".join([f"  {i+1}. 📍 {s}" for i, s in enumerate(sd["spots"])])
    reply = f"🏛️ {city}热门景点推荐：\n{spots_text}\n\n想了解哪个景点的详细攻略？"
    add(SPOT_SYSTEM, [
        human(q),
        tc("get_context", {}), obs("暂无上下文记忆"),
        tc("search_spots", {"query": f"{city}景点"}), obs(spots_data),
        tc("reply_channel_message", {"text": reply}), obs("消息已发送"),
    ])

# 3b. 深度攻略（search_local_knowledge）
for _ in range(50):
    city = random.choice(list(SPOTS.keys()))
    spot = random.choice(SPOTS[city])
    q = random.choice(DEEP_SPOT_QS[:8]).format(spot=spot, spot2=spot)
    knowledge = json.dumps({"spot": spot, "city": city, "content": f"{spot}是{city}著名景点，建议游玩2-3小时。", "tips": "建议提前预约门票，避开高峰。"}, ensure_ascii=False)
    reply = f"📖 {spot}深度攻略：\n{spot}是{city}著名景点，建议游玩2-3小时。\n💡 建议提前预约门票，避开高峰。"
    add(SPOT_SYSTEM, [
        human(q),
        tc("get_context", {}), obs("暂无上下文记忆"),
        tc("search_local_knowledge", {"query": f"{spot}攻略"}), obs(knowledge),
        tc("reply_channel_message", {"text": reply}), obs("消息已发送"),
    ])

# 3c. 融合检索（search_combined）
for _ in range(30):
    city = random.choice(list(SPOTS.keys()))
    q = f"{city}有什么好玩的，给我详细攻略"
    combined = json.dumps({"rag_results": [{"spot": s} for s in SPOTS[city][:3]], "poi_results": SPOTS[city]}, ensure_ascii=False)
    reply = f"📍 {city}综合攻略已整理好！推荐：{'、'.join(SPOTS[city][:3])}"
    add(SPOT_SYSTEM, [
        human(q),
        tc("get_context", {}), obs("暂无上下文记忆"),
        tc("search_combined", {"query": f"{city}旅游攻略"}), obs(combined),
        tc("reply_channel_message", {"text": reply}), obs("消息已发送"),
    ])

# 3d. 先POI再RAG（两步工具调用）
for _ in range(30):
    city = random.choice(list(SPOTS.keys()))
    spot = random.choice(SPOTS[city])
    q = f"{spot}值得去吗？给我详细攻略"
    spots_data = fake_spots_result(city)
    knowledge = json.dumps({"content": f"{spot}非常值得一去，建议预留半天时间。"}, ensure_ascii=False)
    reply = f"📖 {spot}绝对值得去！建议预留半天时间。详细攻略已为你准备好。"
    add(SPOT_SYSTEM, [
        human(q),
        tc("get_context", {}), obs("暂无上下文记忆"),
        tc("search_spots", {"query": spot}), obs(spots_data),
        tc("search_local_knowledge", {"query": f"{spot}攻略"}), obs(knowledge),
        tc("reply_channel_message", {"text": reply}), obs("消息已发送"),
    ])

# 3e. 从记忆获取城市
for _ in range(20):
    city = random.choice(list(SPOTS.keys()))
    q = random.choice(["附近有什么好玩的", "推荐个景点呗", "有什么好去处"])
    memory = json.dumps({"current_city": city}, ensure_ascii=False)
    spots_data = fake_spots_result(city)
    sd = json.loads(spots_data)
    reply = f"根据你在{city}，推荐：{'、'.join(sd['spots'][:3])}"
    add(SPOT_SYSTEM, [
        human(q),
        tc("get_context", {}), obs(memory),
        tc("search_spots", {"query": f"{city}景点"}), obs(spots_data),
        tc("reply_channel_message", {"text": reply}), obs("消息已发送"),
    ])

spot_count = len(dataset) - before
print(f"  Spot: {spot_count} 条")

# =====================================================================
# 4. Plan Agent 数据 (~200条)
# =====================================================================
print("生成 Plan Agent 数据...")
before = len(dataset)

# 4a. 驾车路线
for _ in range(100):
    a, b = random.sample(CITIES, 2)
    q = random.choice(ROUTE_QS).format(a=a, b=b)
    route_data = fake_route(a, b)
    rd = json.loads(route_data)
    reply = f"🚗 {a}→{b}：约{rd['distance_km']}公里，耗时约{rd['duration_min']}分钟\n🛣️ {rd['roads']}\n💡 出发前检查车况，注意安全！"
    add(PLAN_SYSTEM, [
        human(q),
        tc("get_context", {}), obs("暂无上下文记忆"),
        tc("get_driving_route", {"origin": a, "destination": b}), obs(route_data),
        tc("reply_channel_message", {"text": reply}), obs("消息已发送"),
    ])

# 4b. 从记忆获取起点
for _ in range(50):
    a, b = random.sample(CITIES, 2)
    q = f"从这里去{b}要多久"
    memory = json.dumps({"current_city": a}, ensure_ascii=False)
    route_data = fake_route(a, b)
    rd = json.loads(route_data)
    reply = f"🚗 从{a}到{b}：约{rd['distance_km']}公里，{rd['duration_min']}分钟"
    add(PLAN_SYSTEM, [
        human(q),
        tc("get_context", {}), obs(memory),
        tc("get_driving_route", {"origin": a, "destination": b}), obs(route_data),
        tc("reply_channel_message", {"text": reply}), obs("消息已发送"),
    ])

# 4c. 路线查询异常
for _ in range(20):
    a, b = random.sample(CITIES, 2)
    q = random.choice(ROUTE_QS).format(a=a, b=b)
    add(PLAN_SYSTEM, [
        human(q),
        tc("get_context", {}), obs("暂无上下文记忆"),
        tc("get_driving_route", {"origin": a, "destination": b}), obs("路线规划失败：未找到有效路线"),
        tc("reply_channel_message", {"text": f"抱歉，暂时无法规划{a}到{b}的路线，可能两地之间无法驾车直达 🙏"}), obs("消息已发送"),
    ])

plan_count = len(dataset) - before
print(f"  Plan: {plan_count} 条")

# =====================================================================
# 去重 & 保存
# =====================================================================
# 按用户问题去重
seen = set()
final = []
for d in dataset:
    q = d["conversations"][0]["value"]
    key = q + "|" + d["system"][:20]
    if key in seen:
        continue
    seen.add(key)
    final.append(d)

print(f"\n去重前: {len(dataset)} 条")
print(f"去重后: {len(final)} 条")

# 统计
from collections import Counter
seq_counter = Counter()
for d in final:
    seq = []
    for m in d["conversations"]:
        if m["from"] == "gpt":
            for t in m.get("tool_calls", []):
                seq.append(t["name"])
    seq_counter[" → ".join(seq)] += 1

print(f"工具调用序列种类: {len(seq_counter)} 种")

lens = Counter(len(d["conversations"]) for d in final)
print(f"对话长度分布:")
for l, c in sorted(lens.items()):
    print(f"  {l}轮: {c}条")

# 保存
OUT = r"d:\20251224\AI_Study\OpenAgents\data\lora_ready\01_tool_calling.json"
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(final, f, ensure_ascii=False, indent=2)

print(f"\n✅ 输出: {OUT}")
print(f"📊 总计: {len(final)} 条")

sys_counts = Counter()
for d in final:
    s = d["system"]
    if "总控网关" in s: sys_counts["router"] += 1
    elif "天气" in s: sys_counts["weather"] += 1
    elif "景点" in s: sys_counts["spot"] += 1
    elif "行程" in s: sys_counts["plan"] += 1
print(f"   Router: {sys_counts['router']}")
print(f"   Weather: {sys_counts['weather']}")
print(f"   Spot: {sys_counts['spot']}")
print(f"   Plan: {sys_counts['plan']}")
