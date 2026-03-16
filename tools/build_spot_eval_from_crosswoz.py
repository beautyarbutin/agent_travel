"""
Build a public spot benchmark from the raw CrossWOZ data package.

The resulting JSON matches the input schema expected by eval_spot_answers.py,
so it can be uploaded to AutoDL and evaluated without any Hugging Face access.
"""
from __future__ import annotations

import argparse
import json
import random
import re
from collections import defaultdict
from pathlib import Path
from typing import Any
from zipfile import ZipFile


TOOLS_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT = TOOLS_DIR / "spot_eval_crosswoz.json"
DEFAULT_CACHE_ZIP = (
    Path.home()
    / ".cache"
    / "huggingface"
    / "hub"
    / "datasets--ConvLab--crosswoz"
    / "snapshots"
)

TARGET_SLOTS = ["名称", "地址", "游玩时间", "门票", "评分"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build public spot benchmark from CrossWOZ.")
    parser.add_argument(
        "--zip-path",
        type=str,
        default=None,
        help="Path to CrossWOZ data.zip. If omitted, try the local HF cache.",
    )
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT), help="Output JSON path.")
    parser.add_argument("--max-per-slot", type=int, default=30, help="Max samples per primary slot.")
    parser.add_argument("--seed", type=int, default=20260314, help="Random seed.")
    return parser.parse_args()


def find_default_zip() -> Path:
    if not DEFAULT_CACHE_ZIP.exists():
        raise FileNotFoundError("CrossWOZ cache not found. Please provide --zip-path.")

    snapshots = sorted(p for p in DEFAULT_CACHE_ZIP.iterdir() if p.is_dir())
    if not snapshots:
        raise FileNotFoundError("CrossWOZ snapshots not found. Please provide --zip-path.")

    for snapshot in reversed(snapshots):
        candidate = snapshot / "data.zip"
        if candidate.exists():
            return candidate

    raise FileNotFoundError("CrossWOZ data.zip not found. Please provide --zip-path.")


def normalize_space(text: str) -> str:
    return " ".join((text or "").split()).strip()


def normalize_title(text: str) -> str:
    text = normalize_space(text)
    return text.replace("（", "(").replace("）", ")")


def name_variants(name: str) -> list[str]:
    if not name:
        return []
    normalized = normalize_title(name)
    variants = [normalized]
    if "(" in normalized and ")" in normalized:
        prefix = normalized.split("(", 1)[0].strip()
        inside = normalized.split("(", 1)[1].split(")", 1)[0].strip()
        variants.extend([prefix, inside])
    deduped = []
    seen = set()
    for item in variants:
        if item and item not in seen:
            deduped.append(item)
            seen.add(item)
    return deduped


def money_variants(value: Any) -> list[str]:
    text = str(value).strip()
    if not text:
        return []
    variants = [text]
    if text == "0":
        variants.extend(["0元", "免费", "免门票", "不用门票", "无需门票"])
    elif text.isdigit():
        variants.extend([f"{text}元", f"门票{text}元", f"{text}块"])
    elif text == "免费":
        variants.extend(["免费", "免门票", "不用门票", "无需门票"])
    deduped = []
    seen = set()
    for item in variants:
        if item and item not in seen:
            deduped.append(item)
            seen.add(item)
    return deduped


def duration_variants(value: str) -> list[str]:
    text = normalize_space(value)
    if not text:
        return []
    variants = [text]
    stripped = text.replace("小时 - ", "小时-").replace("小时- ", "小时-")
    variants.append(stripped)
    if " - " in text:
        compact = text.replace(" - ", "-")
        variants.append(compact)
        left, right = [part.strip() for part in text.split(" - ", 1)]
        variants.append(f"{left}到{right}")
        variants.append(f"{left}至{right}")
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
            variants.append(compact.replace("小时-", "-"))
    deduped = []
    seen = set()
    for item in variants:
        item = item.strip()
        if item and item not in seen:
            deduped.append(item)
            seen.add(item)
    return deduped


def rating_variants(value: Any) -> list[str]:
    text = str(value).strip()
    if not text:
        return []
    return [text, f"{text}分"]


