"""
天气工具 - 使用高德地理编码 + Open-Meteo API 获取任意城市的实时天气/短期预报
支持全国所有城市和区县，无需手动维护城市列表。
"""
import os
import datetime
import re

import requests
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


def _format_weather_desc(weather_code: int) -> str:
    return WMO_WEATHER_CODES.get(weather_code, f"未知({weather_code})")


def _clothing_advice(temp: float) -> str:
    if temp < 0:
        return "极寒天气，建议穿羽绒服、棉衣等厚重保暖衣物，注意防寒"
    if temp < 5:
        return "天气寒冷，建议穿羽绒服、毛衣加厚外套"
    if temp < 10:
        return "天气较冷，建议穿厚外套、毛衣"
    if temp < 15:
        return "天气偏凉，建议穿夹克、薄外套"
    if temp < 20:
        return "天气舒适偏凉，建议穿长袖衬衫或薄外套"
    if temp < 25:
        return "天气舒适，建议穿长袖或短袖"
    if temp < 30:
        return "天气温暖，建议穿短袖、薄衣"
    return "天气炎热，建议穿短袖短裤，注意防暑"


def _rain_tip(weather_code: int) -> str:
    rainy_codes = (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99)
    return "\n☔ 出行提醒：当前有降水，请记得带伞！" if weather_code in rainy_codes else ""


def _parse_date_like(value: str, today: datetime.date) -> datetime.date | None:
    text = (value or "").strip()
    if not text:
        return None

    text = text.replace("/", "-").replace(".", "-")
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M"):
        try:
            return datetime.datetime.strptime(text, fmt).date()
        except ValueError:
            pass

    md_match = re.fullmatch(r"(\d{1,2})月(\d{1,2})日?", text)
    if md_match:
        month = int(md_match.group(1))
        day = int(md_match.group(2))
        candidate = datetime.date(today.year, month, day)
        if candidate < today - datetime.timedelta(days=1):
            candidate = datetime.date(today.year + 1, month, day)
        return candidate

    d_match = re.fullmatch(r"(\d{1,2})-(\d{1,2})", text)
    if d_match:
        month = int(d_match.group(1))
        day = int(d_match.group(2))
        candidate = datetime.date(today.year, month, day)
        if candidate < today - datetime.timedelta(days=1):
            candidate = datetime.date(today.year + 1, month, day)
        return candidate

    keywords = {
        "今天": 0,
        "明天": 1,
        "后天": 2,
        "大后天": 3,
    }
    if text in keywords:
        return today + datetime.timedelta(days=keywords[text])

    return None


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

        weather_desc = _format_weather_desc(weather_code)
        clothing = _clothing_advice(temp)
        rain_tip = _rain_tip(weather_code)

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


def get_weather_forecast(
    city: str,
    start_date: str = "",
    end_date: str = "",
    days: int = 0,
) -> str:
    """
    获取指定城市未来几天或指定日期区间的天气预报。

    Args:
        city: 城市名称，例如"宁波"、"鄞州区"
        start_date: 起始日期，支持"2026-03-21"、"3月21日"、"明天"
        end_date: 结束日期，支持"2026-03-24"、"3月24日"
        days: 未来天数，例如 3 表示未来三天
    """
    lat, lon, display_name = _geocode(city)

    if lat is None:
        return f"抱歉，无法识别城市「{city}」，请检查城市名称是否正确。"

    today = datetime.date.today()

    try:
        start = _parse_date_like(start_date, today) if start_date else None
        end = _parse_date_like(end_date, today) if end_date else None

        if days and days > 0 and start is None and end is None:
            start = today
            end = today + datetime.timedelta(days=max(days - 1, 0))

        if start and end is None:
            end = start
        if end and start is None:
            start = end

        if start is None or end is None:
            start = today
            end = today + datetime.timedelta(days=2)

        if end < start:
            start, end = end, start

        max_range_end = today + datetime.timedelta(days=15)
        if start < today:
            start = today
        if end > max_range_end:
            end = max_range_end

        if end < start:
            return "抱歉，可查询的天气预报时间范围不足，请换一个更近的日期。"

        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "daily": ",".join(
                [
                    "weather_code",
                    "temperature_2m_max",
                    "temperature_2m_min",
                    "precipitation_probability_max",
                    "wind_speed_10m_max",
                ]
            ),
            "timezone": "Asia/Shanghai",
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        }

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        daily = data.get("daily", {})

        dates = daily.get("time", [])
        weather_codes = daily.get("weather_code", [])
        temp_max_list = daily.get("temperature_2m_max", [])
        temp_min_list = daily.get("temperature_2m_min", [])
        rain_prob_list = daily.get("precipitation_probability_max", [])
        wind_max_list = daily.get("wind_speed_10m_max", [])

        if not dates:
            return f"暂时没有查询到 {display_name} 在该时间段的天气预报。"

        lines = [
            f"📍 {display_name} 天气预报（{dates[0]} 至 {dates[-1]}）"
        ]

        for i, date_text in enumerate(dates):
            date_obj = datetime.date.fromisoformat(date_text)
            prefix = ""
            if date_obj == today:
                prefix = "今天"
            elif date_obj == today + datetime.timedelta(days=1):
                prefix = "明天"
            elif date_obj == today + datetime.timedelta(days=2):
                prefix = "后天"

            weather_desc = _format_weather_desc(weather_codes[i])
            temp_max = temp_max_list[i]
            temp_min = temp_min_list[i]
            rain_prob = rain_prob_list[i]
            wind_max = wind_max_list[i]
            clothing = _clothing_advice((temp_max + temp_min) / 2)

            label = f"{date_text}"
            if prefix:
                label = f"{prefix}（{date_text}）"

            lines.append(
                f"\n🗓️ {label}\n"
                f"☁️ 天气：{weather_desc}\n"
                f"🌡️ 气温：{temp_min}°C ~ {temp_max}°C\n"
                f"🌧️ 降水概率：{rain_prob}%\n"
                f"💨 最大风速：{wind_max} km/h\n"
                f"🧥 穿衣建议：{clothing}"
            )

        return "\n".join(lines)

    except requests.exceptions.Timeout:
        return f"查询{display_name}天气预报超时，请稍后重试。"
    except Exception as e:
        return f"查询{display_name}天气预报时出错：{str(e)}"
