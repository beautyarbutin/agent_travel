from __future__ import annotations

import json
from argparse import ArgumentParser, Namespace
from collections import Counter
from pathlib import Path
from typing import Any


TOOLS_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT = TOOLS_DIR / "router_eval_risawoz.json"

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
]

DOMAIN_TO_ROUTE = {
    "天气": "weather",
    "weather": "weather",
    "旅游景点": "spot",
    "景点": "spot",
    "attraction": "spot",
    "通用": "chat",
    "general": "chat",
    "火车": "plan",
    "飞机": "plan",
    "地铁": "plan",
    "出租": "plan",
    "打车": "plan",
    "train": "plan",
    "flight": "plan",
    "metro": "plan",
    "taxi": "plan",
}

ROUTE_TO_AGENT = {
    "weather": "weather_agent",
    "spot": "spot_agent",
    "plan": "plan_agent",
}


def parse_args() -> Namespace:
    parser = ArgumentParser(description="Build router evaluation cases from GEM/RiSAWOZ.")
    parser.add_argument("--split", default="validation", help="Dataset split, e.g. validation/test/train")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output JSON path")
    parser.add_argument(
        "--max-per-route",
        type=int,
        default=120,
        help="Maximum kept turns per route class",
    )
    return parser.parse_args()


def normalize_domain(domain: str) -> str:
    return (domain or "").strip().lower()


def route_from_domains(domains: list[str]) -> str | None:
    mapped = {
        DOMAIN_TO_ROUTE[normalize_domain(domain)]
        for domain in domains
        if normalize_domain(domain) in DOMAIN_TO_ROUTE
    }
    if len(mapped) != 1:
        return None
    return next(iter(mapped))


def compact_belief_state(turn: dict[str, Any]) -> str:
    belief_state = turn.get("belief_state") or {}
    informed = belief_state.get("inform slot-values") or {}
    compact: dict[str, Any] = {}
    for key, value in informed.items():
        if value in ("", None, [], {}):
            continue
        compact[key] = value
    if not compact:
        return "暂无上下文记忆"
    return json.dumps(compact, ensure_ascii=False)


def build_case(user_text: str, route: str, context_text: str) -> dict[str, Any]:
    conversations: list[dict[str, Any]] = [
        {"from": "human", "value": user_text},
        {"from": "gpt", "value": "", "tool_calls": [{"name": "get_context", "arguments": {}}]},
        {"from": "observation", "value": context_text},
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

    return {
        "system": SYSTEM_PROMPT,
        "tools": TOOLS,
        "conversations": conversations,
    }


def main() -> None:
    args = parse_args()

    try:
        from datasets import load_dataset  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency: datasets. Install with `pip install datasets` first."
        ) from exc

    dataset = load_dataset("GEM/RiSAWOZ", split=args.split)

    kept: list[dict[str, Any]] = []
    route_counts: Counter[str] = Counter()
    skip_counts: Counter[str] = Counter()

    for row in dataset:
        dialogue = row.get("dialogue") or []
        for turn in dialogue:
            user_text = (turn.get("user_utterance") or "").strip()
            if not user_text:
                skip_counts["empty_user_text"] += 1
                continue

            domains = turn.get("turn_domain") or []
            route = route_from_domains(domains)
            if route is None:
                skip_counts["ambiguous_or_unsupported_domain"] += 1
                continue

            if route_counts[route] >= args.max_per_route:
                skip_counts[f"{route}_overflow"] += 1
                continue

            context_text = compact_belief_state(turn)
            kept.append(build_case(user_text=user_text, route=route, context_text=context_text))
            route_counts[route] += 1

    output_path = Path(args.output).resolve()
    output_path.write_text(json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Saved {len(kept)} cases to {output_path}")
    print("Route counts:", json.dumps(route_counts, ensure_ascii=False))
    print("Skip counts:", json.dumps(skip_counts, ensure_ascii=False))


if __name__ == "__main__":
    main()
