"""
Evaluate spot answer quality with the same provided context.

This script uses local LLaMA-Factory ChatModel inference so base vs LoRA can be
compared under identical retrieval context, which matches the real spot-agent
workflow better than asking the naked model to recall facts from memory.
"""
from __future__ import annotations

import json
import re
from argparse import ArgumentParser, Namespace
from datetime import datetime
from pathlib import Path
from typing import Any


TOOLS_DIR = Path(__file__).resolve().parent
ROOT_DIR = TOOLS_DIR.parent
DEFAULT_DATASET = TOOLS_DIR / "spot_eval_cases.json"
DEFAULT_REPORT_ROOT = ROOT_DIR / "reports"


def parse_args() -> Namespace:
    parser = ArgumentParser(description="Evaluate spot QA answers.")
    parser.add_argument("--dataset", type=str, default=str(DEFAULT_DATASET), help="spot_eval_cases.json path")
    parser.add_argument("--model", type=str, required=True, help="Base model path")
    parser.add_argument("--adapter-path", type=str, default=None, help="Optional LoRA adapter path")
    parser.add_argument("--template", type=str, default="qwen3_5_nothink", help="LLaMA-Factory template")
    parser.add_argument("--infer-backend", type=str, default="huggingface", help="LLaMA-Factory infer_backend")
    parser.add_argument("--temperature", type=float, default=0.0, help="Sampling temperature")
    parser.add_argument("--max-tokens", type=int, default=384, help="Max generation tokens")
    parser.add_argument("--max-samples", type=int, default=0, help="Limit the number of cases. 0 means all.")
    parser.add_argument("--report-dir", type=str, default=None, help="Output directory")
    parser.add_argument("--quiet", action="store_true", help="Only print summary")
    return parser.parse_args()


def ensure_report_dir(report_dir_arg: str | None) -> Path:
    if report_dir_arg:
        path = Path(report_dir_arg).resolve()
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = DEFAULT_REPORT_ROOT / f"spot_eval_{stamp}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_dataset(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def init_chat_model(
    model: str,
    adapter_path: str | None,
    template: str,
    infer_backend: str,
    temperature: float,
    max_tokens: int,
) -> Any:
    from llamafactory.chat import ChatModel

    model_args: dict[str, Any] = {
        "model_name_or_path": model,
        "template": template,
        "infer_backend": infer_backend,
        "trust_remote_code": True,
        "temperature": temperature,
        "max_new_tokens": max_tokens,
        "do_sample": temperature > 0,
    }
    if adapter_path:
        model_args["adapter_name_or_path"] = adapter_path
        model_args["finetuning_type"] = "lora"
    return ChatModel(model_args)


def build_system_prompt() -> str:
    return (
        "你是专业的旅游景点助手。请严格基于给定参考资料回答，不要编造资料中没有的信息。"
        "回答用自然中文，尽量控制在2到5句，并优先给出用户真正关心的景点信息。"
    )


def build_user_prompt(case: dict[str, Any]) -> str:
    context = case["context"]
    tags = "、".join(context.get("tags", [])) or "无"
    return (
        "参考资料：\n"
        f"- 景点：{context.get('spot_name', '')}\n"
        f"- 城市：{context.get('city', '')}\n"
        f"- 区县：{context.get('district', '')}\n"
        f"- 建议时长：{context.get('duration', '')}\n"
        f"- 预算：{context.get('budget', '')}\n"
        f"- 标签：{tags}\n"
        f"- 摘要：{context.get('content_summary', '')}\n\n"
        f"用户问题：{case['query']}\n\n"
        "请只根据以上资料回答，不要提到“根据资料”这类措辞。"
    )


def normalize_text(text: str) -> str:
    text = text or ""
    text = text.lower()
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[，。！？；：、“”‘’（）()【】\[\],.!?;:\"'`·]", "", text)
    return text


def contains_any(answer: str, candidates: list[str]) -> bool:
    norm_answer = normalize_text(answer)
    for candidate in candidates:
        if candidate and normalize_text(candidate) in norm_answer:
            return True
    return False


def lcs_length(a: str, b: str) -> int:
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    for char_a in a:
        curr = [0]
        for idx, char_b in enumerate(b, start=1):
            if char_a == char_b:
                curr.append(prev[idx - 1] + 1)
            else:
                curr.append(max(prev[idx], curr[-1]))
        prev = curr
    return prev[-1]


def rouge_l_f1(prediction: str, reference: str) -> float:
    pred = normalize_text(prediction)
    ref = normalize_text(reference)
    if not pred or not ref:
        return 0.0
    lcs = lcs_length(pred, ref)
    precision = lcs / len(pred)
    recall = lcs / len(ref)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def score_answer(case: dict[str, Any], answer: str) -> dict[str, Any]:
    expected_facts = case["expected_facts"]
    required_keys = case["required_keys"]

    hits: dict[str, bool] = {}
    for key in required_keys:
        hits[key] = contains_any(answer, expected_facts.get(key, []))

    fact_hits = sum(1 for value in hits.values() if value)
    fact_coverage = fact_hits / len(required_keys) if required_keys else 0.0

    return {
        "required_keys": required_keys,
        "fact_hits": hits,
        "fact_coverage": fact_coverage,
        "strict_success": fact_hits == len(required_keys) if required_keys else False,
        "rouge_l_f1": rouge_l_f1(answer, case["reference_answer"]),
    }


