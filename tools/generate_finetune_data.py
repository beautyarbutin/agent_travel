"""
OpenAgents 旅游助手 - LLaMA-Factory 微调数据集生成器
格式：ShareGPT（LLaMA-Factory 标准 function_call / observation 格式）
目标：训练 Qwen3.5-4B 在 Agent 场景下 100% 可靠地调用 MCP 工具
"""
import json
import random
import os

random.seed(42)

# =========================================================================
# 工具定义 (和 mcp_server.py 中注册的 6 个工具一致)
# =========================================================================
TOOLS = json.dumps([
    {
        "name": "get_weather",
        "description": "获取指定城市的实时天气信息，包括温度、天气状况、风速、湿度和穿衣建议。",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string", "description": "城市名称"}},
            "required": ["city"]
        }
    },
    {
        "name": "search_spots",
        "description": "搜索指定城市或地区的景点信息。使用高德地图 POI 搜索 API。",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "地名或景点名"}},
            "required": ["query"]
        }
    },
    {
        "name": "get_driving_route",
        "description": "获取两地之间的驾车路线规划，包括距离、耗时和途经道路。",
        "parameters": {
            "type": "object",
            "properties": {
                "origin": {"type": "string", "description": "出发地名称"},
                "destination": {"type": "string", "description": "目的地名称"}
            },
            "required": ["origin", "destination"]
        }
    },
    {
        "name": "search_local_knowledge",
        "description": "搜索本地景点深度游玩指南（RAG知识库），获取深度攻略、避坑提示等独家信息。",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "景点名称或问题"}},
            "required": ["query"]
        }
    },
    {
        "name": "save_context",
        "description": "保存/更新用户对话上下文到本地记忆文件（增量更新）。",
        "parameters": {
            "type": "object",
            "properties": {
                "current_city": {"type": "string"},
                "current_spot": {"type": "string"},
                "travel_party": {"type": "string"},
                "preferences": {"type": "string"},
                "notes": {"type": "string"}
            }
        }
    },
    {
        "name": "get_context",
        "description": "读取当前对话上下文记忆，获取用户之前提到的城市、景点、偏好等。",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "send_direct_message",
        "description": "将消息直接转发给指定的子Agent处理。",
        "parameters": {
            "type": "object",
            "properties": {
                "target_agent_id": {"type": "string"},
                "text": {"type": "string"}
            },
            "required": ["target_agent_id", "text"]
        }
    },
    {
        "name": "send_channel_message",
        "description": "发送消息到公共频道。",
        "parameters": {
            "type": "object",
            "properties": {
                "channel": {"type": "string"},
                "text": {"type": "string"}
            },
            "required": ["channel", "text"]
        }
    },
    {
        "name": "reply_channel_message",
        "description": "回复当前频道的最新消息。",
        "parameters": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"]
        }
    }
], ensure_ascii=False)


# =========================================================================
# System Prompts (和 YAML 配置一致)
# =========================================================================
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


# =========================================================================
# 辅助函数：构建一条 function_call
# =========================================================================
def fc(name: str, arguments: dict) -> dict:
    """生成一条 function_call 对话记录"""
    return {"from": "function_call", "value": json.dumps({"name": name, "arguments": arguments}, ensure_ascii=False)}


def obs(value: str) -> dict:
    """生成一条 observation（工具返回）对话记录"""
    return {"from": "observation", "value": value}


# =========================================================================
# 城市/景点/偏好 素材库
# =========================================================================
CITIES = [
    "衡水", "北京", "上海", "广州", "深圳", "成都", "杭州", "南京",
    "故城县", "如皋市", "庆云县", "德州", "南通", "苏州", "西安", "重庆",
    "武汉", "长沙", "青岛", "大连", "厦门", "桂林", "丽江", "三亚"
]

SPOTS = {
    "衡水": ["衡水湖", "武强年画博物馆", "冀州古城"],
    "北京": ["故宫", "长城", "颐和园", "天坛", "圆明园"],
    "上海": ["外滩", "东方明珠", "豫园", "迪士尼"],
    "成都": ["大熊猫基地", "宽窄巷子", "锦里", "都江堰", "武侯祠"],
    "杭州": ["西湖", "灵隐寺", "千岛湖", "宋城"],
    "西安": ["兵马俑", "大雁塔", "华清宫", "钟楼"],
    "故城县": ["故城大运河", "庆林寺塔"],
    "庆云县": ["庆云海岛金山寺", "月亮湾"],
}

