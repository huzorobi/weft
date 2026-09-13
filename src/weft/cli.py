"""Minimal command-line entry point.

Phase 0 exposes only what exists and is safe offline: the version and the legal
responsibility statement the operator must accept before any run. Run commands
(seed expansion) arrive with the orchestrator in Phase 1.
"""
from __future__ import annotations

import argparse
import sys

from weft import __version__
from weft.compliance.engagement import LEGAL_STATEMENT, LEGAL_STATEMENT_VERSION


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="weft", description="Free-source OSINT aggregator.")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("version", help="print the Weft version")
    sub.add_parser("legal", help="print the responsibility statement the operator must accept")

    args = parser.parse_args(argv)

    if args.command == "version":
        print(f"weft {__version__}")
        return 0
    if args.command == "legal":
        print(f"Weft responsibility statement (version {LEGAL_STATEMENT_VERSION})\n")
        print(LEGAL_STATEMENT)
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
