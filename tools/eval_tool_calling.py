"""
Evaluate tool-calling behavior through an OpenAI-compatible chat endpoint.

The script replays ShareGPT-style samples turn by turn. Each expected assistant
tool call becomes one evaluation item, so you can compare a base model and a
LoRA-tuned model on:

1. tool selection accuracy
2. argument exact match rate
3. turn-level exact match rate
4. sample-level full-chain success rate

It also reports "decision turns" separately to avoid `get_context` dominating
the score.
"""
from __future__ import annotations

import copy
import json
import random
from argparse import ArgumentParser, Namespace
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import requests


TOOLS_DIR = Path(__file__).resolve().parent
ROOT_DIR = TOOLS_DIR.parent
DEFAULT_DATASET = TOOLS_DIR / "tool_call_eval_cases.json"
DEFAULT_REPORT_ROOT = ROOT_DIR / "reports"
NON_DECISION_TOOLS = {"get_context", "reply_channel_message", "send_channel_message"}

# Tools whose text payload should not be exact-matched because wording can vary.
COMPARE_KEYS: dict[str, list[str] | None] = {
    "get_context": [],
    "get_weather": ["city"],
    "search_spots": ["query"],
    "search_local_knowledge": ["query"],
    "search_combined": ["query"],
    "get_driving_route": ["origin", "destination"],
    "send_direct_message": ["target_agent_id"],
    "send_channel_message": [],
    "reply_channel_message": [],
    # None means: compare every expected key-value pair.
    "save_context": None,
}


def parse_args() -> Namespace:
    parser = ArgumentParser(description="Evaluate tool-calling accuracy.")
    parser.add_argument(
        "--backend",
        type=str,
        choices=["api", "llamafactory"],
        default="api",
        help="Use an OpenAI-compatible API or local LLaMA-Factory ChatModel inference.",
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default=str(DEFAULT_DATASET),
        help="ShareGPT-style dataset path with gpt.tool_calls turns.",
    )
    parser.add_argument(
        "--endpoint",
        type=str,
        default="http://localhost:1234/v1/chat/completions",
        help="OpenAI-compatible chat completions endpoint.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="local-qwen",
        help="Model name sent to the API, or local model path for llamafactory backend.",
    )
    parser.add_argument(
        "--adapter-path",
        type=str,
        default=None,
        help="Optional LoRA adapter path for --backend llamafactory.",
    )
    parser.add_argument(
        "--template",
        type=str,
        default="qwen3_5_nothink",
        help="Chat template used by --backend llamafactory.",
    )
    parser.add_argument(
        "--infer-backend",
        type=str,
        default="huggingface",
        help="LLaMA-Factory infer_backend for --backend llamafactory.",
    )
    parser.add_argument("--timeout", type=int, default=120, help="HTTP timeout in seconds.")
    parser.add_argument("--temperature", type=float, default=0.0, help="Sampling temperature.")
    parser.add_argument("--max-tokens", type=int, default=512, help="Generation max_tokens.")
    parser.add_argument(
        "--max-samples",
        type=int,
        default=0,
        help="Limit the number of samples loaded from the dataset. 0 means all.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=20260313,
        help="Random seed used when --max-samples > 0.",
    )
    parser.add_argument(
        "--report-dir",
        type=str,
        default=None,
        help="Output directory. Defaults to reports/tool_call_eval_<timestamp>.",
    )
    parser.add_argument("--quiet", action="store_true", help="Only print summary.")
    return parser.parse_args()


def load_dataset(path: Path, max_samples: int, seed: int) -> list[dict[str, Any]]:
    samples = json.loads(path.read_text(encoding="utf-8"))
    if max_samples and max_samples < len(samples):
        rng = random.Random(seed)
        indices = sorted(rng.sample(range(len(samples)), max_samples))
        samples = [samples[idx] for idx in indices]
    return samples


def parse_tools(raw_tools: Any) -> list[dict[str, Any]]:
    if isinstance(raw_tools, str):
        parsed = json.loads(raw_tools)
    elif isinstance(raw_tools, list):
        parsed = raw_tools
    else:
        raise ValueError(f"Unsupported tools payload: {type(raw_tools)!r}")

    openai_tools = []
    for tool in parsed:
        openai_tools.append(
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters", {"type": "object", "properties": {}}),
                },
            }
        )
    return openai_tools


