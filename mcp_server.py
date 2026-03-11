"""
旅游助手 MCP Server
将天气查询、景点搜索、路线规划三个工具通过 MCP 协议标准化暴露。
任何支持 MCP 的客户端（Cursor、Claude Desktop 等）都可以直接接入使用。

启动方式：python mcp_server.py
"""
import os
import sys
import requests
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# 加载环境变量
base_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(base_dir, '.env'))

# 创建 MCP Server 实例
mcp = FastMCP("TravelAssistant")


# ============================================================
# Tool 1: 天气查询
# ============================================================
@mcp.tool()
def get_weather(city: str) -> str:
    """
    获取指定城市的实时天气信息，包括温度、天气状况、风速、湿度和穿衣建议。
    
    Args:
        city: 城市名称，例如"北京"、"上海"、"故城"
    """
    api_key = os.getenv("OPENWEATHER_API_KEY")
    if not api_key:
        return "错误：未配置 OPENWEATHER_API_KEY"

    try:
        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {
            "q": f"{city},CN",
            "appid": api_key,
            "units": "metric",
            "lang": "zh_cn"
        }
        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        if data.get("cod") != 200:
            return f"查询失败：{data.get('message', '未知错误')}"

        temp = data["main"]["temp"]
        feels_like = data["main"]["feels_like"]
        humidity = data["main"]["humidity"]
        weather_desc = data["weather"][0]["description"]
        wind_speed = data["wind"]["speed"]

        # 穿衣建议
        if temp < 5:
            clothing = "🧥 天气寒冷，建议穿着：羽绒服或厚外套、毛衣保暖层、围巾和手套、注意保暖防寒！"
        elif temp < 15:
            clothing = "🧶 天气较凉，建议穿着：外套或夹克、长袖衬衫、可备薄围巾"
        elif temp < 25:
            clothing = "👕 天气舒适，建议穿着：长袖或薄外套、休闲装即可"
        else:
            clothing = "☀️ 天气炎热，建议穿着：短袖、短裤、注意防晒补水"

        return (
            f"📍 {city}今天天气情况：\n"
            f"🌡️ 温度：{temp}°C（体感 {feels_like}°C）\n"
            f"☁️ 天气：{weather_desc}\n"
            f"💨 风速：{wind_speed} km/h\n"
            f"💧 湿度：{humidity}%\n"
            f"👔 穿衣建议：{clothing}"
        )
    except Exception as e:
        return f"查询天气时发生错误：{str(e)}"


# ============================================================
# Tool 2: 景点搜索（高德 POI）
# ============================================================
@mcp.tool()
def search_spots(query: str) -> str:
    """
    搜索指定城市或地区的景点信息。使用高德地图 POI 搜索 API，覆盖全国所有城市和区县。
    
    Args:
        query: 地名或景点名，例如"庆云县"、"衡水旅游"、"故城县景点"
    """
    api_key = os.getenv("AMAP_API_KEY")
    if not api_key:
        return "错误：未配置 AMAP_API_KEY"

    try:
        url = "https://restapi.amap.com/v3/place/text"
        params = {
            "key": api_key,
            "keywords": query,
            "types": "110000",
            "city": "",
            "citylimit": "false",
            "offset": 10,
            "output": "json",
            "extensions": "all",
        }

        for suffix in ["县", "市", "区", "镇", "州"]:
            if suffix in query:
                params["city"] = query
                params["keywords"] = "景点 旅游 风景"
                break

        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        if data.get("status") != "1":
            return f"高德 API 请求失败: {data.get('info', '未知错误')}"

        pois = data.get("pois", [])
        if not pois:
            params["types"] = ""
            params["keywords"] = query + " 景点 旅游"
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            pois = data.get("pois", [])

        if not pois:
            return f"没有找到关于 '{query}' 的景点信息。"

        results = []
        for i, poi in enumerate(pois, 1):
            name = poi.get("name", "未知")
            address = poi.get("address", "暂无")
            pname = poi.get("pname", "")
            cityname = poi.get("cityname", "")
            adname = poi.get("adname", "")
            location_str = " > ".join([p for p in [pname, cityname, adname] if p])

            entry = f"{i}. 📍 {name}\n   📌 {location_str}\n   🏠 {address}"
            tel = poi.get("tel", "")
            if tel and tel != "[]":
                entry += f"\n   📞 {tel}"
            results.append(entry)

        total = data.get("count", len(pois))
        return f"'{query}' 相关景点（共{total}个，展示{len(pois)}个）：\n\n" + "\n\n".join(results)

    except Exception as e:
        return f"搜索景点时发生错误: {str(e)}"


# ============================================================
# Tool 4: 景点深度指南检索（RAG 知识库）
# ============================================================
@mcp.tool()
def search_local_knowledge(query: str) -> str:
    """
    搜索本地景点深度游玩指南（RAG知识库），获取高德API无法提供的深度攻略、避坑提示、特色美食等独家信息。
    
    Args:
        query: 景点的名称或相关问题，例如"故城县攻略"、"衡水湖怎么玩"
    """
    try:
        sys.path.insert(0, os.path.join(base_dir, 'tools'))
        from spot_tools import search_knowledge
        return search_knowledge(query)
    except Exception as e:
        return f"RAG检索知识库时发生错误：{str(e)}"


