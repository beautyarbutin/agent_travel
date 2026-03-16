"""
结构化对话上下文记忆工具

提供 save_context 和 get_context 两个函数，用于持久化和读取
用户对话中的关键实体信息（当前城市、景点、出行偏好等）。
存储文件：storage/user_context.json
"""

import json
import os
from datetime import datetime

# 存储路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTEXT_FILE = os.path.join(BASE_DIR, "storage", "user_context.json")


def _load_context() -> dict:
    """从文件加载当前上下文，不存在则返回空字典。"""
    if os.path.exists(CONTEXT_FILE):
        try:
            with open(CONTEXT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def _save_context_to_file(context: dict):
    """将上下文写入文件。"""
    os.makedirs(os.path.dirname(CONTEXT_FILE), exist_ok=True)
    with open(CONTEXT_FILE, "w", encoding="utf-8") as f:
        json.dump(context, f, ensure_ascii=False, indent=2)


def save_context(
    current_city: str = "",
    origin_city: str = "",
    destination_city: str = "",
    current_spot: str = "",
    travel_party: str = "",
    preferences: str = "",
    departure_time: str = "",
    trip_days: str = "",
    notes: str = "",
) -> str:
    """
    保存/更新用户对话上下文到本地记忆文件。
    只有传入的非空字段会覆盖旧值，空字段保持不变（增量更新）。

    Args:
        current_city: 当前讨论的城市名，例如"衡水"、"北京"
        origin_city: 跨城行程中的出发地，例如"故城县"
        destination_city: 跨城行程中的目的地，例如"如皋市"
        current_spot: 当前讨论的具体景点名，例如"衡水湖"、"故宫"
        travel_party: 出行人员情况，例如"带小孩"、"情侣"、"独自"
        preferences: 用户偏好，例如"不喜欢爬山，喜欢历史古迹"
        departure_time: 出发时间，例如"今天出发"、"下周六"
        trip_days: 行程天数，例如"三天"、"2天1晚"
        notes: 其他备注，例如"预算200以内"、"只有半天时间"
    """
    try:
        context = _load_context()

        # 增量更新：只覆盖非空字段
        if current_city:
            context["current_city"] = current_city
        if origin_city:
            context["origin_city"] = origin_city
        if destination_city:
            context["destination_city"] = destination_city
        if current_spot:
            context["current_spot"] = current_spot
        if travel_party:
            context["travel_party"] = travel_party
        if preferences:
            context["preferences"] = preferences
        if departure_time:
            context["departure_time"] = departure_time
        if trip_days:
            context["trip_days"] = trip_days
        if notes:
            context["notes"] = notes

        context["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        _save_context_to_file(context)

        # 构建确认信息
        updated_fields = []
        if current_city:
            updated_fields.append(f"城市={current_city}")
        if origin_city:
            updated_fields.append(f"出发地={origin_city}")
        if destination_city:
            updated_fields.append(f"目的地={destination_city}")
        if current_spot:
            updated_fields.append(f"景点={current_spot}")
        if travel_party:
            updated_fields.append(f"出行人员={travel_party}")
        if preferences:
            updated_fields.append(f"偏好={preferences}")
        if departure_time:
            updated_fields.append(f"出发时间={departure_time}")
        if trip_days:
            updated_fields.append(f"行程天数={trip_days}")
        if notes:
            updated_fields.append(f"备注={notes}")

        return f"✅ 上下文已更新：{', '.join(updated_fields)}"

    except Exception as e:
        return f"保存上下文时发生错误：{str(e)}"


def get_context() -> str:
    """
    读取当前对话上下文记忆，返回用户之前对话中提取的关键信息。
    包括：当前城市、当前景点、出行人员、用户偏好、备注等。
    如果没有历史上下文，返回"暂无上下文记忆"。
    """
    try:
        context = _load_context()

        if not context:
            return "暂无上下文记忆，这是一个新的对话。"

        lines = ["📋 当前对话上下文记忆："]

        if context.get("current_city"):
            lines.append(f"  🏙️ 当前城市：{context['current_city']}")
        if context.get("origin_city"):
            lines.append(f"  🚩 出发地：{context['origin_city']}")
        if context.get("destination_city"):
            lines.append(f"  🎯 目的地：{context['destination_city']}")
        if context.get("current_spot"):
            lines.append(f"  📍 当前景点：{context['current_spot']}")
        if context.get("travel_party"):
            lines.append(f"  👥 出行人员：{context['travel_party']}")
        if context.get("preferences"):
            lines.append(f"  ❤️ 用户偏好：{context['preferences']}")
        if context.get("departure_time"):
            lines.append(f"  🗓️ 出发时间：{context['departure_time']}")
        if context.get("trip_days"):
            lines.append(f"  ⏳ 行程天数：{context['trip_days']}")
        if context.get("notes"):
            lines.append(f"  📝 备注：{context['notes']}")
        if context.get("last_updated"):
            lines.append(f"  🕐 最后更新：{context['last_updated']}")

        return "\n".join(lines)

    except Exception as e:
        return f"读取上下文时发生错误：{str(e)}"