def normalize_scalar(value: Any) -> Any:
    if isinstance(value, str):
        return " ".join(value.strip().split())
    if isinstance(value, list):
        return [normalize_scalar(item) for item in value]
    if isinstance(value, dict):
        return {str(key): normalize_scalar(val) for key, val in sorted(value.items())}
    return value


def normalize_args(args: dict[str, Any]) -> dict[str, Any]:
    return {str(key): normalize_scalar(val) for key, val in sorted(args.items())}


def get_compare_keys(tool_name: str, expected_args: dict[str, Any]) -> list[str]:
    rule = COMPARE_KEYS.get(tool_name)
    if rule is None:
        return sorted(expected_args.keys())
    return list(rule)


def filter_args(
    tool_name: str,
    expected_args: dict[str, Any],
    predicted_args: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    keys = get_compare_keys(tool_name, expected_args)
    if not keys:
        return {}, {}
    expected_filtered = {key: expected_args[key] for key in keys if key in expected_args}
    predicted_filtered = {key: predicted_args[key] for key in keys if key in predicted_args}
    return normalize_args(expected_filtered), normalize_args(predicted_filtered)


def parse_tool_arguments(raw_arguments: Any) -> dict[str, Any]:
    if raw_arguments is None:
        return {}
    if isinstance(raw_arguments, dict):
        return raw_arguments
    if isinstance(raw_arguments, str):
        text = raw_arguments.strip()
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"__raw__": text}
    return {"__raw__": raw_arguments}


def normalize_tool_call(raw_tool_call: dict[str, Any]) -> dict[str, Any]:
    if "function" in raw_tool_call:
        function = raw_tool_call["function"]
        return {
            "id": raw_tool_call.get("id", ""),
            "name": function.get("name", ""),
            "arguments": parse_tool_arguments(function.get("arguments")),
        }
    return {
        "id": raw_tool_call.get("id", ""),
        "name": raw_tool_call.get("name", ""),
        "arguments": parse_tool_arguments(raw_tool_call.get("arguments")),
    }


def infer_role(system_prompt: str) -> str:
    text = system_prompt or ""
    if "总控网关" in text or "接收用户消息后" in text or "收到用户消息后" in text:
        return "router"
    if "天气助手" in text:
        return "weather"
    if "景点助手" in text:
        return "spot"
    if "行程助手" in text:
        return "plan"
    return "unknown"


def build_assistant_message(
    expected_tool_calls: list[dict[str, Any]],
    content: str,
    turn_ids: list[str],
) -> dict[str, Any]:
    openai_tool_calls = []
    for idx, call in enumerate(expected_tool_calls):
        call_id = turn_ids[idx]
        openai_tool_calls.append(
            {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": call["name"],
                    "arguments": json.dumps(call["arguments"], ensure_ascii=False),
                },
            }
        )
    return {"role": "assistant", "content": content or "", "tool_calls": openai_tool_calls}