# ============================================================
# Tool 4b: 综合检索（RAG 知识库 + 高德 POI 实时数据融合）
# ============================================================
@mcp.tool()
def search_combined(query: str) -> str:
    """
    融合检索工具：同时查询本地 RAG 知识库（深度攻略）和高德地图 POI API（实时地址/评分/电话），
    以"深度攻略 + 实时信息"双层结构呈现结果。

    推荐在以下场景优先使用此工具（而非分别调用两个工具）：
    - 用户问景点怎么玩（同时需要深度攻略和位置信息）
    - 用户问某个城市/区县有什么好玩的
    - 需要在同一回复中展示本地独家经验和权威官方地址时

    Args:
        query: 用户问题，例如"衡水湖怎么玩"、"故城县有什么景点"
    """
    try:
        sys.path.insert(0, os.path.join(base_dir, 'tools'))
        from spot_tools import search_combined as _search_combined
        return _search_combined(query)
    except Exception as e:
        return f"综合检索时发生错误：{str(e)}"



# ============================================================
# Tool 3: 驾车路线规划（高德）
# ============================================================
@mcp.tool()
def get_driving_route(origin: str, destination: str) -> str:
    """
    获取两地之间的驾车路线规划，包括距离、耗时和途经道路。使用高德地图 API。
    
    Args:
        origin: 出发地名称，例如"德州市"
        destination: 目的地名称，例如"故城县"
    """
    api_key = os.getenv("AMAP_API_KEY")
    if not api_key:
        return "错误：未配置 AMAP_API_KEY"

    def geocode(address):
        url = "https://restapi.amap.com/v3/geocode/geo"
        params = {"key": api_key, "address": address, "output": "json"}
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        if data.get("status") == "1" and data.get("geocodes"):
            return data["geocodes"][0]["location"]
        return None

    try:
        origin_loc = geocode(origin)
        dest_loc = geocode(destination)

        if not origin_loc:
            return f"无法解析出发地 '{origin}' 的位置坐标"
        if not dest_loc:
            return f"无法解析目的地 '{destination}' 的位置坐标"

        url = "https://restapi.amap.com/v3/direction/driving"
        params = {
            "key": api_key,
            "origin": origin_loc,
            "destination": dest_loc,
            "extensions": "all",
            "output": "json",
        }
        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        if data.get("status") != "1":
            return f"路线规划失败: {data.get('info', '未知错误')}"

        route = data.get("route", {})
        paths = route.get("paths", [])
        if not paths:
            return "未找到可行的驾车路线"

        path = paths[0]
        distance_km = round(int(path.get("distance", 0)) / 1000, 1)
        duration_min = round(int(path.get("duration", 0)) / 60)

        roads = []
        for step in path.get("steps", []):
            road = step.get("road", "")
            instruction = step.get("instruction", "")
            if road and road not in roads:
                roads.append(road)

        roads_str = " → ".join(roads[:8]) if roads else "详见导航"

        return (
            f"🚗 从 {origin} 到 {destination} 的驾车路线：\n"
            f"📏 总距离：约 {distance_km} 公里\n"
            f"⏱️ 预计耗时：约 {duration_min} 分钟\n"
            f"🛣️ 主要道路：{roads_str}"
        )

    except Exception as e:
        return f"路线规划时发生错误: {str(e)}"


# ============================================================
# Tool 5: 保存对话上下文记忆
# ============================================================
@mcp.tool()
def save_context(
    current_city: str = "",
    current_spot: str = "",
    travel_party: str = "",
    preferences: str = "",
    notes: str = "",
) -> str:
    """
    保存/更新用户对话上下文到本地记忆文件（增量更新，只覆盖非空字段）。
    当用户提到城市、景点、出行人员、偏好等关键信息时，调用此工具保存。
    
    Args:
        current_city: 当前讨论的城市名，例如"衡水"、"北京"
        current_spot: 当前讨论的具体景点名，例如"衡水湖"、"故宫"
        travel_party: 出行人员情况，例如"带小孩"、"情侣"、"独自"
        preferences: 用户偏好，例如"不喜欢爬山，喜欢历史古迹"
        notes: 其他备注，例如"预算200以内"、"只有半天时间"
    """
    try:
        sys.path.insert(0, os.path.join(base_dir, 'tools'))
        from memory_tools import save_context as _save
        return _save(current_city, current_spot, travel_party, preferences, notes)
    except Exception as e:
        return f"保存上下文时发生错误：{str(e)}"


# ============================================================
# Tool 6: 读取对话上下文记忆
# ============================================================
@mcp.tool()
def get_context() -> str:
    """
    读取当前对话上下文记忆，获取用户之前对话中提到的城市、景点、出行偏好等信息。
    在处理用户请求之前调用此工具，可以了解对话背景。
    """
    try:
        sys.path.insert(0, os.path.join(base_dir, 'tools'))
        from memory_tools import get_context as _get
        return _get()
    except Exception as e:
        return f"读取上下文时发生错误：{str(e)}"


# ============================================================
# 启动 MCP Server
# ============================================================
if __name__ == "__main__":
    print("🚀 旅游助手 MCP Server 启动中...")
    print("📦 提供工具：get_weather, search_spots, get_driving_route, search_local_knowledge, save_context, get_context")
    print("🔌 使用 stdio 传输协议")
    mcp.run()

