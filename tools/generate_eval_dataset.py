"""
离线扩展 RAG 评测集生成脚本。

目标：
1. 保留当前手工基线 case
2. 基于现有 doecment.json 自动扩展到更大规模
3. 不依赖本地大模型或外部 API，保证可复现
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


TOOLS_DIR = Path(__file__).resolve().parent
ROOT_DIR = TOOLS_DIR.parent
DEFAULT_INPUT = ROOT_DIR / "storage" / "doecment.json"
DEFAULT_OUTPUT = TOOLS_DIR / "expanded_test_cases.json"

SOURCE_PLAN = {
    "独家手写攻略": 20,
    "Kaggle/去哪儿网": 40,
    "China312地理数据集": 10,
}

PREFERRED_CITY_CASES = [
    "北京",
    "重庆",
    "武汉",
    "长沙",
    "成都",
    "西安",
    "桂林",
    "拉萨",
    "洛阳",
    "济南",
    "大理",
    "青岛",
    "杭州",
    "厦门",
    "昆明",
    "丽江",
    "衡水",
    "德州",
    "石家庄",
    "荆州",
]

BASELINE_CASES: list[dict[str, Any]] = [
    {"query": "衡水湖怎么玩", "expected_id": "spot_hengshui_001", "desc": "手写·直接提景点名", "category": "手写"},
    {"query": "故城二道街有什么好吃的", "expected_id": "spot_gucheng_001", "desc": "手写·美食+景点名", "category": "手写"},
    {"query": "正定古城攻略", "expected_id": "spot_shijiazhuang_001", "desc": "手写·古城攻略", "category": "手写"},
    {"query": "庆云有什么寺庙", "expected_id": "spot_qingyun_001", "desc": "手写·寺庙搜索", "category": "手写"},
    {"query": "庆林寺塔值得去吗", "expected_id": "spot_gucheng_002", "desc": "手写·具体古塔", "category": "手写"},
    {"query": "哪里适合观鸟", "expected_id": "spot_hengshui_001", "desc": "手写·标签语义", "category": "手写"},
    {"query": "带小孩去哪玩", "expected_id": "spot_qingyun_001", "desc": "手写·亲子标签", "category": "手写"},
    {"query": "哪里有免费停车", "expected_id": "spot_shijiazhuang_001", "desc": "手写·免费停车", "category": "手写"},
    {"query": "运河文化去哪看", "expected_id": "spot_gucheng_001", "desc": "手写·运河文化", "category": "手写"},
    {"query": "想看自然风景去哪", "expected_id": "spot_hengshui_001", "desc": "手写·自然风景", "category": "手写"},
    {"query": "衡水有什么好玩的", "expected_id": "spot_hengshui_001", "desc": "手写·城市级查询", "category": "手写"},
    {"query": "德州旅游推荐", "expected_id": "spot_qingyun_001", "desc": "手写·城市级查询", "category": "手写"},
    {"query": "故宫博物院怎么玩", "expected_id": "kaggle_北京_001", "desc": "Kaggle·故宫", "category": "Kaggle"},
    {"query": "洪崖洞好玩吗", "expected_id": "kaggle_重庆_001", "desc": "Kaggle·洪崖洞", "category": "Kaggle"},
    {"query": "黄鹤楼值得去吗", "expected_id": "kaggle_武汉_002", "desc": "Kaggle·黄鹤楼", "category": "Kaggle"},
    {"query": "岳麓山攻略", "expected_id": "kaggle_长沙_001", "desc": "Kaggle·岳麓山", "category": "Kaggle"},
    {"query": "宽窄巷子怎么逛", "expected_id": "kaggle_成都_003", "desc": "Kaggle·宽窄巷子", "category": "Kaggle"},
    {"query": "兵马俑门票多少钱", "expected_id": "kaggle_西安_006", "desc": "Kaggle·兵马俑", "category": "Kaggle"},
    {"query": "象鼻山在哪", "expected_id": "kaggle_桂林_005", "desc": "Kaggle·象鼻山", "category": "Kaggle"},
    {"query": "布达拉宫开放时间", "expected_id": "kaggle_拉萨_001", "desc": "Kaggle·布达拉宫", "category": "Kaggle"},
    {"query": "龙门石窟怎么游览", "expected_id": "kaggle_洛阳_001", "desc": "Kaggle·龙门石窟", "category": "Kaggle"},
    {"query": "趵突泉好玩吗", "expected_id": "kaggle_济南_001", "desc": "Kaggle·趵突泉", "category": "Kaggle"},
    {"query": "洱海环湖攻略", "expected_id": "kaggle_大理_001", "desc": "Kaggle·洱海", "category": "Kaggle"},
    {"query": "白石山地质公园", "expected_id": "kaggle_保定_001", "desc": "Kaggle·白石山", "category": "Kaggle"},
    {"query": "青岛啤酒博物馆", "expected_id": "kaggle_青岛_015", "desc": "Kaggle·青岛啤酒", "category": "Kaggle"},
    {"query": "天门山玻璃栈道", "expected_id": "kaggle_张家界_011", "desc": "Kaggle·天门山", "category": "Kaggle"},
    {"query": "崂山怎么玩", "expected_id": "kaggle_青岛_041", "desc": "Kaggle·崂山", "category": "Kaggle"},
    {"query": "杭州有什么好玩的", "expected_prefixes": ["kaggle_杭州_"], "desc": "城市级·杭州", "category": "城市级"},
    {"query": "成都旅游攻略", "expected_prefixes": ["kaggle_成都_"], "desc": "城市级·成都", "category": "城市级"},
    {"query": "西安值得去的地方", "expected_prefixes": ["kaggle_西安_"], "desc": "城市级·西安", "category": "城市级"},
    {"query": "厦门景点推荐", "expected_prefixes": ["kaggle_厦门_"], "desc": "城市级·厦门", "category": "城市级"},
    {"query": "重庆三天怎么玩", "expected_prefixes": ["kaggle_重庆_"], "desc": "城市级·重庆", "category": "城市级"},
    {"query": "桂林山水甲天下", "expected_prefixes": ["kaggle_桂林_"], "desc": "城市级·桂林", "category": "城市级"},
    {"query": "丽江古城好玩吗", "expected_prefixes": ["kaggle_丽江_"], "desc": "城市级·丽江", "category": "城市级"},
    {"query": "昆明周边有什么景点", "expected_prefixes": ["kaggle_昆明_"], "desc": "城市级·昆明", "category": "城市级"},
]

SPOT_ONLY_TEMPLATES = [
    "{spot_name}怎么玩",
    "{spot_name}攻略",
    "{spot_name}值得去吗",
    "{spot_name}怎么逛",
]

CITY_SPOT_TEMPLATES = [
    "{city}{spot_name}攻略",
    "{city}{spot_name}值得去吗",
    "{city}{spot_name}怎么玩",
    "{district}{spot_name}怎么逛",
]

CITY_LEVEL_TEMPLATES = [
    "{city}有什么好玩的",
    "{city}旅游攻略",
    "{city}值得去的地方",
    "{city}景点推荐",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="基于本地知识库生成扩展 RAG 评测集。")
    parser.add_argument("--input", type=str, default=str(DEFAULT_INPUT), help="输入 doecment.json 路径")
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT), help="输出 expanded_test_cases.json 路径")
    parser.add_argument("--seed", type=int, default=20260313, help="随机种子，保证结果可复现")
    return parser.parse_args()


def strip_suffix(value: str, suffixes: tuple[str, ...]) -> str:
    text = (value or "").strip()
    for suffix in suffixes:
        if text.endswith(suffix):
            return text[: -len(suffix)]
    return text


def core_city(city: str) -> str:
    return strip_suffix(city, ("市", "地区", "自治州", "盟", "州"))


def core_district(district: str) -> str:
    return strip_suffix(district, ("区", "县", "旗", "市"))


def load_docs(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def usable_doc(doc: dict[str, Any]) -> bool:
    return bool(doc.get("id") and (doc.get("spot_name") or "").strip())


def source_alias(source: str) -> str:
    return {
        "独家手写攻略": "手写",
        "Kaggle/去哪儿网": "Kaggle",
        "China312地理数据集": "China312",
    }.get(source, source or "未知")


def build_spot_name_counts(docs: list[dict[str, Any]]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for doc in docs:
        if usable_doc(doc):
            counter[(doc.get("spot_name") or "").strip()] += 1
    return counter


def choose_template(templates: list[str], index: int) -> str:
    return templates[index % len(templates)]


def add_case(cases: list[dict[str, Any]], seen: set[str], case: dict[str, Any]) -> None:
    query = case["query"].strip()
    signature = json.dumps(
        {
            "query": query,
            "expected_id": case.get("expected_id"),
            "expected_ids": case.get("expected_ids"),
            "expected_prefixes": case.get("expected_prefixes"),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    if not query or signature in seen:
        return
    seen.add(signature)
    case["query"] = query
    cases.append(case)


def sample_docs_by_source(docs: list[dict[str, Any]], rng: random.Random) -> list[dict[str, Any]]:
    sampled: list[dict[str, Any]] = []
    for source, limit in SOURCE_PLAN.items():
        pool = [doc for doc in docs if doc.get("source") == source and usable_doc(doc)]
        pool.sort(key=lambda item: item.get("id", ""))
        if len(pool) <= limit:
            sampled.extend(pool)
        else:
            sampled.extend(rng.sample(pool, limit))
    return sampled


def build_exact_cases(
    doc: dict[str, Any],
    index: int,
    spot_name_counts: Counter[str],
) -> list[dict[str, Any]]:
    source = doc.get("source", "")
    alias = source_alias(source)
    spot_name = (doc.get("spot_name") or "").strip()
    city = core_city(doc.get("city", ""))
    district = core_district(doc.get("district", ""))
    doc_id = doc["id"]

    cases: list[dict[str, Any]] = []

    if spot_name_counts[spot_name] == 1:
        spot_query = choose_template(SPOT_ONLY_TEMPLATES, index).format(spot_name=spot_name)
        cases.append(
            {
                "query": spot_query,
                "expected_id": doc_id,
                "desc": f"精确景点·{alias}",
                "category": "精确景点",
            }
        )

    geo_text = district if district and district != city else city
    if geo_text:
        geo_query = choose_template(CITY_SPOT_TEMPLATES, index).format(
            city=city,
            district=geo_text,
            spot_name=spot_name,
        )
        cases.append(
            {
                "query": geo_query,
                "expected_id": doc_id,
                "desc": f"城市+景点·{alias}",
                "category": "城市+景点",
            }
        )

    return cases


def build_city_cases(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    city_to_ids: dict[str, list[str]] = defaultdict(list)
    for doc in docs:
        if not usable_doc(doc):
            continue
        city = core_city(doc.get("city", ""))
        if not city:
            continue
        city_to_ids[city].append(doc["id"])

    cases: list[dict[str, Any]] = []
    seen_cities: set[str] = set()
    for index, city in enumerate(PREFERRED_CITY_CASES):
        ids = city_to_ids.get(city, [])
        if not ids:
            continue
        seen_cities.add(city)
        query = choose_template(CITY_LEVEL_TEMPLATES, index).format(city=city)
        cases.append(
            {
                "query": query,
                "expected_ids": sorted(ids),
                "desc": "城市级·多答案",
                "category": "城市级",
            }
        )

    # 再补一些有代表性的城市，避免只落在手工列举名单
    extra_candidates = sorted(
        (
            (city, ids)
            for city, ids in city_to_ids.items()
            if city not in seen_cities and len(ids) >= 3
        ),
        key=lambda item: (-len(item[1]), item[0]),
    )
    for index, (city, ids) in enumerate(extra_candidates[:10], start=len(cases)):
        query = choose_template(CITY_LEVEL_TEMPLATES, index).format(city=city)
        cases.append(
            {
                "query": query,
                "expected_ids": sorted(ids),
                "desc": "城市级·自动补充",
                "category": "城市级",
            }
        )

    return cases


def generate_dataset(docs: list[dict[str, Any]], rng: random.Random) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    seen: set[str] = set()

    for case in BASELINE_CASES:
        add_case(cases, seen, dict(case))

    sampled_docs = sample_docs_by_source(docs, rng)
    spot_name_counts = build_spot_name_counts(docs)

    for index, doc in enumerate(sampled_docs):
        for case in build_exact_cases(doc, index=index, spot_name_counts=spot_name_counts):
            add_case(cases, seen, case)

    for case in build_city_cases(docs):
        add_case(cases, seen, case)

    return cases


def print_summary(cases: list[dict[str, Any]]) -> None:
    category_counts = Counter(case.get("category", "未分类") for case in cases)
    print("\n📊 扩展评测集统计")
    print(f"  总 case 数: {len(cases)}")
    for category, count in category_counts.items():
        print(f"  - {category}: {count}")


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    docs = load_docs(input_path)
    rng = random.Random(args.seed)
    cases = generate_dataset(docs, rng)

    output_path.write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"📦 已加载知识库: {input_path}")
    print(f"💾 已生成扩展测试集: {output_path}")
    print_summary(cases)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
