"""
Build a reproducible spot benchmark from exact match expanded test cases.

The benchmark is designed for comparing base vs LoRA spot-answer generation
under the same provided context. Each case includes:

- a user query
- the matched source document
- a compact context payload
- a reference answer template
- required fact keys for deterministic scoring
"""
from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any


TOOLS_DIR = Path(__file__).resolve().parent
ROOT_DIR = TOOLS_DIR.parent
DEFAULT_CASES = TOOLS_DIR / "expanded_test_cases.json"
DEFAULT_DOCS = ROOT_DIR / "storage" / "doecment.json"
DEFAULT_OUTPUT = TOOLS_DIR / "spot_eval_cases.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build spot evaluation cases.")
    parser.add_argument("--cases", type=str, default=str(DEFAULT_CASES), help="expanded_test_cases.json path")
    parser.add_argument("--docs", type=str, default=str(DEFAULT_DOCS), help="doecment.json path")
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT), help="output benchmark path")
    parser.add_argument("--max-cases", type=int, default=80, help="number of cases to sample, 0 means all")
    parser.add_argument("--seed", type=int, default=20260314, help="random seed")
    return parser.parse_args()


def core_city(text: str) -> str:
    text = (text or "").strip()
    for suffix in ("市", "地区", "自治州", "盟", "州"):
        if text.endswith(suffix):
            return text[: -len(suffix)]
    return text


def core_district(text: str) -> str:
    text = (text or "").strip()
    for suffix in ("区", "县", "旗", "市"):
        if text.endswith(suffix):
            return text[: -len(suffix)]
    return text


def first_sentences(text: str, max_len: int = 120) -> str:
    raw = " ".join((text or "").split())
    if not raw:
        return ""
    chunks = []
    current = []
    for ch in raw:
        current.append(ch)
        if ch in "。！？；;":
            chunks.append("".join(current).strip())
            if len("".join(chunks)) >= max_len:
                break
            current = []
    if current and len("".join(chunks)) < max_len:
        chunks.append("".join(current).strip())
    merged = "".join(chunks).strip()
    return merged[:max_len].rstrip("，,、 ")


def spot_name_variants(spot_name: str) -> list[str]:
    variants = [spot_name.strip()]
    if "(" in spot_name and ")" in spot_name:
        prefix = spot_name.split("(", 1)[0].strip()
        inside = spot_name.split("(", 1)[1].split(")", 1)[0].strip()
        variants.extend([prefix, inside])
    if "（" in spot_name and "）" in spot_name:
        prefix = spot_name.split("（", 1)[0].strip()
        inside = spot_name.split("（", 1)[1].split("）", 1)[0].strip()
        variants.extend([prefix, inside])
    deduped = []
    seen = set()
    for item in variants:
        if item and item not in seen:
            deduped.append(item)
            seen.add(item)
    return deduped


def duration_variants(duration: str) -> list[str]:
    text = duration.strip()
    variants = [text]
    stripped = text.replace("建议游览时间：", "").replace("建议游玩时间：", "").strip()
    if stripped:
        variants.append(stripped)
        normalized = stripped.replace(" - ", "-").replace("小时 - ", "-").replace("小时-", "-")
        variants.append(normalized)
        if " - " in stripped:
            left, right = [part.strip() for part in stripped.split(" - ", 1)]
            variants.extend([f"{left}到{right}", f"{left}至{right}"])
            if left.endswith("小时") and right.endswith("小时"):
                left_num = left[:-2].strip()
                right_num = right[:-2].strip()
                variants.extend(
                    [
                        f"{left_num}到{right_num}小时",
                        f"{left_num}至{right_num}小时",
                        f"{left_num}-{right_num}小时",
                        f"{left_num}~{right_num}小时",
                    ]
                )
    deduped = []
    seen = set()
    for item in variants:
        item = item.strip()
        if item and item not in seen:
            deduped.append(item)
            seen.add(item)
    return deduped


def budget_variants(budget: str) -> list[str]:
    mapping = {
        "高": ["高", "偏高", "较高", "花费较高", "预算较高"],
        "中": ["中", "中等", "适中", "预算适中"],
        "低": ["低", "偏低", "较低", "花费较低", "预算较低"],
        "免费": ["免费", "免门票", "不用门票", "无需门票"],
    }
    return mapping.get(budget.strip(), [budget.strip()] if budget.strip() else [])


def infer_required_keys(query: str) -> list[str]:
    q = query.strip()
    needs_location = any(token in q for token in ("在哪", "哪里", "地址", "位置"))
    needs_budget = any(token in q for token in ("门票", "多少钱", "预算", "费用", "价格"))
    needs_duration = any(token in q for token in ("怎么玩", "攻略", "怎么逛", "游览", "路线", "环湖"))
    needs_highlights = any(token in q for token in ("好玩吗", "值得去吗", "推荐", "看什么", "特色", "适合"))

    required = ["spot_name"]
    if needs_location:
        required.append("location")
    if needs_budget:
        required.append("budget")
    if needs_duration:
        required.append("duration")
    if needs_highlights or (not needs_location and not needs_budget):
        required.append("highlight")
    # Keep order stable and unique.
    seen = set()
    ordered = []
    for item in required:
        if item not in seen:
            ordered.append(item)
            seen.add(item)
    return ordered


