"""Command-line entry point.

Exposes the safe, offline-usable commands: version, the legal statement, the retention
check, and the purge command that closes out an engagement.
"""
from __future__ import annotations

import argparse
import sys

from weft import __version__
from weft.compliance.engagement import LEGAL_STATEMENT, LEGAL_STATEMENT_VERSION


def _stores():
    from weft.config import load_settings
    from weft.storage.meta import EngagementRepository, MetaStore

    meta = MetaStore(load_settings().database_url)
    return meta, EngagementRepository(meta)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="weft", description="Free-source OSINT aggregator.")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("version", help="print the Weft version")
    sub.add_parser("legal", help="print the responsibility statement the operator must accept")

    ret = sub.add_parser("retention", help="list engagements past their end date")
    ret.add_argument("--flag", action="store_true", help="mark expired engagements as 'expired'")

    rep = sub.add_parser("report", help="build the Markdown report for an engagement from the persisted graph")
    rep.add_argument("engagement_id")
    rep.add_argument("--model", default="", help="local Ollama model for the AI narrative (empty to skip)")
    rep.add_argument("--out", default="", help="write to this file instead of stdout")

    pur = sub.add_parser("purge", help="delete an engagement's personal data and findings (keeps redacted audit)")
    pur.add_argument("engagement_id")
    pur.add_argument("--yes", action="store_true", help="confirm the irreversible purge")

    args = parser.parse_args(argv)

    if args.command == "version":
        print(f"weft {__version__}")
        return 0
    if args.command == "legal":
        print(f"Weft responsibility statement (version {LEGAL_STATEMENT_VERSION})\n")
        print(LEGAL_STATEMENT)
        return 0
    if args.command == "retention":
        from weft.lifecycle import expired_engagements, flag_expired
        _, repo = _stores()
        if args.flag:
            ids = flag_expired(repo)
            print(f"flagged {len(ids)} expired engagement(s): {', '.join(ids) or '(none)'}")
        else:
            exp = expired_engagements(repo)
            if not exp:
                print("no engagements past their end date.")
            for e in exp:
                print(f"  {e.id} — {e.client} — ended {e.end_date}")
        return 0
    if args.command == "report":
        from weft.config import load_settings
        from weft.reporting import build_report
        from weft.storage.graph import open_neo4j
        _, repo = _stores()
        eng = repo.get(args.engagement_id)
        if eng is None:
            print(f"no engagement '{args.engagement_id}'.")
            return 2
        settings = load_settings()
        neo = open_neo4j(settings, args.engagement_id)
        if neo is None:
            print("Neo4j is not reachable; no persisted graph to report on.")
            return 2
        graph = neo.load()
        neo.close()
        reasoner = None
        if args.model:
            from weft.core.reasoner import OllamaReasoner
            reasoner = OllamaReasoner(args.model, base_url=settings.ollama_url)
        md = build_report(eng, graph, reasoner=reasoner)
        if args.out:
            from pathlib import Path
            Path(args.out).write_text(md, encoding="utf-8")
            print(f"wrote {args.out} ({len(graph.nodes)} entities)")
        else:
            print(md)
        return 0
    if args.command == "purge":
        if not args.yes:
            print(f"Refusing to purge {args.engagement_id} without --yes (this is irreversible).")
            return 2
        from weft.config import load_settings
        from weft.lifecycle import purge_engagement
        from weft.storage.graph import open_neo4j
        meta, _ = _stores()
        graph = open_neo4j(load_settings(), args.engagement_id)
        result = purge_engagement(args.engagement_id, meta_store=meta, graph=graph)
        if graph is not None:
            graph.close()
        print(result.summary())
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
