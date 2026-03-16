from __future__ import annotations

import json
from argparse import ArgumentParser, Namespace
from pathlib import Path


METRICS = [
    ("tool_call_emission_rate", "Tool-call emission"),
    ("tool_name_accuracy", "Tool-name accuracy"),
    ("argument_exact_match_rate", "Argument exact match"),
    ("turn_exact_match_rate", "Turn exact match"),
    ("decision_tool_name_accuracy", "Decision tool-name accuracy"),
    ("decision_turn_exact_match_rate", "Decision turn exact match"),
    ("sample_full_chain_success_rate", "Sample full-chain success"),
]


def parse_args() -> Namespace:
    parser = ArgumentParser(description="Compare two tool-calling evaluation reports.")
    parser.add_argument("--base", required=True, help="Path to base results.json")
    parser.add_argument("--tuned", required=True, help="Path to tuned/LoRA results.json")
    parser.add_argument("--base-label", default="Base", help="Display label for base model")
    parser.add_argument("--tuned-label", default="LoRA", help="Display label for tuned model")
    parser.add_argument("--output", default="", help="Optional output markdown path")
    return parser.parse_args()


def load_summary(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload["summary"]


def format_percent(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.2f}%"


def format_delta_pp(delta: float | None) -> str:
    if delta is None:
        return "N/A"
    return f"{delta * 100:+.2f} pp"


def format_relative(base: float | None, tuned: float | None) -> str:
    if base is None or tuned is None:
        return "N/A"
    if abs(base) < 1e-12:
        return "N/A"
    return f"{((tuned - base) / base) * 100:+.2f}%"


def build_markdown(
    base_summary: dict,
    tuned_summary: dict,
    base_label: str,
    tuned_label: str,
    base_path: Path,
    tuned_path: Path,
) -> str:
    lines = [
        "# Tool Calling Comparison Report",
        "",
        f"- Base report: `{base_path}`",
        f"- Tuned report: `{tuned_path}`",
        "",
        "| Metric | "
        + base_label
        + " | "
        + tuned_label
        + " | Absolute Delta | Relative Improvement |",
        "|---|---:|---:|---:|---:|",
    ]

    for metric_key, metric_label in METRICS:
        base_value = base_summary.get(metric_key)
        tuned_value = tuned_summary.get(metric_key)
        delta = None if base_value is None or tuned_value is None else tuned_value - base_value
        lines.append(
            "| "
            + metric_label
            + " | "
            + format_percent(base_value)
            + " | "
            + format_percent(tuned_value)
            + " | "
            + format_delta_pp(delta)
            + " | "
            + format_relative(base_value, tuned_value)
            + " |"
        )

    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    base_path = Path(args.base).resolve()
    tuned_path = Path(args.tuned).resolve()

    base_summary = load_summary(base_path)
    tuned_summary = load_summary(tuned_path)

    report = build_markdown(
        base_summary=base_summary,
        tuned_summary=tuned_summary,
        base_label=args.base_label,
        tuned_label=args.tuned_label,
        base_path=base_path,
        tuned_path=tuned_path,
    )
    print(report)

    if args.output:
        output_path = Path(args.output).resolve()
        output_path.write_text(report, encoding="utf-8")
        print(f"Saved report to: {output_path}")


if __name__ == "__main__":
    main()
