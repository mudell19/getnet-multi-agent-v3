"""Command line: issue tokens, ingest the knowledge base, refresh the crawl."""

from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="getnet-multi-agent")
    sub = parser.add_subparsers(dest="cmd", required=True)
    tok = sub.add_parser("token", help="issue a signed JWT")
    tok.add_argument("--sub", required=True)
    tok.add_argument("--role", required=True, choices=["merchant", "operator"])
    tok.add_argument("--hours", type=float, default=12)
    ing = sub.add_parser("ingest", help="build the vector index from the crawl cache")
    ing.add_argument("--rebuild", action="store_true")
    sub.add_parser("refresh", help="re-crawl the public pages")
    args = parser.parse_args(argv)

    if args.cmd == "token":
        from getnet_multi_agent.security.auth import issue_token

        print(issue_token(args.sub, args.role, hours=args.hours))
    elif args.cmd == "ingest":
        from getnet_multi_agent.rag.ingest import ingest

        ingest(rebuild=args.rebuild)
    elif args.cmd == "refresh":
        from getnet_multi_agent.rag.crawler import refresh

        refresh()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
