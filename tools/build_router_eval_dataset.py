from __future__ import annotations

import json
from pathlib import Path
from typing import Any


TOOLS_DIR = Path(__file__).resolve().parent
OUTPUT_PATH = TOOLS_DIR / "router_eval_cases.json"

SYSTEM_PROMPT = """# 最高优先级规则（违反=失败）
你必须通过调用工具来完成任务！禁止输出纯文本！禁止调用finish工具！

你是旅游小助手的总控网关。收到用户消息后，判断意图并执行对应操作。

## 记忆系统操作流程
第一步：调用 get_context 读取上下文记忆。
第二步：指代消解+意图识别+转发（天气→weather_agent，景点→spot_agent，行程→plan_agent，闲聊→send_channel_message）。
第三步：如果出现新信息，调用 save_context 保存。"""

TOOLS = [
    {
        "name": "get_weather",
        "description": "获取指定城市的实时天气信息",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string", "description": "城市名称"}},
            "required": ["city"],
        },
    },
    {
        "name": "search_spots",
        "description": "搜索指定城市或地区的景点信息（高德地图POI）",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "地名或景点名"}},
            "required": ["query"],
        },
    },
    {
        "name": "get_driving_route",
        "description": "获取两地之间的驾车路线规划",
        "parameters": {
            "type": "object",
            "properties": {
                "origin": {"type": "string", "description": "出发地"},
                "destination": {"type": "string", "description": "目的地"},
            },
            "required": ["origin", "destination"],
        },
    },
    {
        "name": "search_local_knowledge",
        "description": "搜索本地RAG知识库的深度攻略",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "景点名或问题"}},
            "required": ["query"],
        },
    },
    {
        "name": "search_combined",
        "description": "融合检索：同时查RAG知识库和高德POI",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "用户问题"}},
            "required": ["query"],
        },
    },
    {
        "name": "save_context",
        "description": "保存用户对话上下文到记忆",
        "parameters": {
            "type": "object",
            "properties": {
                "current_city": {"type": "string"},
                "current_spot": {"type": "string"},
                "travel_party": {"type": "string"},
                "preferences": {"type": "string"},
                "notes": {"type": "string"},
            },
        },
    },
    {
        "name": "get_context",
        "description": "读取对话上下文记忆",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "send_direct_message",
        "description": "转发给指定子Agent处理",
        "parameters": {
            "type": "object",
            "properties": {
                "target_agent_id": {"type": "string"},
                "text": {"type": "string"},
            },
            "required": ["target_agent_id", "text"],
        },
    },
    {
        "name": "send_channel_message",
        "description": "发送消息到公共频道",
        "parameters": {
            "type": "object",
            "properties": {
                "channel": {"type": "string"},
                "text": {"type": "string"},
            },
            "required": ["channel", "text"],
        },
    },
    {
        "name": "reply_channel_message",
        "description": "回复频道消息",
        "parameters": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
]

ROUTE_TO_AGENT = {
    "weather": "weather_agent",
    "spot": "spot_agent",
    "plan": "plan_agent",
}


