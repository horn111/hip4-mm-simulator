"""Generate the deterministic data artifacts consumed by the static demo."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from hl_paper_trading.replay import build_demo_trace

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "tests" / "fixtures" / "sample_recording.jsonl"
VALIDATION = ROOT / "docs" / "validation-mainnet-8220-24h.json"
OUTPUT_DIR = ROOT / "demo" / "public" / "data"


def expected_outputs() -> dict[Path, str]:
    trace = build_demo_trace(SAMPLE)
    validation = json.loads(VALIDATION.read_text(encoding="utf-8"))
    return {
        OUTPUT_DIR / "sample-replay.json": trace.model_dump_json(indent=2) + "\n",
        OUTPUT_DIR / "validation-24h.json": json.dumps(
            validation, indent=2, ensure_ascii=False
        )
        + "\n",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when committed demo data differs from generated output",
    )
    args = parser.parse_args()
    outputs = expected_outputs()
    if args.check:
        mismatches = [
            path
            for path, expected in outputs.items()
            if not path.exists() or path.read_text(encoding="utf-8") != expected
        ]
        if mismatches:
            for path in mismatches:
                print(f"stale demo artifact: {path.relative_to(ROOT)}")
            return 1
        print("demo data artifacts are current")
        return 0

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path, content in outputs.items():
        path.write_text(content, encoding="utf-8", newline="\n")
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
