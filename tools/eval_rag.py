"""
RAG 检索评测脚本

升级点：
1. 基于结构化 Top-K 结果计算真正的 Hit@K / MRR
2. 支持默认样例集或外部 JSON 数据集
3. 自动生成图文报告（Markdown + PNG 图表）
4. 输出机器可读结果 results.json，便于后续持续评测
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt


TOOLS_DIR = Path(__file__).resolve().parent
ROOT_DIR = TOOLS_DIR.parent
DEFAULT_EXPANDED_DATASET = TOOLS_DIR / "expanded_test_cases.json"
DEFAULT_REPORT_ROOT = ROOT_DIR / "reports"
DEFAULT_CUTOFFS = (1, 3, 5)

sys.path.insert(0, str(TOOLS_DIR))
from spot_tools import retrieve_knowledge


plt.rcParams["font.sans-serif"] = [
    "Microsoft YaHei",
    "SimHei",
    "Noto Sans CJK SC",
    "Arial Unicode MS",
    "DejaVu Sans",
]
plt.rcParams["axes.unicode_minus"] = False


DEFAULT_TEST_CASES: list[dict[str, str]] = [
    {"query": "衡水湖怎么玩", "expected_id": "spot_hengshui_001", "desc": "手写·直接提景点名"},
    {"query": "故城二道街有什么好吃的", "expected_id": "spot_gucheng_001", "desc": "手写·美食+景点名"},
    {"query": "正定古城攻略", "expected_id": "spot_shijiazhuang_001", "desc": "手写·古城攻略"},
    {"query": "庆云有什么寺庙", "expected_id": "spot_qingyun_001", "desc": "手写·寺庙搜索"},
    {"query": "庆林寺塔值得去吗", "expected_id": "spot_gucheng_002", "desc": "手写·具体古塔"},
    {"query": "哪里适合观鸟", "expected_id": "spot_hengshui_001", "desc": "手写·标签语义"},
    {"query": "带小孩去哪玩", "expected_id": "spot_qingyun_001", "desc": "手写·亲子标签"},
    {"query": "哪里有免费停车", "expected_id": "spot_shijiazhuang_001", "desc": "手写·免费停车"},
    {"query": "运河文化去哪看", "expected_id": "spot_gucheng_001", "desc": "手写·运河文化"},
    {"query": "想看自然风景去哪", "expected_id": "spot_hengshui_001", "desc": "手写·自然风景"},
    {"query": "衡水有什么好玩的", "expected_id": "spot_hengshui_001", "desc": "手写·城市级查询"},
    {"query": "德州旅游推荐", "expected_id": "spot_qingyun_001", "desc": "手写·城市级查询"},
    {"query": "故宫博物院怎么玩", "expected_id": "kaggle_北京_001", "desc": "Kaggle·故宫"},
    {"query": "洪崖洞好玩吗", "expected_id": "kaggle_重庆_001", "desc": "Kaggle·洪崖洞"},
    {"query": "黄鹤楼值得去吗", "expected_id": "kaggle_武汉_002", "desc": "Kaggle·黄鹤楼"},
    {"query": "岳麓山攻略", "expected_id": "kaggle_长沙_001", "desc": "Kaggle·岳麓山"},
    {"query": "宽窄巷子怎么逛", "expected_id": "kaggle_成都_003", "desc": "Kaggle·宽窄巷子"},
    {"query": "兵马俑门票多少钱", "expected_id": "kaggle_西安_006", "desc": "Kaggle·兵马俑"},
    {"query": "象鼻山在哪", "expected_id": "kaggle_桂林_005", "desc": "Kaggle·象鼻山"},
    {"query": "布达拉宫开放时间", "expected_id": "kaggle_拉萨_001", "desc": "Kaggle·布达拉宫"},
    {"query": "龙门石窟怎么游览", "expected_id": "kaggle_洛阳_001", "desc": "Kaggle·龙门石窟"},
    {"query": "趵突泉好玩吗", "expected_id": "kaggle_济南_001", "desc": "Kaggle·趵突泉"},
    {"query": "洱海环湖攻略", "expected_id": "kaggle_大理_001", "desc": "Kaggle·洱海"},
    {"query": "白石山地质公园", "expected_id": "kaggle_保定_001", "desc": "Kaggle·白石山"},
    {"query": "青岛啤酒博物馆", "expected_id": "kaggle_青岛_015", "desc": "Kaggle·青岛啤酒"},
    {"query": "天门山玻璃栈道", "expected_id": "kaggle_张家界_011", "desc": "Kaggle·天门山"},
    {"query": "崂山怎么玩", "expected_id": "kaggle_青岛_041", "desc": "Kaggle·崂山"},
    {"query": "杭州有什么好玩的", "expected_id": "kaggle_杭州_", "desc": "城市级·杭州"},
    {"query": "成都旅游攻略", "expected_id": "kaggle_成都_", "desc": "城市级·成都"},
    {"query": "西安值得去的地方", "expected_id": "kaggle_西安_", "desc": "城市级·西安"},
    {"query": "厦门景点推荐", "expected_id": "kaggle_厦门_", "desc": "城市级·厦门"},
    {"query": "重庆三天怎么玩", "expected_id": "kaggle_重庆_", "desc": "城市级·重庆"},
    {"query": "桂林山水甲天下", "expected_id": "kaggle_桂林_", "desc": "城市级·桂林"},
    {"query": "丽江古城好玩吗", "expected_id": "kaggle_丽江_", "desc": "城市级·丽江"},
    {"query": "昆明周边有什么景点", "expected_id": "kaggle_昆明_", "desc": "城市级·昆明"},
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="评测 RAG 检索质量并生成图文报告。")
    parser.add_argument("--dataset", type=str, default=None, help="外部测试集 JSON 路径")
    parser.add_argument("--top-k", type=int, default=5, help="每个 query 评估的返回条数")
    parser.add_argument("--min-score", type=float, default=0.5, help="保留结果的最小相关度阈值")
    parser.add_argument("--report-dir", type=str, default=None, help="报告输出目录")
    parser.add_argument("--quiet", action="store_true", help="只打印汇总，不逐条打印")
    return parser.parse_args()


def load_test_cases(dataset_arg: str | None) -> tuple[list[dict[str, Any]], str]:
    dataset_path = Path(dataset_arg).resolve() if dataset_arg else None
    dataset_label = "builtin"
    raw_cases: list[dict[str, Any]]

    if dataset_path is not None:
        with dataset_path.open("r", encoding="utf-8") as f:
            raw_cases = json.load(f)
        dataset_label = str(dataset_path)
    elif DEFAULT_EXPANDED_DATASET.exists():
        with DEFAULT_EXPANDED_DATASET.open("r", encoding="utf-8") as f:
            raw_cases = json.load(f)
        dataset_label = str(DEFAULT_EXPANDED_DATASET)
    else:
        raw_cases = DEFAULT_TEST_CASES

    normalized_cases: list[dict[str, Any]] = []
    for idx, case in enumerate(raw_cases, start=1):
        if not isinstance(case, dict):
            raise ValueError(f"测试用例 #{idx} 不是对象: {case!r}")

        query = str(case.get("query", "")).strip()
        desc = str(case.get("desc", "未分类")).strip() or "未分类"
        category = str(case.get("category", "")).strip()
        if not category:
            category = desc.split("·", 1)[0] if "·" in desc else desc

        expected_id = str(case.get("expected_id", "")).strip()
        expected_ids = [str(item).strip() for item in case.get("expected_ids", []) if str(item).strip()]
        expected_prefixes = [str(item).strip() for item in case.get("expected_prefixes", []) if str(item).strip()]

        if expected_id:
            if case.get("expected_id_exact", False):
                expected_ids.insert(0, expected_id)
            elif expected_id.endswith("_"):
                expected_prefixes.insert(0, expected_id)
            else:
                expected_ids.insert(0, expected_id)

        if not query:
            raise ValueError(f"测试用例 #{idx} 缺少 query")
        if not expected_ids and not expected_prefixes:
            raise ValueError(f"测试用例 #{idx} 缺少 expected_id / expected_ids / expected_prefixes")

        normalized_cases.append(
            {
                "query": query,
                "desc": desc,
                "category": category,
                "expected_ids": expected_ids,
                "expected_prefixes": expected_prefixes,
            }
        )

    return normalized_cases, dataset_label


def load_knowledge_stats() -> dict[str, Any]:
    doc_path = ROOT_DIR / "storage" / "doecment.json"
    if not doc_path.exists():
        return {"total_docs": 0, "source_counts": {}}

    with doc_path.open("r", encoding="utf-8") as f:
        docs = json.load(f)

    source_counts = Counter(doc.get("source", "<missing>") for doc in docs)
    return {
        "total_docs": len(docs),
        "source_counts": dict(source_counts),
    }


def load_knowledge_lookup() -> dict[str, dict[str, Any]]:
    doc_path = ROOT_DIR / "storage" / "doecment.json"
    if not doc_path.exists():
        return {}
    with doc_path.open("r", encoding="utf-8") as f:
        docs = json.load(f)
    return {doc["id"]: doc for doc in docs if doc.get("id")}


def expected_label(case: dict[str, Any]) -> str:
    labels = list(case["expected_ids"])
    labels.extend(f"{prefix}*" for prefix in case["expected_prefixes"])
    return ", ".join(labels)


def matches_expected(case: dict[str, Any], result_id: str) -> bool:
    if not result_id:
        return False
    if result_id in case["expected_ids"]:
        return True
    return any(result_id.startswith(prefix) for prefix in case["expected_prefixes"])


def normalize_city_name(city: str) -> str:
    text = (city or "").strip()
    for suffix in ("市", "地区", "自治州", "盟", "州"):
        if text.endswith(suffix):
            return text[: -len(suffix)]
    return text


def normalize_spot_name(spot_name: str) -> str:
    text = (spot_name or "").lower().strip()
    for token in (" ", "·", "•", ",", "，", "、", "/", "(", ")", "（", "）", "-", "+"):
        text = text.replace(token, "")
    for token in (
        "景区",
        "旅游区",
        "风景区",
        "风景名胜区",
        "国家湿地公园",
        "湿地公园",
        "国家森林公园",
        "森林公园",
        "旅游度假区",
        "度假区",
    ):
        text = text.replace(token, "")
    return text


def collect_expected_docs(case: dict[str, Any], knowledge_lookup: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for doc_id in case["expected_ids"]:
        doc = knowledge_lookup.get(doc_id)
        if doc is not None:
            docs.append(doc)
    for prefix in case["expected_prefixes"]:
        docs.extend(doc for doc_id, doc in knowledge_lookup.items() if doc_id.startswith(prefix))
    return docs


def same_entity(expected_doc: dict[str, Any], actual_doc: dict[str, Any]) -> bool:
    expected_name = normalize_spot_name(expected_doc.get("spot_name", ""))
    actual_name = normalize_spot_name(actual_doc.get("spot_name", ""))
    if not expected_name or not actual_name:
        return False

    expected_city = normalize_city_name(expected_doc.get("city", ""))
    actual_city = normalize_city_name(actual_doc.get("city", ""))
    city_match = bool(expected_city and actual_city and (expected_city == actual_city or expected_city in actual_city or actual_city in expected_city))
    name_match = expected_name == actual_name or expected_name in actual_name or actual_name in expected_name
    return city_match and name_match


def summarize_case_top_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "rank": item["rank"],
            "id": item["id"],
            "spot_name": item["spot_name"],
            "city": item["city"],
            "score": round(float(item["score"]), 4),
            "source": item["source"],
        }
        for item in results
    ]


def evaluate_cases(
    cases: list[dict[str, Any]],
    knowledge_lookup: dict[str, dict[str, Any]],
    top_k: int,
    min_score: float,
    quiet: bool,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    for idx, case in enumerate(cases, start=1):
        retrieved = retrieve_knowledge(case["query"], top_k=top_k, min_score=min_score)
        expected_docs = collect_expected_docs(case, knowledge_lookup)
        strict_matched_rank = None
        strict_matched_result = None
        loose_matched_rank = None
        loose_matched_result = None

        for item in retrieved:
            result_id = item.get("id", "")
            if strict_matched_rank is None and matches_expected(case, result_id):
                strict_matched_rank = int(item["rank"])
                strict_matched_result = item
            if loose_matched_rank is None:
                actual_doc = knowledge_lookup.get(result_id)
                if actual_doc is not None and any(same_entity(expected_doc, actual_doc) for expected_doc in expected_docs):
                    loose_matched_rank = int(item["rank"])
                    loose_matched_result = item
            if strict_matched_rank is not None and loose_matched_rank is not None:
                break

        record = {
            "index": idx,
            "query": case["query"],
            "desc": case["desc"],
            "category": case["category"],
            "expected": expected_label(case),
            "expected_ids": list(case["expected_ids"]),
            "expected_prefixes": list(case["expected_prefixes"]),
            "matched_rank": strict_matched_rank,
            "matched": strict_matched_rank is not None,
            "matched_id": strict_matched_result.get("id", "") if strict_matched_result else "",
            "matched_spot_name": strict_matched_result.get("spot_name", "") if strict_matched_result else "",
            "strict_matched_rank": strict_matched_rank,
            "strict_matched": strict_matched_rank is not None,
            "strict_matched_id": strict_matched_result.get("id", "") if strict_matched_result else "",
            "strict_matched_spot_name": strict_matched_result.get("spot_name", "") if strict_matched_result else "",
            "loose_matched_rank": loose_matched_rank,
            "loose_matched": loose_matched_rank is not None,
            "loose_matched_id": loose_matched_result.get("id", "") if loose_matched_result else "",
            "loose_matched_spot_name": loose_matched_result.get("spot_name", "") if loose_matched_result else "",
            "top_results": summarize_case_top_results(retrieved),
        }
        results.append(record)

        if not quiet:
            if strict_matched_rank == 1:
                status = "✅ Hit@1"
            elif strict_matched_rank is not None:
                status = f"🟡 Hit@{strict_matched_rank}"
            else:
                status = "❌ Miss"
            print(f"[{idx}/{len(cases)}] {status} | {case['desc']}")
            print(f"  问题: {case['query']}")
            print(f"  期望: {record['expected']}")
            if record["top_results"]:
                top1 = record["top_results"][0]
                print(f"  Top1: {top1['id']} | {top1['spot_name']} | {top1['score']:.2f}")
            else:
                print("  Top1: <empty>")

    return results


def compute_summary(case_results: list[dict[str, Any]], cutoffs: list[int], rank_key: str) -> dict[str, Any]:
    total = len(case_results)
    summary: dict[str, Any] = {
        "total_cases": total,
        "evaluated_at": datetime.now().isoformat(timespec="seconds"),
        "miss_count": sum(1 for item in case_results if item[rank_key] is None),
    }

    for cutoff in cutoffs:
        hit_count = sum(1 for item in case_results if item[rank_key] is not None and item[rank_key] <= cutoff)
        summary[f"hit_at_{cutoff}"] = hit_count
        summary[f"hit_at_{cutoff}_rate"] = (hit_count / total) if total else 0.0

    reciprocal_rank_sum = sum((1.0 / item[rank_key]) for item in case_results if item[rank_key] is not None)
    summary["mrr"] = reciprocal_rank_sum / total if total else 0.0

    hit_ranks = [item[rank_key] for item in case_results if item[rank_key] is not None]
    summary["mean_hit_rank"] = (sum(hit_ranks) / len(hit_ranks)) if hit_ranks else None
    return summary


def compute_category_rows(case_results: list[dict[str, Any]], cutoffs: list[int], rank_key: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in case_results:
        grouped.setdefault(item["category"], []).append(item)

    rows: list[dict[str, Any]] = []
    for category, items in grouped.items():
        row = {
            "category": category,
            "count": len(items),
            "mrr": sum((1.0 / item[rank_key]) for item in items if item[rank_key] is not None) / len(items),
        }
        for cutoff in cutoffs:
            hit_count = sum(1 for item in items if item[rank_key] is not None and item[rank_key] <= cutoff)
            row[f"hit_at_{cutoff}"] = hit_count
            row[f"hit_at_{cutoff}_rate"] = hit_count / len(items)
        rows.append(row)
    return rows


def build_rank_distribution(case_results: list[dict[str, Any]], top_k: int, rank_key: str) -> dict[str, int]:
    distribution = {str(rank): 0 for rank in range(1, top_k + 1)}
    distribution["Miss"] = 0
    for item in case_results:
        if item[rank_key] is None:
            distribution["Miss"] += 1
        else:
            distribution[str(item[rank_key])] += 1
    return distribution


def ensure_output_dir(report_dir_arg: str | None) -> Path:
    if report_dir_arg:
        output_dir = Path(report_dir_arg).resolve()
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = DEFAULT_REPORT_ROOT / f"rag_eval_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "images").mkdir(exist_ok=True)
    return output_dir


def plot_overall_metrics(strict_summary: dict[str, Any], loose_summary: dict[str, Any], cutoffs: list[int], output_path: Path) -> None:
    labels = [f"Hit@{cutoff}" for cutoff in cutoffs] + ["MRR"]
    strict_values = [strict_summary[f"hit_at_{cutoff}_rate"] * 100 for cutoff in cutoffs] + [strict_summary["mrr"] * 100]
    loose_values = [loose_summary[f"hit_at_{cutoff}_rate"] * 100 for cutoff in cutoffs] + [loose_summary["mrr"] * 100]

    fig, ax = plt.subplots(figsize=(8, 4.8))
    x = np.arange(len(labels))
    width = 0.36
    strict_bars = ax.bar(x - width / 2, strict_values, width=width, label="Strict", color="#2d6a4f")
    loose_bars = ax.bar(x + width / 2, loose_values, width=width, label="Loose", color="#e9c46a")
    ax.set_title("RAG 检索总体指标（严格 vs 宽松）")
    ax.set_ylabel("百分比 / MRR x 100")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylim(0, max(100, max(strict_values + loose_values) + 10))
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    ax.legend()

    for bar, value in list(zip(strict_bars, strict_values)) + list(zip(loose_bars, loose_values)):
        ax.text(bar.get_x() + bar.get_width() / 2, value + 1, f"{value:.1f}", ha="center", va="bottom", fontsize=10)

    fig.tight_layout()
    fig.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def plot_category_metrics(category_rows: list[dict[str, Any]], cutoffs: list[int], output_path: Path) -> None:
    if not category_rows:
        return

    labels = [row["category"] for row in category_rows]
    x = np.arange(len(labels))
    width = 0.22 if len(cutoffs) >= 3 else 0.28
    colors = ["#1d3557", "#457b9d", "#a8dadc", "#e9c46a"]

    fig, ax = plt.subplots(figsize=(9, 5.2))
    center_offset = (len(cutoffs) - 1) / 2
    for idx, cutoff in enumerate(cutoffs):
        values = [row[f"hit_at_{cutoff}_rate"] * 100 for row in category_rows]
        positions = x + (idx - center_offset) * width
        ax.bar(positions, values, width=width, label=f"Hit@{cutoff}", color=colors[idx % len(colors)])

    ax.set_title("分类命中率对比")
    ax.set_ylabel("命中率 (%)")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylim(0, 100)
    ax.legend()
    ax.grid(axis="y", linestyle="--", alpha=0.35)

    fig.tight_layout()
    fig.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def plot_rank_distribution(rank_distribution: dict[str, int], output_path: Path) -> None:
    labels = list(rank_distribution.keys())
    values = list(rank_distribution.values())
    colors = ["#2a9d8f" if label != "Miss" else "#e76f51" for label in labels]

    fig, ax = plt.subplots(figsize=(8, 4.6))
    bars = ax.bar(labels, values, color=colors)
    ax.set_title("命中排名分布")
    ax.set_xlabel("首次命中排名")
    ax.set_ylabel("Case 数")
    ax.grid(axis="y", linestyle="--", alpha=0.35)

    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, value + 0.15, str(value), ha="center", va="bottom", fontsize=10)

    fig.tight_layout()
    fig.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def plot_knowledge_sources(knowledge_stats: dict[str, Any], output_path: Path) -> None:
    source_counts = knowledge_stats.get("source_counts", {})
    if not source_counts:
        return

    labels = list(source_counts.keys())
    values = list(source_counts.values())

    fig, ax = plt.subplots(figsize=(8, 4.8))
    bars = ax.barh(labels, values, color=["#264653", "#2a9d8f", "#e9c46a", "#e76f51"][: len(labels)])
    ax.set_title("知识库来源分布")
    ax.set_xlabel("文档条数")
    ax.grid(axis="x", linestyle="--", alpha=0.35)

    for bar, value in zip(bars, values):
        ax.text(value + max(values) * 0.01, bar.get_y() + bar.get_height() / 2, str(value), va="center", fontsize=10)

    fig.tight_layout()
    fig.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def format_percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def render_summary_table(summary: dict[str, Any], cutoffs: list[int]) -> str:
    lines = ["| 指标 | 数值 |", "|---|---:|"]
    for cutoff in cutoffs:
        lines.append(f"| Hit@{cutoff} | {summary[f'hit_at_{cutoff}']}/{summary['total_cases']} ({format_percent(summary[f'hit_at_{cutoff}_rate'])}) |")
    lines.append(f"| MRR | {summary['mrr']:.4f} |")
    mean_hit_rank = "-" if summary["mean_hit_rank"] is None else f"{summary['mean_hit_rank']:.2f}"
    lines.append(f"| 平均命中排名 | {mean_hit_rank} |")
    lines.append(f"| Miss 数量 | {summary['miss_count']} |")
    return "\n".join(lines)


def render_category_table(category_rows: list[dict[str, Any]], cutoffs: list[int]) -> str:
    headers = ["分类", "Case 数"] + [f"Hit@{cutoff}" for cutoff in cutoffs] + ["MRR"]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in category_rows:
        values = [row["category"], str(row["count"])]
        values.extend(f"{row[f'hit_at_{cutoff}']}/{row['count']} ({format_percent(row[f'hit_at_{cutoff}_rate'])})" for cutoff in cutoffs)
        values.append(f"{row['mrr']:.4f}")
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def render_failure_table(case_results: list[dict[str, Any]], rank_key: str, limit: int = 10) -> str:
    misses = [item for item in case_results if item[rank_key] is None][:limit]
    if not misses:
        return "无未命中样例。"

    lines = [
        "| Query | 期望 | Top1 返回ID | Top1 返回景点 |",
        "|---|---|---|---|",
    ]
    for item in misses:
        top1 = item["top_results"][0] if item["top_results"] else {}
        lines.append(
            "| {query} | {expected} | {top1_id} | {top1_name} |".format(
                query=item["query"],
                expected=item["expected"],
                top1_id=top1.get("id", "<empty>"),
                top1_name=top1.get("spot_name", "<empty>"),
            )
        )
    return "\n".join(lines)


def write_report_markdown(
    output_dir: Path,
    strict_summary: dict[str, Any],
    loose_summary: dict[str, Any],
    strict_category_rows: list[dict[str, Any]],
    loose_category_rows: list[dict[str, Any]],
    case_results: list[dict[str, Any]],
    knowledge_stats: dict[str, Any],
    dataset_label: str,
    top_k: int,
    min_score: float,
    cutoffs: list[int],
) -> Path:
    source_lines = ["| 来源 | 数量 |", "|---|---:|"]
    for source, count in knowledge_stats.get("source_counts", {}).items():
        source_lines.append(f"| {source} | {count} |")

    report = f"""# RAG 检索评测报告