def obs_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def build_router_case(
    user_text: str,
    route: str,
    context_observation: Any = "暂无上下文记忆",
    save_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    conversations: list[dict[str, Any]] = [
        {"from": "human", "value": user_text},
        {"from": "gpt", "value": "", "tool_calls": [{"name": "get_context", "arguments": {}}]},
        {"from": "observation", "value": obs_text(context_observation)},
    ]

    if route == "chat":
        conversations.append(
            {
                "from": "gpt",
                "value": "",
                "tool_calls": [
                    {
                        "name": "send_channel_message",
                        "arguments": {"channel": "travel_assistant", "text": user_text},
                    }
                ],
            }
        )
    else:
        conversations.extend(
            [
                {
                    "from": "gpt",
                    "value": "",
                    "tool_calls": [
                        {
                            "name": "send_direct_message",
                            "arguments": {
                                "target_agent_id": ROUTE_TO_AGENT[route],
                                "text": user_text,
                            },
                        }
                    ],
                },
                {
                    "from": "observation",
                    "value": f"消息已发送给{ROUTE_TO_AGENT[route]}",
                },
            ]
        )

    if save_context:
        conversations.append(
            {
                "from": "gpt",
                "value": "",
                "tool_calls": [{"name": "save_context", "arguments": save_context}],
            }
        )

    return {
        "system": SYSTEM_PROMPT,
        "tools": TOOLS,
        "conversations": conversations,
    }


def build_dataset() -> list[dict[str, Any]]:
    specs = [
        {"user": "帮我看下苏州今天冷不冷", "route": "weather", "save": {"current_city": "苏州"}},
        {"user": "成都周末会下雨吗", "route": "weather", "save": {"current_city": "成都"}},
        {"user": "查看青岛明天气温", "route": "weather", "save": {"current_city": "青岛"}},
        {"user": "昆明最近天气怎么样", "route": "weather", "save": {"current_city": "昆明"}},
        {"user": "深圳今天适合穿短袖吗", "route": "weather", "save": {"current_city": "深圳"}},
        {"user": "厦门下周天气如何", "route": "weather", "save": {"current_city": "厦门"}},
        {
            "user": "推荐一下西安适合带爸妈逛的景点",
            "route": "spot",
            "save": {"current_city": "西安", "travel_party": "带父母"},
        },
        {"user": "北京有什么适合拍照的景点", "route": "spot", "save": {"current_city": "北京"}},
        {
            "user": "杭州西湖值得去吗",
            "route": "spot",
            "save": {"current_city": "杭州", "current_spot": "西湖"},
        },
        {"user": "重庆适合夜游的地方有哪些", "route": "spot", "save": {"current_city": "重庆"}},
        {"user": "帮我找找青岛看海的景点", "route": "spot", "save": {"current_city": "青岛"}},
        {
            "user": "洛阳龙门石窟怎么玩",
            "route": "spot",
            "save": {"current_city": "洛阳", "current_spot": "龙门石窟"},
        },
        {"user": "帮我规划一下上海两日游", "route": "plan", "save": {"current_city": "上海", "notes": "两日游"}},
        {
            "user": "预算2000，安排个成都三天行程",
            "route": "plan",
            "save": {"current_city": "成都", "notes": "预算2000，三天行程"},
        },
        {"user": "从衡水到如皋怎么走", "route": "plan"},
        {"user": "北京到天津开车多久", "route": "plan"},
        {
            "user": "下个月去厦门玩两天，帮我排一下",
            "route": "plan",
            "save": {"current_city": "厦门", "notes": "两天行程"},
        },
        {
            "user": "我和朋友想去重庆玩三天，怎么安排",
            "route": "plan",
            "save": {"current_city": "重庆", "travel_party": "和朋友", "notes": "三天行程"},
        },
        {"user": "你好呀", "route": "chat"},
        {"user": "谢谢你", "route": "chat"},
        {"user": "你是谁", "route": "chat"},
        {"user": "哈哈你还挺聪明", "route": "chat"},
        {"user": "那边周末会下雨吗", "route": "weather", "context": {"current_city": "青岛"}},
        {"user": "这两天冷不冷", "route": "weather", "context": {"current_city": "哈尔滨"}},
        {"user": "要不要带伞", "route": "weather", "context": {"current_city": "苏州"}},
        {"user": "那我明天穿什么合适", "route": "weather", "context": {"current_city": "昆明"}},
        {
            "user": "那附近还有什么适合老人逛的",
            "route": "spot",
            "context": {"current_city": "西安", "travel_party": "带父母"},
        },
        {
            "user": "这个景点值不值得去",
            "route": "spot",
            "context": {"current_city": "洛阳", "current_spot": "龙门石窟"},
        },
        {"user": "周边还有什么能看夜景的", "route": "spot", "context": {"current_city": "重庆"}},
        {
            "user": "那边有没有适合小孩玩的",
            "route": "spot",
            "context": {"current_city": "青岛", "travel_party": "带小孩"},
        },
        {"user": "那我两天怎么安排", "route": "plan", "context": {"current_city": "厦门"}},
        {"user": "那从这里开车去机场要多久", "route": "plan", "context": {"current_city": "杭州"}},
        {"user": "那预算1500的话怎么排", "route": "plan", "context": {"current_city": "成都"}},
        {
            "user": "我们三个人的话行程怎么调",
            "route": "plan",
            "context": {"current_city": "上海", "travel_party": "三个人"},
        },
    ]

    return [
        build_router_case(
            user_text=item["user"],
            route=item["route"],
            context_observation=item.get("context", "暂无上下文记忆"),
            save_context=item.get("save"),
        )
        for item in specs
    ]


def main() -> None:
    dataset = build_dataset()
    OUTPUT_PATH.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(dataset)} cases to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