PARTIES = ["带小孩", "情侣出行", "独自旅行", "和朋友一起", "带老人", "全家出游"]
PREFERENCES = ["喜欢历史古迹", "喜欢自然风光", "不喜欢爬山", "喜欢美食", "喜欢拍照打卡"]

WEATHER_QUESTIONS = [
    "{city}天气怎么样", "{city}今天天气如何", "{city}现在多少度",
    "{city}会不会下雨", "帮我查一下{city}的天气", "{city}冷不冷",
    "明天去{city}穿什么衣服好", "{city}天气好吗", "查看{city}今日天气",
]

SPOT_QUESTIONS = [
    "{city}有什么好玩的", "{city}有哪些景点", "{city}旅游推荐",
    "推荐一下{city}的景点", "{city}有什么值得去的地方", "{city}哪里好玩",
    "{city}必去的景点有哪些", "去{city}玩去哪些地方",
]

DEEP_SPOT_QUESTIONS = [
    "{spot}怎么玩", "{spot}攻略", "{spot}有什么好吃的",
    "{spot}值得去吗", "{spot}门票多少钱", "去{spot}要注意什么",
    "{spot}有什么特色", "{spot}避坑指南",
]

ROUTE_QUESTIONS = [
    "从{a}到{b}怎么走", "从{a}开车到{b}多远", "{a}到{b}的驾车路线",
    "从{a}去{b}怎么去", "{a}自驾到{b}要多久", "从{a}出发到{b}怎么走",
    "帮我规划从{a}到{b}的路线", "{a}到{b}自驾路线",
]

PLAN_QUESTIONS = [
    "帮我规划{city}{n}天行程", "{city}{n}日游怎么安排",
    "去{city}玩{n}天怎么安排", "{city}{n}天旅游攻略",
]

CHAT_QUESTIONS = [
    "你好", "谢谢你", "帮了大忙", "你是谁", "能帮我什么",
    "今天心情不错", "旅途愉快", "你真棒", "辛苦了",
]

PRONOUN_QUESTIONS = [
    "这个城市天气怎么样", "那里有什么好玩的", "帮我规划那边的行程",
    "这个地方冷不冷", "那个城市有什么景点", "就那个地方怎么去",
]

# =========================================================================
# 天气模拟数据（用于 observation）
# =========================================================================
def fake_weather(city):
    temp = random.randint(-5, 38)
    descs = ["晴朗", "多云", "阴天", "小雨", "大雨", "小雪", "雾"]
    desc = random.choice(descs)
    humidity = random.randint(30, 95)
    wind = round(random.uniform(1, 25), 1)
    return json.dumps({
        "city": city, "temp": temp, "feels_like": temp - 2,
        "desc": desc, "humidity": humidity, "wind_speed": wind
    }, ensure_ascii=False)


def fake_route(origin, dest):
    dist = random.randint(30, 1200)
    dur = int(dist / 80 * 60)
    roads = random.sample(["G2京沪高速", "G3京台高速", "G15沈海高速", "S29滨莱高速",
                           "G20青银高速", "G1京哈高速", "S38新沂高速", "G104国道",
                           "G30连霍高速", "G4京港澳高速", "G50沪渝高速"], k=min(4, 3))
    return json.dumps({
        "distance_km": dist, "duration_min": dur,
        "roads": " → ".join(roads)
    }, ensure_ascii=False)


def fake_spots(city):
    spots = SPOTS.get(city, [f"{city}公园", f"{city}博物馆", f"{city}古镇"])
    return json.dumps({"count": len(spots), "spots": spots}, ensure_ascii=False)


# =========================================================================
# 数据集容器
# =========================================================================
dataset = []


def add(system, convs):
    dataset.append({
        "conversations": convs,
        "system": system,
        "tools": TOOLS
    })


# =========================================================================
# 1. Travel Router 数据（~250 条）
# =========================================================================

