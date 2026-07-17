#!/usr/bin/env python3
"""Manga correct loop CLI.

Usage:
  python cli.py --script script.json --refs ./refs --out ./out
  python cli.py --script script.json --refs ./refs --out ./out --profile anime_seedream
  MANGA_MOCK_IMAGES=1 python cli.py --script script.json --out ./out   # no API spend

Exit code is non-zero if any panel still fails QA after its one
fix-and-regenerate attempt.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate storyboard panels with Seedream and run fail-closed vision QA"
    )
    parser.add_argument("--script", type=Path, required=True, help="Structured script JSON file")
    parser.add_argument("--refs", type=Path, default=None, help="Folder of character/style reference images")
    parser.add_argument("--out", type=Path, required=True, help="Output folder")
    parser.add_argument(
        "--profile",
        default="anime_seedream",
        help="Image model profile from config.yaml (default: anime_seedream)",
    )
    parser.add_argument("--mock", action="store_true", help="Placeholder images, no API spend")
    parser.add_argument("--json", action="store_true", help="Print the full run summary as JSON")
    args = parser.parse_args(argv)

    if args.mock:
        import os

        os.environ["MANGA_MOCK_IMAGES"] = "1"

    from pipeline.config import ConfigError, load_config
    from pipeline.orchestrator import ScriptError, run_correct_loop

    if not args.script.is_file():
        print(f"error: script file not found: {args.script}", file=sys.stderr)
        return 2
    if args.refs and not args.refs.is_dir():
        print(f"error: refs folder not found: {args.refs}", file=sys.stderr)
        return 2

    try:
        settings = load_config(profile=args.profile, strict=True)
    except ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    def emit(event: str, payload: dict) -> None:
        idx = payload.get("index")
        if event == "panel_start":
            print(f"[panel {idx}] generating…", flush=True)
        elif event == "panel_done":
            rec = payload.get("record") or {}
            status = "PASS" if rec.get("passed") else "FAIL (needs review)"
            print(f"[panel {idx}] {status} → {rec.get('path')}", flush=True)

    try:
        summary = run_correct_loop(args.script, args.refs, args.out, settings, emit=emit)
    except ScriptError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(
            f"\n{summary['passed']}/{summary['panel_count']} panels passed QA. "
            f"Output: {args.out}"
        )
        if summary["failed_panels"]:
            print(f"Failed panels (see {args.out}/qa/): {summary['failed_panels']}")

    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