def build_turns(samples: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[int, list[int]]]:
    turns: list[dict[str, Any]] = []
    sample_to_turn_indices: dict[int, list[int]] = defaultdict(list)

    for sample_idx, sample in enumerate(samples):
        tools = parse_tools(sample.get("tools", []))
        system_prompt = sample.get("system", "")
        role = infer_role(system_prompt)
        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        pending_tool_ids: list[str] = []

        conversations = sample.get("conversations", [])
        for msg in conversations:
            sender = msg.get("from")
            if sender == "human":
                messages.append({"role": "user", "content": msg.get("value", "")})
                continue

            if sender == "gpt" and msg.get("tool_calls"):
                expected_tool_calls = [normalize_tool_call(item) for item in msg["tool_calls"]]
                turn_idx = len(turns)
                turn_number = len(sample_to_turn_indices[sample_idx]) + 1
                turns.append(
                    {
                        "sample_index": sample_idx,
                        "turn_index": turn_number,
                        "role": role,
                        "messages": copy.deepcopy(messages),
                        "tools": tools,
                        "expected_tool_calls": expected_tool_calls,
                        "expected_content": msg.get("value", ""),
                    }
                )
                sample_to_turn_indices[sample_idx].append(turn_idx)

                pending_tool_ids = [
                    f"sample{sample_idx}_turn{turn_number}_call{call_idx}"
                    for call_idx in range(len(expected_tool_calls))
                ]
                messages.append(
                    build_assistant_message(expected_tool_calls, msg.get("value", ""), pending_tool_ids)
                )
                continue

            if sender == "observation":
                tool_call_id = pending_tool_ids[0] if pending_tool_ids else "observation"
                messages.append({"role": "tool", "tool_call_id": tool_call_id, "content": msg.get("value", "")})
                pending_tool_ids = []
                continue

            if sender == "gpt":
                messages.append({"role": "assistant", "content": msg.get("value", "")})

    return turns, sample_to_turn_indices