# --- 1a. 天气意图 → 转发给 weather_agent ---
for _ in range(60):
    city = random.choice(CITIES)
    q = random.choice(WEATHER_QUESTIONS).format(city=city)
    add(ROUTER_SYSTEM, [
        {"from": "human", "value": q},
        fc("get_context", {}),
        obs("暂无上下文记忆"),
        fc("send_direct_message", {"target_agent_id": "weather_agent", "text": q}),
        obs("消息已发送给weather_agent"),
        fc("save_context", {"current_city": city}),
        obs("上下文已保存"),
    ])

# --- 1b. 景点意图 → 转发给 spot_agent ---
for _ in range(50):
    city = random.choice(CITIES)
    q = random.choice(SPOT_QUESTIONS).format(city=city)
    add(ROUTER_SYSTEM, [
        {"from": "human", "value": q},
        fc("get_context", {}),
        obs("暂无上下文记忆"),
        fc("send_direct_message", {"target_agent_id": "spot_agent", "text": q}),
        obs("消息已发送给spot_agent"),
        fc("save_context", {"current_city": city}),
        obs("上下文已保存"),
    ])

# --- 1c. 路线意图 → 转发给 plan_agent ---
for _ in range(50):
    a, b = random.sample(CITIES, 2)
    q = random.choice(ROUTE_QUESTIONS).format(a=a, b=b)
    add(ROUTER_SYSTEM, [
        {"from": "human", "value": q},
        fc("get_context", {}),
        obs("暂无上下文记忆"),
        fc("send_direct_message", {"target_agent_id": "plan_agent", "text": q}),
        obs("消息已发送给plan_agent"),
        fc("save_context", {"current_city": b}),
        obs("上下文已保存"),
    ])

# --- 1d. 行程规划意图 → 转发给 plan_agent ---
for _ in range(30):
    city = random.choice(CITIES)
    n = random.choice([1, 2, 3, 4, 5])
    q = random.choice(PLAN_QUESTIONS).format(city=city, n=n)
    party = random.choice(PARTIES)
    add(ROUTER_SYSTEM, [
        {"from": "human", "value": f"{q}，{party}"},
        fc("get_context", {}),
        obs("暂无上下文记忆"),
        fc("send_direct_message", {"target_agent_id": "plan_agent", "text": f"{q}，{party}"}),
        obs("消息已发送给plan_agent"),
        fc("save_context", {"current_city": city, "travel_party": party}),
        obs("上下文已保存"),
    ])

# --- 1e. 指代消解（"这个地方"、"那里"等）→ 用记忆替换后转发 ---
for _ in range(40):
    city = random.choice(CITIES)
    pq = random.choice(PRONOUN_QUESTIONS)
    memory = json.dumps({"current_city": city}, ensure_ascii=False)

    if "天气" in pq or "冷" in pq:
        target = "weather_agent"
        resolved = f"{city}天气怎么样"
    elif "好玩" in pq or "景点" in pq:
        target = "spot_agent"
        resolved = f"{city}有什么好玩的"
    elif "行程" in pq:
        target = "plan_agent"
        resolved = f"规划{city}的行程"
    else:
        target = "plan_agent"
        resolved = f"从当前位置到{city}怎么去"

    add(ROUTER_SYSTEM, [
        {"from": "human", "value": pq},
        fc("get_context", {}),
        obs(memory),
        fc("send_direct_message", {"target_agent_id": target, "text": resolved}),
        obs(f"消息已发送给{target}"),
    ])

# --- 1f. 闲聊 → 直接回复，不转发 ---
for _ in range(20):
    q = random.choice(CHAT_QUESTIONS)
    replies = {
        "你好": "你好呀！我是你的旅游小助手 🌟 有什么可以帮你的吗？",
        "谢谢你": "不客气～祝你旅途愉快！🎒✨",
        "帮了大忙": "能帮到你真开心！还有什么需要了解的尽管问～ 😊",
        "你是谁": "我是旅游小助手，可以帮你查天气、找景点、规划行程哦！🗺️",
        "能帮我什么": "我可以帮你查实时天气 ☀️、推荐景点 🏛️、规划行程 🗺️、查驾车路线 🚗 哦！",
        "今天心情不错": "心情好就该出去玩！要不要我帮你推荐个好去处？🌈",
        "旅途愉快": "谢谢～也祝你一路顺风！🎉",
        "你真棒": "谢谢夸奖！继续为你服务 💪",
        "辛苦了": "为你服务是我的荣幸！还有什么需要帮忙的吗？😄",
    }
    reply = replies.get(q, "谢谢你！有旅游方面的问题随时问我哦～ 🌟")
    add(ROUTER_SYSTEM, [
        {"from": "human", "value": q},
        fc("get_context", {}),
        obs("暂无上下文记忆"),
        fc("send_channel_message", {"channel": "general", "text": reply}),
        obs("消息已发送"),
    ])


