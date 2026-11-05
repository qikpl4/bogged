#!/usr/bin/env python3
"""Bogged CLI — look up Minecraft mappings from the packed binary data.

Data can be sourced from any URL supported by urllib, e.g.:

    python cli/main.py --side mojmap --version 1.21.1 wrap
    python cli/main.py --base-url file:///path/to/www/public/data --side yarn --version 1.21.1 --match exact Level
"""

import argparse
import shutil
import sys
import time

import lookup
import render
import sources


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Look up Minecraft mappings (Mojmap, Yarn, Intermediary) across versions.",
    )
    parser.add_argument(
        "--base-url",
        default=sources.DEFAULT_BASE_URL,
        help=f"where versions.json and the per-version folders live (default: {sources.DEFAULT_BASE_URL}); "
             "use a file:// URL for local data",
    )
    parser.add_argument("--side", required=True, choices=["mojmap", "yarn", "intermediary"],
                        help="mapping side to search")
    parser.add_argument("--version", required=True,
                        help="game version to look up, e.g. 1.21.1")
    parser.add_argument("--match", default="prefix", choices=["prefix", "exact", "contains"],
                        help="name match mode (default: prefix)")
    parser.add_argument("--csv", action="store_true",
                        help="output CSV instead of a table (absent values are empty fields)")
    parser.add_argument("--quiet", action="store_true",
                        help="suppress the summary line printed to stderr")
    parser.add_argument("--width", type=int, default=None, metavar="N",
                        help="wrap the table to N columns (0 = no limit); "
                             "default: terminal width, or no limit when not a TTY")
    parser.add_argument("query", help="name to look up")
    return parser.parse_args(argv)


def table_width(requested: int | None) -> int | None:
    if requested is not None:
        return requested if requested > 0 else None
    if sys.stdout.isatty():
        return shutil.get_terminal_size().columns
    return None


def no_results_message(args: argparse.Namespace) -> str:
    mode_label = {"exact": "exactly matching", "prefix": "starting with", "contains": "containing"}[args.match]
    return f"No {mode_label} “{args.query}” in {args.version} ({args.side})."


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    started = time.perf_counter()
    try:
        result = lookup.lookup(args.base_url, args.version, args.side, args.query, args.match)
    except (RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    if args.csv:
        print(render.render_csv(result.records), end="")
        if not result.records and not args.quiet:
            print(no_results_message(args), file=sys.stderr)
    elif result.records:
        print(render.render_table(result.records, max_width=table_width(args.width)))
    else:
        print(no_results_message(args))

    if not args.quiet:
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        print(f"{len(result.records)} result(s) · {result.files_fetched} file(s) fetched · {elapsed_ms} ms",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
