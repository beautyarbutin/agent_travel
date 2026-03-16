import argparse
import json
import re
from pathlib import Path


def normalize_raw_text(raw: str) -> str:
    text = raw.strip()
    text = re.sub(r'"tags"\s*:\s*,', '"tags": [],', text)
    text = re.sub(r"\]\s*\[", ",", text, count=1)
    return text


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Merge two back-to-back JSON arrays into one JSON array."
    )
    parser.add_argument("input", type=Path, help="Source .txt or .json file")
    parser.add_argument("output", type=Path, help="Destination .json file")
    args = parser.parse_args()

    raw = args.input.read_text(encoding="utf-8")
    merged = normalize_raw_text(raw)
    data = json.loads(merged)

    args.output.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {len(data)} records to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
