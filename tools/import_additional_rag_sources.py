"""
Import additional public travel datasets into the structured RAG knowledge base.

Chosen sources for this pass:
1. ConvLab/CrossWOZ attraction database
2. Kakuluk/Hong_Kong_Tour_Guide

Rationale:
- Both are public and directly downloadable in the current environment.
- Both are Chinese travel-domain data.
- Both can be transformed into the current structured schema used by spots_knowledge.json.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import requests
from huggingface_hub import hf_hub_download


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
DATASETS_DIR = DATA_DIR / "datasets_rag"
SPOTS_FILE = DATA_DIR / "spots_knowledge.json"
PROCESSED_CROSSWOZ = DATASETS_DIR / "crosswoz_attractions_processed.json"
PROCESSED_HK = DATASETS_DIR / "hongkong_tour_guide_processed.json"

NEW_SOURCES = {"CrossWOZ景点库", "香港旅游指南QA"}

TAG_KEYWORDS = {
    "自然风景": ["湖", "山", "瀑布", "峡谷", "湿地", "森林", "草原", "花海", "溪", "泉", "海滩"],
    "历史": ["古", "遗址", "历史", "朝", "纪念", "文物", "遗迹", "古蹟"],
    "寺庙": ["寺", "庙", "祠", "塔", "佛", "道观", "禅"],
    "古建筑": ["古城", "古镇", "古街", "古建", "城墙", "城楼", "牌坊", "建筑群"],
    "博物馆": ["博物馆", "展馆", "纪念馆", "艺术馆", "文化馆"],
    "公园": ["公园", "广场", "花园", "植物园"],
    "美食": ["美食", "小吃", "餐厅", "饭店", "牛腩", "奶茶"],
    "夜景": ["夜景", "灯光", "夜市", "夜"],
    "亲子": ["亲子", "儿童", "孩子", "乐园", "缆车"],
    "拍照": ["拍照", "打卡", "摄影", "机位", "俯瞰", "观景台"],
    "观景": ["观景", "俯瞰", "全景", "维港", "海景"],
    "地铁便利": ["地铁", "站", "出口"],
}

DISTRICT_PATTERN = re.compile(r"([\u4e00-\u9fff]{2,12}(?:区|縣|县|镇|鄉|乡))")
CITY_PATTERN = re.compile(r"([\u4e00-\u9fff]{2,12}(?:市|州|特别行政区))")


def normalize_text(text: Any) -> str:
    return " ".join(str(text or "").split()).strip()


def extract_tags(*parts: str) -> list[str]:
    text = " ".join(normalize_text(part) for part in parts)
    tags: list[str] = []
    for tag, keywords in TAG_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            tags.append(tag)
    if not tags:
        tags.append("景点")
    return tags[:8]


def infer_city_and_district(address: str, fallback_city: str = "", fallback_district: str = "") -> tuple[str, str]:
    text = normalize_text(address)
    city = fallback_city
    district = fallback_district

    city_match = CITY_PATTERN.search(text)
    if city_match:
        city = city_match.group(1)
    elif "香港" in text:
        city = "香港特别行政区"

    district_match = DISTRICT_PATTERN.search(text)
    if district_match:
        district = district_match.group(1)
        if city and district.startswith(city):
            district = district[len(city):].strip()

    return city, district


def budget_from_ticket(ticket: Any) -> str:
    text = normalize_text(ticket)
    if not text or text.lower() == "none":
        return "未知"
    if text in {"0", "免费", "免票"}:
        return "免费"
    try:
        value = float(text)
    except ValueError:
        nums = re.findall(r"\d+\.?\d*", text)
        if not nums:
            return "未知"
        value = float(nums[0])
    if value <= 0:
        return "免费"
    if value <= 50:
        return "低"
    if value <= 150:
        return "中"
    return "高"


def build_crosswoz_records() -> list[dict[str, Any]]:
    path = hf_hub_download(repo_id="ConvLab/crosswoz", repo_type="dataset", filename="data.zip")
    with ZipFile(path) as zf:
        raw = json.loads(zf.read("data/attraction_db.json").decode("utf-8"))

    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for idx, item in enumerate(raw, start=1):
        spot_name = normalize_text(item[0])
        details = item[1]
        address = normalize_text(details.get("地址", ""))
        city, district = infer_city_and_district(address)

        dedupe_key = (city, spot_name)
        if not spot_name or dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        phone = normalize_text(details.get("电话", ""))
        subway = normalize_text(details.get("地铁", ""))
        duration = normalize_text(details.get("游玩时间", "")) or "未知"
        rating = details.get("评分", 0) or 0
        nearby_spots = [normalize_text(x) for x in details.get("周边景点", [])[:8] if normalize_text(x)]
        nearby_foods = [normalize_text(x) for x in details.get("周边餐馆", [])[:8] if normalize_text(x)]
        nearby_hotels = [normalize_text(x) for x in details.get("周边酒店", [])[:5] if normalize_text(x)]

        content_parts = []
        if address:
            content_parts.append(f"地址：{address}")
        if subway:
            content_parts.append(f"交通：靠近{subway}")
        if phone:
            content_parts.append(f"电话：{phone}")
        if details.get("门票", "") not in ("", None):
            content_parts.append(f"门票：{details['门票']}")
        if duration and duration != "未知":
            content_parts.append(f"建议游玩时间：{duration}")
        if nearby_spots:
            content_parts.append(f"周边景点：{'、'.join(nearby_spots)}")
        if nearby_foods:
            content_parts.append(f"周边餐馆：{'、'.join(nearby_foods)}")
        if nearby_hotels:
            content_parts.append(f"周边酒店：{'、'.join(nearby_hotels)}")

        content = "；".join(content_parts)
        tags = extract_tags(spot_name, content)

        records.append(
            {
                "id": f"crosswoz_attraction_{idx:04d}",
                "city": city or "未知城市",
                "district": district,
                "spot_name": spot_name,
                "content": content,
                "tags": tags,
                "duration": duration,
                "budget": budget_from_ticket(details.get("门票", "")),
                "rating": float(rating) if rating not in ("", None) else 0.0,
                "source": "CrossWOZ景点库",
            }
        )

    return records


def extract_hk_spot_name(question: str) -> str:
    text = normalize_text(question)
    patterns = [
        r"如何從.+?到(.+?)[？?]?$",
        r"如何前往(.+?)[？?]?$",
        r"(.+?)有什麼特色[？?]?$",
        r"(.+?)值得去嗎[？?]?$",
        r"(.+?)值得逛嗎[？?]?$",
        r"(.+?)有什麼看點[？?]?$",
        r"(.+?)最佳參觀時間[？?]?$",
        r"(.+?)最佳拍攝時段[？?]?$",
        r"(.+?)最佳合影角度[？?]?$",
        r"(.+?)最佳觀賞點[？?]?$",
        r"(.+?)怎麼拍照最好[？?]?$",
        r"(.+?)拍攝技巧[？?]?$",
        r"(.+?)怎麼玩最有效率[？?]?$",
        r"如何安排(.+?)半日遊路線[？?]?$",
        r"(.+?)一日遊路線規劃[？?]?$",
        r"(.+?)遊玩攻略[？?]?$",
        r"如何參觀(.+?)[？?]?$",
        r"(.+?)徒步注意事項[？?]?$",
        r"(.+?)必體驗什麼[？?]?$",
        r"(.+?)有什麼值得買[？?]?$",
        r"(.+?)開放時間.*$",
        r"(.+?)在哪.*$",
    ]
    for pattern in patterns:
        match = re.match(pattern, text)
        if match:
            spot = normalize_text(match.group(1))
            for prefix in ["東區", "南區", "北角", "油尖旺區", "中環", "香港", "尖沙咀", "鰂魚涌", "西環"]:
                if spot.startswith(prefix) and len(spot) > len(prefix) + 1:
                    spot = spot[len(prefix):].strip()
                    break
            return spot
    return ""


def keep_hk_row(question: str, response: str) -> bool:
    text = f"{normalize_text(question)} {normalize_text(response)}"
    if any(keyword in text for keyword in ["招牌菜", "牛腩", "餐廳", "餐厅", "美食"]):
        return False
    if any(keyword in text for keyword in ["香港各區", "香港哪裡", "各區中哪個", "哪區最適合"]):
        return False

    return any(
        keyword in text
        for keyword in [
            "館",
            "區",
            "山頂",
            "纜車",
            "海洋公園",
            "藝術館",
            "博物館",
            "建築群",
            "碼頭",
            "海灘",
            "公園",
            "天星小輪",
            "廟",
            "教堂",
            "特色",
            "前往",
            "路線",
            "攻略",
            "拍攝",
            "參觀",
        ]
    )


def district_from_hk_question(question: str) -> str:
    text = normalize_text(question)
    match = DISTRICT_PATTERN.search(text)
    if match:
        return match.group(1)
    return ""


def build_hk_guide_records() -> list[dict[str, Any]]:
    path = hf_hub_download(
        repo_id="Kakuluk/Hong_Kong_Tour_Guide",
        repo_type="dataset",
        filename="HONGKONG_data.json",
    )
    raw_rows = json.loads(Path(path).read_text(encoding="utf-8"))

    records: list[dict[str, Any]] = []
    seen: set[str] = set()

    for idx, row in enumerate(raw_rows, start=1):
        question = normalize_text(row.get("Question", ""))
        response = normalize_text(row.get("Response", ""))
        cot = normalize_text(row.get("Complex_CoT", ""))
        if not question or not response or not keep_hk_row(question, response):
            continue

        spot_name = extract_hk_spot_name(question)
        if not spot_name:
            continue
        if spot_name in seen:
            continue
        seen.add(spot_name)

        content_parts = [f"问答摘要：{response}"]
        if cot:
            content_parts.append(f"深度提示：{cot}")
        content = "；".join(content_parts)

        records.append(
            {
                "id": f"hk_tour_guide_{idx:04d}",
                "city": "香港特别行政区",
                "district": district_from_hk_question(question),
                "spot_name": spot_name,
                "content": content,
                "tags": extract_tags(question, response, cot, "香港旅游"),
                "duration": "未知",
                "budget": "未知",
                "rating": 4.2,
                "source": "香港旅游指南QA",
            }
        )

    return records


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    spots = json.loads(SPOTS_FILE.read_text(encoding="utf-8"))
    base_spots = [item for item in spots if item.get("source") not in NEW_SOURCES]

    crosswoz_records = build_crosswoz_records()
    hk_records = build_hk_guide_records()

    save_json(PROCESSED_CROSSWOZ, crosswoz_records)
    save_json(PROCESSED_HK, hk_records)

    merged = base_spots + crosswoz_records + hk_records
    save_json(SPOTS_FILE, merged)

    source_counts = Counter(item.get("source", "") for item in merged)
    print("Merged records:", len(merged))
    print("Added CrossWOZ:", len(crosswoz_records))
    print("Added Hong Kong guide:", len(hk_records))
    print("Source counts:", dict(source_counts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
