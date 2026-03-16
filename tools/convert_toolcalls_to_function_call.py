"""
Convert ShareGPT-style `gpt + tool_calls` samples into LLaMA-Factory
tool-calling SFT samples that use `function_call + observation`.

Usage:
    python tools/convert_toolcalls_to_function_call.py input.json output.json
"""

import json
import sys
from pathlib import Path


def convert_conversations(conversations):
    converted = []
    for message in conversations:
        role = message.get("from")
        value = message.get("value", "")

        if role == "gpt" and message.get("tool_calls"):
            for tool_call in message["tool_calls"]:
                converted.append(
                    {
                        "from": "function_call",
                        "value": json.dumps(
                            {
                                "name": tool_call["name"],
                                "arguments": tool_call.get("arguments", {}),
                            },
                            ensure_ascii=False,
                        ),
                    }
                )
            if value:
                converted.append({"from": "gpt", "value": value})
            continue

        converted.append({"from": role, "value": value})

    return converted


def main():
    if len(sys.argv) != 3:
        print("Usage: python tools/convert_toolcalls_to_function_call.py input.json output.json")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])

    data = json.loads(input_path.read_text(encoding="utf-8"))
    converted = []

    for sample in data:
        new_sample = {
            "system": sample.get("system", ""),
            "tools": sample.get("tools", ""),
            "conversations": convert_conversations(sample.get("conversations", [])),
        }
        converted.append(new_sample)

    output_path.write_text(
        json.dumps(converted, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Converted {len(converted)} samples -> {output_path}")


if __name__ == "__main__":
    main()