def extract_location_candidates(address: str) -> list[str]:
    text = normalize_space(address)
    if not text:
        return []
    variants = [text]

    city_match = re.search(r"(.+?市)", text)
    district_match = re.search(r"(.+?(?:区|县|镇|乡|村))", text)
    if city_match:
        city = city_match.group(1)
        variants.extend([city, city[:-1] if city.endswith("市") else city])
    if district_match:
        district = district_match.group(1)
        variants.append(district)
    deduped = []
    seen = set()
    for item in variants:
        if item and item not in seen:
            deduped.append(item)
            seen.add(item)
    return deduped


def collect_user_requested_slots(user_turn: dict[str, Any]) -> list[str]:
    slots: list[str] = []
    acts = user_turn.get("dialogue_acts", {})
    for item in acts.get("binary", []):
        if item.get("domain") == "景点" and item.get("intent") == "Request":
            slot = item.get("slot", "").strip()
            if slot in TARGET_SLOTS:
                slots.append(slot)
    return slots


def infer_primary_slot(user_turn: dict[str, Any]) -> str | None:
    requested = collect_user_requested_slots(user_turn)
    for slot in TARGET_SLOTS:
        if slot in requested:
            return slot
    return None


def find_spot_name(system_turn: dict[str, Any], user_turn: dict[str, Any]) -> str | None:
    db_results = system_turn.get("db_results", {}).get("景点")
    if isinstance(db_results, list) and len(db_results) == 1 and db_results[0].get("名称"):
        return db_results[0]["名称"]

    for item in system_turn.get("dialogue_acts", {}).get("non-categorical", []):
        if item.get("domain") == "景点" and item.get("slot") == "名称" and item.get("value"):
            return item["value"]

    for state_item in reversed(user_turn.get("user_state", [])):
        spot_state = state_item.get("景点")
        if not spot_state:
            continue
        inform = spot_state.get("inform", {})
        if "名称" in inform and inform["名称"][0]:
            return inform["名称"][0]

    return None


def build_context(row: dict[str, Any]) -> dict[str, Any]:
    facts = []
    if row.get("地址"):
        facts.append(f"地址：{row['地址']}")
    if row.get("地铁"):
        facts.append(f"交通：{row['地铁']}")
    if row.get("电话"):
        facts.append(f"电话：{row['电话']}")
    if row.get("评分") not in ("", None):
        facts.append(f"评分：{row['评分']}分")
    if row.get("周边景点"):
        facts.append(f"周边景点：{'、'.join(row['周边景点'][:3])}")

    return {
        "spot_name": normalize_title(str(row.get("名称", ""))),
        "city": "",
        "district": "",
        "duration": normalize_space(str(row.get("游玩时间", ""))),
        "budget": str(row.get("门票", "")).strip(),
        "tags": ["景点"],
        "content_summary": "；".join(facts),
        "source": "CrossWOZ",
    }


def build_expected_facts(row: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "spot_name": name_variants(str(row.get("名称", ""))),
        "location": extract_location_candidates(str(row.get("地址", ""))),
        "duration": duration_variants(str(row.get("游玩时间", ""))),
        "budget": money_variants(row.get("门票", "")),
        "rating": [] if row.get("评分") in ("", None, "None") else rating_variants(row.get("评分", "")),
    }


def build_reference_answer(user_query: str, row: dict[str, Any], requested_slots: list[str]) -> str:
    name = normalize_title(str(row.get("名称", "")))
    parts = []
    if "名称" in requested_slots or not requested_slots:
        parts.append(f"推荐你关注{name}")
    else:
        parts.append(f"{name}")

    if "地址" in requested_slots and row.get("地址"):
        parts.append(f"地址是{row['地址']}")
    if "游玩时间" in requested_slots and row.get("游玩时间"):
        parts.append(f"建议游玩时间是{row['游玩时间']}")
    if "门票" in requested_slots and row.get("门票") not in ("", None):
        parts.append(f"门票大致是{row['门票']}元" if str(row["门票"]).isdigit() else f"门票是{row['门票']}")
    if "评分" in requested_slots and row.get("评分") not in ("", None):
        parts.append(f"评分约{row['评分']}分")

    if len(parts) == 1:
        parts.append("这是一个适合游览的景点")
    return "，".join(parts) + "。"