def call_model(
    endpoint: str,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    temperature: float,
    max_tokens: int,
    timeout: int,
) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    response = requests.post(endpoint, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()


def convert_messages_for_llamafactory(
    messages: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str | None]:
    system = None
    internal_messages: list[dict[str, Any]] = []

    for message in messages:
        role = message.get("role")
        if role == "system":
            system = message.get("content", "")
            continue
        if role == "user":
            internal_messages.append({"role": "user", "content": message.get("content", "")})
            continue
        if role == "assistant":
            tool_calls = message.get("tool_calls") or []
            if tool_calls:
                for tool_call in tool_calls:
                    function = tool_call.get("function", {})
                    internal_messages.append(
                        {
                            "role": "function",
                            "content": json.dumps(
                                {
                                    "name": function.get("name", ""),
                                    "arguments": parse_tool_arguments(function.get("arguments")),
                                },
                                ensure_ascii=False,
                            ),
                        }
                    )
            else:
                internal_messages.append({"role": "assistant", "content": message.get("content", "") or ""})
            continue
        if role == "tool":
            internal_messages.append({"role": "observation", "content": message.get("content", "")})

    return internal_messages, system


def convert_tools_for_llamafactory(tools: list[dict[str, Any]]) -> str:
    return json.dumps([tool["function"] for tool in tools], ensure_ascii=False)


def extract_tool_calls_from_text(chat_model: Any, response_text: str) -> list[dict[str, Any]]:
    template = chat_model.engine.template
    extracted = None

    format_tools = getattr(template, "format_tools", None)
    if format_tools is not None and hasattr(format_tools, "extract"):
        extracted = format_tools.extract(response_text)
    elif hasattr(template, "extract_tool"):
        extracted = template.extract_tool(response_text)

    if not extracted:
        return []

    parsed_calls: list[dict[str, Any]] = []
    candidates: list[Any]
    if isinstance(extracted, tuple):
        candidates = [extracted]
    elif isinstance(extracted, list):
        candidates = extracted
    else:
        candidates = [extracted]

    for item in candidates:
        if isinstance(item, tuple) and len(item) == 2:
            name, arguments = item
        elif isinstance(item, dict):
            name = item.get("name", "")
            arguments = item.get("arguments", item.get("argument", {}))
        else:
            continue
        parsed_calls.append({"id": "", "name": name, "arguments": parse_tool_arguments(arguments)})

    return parsed_calls


def init_llamafactory_chat_model(
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


def call_model_llamafactory(
    chat_model: Any,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    internal_messages, system = convert_messages_for_llamafactory(messages)
    tool_payload = convert_tools_for_llamafactory(tools)
    responses = chat_model.chat(internal_messages, system=system, tools=tool_payload)
    first = responses[0]
    response_text = getattr(first, "response_text", "")
    predicted_tool_calls = extract_tool_calls_from_text(chat_model, response_text)
    raw_response = {"response_text": response_text}
    return raw_response, predicted_tool_calls


def compare_turn(expected_calls: list[dict[str, Any]], predicted_calls: list[dict[str, Any]]) -> dict[str, Any]:
    expected_first = expected_calls[0] if expected_calls else None
    predicted_first = predicted_calls[0] if predicted_calls else None

    emitted_tool_call = predicted_first is not None
    tool_count_match = len(expected_calls) == len(predicted_calls)
    tool_name_match = bool(
        expected_first and predicted_first and expected_first["name"] == predicted_first["name"]
    )

    arg_evaluable = False
    arg_exact_match = None
    arg_key_recall = None
    arg_expected = {}
    arg_predicted = {}

    if expected_first:
        expected_args = expected_first.get("arguments", {}) or {}
        predicted_args = predicted_first.get("arguments", {}) if predicted_first else {}
        arg_expected, arg_predicted = filter_args(expected_first["name"], expected_args, predicted_args or {})

        if arg_expected:
            arg_evaluable = True
            matched = sum(
                1 for key, value in arg_expected.items() if key in arg_predicted and arg_predicted[key] == value
            )
            arg_exact_match = arg_expected == arg_predicted
            arg_key_recall = matched / len(arg_expected)
        else:
            arg_exact_match = True

    turn_exact_match = bool(tool_name_match and tool_count_match and arg_exact_match)

    return {
        "emitted_tool_call": emitted_tool_call,
        "tool_count_match": tool_count_match,
        "tool_name_match": tool_name_match,
        "arg_evaluable": arg_evaluable,
        "arg_exact_match": arg_exact_match,
        "arg_key_recall": arg_key_recall,
        "turn_exact_match": turn_exact_match,
        "arg_expected": arg_expected,
        "arg_predicted": arg_predicted,
    }


def evaluate_turns(
    turns: list[dict[str, Any]],
    model: str,
    timeout: int,
    temperature: float,
    max_tokens: int,
    quiet: bool,
    backend: str,
    endpoint: str,
    adapter_path: str | None,
    template: str,
    infer_backend: str,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    chat_model = None
    if backend == "llamafactory":
        chat_model = init_llamafactory_chat_model(
            model=model,
            adapter_path=adapter_path,
            template=template,
            infer_backend=infer_backend,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    for idx, turn in enumerate(turns, start=1):
        error = None
        raw_response = None
        predicted_tool_calls: list[dict[str, Any]] = []

        try:
            if backend == "api":
                raw_response = call_model(
                    endpoint=endpoint,
                    model=model,
                    messages=turn["messages"],
                    tools=turn["tools"],
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout,
                )
                choice = raw_response["choices"][0]
                message = choice.get("message", {})
                predicted_tool_calls = [normalize_tool_call(item) for item in message.get("tool_calls", [])]
            else:
                raw_response, predicted_tool_calls = call_model_llamafactory(
                    chat_model=chat_model,
                    messages=turn["messages"],
                    tools=turn["tools"],
                )
        except Exception as exc:  # pragma: no cover
            error = str(exc)

        comparison = compare_turn(turn["expected_tool_calls"], predicted_tool_calls) if error is None else {
            "emitted_tool_call": False,
            "tool_count_match": False,
            "tool_name_match": False,
            "arg_evaluable": False,
            "arg_exact_match": False,
            "arg_key_recall": None,
            "turn_exact_match": False,
            "arg_expected": {},
            "arg_predicted": {},
        }

        expected_first = turn["expected_tool_calls"][0]
        predicted_first = predicted_tool_calls[0] if predicted_tool_calls else {"name": "", "arguments": {}}
        record = {
            "index": idx,
            "sample_index": turn["sample_index"],
            "turn_index": turn["turn_index"],
            "role": turn["role"],
            "expected_tool_name": expected_first["name"],
            "predicted_tool_name": predicted_first.get("name", ""),
            "expected_arguments": expected_first.get("arguments", {}),
            "predicted_arguments": predicted_first.get("arguments", {}),
            "comparison": comparison,
            "error": error,
            "raw_response": raw_response,
        }
        results.append(record)

        if not quiet:
            status = "OK" if comparison["turn_exact_match"] else "MISS"
            print(
                f"[{idx}/{len(turns)}] {status} | sample={turn['sample_index']} "
                f"turn={turn['turn_index']} {expected_first['name']} -> {predicted_first.get('name', '<none>')}"
            )
            if error:
                print(f"  error: {error}")
            elif comparison["arg_evaluable"] and not comparison["arg_exact_match"]:
                print(f"  expected args: {comparison['arg_expected']}")
                print(f"  predicted args: {comparison['arg_predicted']}")

    return results


def safe_rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def summarize_results(results: list[dict[str, Any]], sample_to_turn_indices: dict[int, list[int]]) -> dict[str, Any]:
    total_turns = len(results)
    emitted_turns = sum(1 for item in results if item["comparison"]["emitted_tool_call"])
    name_matches = sum(1 for item in results if item["comparison"]["tool_name_match"])
    exact_turn_matches = sum(1 for item in results if item["comparison"]["turn_exact_match"])
    arg_evaluable_items = [item for item in results if item["comparison"]["arg_evaluable"]]
    arg_exact_matches = sum(1 for item in arg_evaluable_items if item["comparison"]["arg_exact_match"])

    decision_items = [item for item in results if item["expected_tool_name"] not in NON_DECISION_TOOLS]
    decision_name_matches = sum(1 for item in decision_items if item["comparison"]["tool_name_match"])
    decision_exact_matches = sum(1 for item in decision_items if item["comparison"]["turn_exact_match"])

    sample_successes = 0
    for turn_indices in sample_to_turn_indices.values():
        if turn_indices and all(results[idx]["comparison"]["turn_exact_match"] for idx in turn_indices):
            sample_successes += 1

    per_tool_counts: Counter[str] = Counter(item["expected_tool_name"] for item in results)
    per_tool_rows: list[dict[str, Any]] = []
    for tool_name in sorted(per_tool_counts):
        tool_items = [item for item in results if item["expected_tool_name"] == tool_name]
        tool_arg_items = [item for item in tool_items if item["comparison"]["arg_evaluable"]]
        per_tool_rows.append(
            {
                "tool_name": tool_name,
                "count": len(tool_items),
                "tool_name_accuracy": safe_rate(
                    sum(1 for item in tool_items if item["comparison"]["tool_name_match"]),
                    len(tool_items),
                ),
                "turn_exact_match_rate": safe_rate(
                    sum(1 for item in tool_items if item["comparison"]["turn_exact_match"]),
                    len(tool_items),
                ),
                "arg_exact_match_rate": (
                    safe_rate(
                        sum(1 for item in tool_arg_items if item["comparison"]["arg_exact_match"]),
                        len(tool_arg_items),
                    )
                    if tool_arg_items
                    else None
                ),
            }
        )

    per_role_rows: list[dict[str, Any]] = []
    for role_name in sorted({item["role"] for item in results}):
        role_items = [item for item in results if item["role"] == role_name]
        per_role_rows.append(
            {
                "role": role_name,
                "count": len(role_items),
                "tool_name_accuracy": safe_rate(
                    sum(1 for item in role_items if item["comparison"]["tool_name_match"]),
                    len(role_items),
                ),
                "turn_exact_match_rate": safe_rate(
                    sum(1 for item in role_items if item["comparison"]["turn_exact_match"]),
                    len(role_items),
                ),
            }
        )

    return {
        "total_samples": len(sample_to_turn_indices),
        "total_turns": total_turns,
        "tool_call_emission_rate": safe_rate(emitted_turns, total_turns),
        "tool_name_accuracy": safe_rate(name_matches, total_turns),
        "turn_exact_match_rate": safe_rate(exact_turn_matches, total_turns),
        "argument_exact_match_rate": safe_rate(arg_exact_matches, len(arg_evaluable_items)),
        "decision_turns": len(decision_items),
        "decision_tool_name_accuracy": safe_rate(decision_name_matches, len(decision_items)),
        "decision_turn_exact_match_rate": safe_rate(decision_exact_matches, len(decision_items)),
        "sample_full_chain_success_rate": safe_rate(sample_successes, len(sample_to_turn_indices)),
        "arg_evaluable_turns": len(arg_evaluable_items),
        "per_tool": per_tool_rows,
        "per_role": per_role_rows,
    }


def make_report_markdown(
    dataset_path: Path,
    endpoint: str,
    model: str,
    summary: dict[str, Any],
) -> str:
    lines = [
        "# Tool Calling Evaluation Report",
        "",
        f"- Generated at: {datetime.now().isoformat(timespec='seconds')}",
        f"- Dataset: `{dataset_path}`",
        f"- Endpoint: `{endpoint}`",
        f"- Model: `{model}`",
        "",
        "## Overall Metrics",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Total samples | {summary['total_samples']} |",
        f"| Total turns | {summary['total_turns']} |",
        f"| Tool-call emission rate | {summary['tool_call_emission_rate']:.2%} |",
        f"| Tool-name accuracy | {summary['tool_name_accuracy']:.2%} |",
        f"| Argument exact match rate | {summary['argument_exact_match_rate']:.2%} |",
        f"| Turn exact match rate | {summary['turn_exact_match_rate']:.2%} |",
        f"| Decision-turn count | {summary['decision_turns']} |",
        f"| Decision-turn tool-name accuracy | {summary['decision_tool_name_accuracy']:.2%} |",
        f"| Decision-turn exact match rate | {summary['decision_turn_exact_match_rate']:.2%} |",
        f"| Sample full-chain success rate | {summary['sample_full_chain_success_rate']:.2%} |",
        "",
        "## Per Tool",
        "",
        "| Tool | Count | Tool-name Acc | Arg Exact | Turn Exact |",
        "|---|---:|---:|---:|---:|",
    ]

    for row in summary["per_tool"]:
        arg_exact = "N/A" if row["arg_exact_match_rate"] is None else f"{row['arg_exact_match_rate']:.2%}"
        lines.append(
            f"| {row['tool_name']} | {row['count']} | {row['tool_name_accuracy']:.2%} | "
            f"{arg_exact} | {row['turn_exact_match_rate']:.2%} |"
        )

    lines.extend(
        [
            "",
            "## Per Role",
            "",
            "| Role | Count | Tool-name Acc | Turn Exact |",
            "|---|---:|---:|---:|",
        ]
    )
    for row in summary["per_role"]:
        lines.append(
            f"| {row['role']} | {row['count']} | {row['tool_name_accuracy']:.2%} | "
            f"{row['turn_exact_match_rate']:.2%} |"
        )

    return "\n".join(lines) + "\n"


def ensure_report_dir(report_dir_arg: str | None) -> Path:
    if report_dir_arg:
        path = Path(report_dir_arg).resolve()
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = DEFAULT_REPORT_ROOT / f"tool_call_eval_{stamp}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def main() -> None:
    args = parse_args()
    dataset_path = Path(args.dataset).resolve()
    if not dataset_path.exists():
        raise FileNotFoundError(
            f"Dataset not found: {dataset_path}\n"
            f"Tip: create {DEFAULT_DATASET.name} or pass --dataset <path>."
        )

    samples = load_dataset(dataset_path, args.max_samples, args.seed)
    turns, sample_to_turn_indices = build_turns(samples)
    report_dir = ensure_report_dir(args.report_dir)

    results = evaluate_turns(
        turns=turns,
        model=args.model,
        timeout=args.timeout,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        quiet=args.quiet,
        backend=args.backend,
        endpoint=args.endpoint,
        adapter_path=args.adapter_path,
        template=args.template,
        infer_backend=args.infer_backend,
    )
    summary = summarize_results(results, sample_to_turn_indices)

    payload = {
        "meta": {
            "dataset": str(dataset_path),
            "endpoint": args.endpoint if args.backend == "api" else "llamafactory://local",
            "backend": args.backend,
            "model": args.model,
            "adapter_path": args.adapter_path,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "sample_count": len(samples),
            "turn_count": len(turns),
        },
        "summary": summary,
        "results": results,
    }

    (report_dir / "results.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (report_dir / "report.md").write_text(
        make_report_markdown(dataset_path, args.endpoint, args.model, summary),
        encoding="utf-8",
    )

    print(f"Results saved to: {report_dir}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