- 生成时间：{strict_summary['evaluated_at']}
- 测试集：`{dataset_label}`
- 检索返回 Top-K：`{top_k}`
- 最小分数阈值：`{min_score}`
- 知识库总条目：`{knowledge_stats.get('total_docs', 0)}`

## 严格 Doc-ID 指标

{render_summary_table(strict_summary, cutoffs)}

## 宽松实体级指标

说明：若命中的是“同城市 + 同景点实体”的跨来源条目，也视为命中。

{render_summary_table(loose_summary, cutoffs)}

![总体指标](images/01_overall_metrics.png)

## 分类表现（严格）

{render_category_table(strict_category_rows, cutoffs)}

## 分类表现（宽松）

{render_category_table(loose_category_rows, cutoffs)}

![分类命中率](images/02_category_metrics.png)

## 命中排名分布

![命中排名分布](images/03_rank_distribution.png)

## 知识库来源分布

{chr(10).join(source_lines)}

![知识库来源分布](images/04_knowledge_sources.png)

## 典型未命中样例

### 严格未命中

{render_failure_table(case_results, rank_key="strict_matched_rank")}

### 宽松未命中

{render_failure_table(case_results, rank_key="loose_matched_rank")}
"""

    report_path = output_dir / "report.md"
    report_path.write_text(report, encoding="utf-8")
    return report_path


def write_results_json(
    output_dir: Path,
    strict_summary: dict[str, Any],
    loose_summary: dict[str, Any],
    strict_category_rows: list[dict[str, Any]],
    loose_category_rows: list[dict[str, Any]],
    case_results: list[dict[str, Any]],
    knowledge_stats: dict[str, Any],
    dataset_label: str,
    top_k: int,
    min_score: float,
) -> Path:
    payload = {
        "config": {
            "dataset": dataset_label,
            "top_k": top_k,
            "min_score": min_score,
        },
        "summary": {
            "strict": strict_summary,
            "loose": loose_summary,
        },
        "knowledge_base": knowledge_stats,
        "categories": {
            "strict": strict_category_rows,
            "loose": loose_category_rows,
        },
        "cases": case_results,
    }
    output_path = output_dir / "results.json"
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def print_summary(title: str, summary: dict[str, Any], cutoffs: list[int], category_rows: list[dict[str, Any]]) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)
    print(f"  总测试数: {summary['total_cases']}")
    for cutoff in cutoffs:
        print(f"  Hit@{cutoff}: {summary[f'hit_at_{cutoff}']}/{summary['total_cases']} = {format_percent(summary[f'hit_at_{cutoff}_rate'])}")
    print(f"  MRR: {summary['mrr']:.4f}")
    if summary["mean_hit_rank"] is not None:
        print(f"  平均命中排名: {summary['mean_hit_rank']:.2f}")
    print(f"  Miss: {summary['miss_count']}")

    print("\n📋 分类表现:")
    for row in category_rows:
        parts = [f"{row['category']} {row['count']}条"]
        parts.extend(f"Hit@{cutoff}={format_percent(row[f'hit_at_{cutoff}_rate'])}" for cutoff in cutoffs)
        parts.append(f"MRR={row['mrr']:.4f}")
        print("  - " + " | ".join(parts))


def main() -> int:
    args = parse_args()
    top_k = max(int(args.top_k), 1)
    cutoffs = sorted({cutoff for cutoff in DEFAULT_CUTOFFS if cutoff <= top_k} | {top_k})

    cases, dataset_label = load_test_cases(args.dataset)
    knowledge_stats = load_knowledge_stats()
    knowledge_lookup = load_knowledge_lookup()
    output_dir = ensure_output_dir(args.report_dir)

    print("=" * 60)
    print("🧪 RAG 检索评测")
    print(f"   测试用例数: {len(cases)}")
    print(f"   数据集来源: {dataset_label}")
    print(f"   输出目录: {output_dir}")
    print("=" * 60)

    case_results = evaluate_cases(cases, knowledge_lookup=knowledge_lookup, top_k=top_k, min_score=args.min_score, quiet=args.quiet)
    strict_summary = compute_summary(case_results, cutoffs, rank_key="strict_matched_rank")
    loose_summary = compute_summary(case_results, cutoffs, rank_key="loose_matched_rank")
    strict_category_rows = compute_category_rows(case_results, cutoffs, rank_key="strict_matched_rank")
    loose_category_rows = compute_category_rows(case_results, cutoffs, rank_key="loose_matched_rank")
    rank_distribution = build_rank_distribution(case_results, top_k=top_k, rank_key="strict_matched_rank")

    images_dir = output_dir / "images"
    plot_overall_metrics(strict_summary, loose_summary, cutoffs, images_dir / "01_overall_metrics.png")
    plot_category_metrics(strict_category_rows, cutoffs, images_dir / "02_category_metrics.png")
    plot_rank_distribution(rank_distribution, images_dir / "03_rank_distribution.png")
    plot_knowledge_sources(knowledge_stats, images_dir / "04_knowledge_sources.png")

    report_path = write_report_markdown(
        output_dir=output_dir,
        strict_summary=strict_summary,
        loose_summary=loose_summary,
        strict_category_rows=strict_category_rows,
        loose_category_rows=loose_category_rows,
        case_results=case_results,
        knowledge_stats=knowledge_stats,
        dataset_label=dataset_label,
        top_k=top_k,
        min_score=args.min_score,
        cutoffs=cutoffs,
    )
    results_path = write_results_json(
        output_dir=output_dir,
        strict_summary=strict_summary,
        loose_summary=loose_summary,
        strict_category_rows=strict_category_rows,
        loose_category_rows=loose_category_rows,
        case_results=case_results,
        knowledge_stats=knowledge_stats,
        dataset_label=dataset_label,
        top_k=top_k,
        min_score=args.min_score,
    )

    print_summary("📊 严格评估结果", strict_summary, cutoffs, strict_category_rows)
    print_summary("📊 宽松评估结果", loose_summary, cutoffs, loose_category_rows)
    print(f"\n📝 报告已生成: {report_path}")
    print(f"📦 结果已保存: {results_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
