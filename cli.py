#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from harness.pipeline import run_pipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verdict Loop — research + red-team debate + optional promo images"
    )
    parser.add_argument("claim", nargs="?", help="Plan or claim to stress-test")
    parser.add_argument(
        "-f",
        "--file",
        type=Path,
        help="Read claim from a text file",
    )
    parser.add_argument(
        "--no-images",
        action="store_true",
        help="Skip promoter / image generation / image critic loop",
    )
    parser.add_argument(
        "--context",
        type=Path,
        help="Optional file with extra notes/links for Scout research",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to config.yaml",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full JSON result to stdout",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run offline with mock models (no API keys required)",
    )
    args = parser.parse_args(argv)

    claim = args.claim
    if args.file:
        claim = args.file.read_text(encoding="utf-8").strip()
    if not claim:
        parser.error("Provide a claim argument or --file")
    extra = args.context.read_text(encoding="utf-8") if args.context else None

    def on_progress(event: str, payload: dict) -> None:
        if event.endswith("_start"):
            extra = ""
            if "round" in payload:
                extra = f" round={payload['round']}"
            if "attempt" in payload:
                extra = f" attempt={payload['attempt']}"
            if "id" in payload:
                extra += f" id={payload['id']}"
            print(f"→ {event}{extra}", file=sys.stderr)
        elif event.endswith("_done") or event in {"creative_pass", "creative_retry", "run_done"}:
            print(f"✓ {event}", file=sys.stderr)

    try:
        result = run_pipeline(
            claim,
            with_images=not args.no_images,
            dry_run=args.dry_run,
            extra_context=extra,
            config_path=args.config,
            on_progress=on_progress,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        verdict = result["debate"]["verdict"]
        print()
        print("=== VERDICT ===")
        print(f"Recommendation: {verdict.get('recommendation')}")
        print(f"Score: {verdict.get('score')}")
        print(f"Reasoning: {verdict.get('reasoning')}")
        if result.get("creative"):
            promo = result["creative"]["promo"]
            print()
            print("=== PROMO ===")
            print(f"Headline: {promo.get('headline')}")
            print(f"Tagline: {promo.get('tagline')}")
            print(f"Approved images: {len(result['creative'].get('approved') or [])}")
        print()
        print(f"Saved: {result['run_dir']}")
        print(f"Report: {Path(result['run_dir']) / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())