def make_reference_answer(query: str, doc: dict[str, Any]) -> str:
    spot_name = (doc.get("spot_name") or "").strip()
    city = (doc.get("city") or "").strip()
    district = (doc.get("district") or "").strip()
    duration = (doc.get("duration") or "").strip()
    budget = str(doc.get("budget") or "").strip()
    tags = [str(item).strip() for item in doc.get("tags", []) if str(item).strip()]
    tag_text = "、".join(tags[:3]) if tags else "旅游观光"
    summary = first_sentences(str(doc.get("content") or ""))

    if any(token in query for token in ("在哪", "哪里", "地址", "位置")):
        return f"{spot_name}位于{city}{district}，亮点有{tag_text}。"
    if any(token in query for token in ("门票", "多少钱", "预算", "费用", "价格")):
        return f"{spot_name}位于{city}{district}，游玩预算大致{budget}，建议游玩{duration}，亮点有{tag_text}。"
    if any(token in query for token in ("怎么玩", "攻略", "怎么逛", "游览", "路线", "环湖")):
        return f"{spot_name}位于{city}{district}，建议游玩{duration}，预算{budget}，亮点有{tag_text}。{summary}"
    if any(token in query for token in ("好玩吗", "值得去吗", "推荐", "适合")):
        return f"{spot_name}位于{city}{district}，亮点有{tag_text}，建议游玩{duration}，预算{budget}。{summary}"
    return f"{spot_name}位于{city}{district}，建议游玩{duration}，预算{budget}，亮点有{tag_text}。{summary}"


def make_context(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "spot_name": (doc.get("spot_name") or "").strip(),
        "city": (doc.get("city") or "").strip(),
        "district": (doc.get("district") or "").strip(),
        "duration": str(doc.get("duration") or "").strip(),
        "budget": str(doc.get("budget") or "").strip(),
        "tags": [str(item).strip() for item in doc.get("tags", []) if str(item).strip()][:5],
        "content_summary": first_sentences(str(doc.get("content") or ""), max_len=180),
        "source": (doc.get("source") or "").strip(),
    }


def make_expected_facts(doc: dict[str, Any]) -> dict[str, list[str]]:
    city = (doc.get("city") or "").strip()
    district = (doc.get("district") or "").strip()
    budget = str(doc.get("budget") or "").strip()
    duration = str(doc.get("duration") or "").strip()
    tags = [str(item).strip() for item in doc.get("tags", []) if str(item).strip()]

    location_candidates = [city, core_city(city)]
    if district:
        location_candidates.extend([district, core_district(district)])
    return {
        "spot_name": spot_name_variants((doc.get("spot_name") or "").strip()),
        "location": [item for item in location_candidates if item],
        "duration": duration_variants(duration) if duration else [],
        "budget": budget_variants(budget) if budget else [],
        "highlight": tags[:5],
    }


def stratified_sample(cases: list[dict[str, Any]], max_cases: int, seed: int) -> list[dict[str, Any]]:
    if max_cases <= 0 or max_cases >= len(cases):
        return list(cases)

    rng = random.Random(seed)
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        buckets[case.get("category", "未知")].append(case)

    categories = sorted(buckets)
    total = len(cases)
    sampled: list[dict[str, Any]] = []

    for category in categories:
        bucket = buckets[category]
        target = max(1, round(len(bucket) / total * max_cases))
        if target >= len(bucket):
            sampled.extend(bucket)
        else:
            sampled.extend(rng.sample(bucket, target))

    # Trim or pad deterministically to the exact requested size.
    sampled.sort(key=lambda item: (item.get("category", ""), item.get("query", "")))
    if len(sampled) > max_cases:
        sampled = sampled[:max_cases]
    elif len(sampled) < max_cases:
        remaining = [item for item in cases if item not in sampled]
        remaining.sort(key=lambda item: (item.get("category", ""), item.get("query", "")))
        sampled.extend(remaining[: max_cases - len(sampled)])

    return sampled


def main() -> None:
    args = parse_args()
    cases_path = Path(args.cases).resolve()
    docs_path = Path(args.docs).resolve()
    output_path = Path(args.output).resolve()

    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    docs = json.loads(docs_path.read_text(encoding="utf-8"))
    doc_map = {doc["id"]: doc for doc in docs if doc.get("id")}

    exact_cases = [case for case in cases if "expected_id" in case and case["expected_id"] in doc_map]
    sampled_cases = stratified_sample(exact_cases, args.max_cases, args.seed)

    output: list[dict[str, Any]] = []
    for idx, case in enumerate(sampled_cases):
        doc = doc_map[case["expected_id"]]
        context = make_context(doc)
        output.append(
            {
                "case_id": f"spot_eval_{idx:03d}",
                "query": case["query"],
                "category": case.get("category", ""),
                "expected_id": case["expected_id"],
                "context": context,
                "reference_answer": make_reference_answer(case["query"], doc),
                "expected_facts": make_expected_facts(doc),
                "required_keys": infer_required_keys(case["query"]),
            }
        )

    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(output)} cases to {output_path}")


if __name__ == "__main__":
    main()
