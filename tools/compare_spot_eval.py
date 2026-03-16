"""Compare two spot evaluation result files."""
from __future__ import annotations

import json
from argparse import ArgumentParser, Namespace
from pathlib import Path


METRICS = [
    ("strict_success_rate", "Strict success"),
    ("avg_fact_coverage", "Average fact coverage"),
    ("avg_rouge_l_f1", "Average ROUGE-L F1"),
    ("error_rate", "Error rate"),
]


def parse_args() -> Namespace:
    parser = ArgumentParser(description="Compare spot evaluation results.")
    parser.add_argument("--base", required=True, help="Base results.json path")
    parser.add_argument("--tuned", required=True, help="Tuned results.json path")
    parser.add_argument("--base-label", default="Base", help="Base display label")
    parser.add_argument("--tuned-label", default="Tuned", help="Tuned display label")
    parser.add_argument("--output", default=None, help="Optional markdown output path")
    return parser.parse_args()


def load_results(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def format_pct(value: float) -> str:
    return f"{value:.2%}"


def main() -> None:
    args = parse_args()
    base_path = Path(args.base).resolve()
    tuned_path = Path(args.tuned).resolve()
    base = load_results(base_path)
    tuned = load_results(tuned_path)

    lines = [
        "# Spot Evaluation Comparison",
        "",
        f"- Base report: `{base_path}`",
        f"- Tuned report: `{tuned_path}`",
        "",
        f"| Metric | {args.base_label} | {args.tuned_label} | Absolute Delta | Relative Improvement |",
        "|---|---:|---:|---:|---:|",
    ]

    for key, label in METRICS:
        base_val = base["summary"][key]
        tuned_val = tuned["summary"][key]
        delta = tuned_val - base_val
        if key == "error_rate":
            rel = 0.0 if base_val == 0 else -delta / base_val
        else:
            rel = 0.0 if base_val == 0 else delta / base_val
        lines.append(
            f"| {label} | {format_pct(base_val)} | {format_pct(tuned_val)} | "
            f"{delta:+.2%} | {rel:+.2%} |"
        )

    content = "\n".join(lines) + "\n"
    print(content)
    if args.output:
        output_path = Path(args.output).resolve()
        output_path.write_text(content, encoding="utf-8")
        print(f"Saved report to: {output_path}")


if __name__ == "__main__":
    main()