# =========================================================================
# 2. Weather Agent 数据（~120 条）
# =========================================================================
for _ in range(80):
    city = random.choice(CITIES)
    q = random.choice(WEATHER_QUESTIONS).format(city=city)
    weather_data = fake_weather(city)
    wd = json.loads(weather_data)

    if wd["temp"] < 5:
        advice = "🧥 天气寒冷，建议穿着羽绒服或厚外套"
    elif wd["temp"] < 15:
        advice = "🧶 天气较凉，建议穿着外套或夹克"
    elif wd["temp"] < 25:
        advice = "👕 天气舒适，建议穿着长袖或薄外套"
    else:
        advice = "☀️ 天气炎热，建议穿着短袖，注意防晒补水"

    reply_text = (
        f"🌡️ {city}今天天气情况：\n"
        f"☁️ 天气：{wd['desc']}\n"
        f"🌡️ 温度：{wd['temp']}°C（体感 {wd['feels_like']}°C）\n"
        f"💨 风速：{wd['wind_speed']} km/h\n"
        f"💧 湿度：{wd['humidity']}%\n"
        f"👔 穿衣建议：{advice}"
    )
    add(WEATHER_SYSTEM, [
        {"from": "human", "value": q},
        fc("get_context", {}),
        obs("暂无上下文记忆"),
        fc("get_weather", {"city": city}),
        obs(weather_data),
        fc("reply_channel_message", {"text": reply_text}),
        obs("消息已发送"),
    ])

# 带记忆的天气查询（没说城市名，靠记忆）
for _ in range(40):
    city = random.choice(CITIES)
    vague_qs = ["天气怎么样", "今天冷不冷", "需要带伞吗", "穿什么衣服好"]
    q = random.choice(vague_qs)
    memory = json.dumps({"current_city": city}, ensure_ascii=False)
    weather_data = fake_weather(city)
    wd = json.loads(weather_data)
    reply_text = f"🌡️ {city}今天{wd['desc']}，气温{wd['temp']}°C，湿度{wd['humidity']}%"

    add(WEATHER_SYSTEM, [
        {"from": "human", "value": q},
        fc("get_context", {}),
        obs(memory),
        fc("get_weather", {"city": city}),
        obs(weather_data),
        fc("reply_channel_message", {"text": reply_text}),
        obs("消息已发送"),
    ])


# =========================================================================
# 3. Spot Agent 数据（~120 条）
# =========================================================================

# 普通景点搜索 → search_spots
for _ in range(60):
    city = random.choice(CITIES)
    q = random.choice(SPOT_QUESTIONS).format(city=city)
    spots_data = fake_spots(city)
    sd = json.loads(spots_data)
    spots_text = "\n".join([f"  {i+1}. 📍 {s}" for i, s in enumerate(sd["spots"])])
    reply_text = f"🏛️ 为您推荐{city}的热门景点：\n{spots_text}\n\n需要了解某个景点的详细攻略吗？"

    add(SPOT_SYSTEM, [
        {"from": "human", "value": q},
        fc("get_context", {}),
        obs("暂无上下文记忆"),
        fc("search_spots", {"query": f"{city}景点"}),
        obs(spots_data),
        fc("reply_channel_message", {"text": reply_text}),
        obs("消息已发送"),
    ])