def build_required_keys(requested_slots: list[str]) -> list[str]:
    key_map = {
        "名称": "spot_name",
        "地址": "location",
        "游玩时间": "duration",
        "门票": "budget",
        "评分": "rating",
    }
    required: list[str] = ["spot_name"]
    for slot in requested_slots:
        mapped = key_map.get(slot)
        if mapped and mapped not in required:
            required.append(mapped)
    return required


def load_crosswoz(zip_path: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    with ZipFile(zip_path) as zf:
        dialogues = json.loads(zf.read("data/dialogues.json").decode("utf-8"))
        db_rows = json.loads(zf.read("data/attraction_db.json").decode("utf-8"))

    db_map: dict[str, dict[str, Any]] = {}
    for row in db_rows:
        if isinstance(row, list) and len(row) == 2 and isinstance(row[1], dict):
            db_map[normalize_title(str(row[0]))] = row[1]

    return dialogues, db_map


def collect_cases(dialogues: list[dict[str, Any]], db_map: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for dialogue in dialogues:
        turns = dialogue.get("turns", [])
        for idx in range(0, len(turns) - 1, 2):
            user_turn = turns[idx]
            system_turn = turns[idx + 1]
            if user_turn.get("speaker") != "user" or system_turn.get("speaker") != "system":
                continue

            primary_slot = infer_primary_slot(user_turn)
            if primary_slot is None:
                continue

            spot_name = find_spot_name(system_turn, user_turn)
            if not spot_name:
                continue

            row = db_map.get(normalize_title(spot_name))
            if row is None:
                continue

            requested_slots = collect_user_requested_slots(user_turn)
            if not requested_slots:
                continue

            expected_facts = build_expected_facts(row)
            required_keys = build_required_keys(requested_slots)
            if any(not expected_facts.get(key) for key in required_keys):
                continue

            cases.append(
                {
                    "case_id": f"crosswoz_{dialogue['dialogue_id']}_{user_turn['utt_idx']}",
                    "query": normalize_space(user_turn.get("utterance", "")),
                    "category": f"CrossWOZ-{primary_slot}",
                    "expected_id": normalize_title(spot_name),
                    "context": build_context(row),
                    "reference_answer": build_reference_answer(user_turn.get("utterance", ""), row, requested_slots),
                    "expected_facts": expected_facts,
                    "required_keys": required_keys,
                    "source_reference": {
                        "dialogue_id": dialogue.get("dialogue_id"),
                        "turn_idx": user_turn.get("utt_idx"),
                        "requested_slots": requested_slots,
                        "system_utterance": system_turn.get("utterance", ""),
                    },
                }
            )
    return cases


def stratified_sample(cases: list[dict[str, Any]], max_per_slot: int, seed: int) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        grouped[case["category"]].append(case)

    rng = random.Random(seed)
    sampled: list[dict[str, Any]] = []
    for category, bucket in sorted(grouped.items()):
        if len(bucket) <= max_per_slot:
            sampled.extend(bucket)
        else:
            sampled.extend(rng.sample(bucket, max_per_slot))

    sampled.sort(key=lambda item: (item["category"], item["query"], item["case_id"]))
    return sampled


def main() -> None:
    args = parse_args()
    zip_path = Path(args.zip_path).resolve() if args.zip_path else find_default_zip()
    output_path = Path(args.output).resolve()

    dialogues, db_map = load_crosswoz(zip_path)
    cases = collect_cases(dialogues, db_map)
    sampled = stratified_sample(cases, args.max_per_slot, args.seed)

    output_path.write_text(json.dumps(sampled, ensure_ascii=False, indent=2), encoding="utf-8")

    counts = defaultdict(int)
    for case in sampled:
        counts[case["category"]] += 1

    print(f"Wrote {len(sampled)} cases to {output_path}")
    for category, count in sorted(counts.items()):
        print(f"  {category}: {count}")


if __name__ == "__main__":
    main()
