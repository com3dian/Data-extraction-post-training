"""Command-line interface for paper extraction."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.data.documents import discover_documents
from src.data.output import ExtractionOutput
from src.model import MODEL_ALIASES, StructuredLLMClient, load_provider_config
from src.zeroshot import PROMPT_FINGERPRINT, run_extraction


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="extract-papers",
        description="Extract Jantzen species-interaction records from papers.",
    )
    parser.add_argument("inputs", nargs="+", type=Path, help="MinerU Markdown, text, or directory")
    parser.add_argument("--provider", choices=sorted(MODEL_ALIASES))
    parser.add_argument("--model", help="Provider alias or full model ID")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/extraction"))
    parser.add_argument("--recursive", action="store_true", help="Search directories recursively")
    parser.add_argument("--overwrite", action="store_true", help="Re-run completed papers")
    parser.add_argument("--stop-on-error", action="store_true")
    parser.add_argument(
        "--response-mode",
        choices=("json_schema", "json_object"),
        default="json_schema",
        help="Use strict schema output, or JSON mode for a provider lacking schema support",
    )
    parser.add_argument("--max-output-tokens", type=int, default=8_000)
    parser.add_argument(
        "--max-paper-chars",
        type=int,
        help="Fail rather than silently truncate papers above this character count",
    )
    parser.add_argument("--timeout", type=float, help="Request timeout in seconds")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List the selected inputs without loading credentials or calling an API",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.max_output_tokens < 1:
        raise SystemExit("--max-output-tokens must be positive")
    if args.max_paper_chars is not None and args.max_paper_chars < 1:
        raise SystemExit("--max-paper-chars must be positive")

    papers = discover_documents(args.inputs, recursive=args.recursive)
    if not papers:
        raise SystemExit("No supported papers found")

    if args.dry_run:
        print(json.dumps({"papers": [str(path) for path in papers]}, indent=2))
        return 0

    config = load_provider_config(args.provider, args.model, timeout_seconds=args.timeout)
    output = ExtractionOutput(args.output_dir)
    output.write_config(
        {
            "provider": config.provider,
            "model": config.model,
            "base_url": config.base_url,
            "response_mode": args.response_mode,
            "max_output_tokens": args.max_output_tokens,
            "max_paper_chars": args.max_paper_chars,
            "prompt_fingerprint": PROMPT_FINGERPRINT,
        }
    )
    client = StructuredLLMClient(config)
    summary = run_extraction(
        args.inputs,
        client=client,
        output=output,
        recursive=args.recursive,
        overwrite=args.overwrite,
        stop_on_error=args.stop_on_error,
        response_mode=args.response_mode,
        max_output_tokens=args.max_output_tokens,
        max_paper_chars=args.max_paper_chars,
    )
    print(
        f"Done: {summary.succeeded} succeeded, {summary.skipped} skipped, "
        f"{summary.failed} failed. Records: {summary.records_path}"
    )
    return 1 if summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
