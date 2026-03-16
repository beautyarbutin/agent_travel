"""
天气工具 - 使用高德地理编码 + Open-Meteo API 获取任意城市的实时天气
支持全国所有城市和区县，无需手动维护城市列表。
"""
import os
import requests
import datetime
from dotenv import load_dotenv

# 加载 .env
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(base_dir, '.env'))


# WMO 天气代码 → 中文描述
WMO_WEATHER_CODES = {
    0: "晴 ☀️",
    1: "大部晴朗 🌤️",
    2: "多云 ⛅",
    3: "阴天 ☁️",
    45: "雾 🌫️",
    48: "雾凇 🌫️",
    51: "小毛毛雨 🌦️",
    53: "毛毛雨 🌦️",
    55: "大毛毛雨 🌦️",
    56: "冻毛毛雨 🌧️",
    57: "冻雨 🌧️",
    61: "小雨 🌧️",
    63: "中雨 🌧️",
    65: "大雨 🌧️",
    66: "冻小雨 🌧️",
    67: "冻大雨 🌧️",
    71: "小雪 🌨️",
    73: "中雪 🌨️",
    75: "大雪 🌨️",
    77: "雪粒 🌨️",
    80: "小阵雨 🌦️",
    81: "中阵雨 🌦️",
    82: "大阵雨 ⛈️",
    85: "小阵雪 🌨️",
    86: "大阵雪 🌨️",
    95: "雷暴 ⛈️",
    96: "雷暴+小冰雹 ⛈️",
    99: "雷暴+大冰雹 ⛈️",
}


def _geocode(city_name: str):
    """使用高德地理编码 API 将城市名转为经纬度，支持全国所有城市和区县"""
    api_key = os.getenv("AMAP_API_KEY")
    if not api_key:
        return None, None, "未配置 AMAP_API_KEY"

    try:
        url = "https://restapi.amap.com/v3/geocode/geo"
        params = {"key": api_key, "address": city_name, "output": "json"}
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()

        if data.get("status") == "1" and data.get("geocodes"):
            geo = data["geocodes"][0]
            location = geo["location"]  # "116.407526,39.904030"
            lon, lat = location.split(",")
            formatted_name = geo.get("formatted_address", city_name)
            # 取省+市+区 作为显示名
            province = geo.get("province", "")
            city = geo.get("city", "")
            district = geo.get("district", "")
            if isinstance(city, list):
                city = ""
            if isinstance(district, list):
                district = ""
            display_name = district or city or province or city_name
            return float(lat), float(lon), display_name
        else:
            return None, None, None
    except Exception:
        return None, None, None


def get_weather(city: str) -> str:
    """
    获取指定城市的实时天气信息，包括温度、天气状况、风速和湿度。
    支持全国所有城市和区县。

    Args:
        city: 要查询天气的城市名称，例如"北京"、"如皋市"、"庆云县"
    
    Returns:
        包含实时天气信息的字符串
    """
    lat, lon, display_name = _geocode(city)

    if lat is None:
        return f"抱歉，无法识别城市「{city}」，请检查城市名称是否正确。"

    try:
        # 调用 Open-Meteo API（免费，无需 API Key）
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m,apparent_temperature",
            "timezone": "Asia/Shanghai",
            "forecast_days": 1,
        }

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        current = data["current"]
        temp = current["temperature_2m"]
        feels_like = current["apparent_temperature"]
        humidity = current["relative_humidity_2m"]
        weather_code = current["weather_code"]
        wind_speed = current["wind_speed_10m"]

        weather_desc = WMO_WEATHER_CODES.get(weather_code, f"未知({weather_code})")

        # 穿衣建议
        if temp < 0:
            clothing = "极寒天气，建议穿羽绒服、棉衣等厚重保暖衣物，注意防寒"
        elif temp < 5:
            clothing = "天气寒冷，建议穿羽绒服、毛衣加厚外套"
        elif temp < 10:
            clothing = "天气较冷，建议穿厚外套、毛衣"
        elif temp < 15:
            clothing = "天气偏凉，建议穿夹克、薄外套"
        elif temp < 20:
            clothing = "天气舒适偏凉，建议穿长袖衬衫或薄外套"
        elif temp < 25:
            clothing = "天气舒适，建议穿长袖或短袖"
        elif temp < 30:
            clothing = "天气温暖，建议穿短袖、薄衣"
        else:
            clothing = "天气炎热，建议穿短袖短裤，注意防暑"

        # 下雨提醒
        rain_tip = ""
        if weather_code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99):
            rain_tip = "\n☔ 出行提醒：当前有降水，请记得带伞！"

        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

        result = (
            f"📍 {display_name} 实时天气（{now}）\n"
            f"🌡️ 温度：{temp}°C（体感 {feels_like}°C）\n"
            f"☁️ 天气：{weather_desc}\n"
            f"💨 风速：{wind_speed} km/h\n"
            f"💧 湿度：{humidity}%\n"
            f"🧥 穿衣建议：{clothing}"
            f"{rain_tip}"
        )

        return result

    except requests.exceptions.Timeout:
        return f"查询{display_name}天气超时，请稍后重试。"
    except Exception as e:
        return f"查询{display_name}天气时出错：{str(e)}"