def evaluate_cases(chat_model: Any, cases: list[dict[str, Any]], quiet: bool) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    system = build_system_prompt()

    for idx, case in enumerate(cases, start=1):
        error = None
        answer = ""

        try:
            response = chat_model.chat([{"role": "user", "content": build_user_prompt(case)}], system=system)
            answer = getattr(response[0], "response_text", "").strip()
        except Exception as exc:  # pragma: no cover
            error = str(exc)

        scoring = (
            score_answer(case, answer)
            if error is None
            else {
                "required_keys": case["required_keys"],
                "fact_hits": {key: False for key in case["required_keys"]},
                "fact_coverage": 0.0,
                "strict_success": False,
                "rouge_l_f1": 0.0,
            }
        )

        record = {
            "index": idx,
            "case_id": case["case_id"],
            "query": case["query"],
            "category": case["category"],
            "expected_id": case["expected_id"],
            "reference_answer": case["reference_answer"],
            "answer": answer,
            "scoring": scoring,
            "error": error,
        }
        results.append(record)

        if not quiet:
            status = "OK" if scoring["strict_success"] else "MISS"
            print(f"[{idx}/{len(cases)}] {status} | {case['case_id']} | {case['query']}")
            if error:
                print(f"  error: {error}")
            elif not scoring["strict_success"]:
                print(f"  fact coverage: {scoring['fact_coverage']:.2%}")

    return results


def safe_rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    strict_successes = sum(1 for item in results if item["scoring"]["strict_success"])
    avg_fact_coverage = sum(item["scoring"]["fact_coverage"] for item in results) / total if total else 0.0
    avg_rouge_l = sum(item["scoring"]["rouge_l_f1"] for item in results) / total if total else 0.0
    error_count = sum(1 for item in results if item["error"])

    key_counts: dict[str, list[bool]] = {}
    for item in results:
        for key, value in item["scoring"]["fact_hits"].items():
            key_counts.setdefault(key, []).append(value)

    per_key = [
        {"key": key, "hit_rate": safe_rate(sum(values), len(values)), "count": len(values)}
        for key, values in sorted(key_counts.items())
    ]

    categories = sorted({item["category"] for item in results})
    per_category = []
    for category in categories:
        subset = [item for item in results if item["category"] == category]
        per_category.append(
            {
                "category": category,
                "count": len(subset),
                "strict_success_rate": safe_rate(
                    sum(1 for item in subset if item["scoring"]["strict_success"]),
                    len(subset),
                ),
                "avg_fact_coverage": sum(item["scoring"]["fact_coverage"] for item in subset) / len(subset),
                "avg_rouge_l_f1": sum(item["scoring"]["rouge_l_f1"] for item in subset) / len(subset),
            }
        )

    return {
        "total_cases": total,
        "strict_success_rate": safe_rate(strict_successes, total),
        "avg_fact_coverage": avg_fact_coverage,
        "avg_rouge_l_f1": avg_rouge_l,
        "error_rate": safe_rate(error_count, total),
        "per_key": per_key,
        "per_category": per_category,
    }


def make_report_markdown(dataset_path: Path, model: str, adapter_path: str | None, summary: dict[str, Any]) -> str:
    lines = [
        "# Spot Evaluation Report",
        "",
        f"- Generated at: {datetime.now().isoformat(timespec='seconds')}",
        f"- Dataset: `{dataset_path}`",
        f"- Model: `{model}`",
        f"- Adapter: `{adapter_path or 'None'}`",
        "",
        "## Overall Metrics",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Total cases | {summary['total_cases']} |",
        f"| Strict success rate | {summary['strict_success_rate']:.2%} |",
        f"| Average fact coverage | {summary['avg_fact_coverage']:.2%} |",
        f"| Average ROUGE-L F1 | {summary['avg_rouge_l_f1']:.4f} |",
        f"| Error rate | {summary['error_rate']:.2%} |",
        "",
        "## Per Fact Key",
        "",
        "| Key | Count | Hit Rate |",
        "|---|---:|---:|",
    ]

    for row in summary["per_key"]:
        lines.append(f"| {row['key']} | {row['count']} | {row['hit_rate']:.2%} |")

    lines.extend(
        [
            "",
            "## Per Category",
            "",
            "| Category | Count | Strict Success | Fact Coverage | ROUGE-L F1 |",
            "|---|---:|---:|---:|---:|",
        ]
    )

    for row in summary["per_category"]:
        lines.append(
            f"| {row['category']} | {row['count']} | {row['strict_success_rate']:.2%} | "
            f"{row['avg_fact_coverage']:.2%} | {row['avg_rouge_l_f1']:.4f} |"
        )

    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    dataset_path = Path(args.dataset).resolve()
    report_dir = ensure_report_dir(args.report_dir)
    cases = load_dataset(dataset_path)
    if args.max_samples > 0:
        cases = cases[: args.max_samples]

    chat_model = init_chat_model(
        model=args.model,
        adapter_path=args.adapter_path,
        template=args.template,
        infer_backend=args.infer_backend,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
    )
    results = evaluate_cases(chat_model, cases, args.quiet)
    summary = summarize_results(results)

    payload = {
        "meta": {
            "dataset": str(dataset_path),
            "backend": "llamafactory",
            "model": args.model,
            "adapter_path": args.adapter_path,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "case_count": len(cases),
        },
        "summary": summary,
        "results": results,
    }

    (report_dir / "results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (report_dir / "report.md").write_text(
        make_report_markdown(dataset_path, args.model, args.adapter_path, summary),
        encoding="utf-8",
    )
    print(f"Results saved to: {report_dir}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