# 深度攻略 → search_local_knowledge
for _ in range(40):
    city = random.choice(list(SPOTS.keys()))
    spot = random.choice(SPOTS[city])
    q = random.choice(DEEP_SPOT_QUESTIONS).format(spot=spot)
    knowledge = json.dumps({
        "spot": spot, "city": city,
        "content": f"{spot}是{city}最著名的景点之一，建议游玩2-3小时。",
        "tips": "建议提前预约门票，避开节假日高峰。"
    }, ensure_ascii=False)
    reply_text = f"📖 关于{spot}的深度攻略：\n{spot}是{city}最著名的景点之一，建议游玩2-3小时。\n💡 小贴士：建议提前预约门票，避开节假日高峰。"

    add(SPOT_SYSTEM, [
        {"from": "human", "value": q},
        fc("get_context", {}),
        obs("暂无上下文记忆"),
        fc("search_local_knowledge", {"query": f"{spot}攻略"}),
        obs(knowledge),
        fc("reply_channel_message", {"text": reply_text}),
        obs("消息已发送"),
    ])

# 先搜 POI 再搜深度攻略（两步工具调用）
for _ in range(20):
    city = random.choice(list(SPOTS.keys()))
    q = f"{city}有什么好玩的，给我详细的攻略"
    spots_data = fake_spots(city)
    knowledge = json.dumps({"content": f"{city}旅游综合攻略..."}, ensure_ascii=False)
    reply_text = f"📍 {city}热门景点 + 深度攻略已为您整理好！"

    add(SPOT_SYSTEM, [
        {"from": "human", "value": q},
        fc("get_context", {}),
        obs("暂无上下文记忆"),
        fc("search_spots", {"query": f"{city}景点"}),
        obs(spots_data),
        fc("search_local_knowledge", {"query": f"{city}攻略"}),
        obs(knowledge),
        fc("reply_channel_message", {"text": reply_text}),
        obs("消息已发送"),
    ])


# =========================================================================
# 4. Plan Agent 数据（~120 条）
# =========================================================================

# 驾车路线查询 → get_driving_route
for _ in range(80):
    a, b = random.sample(CITIES, 2)
    q = random.choice(ROUTE_QUESTIONS).format(a=a, b=b)
    route_data = fake_route(a, b)
    rd = json.loads(route_data)
    reply_text = (
        f"🚗 从{a}到{b}的驾车路线：\n"
        f"📏 总距离：约 {rd['distance_km']} 公里\n"
        f"⏱️ 预计耗时：约 {rd['duration_min']} 分钟\n"
        f"🛣️ 主要道路：{rd['roads']}\n"
        f"💡 建议出发前检查车辆状况，注意行车安全！"
    )
    add(PLAN_SYSTEM, [
        {"from": "human", "value": q},
        fc("get_context", {}),
        obs("暂无上下文记忆"),
        fc("get_driving_route", {"origin": a, "destination": b}),
        obs(route_data),
        fc("reply_channel_message", {"text": reply_text}),
        obs("消息已发送"),
    ])

# 带记忆的路线查询（只说"去XX"，起点靠记忆）
for _ in range(40):
    a = random.choice(CITIES)
    b = random.choice(CITIES)
    if a == b:
        continue
    q = f"从这里开车去{b}要多久"
    memory = json.dumps({"current_city": a}, ensure_ascii=False)
    route_data = fake_route(a, b)
    rd = json.loads(route_data)
    reply_text = (
        f"🚗 从{a}到{b}：约{rd['distance_km']}公里，"
        f"预计{rd['duration_min']}分钟，走{rd['roads']}"
    )
    add(PLAN_SYSTEM, [
        {"from": "human", "value": q},
        fc("get_context", {}),
        obs(memory),
        fc("get_driving_route", {"origin": a, "destination": b}),
        obs(route_data),
        fc("reply_channel_message", {"text": reply_text}),
        obs("消息已发送"),
    ])


# =========================================================================
# 输出
# =========================================================================
output_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "openagents_sft_dataset.json")
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(dataset, f, ensure_ascii=False, indent=2)

# 统计
router_count = sum(1 for d in dataset if "总控网关" in d["system"])
weather_count = sum(1 for d in dataset if "天气助手" in d["system"])
spot_count = sum(1 for d in dataset if "景点助手" in d["system"])
plan_count = sum(1 for d in dataset if "行程助手" in d["system"])

print(f"✅ 数据集生成完成！")
print(f"📊 总计: {len(dataset)} 条")
print(f"   🔀 Router:  {router_count} 条")
print(f"   🌤️ Weather: {weather_count} 条")
print(f"   🏛️ Spot:    {spot_count} 条")
print(f"   🗺️ Plan:    {plan_count} 条")
print(f"📁 保存至: {output_path}")
