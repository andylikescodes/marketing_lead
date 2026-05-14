from __future__ import annotations

import argparse
from pathlib import Path

from marketing_lead.export import write_leads
from marketing_lead.osm import OVERPASS_URL
from marketing_lead.pipeline import search_leads


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "collect":
        _collect(args)
    elif args.command == "serve":
        from marketing_lead.web import run_server

        run_server(host=args.host, port=args.port)
    else:
        parser.print_help()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="marketing-lead",
        description="Discover and score foodservice leads around a ZIP code.",
    )
    subparsers = parser.add_subparsers(dest="command")

    collect = subparsers.add_parser("collect", help="Collect leads around a ZIP/ZCTA.")
    collect.add_argument("--zip", required=True, help="Five-digit ZIP code.")
    collect.add_argument("--radius-mi", type=float, default=2.0, help="Search radius in miles.")
    collect.add_argument("--out", type=Path, required=True, help="Output CSV or JSON path.")
    collect.add_argument("--format", choices=["csv", "json"], default="csv", help="Output format.")
    collect.add_argument("--min-score", type=int, default=0, help="Only export leads at or above this score.")
    collect.add_argument("--limit", type=int, default=0, help="Maximum number of leads to export.")
    collect.add_argument("--overpass-url", default=OVERPASS_URL, help="Overpass API interpreter URL.")
    collect.add_argument("--timeout", type=int, default=45, help="Overpass timeout in seconds.")
    collect.add_argument("--no-abc", action="store_true", help="Skip California ABC free license data.")
    collect.add_argument("--use-llm", action="store_true", help="Ask local Ollama to annotate top leads.")
    collect.add_argument("--llm-model", default="kimi-k2.6:cloud", help="Ollama model name.")

    serve = subparsers.add_parser("serve", help="Start the local web app.")
    serve.add_argument("--host", default="127.0.0.1", help="Host to bind.")
    serve.add_argument("--port", type=int, default=8787, help="Port to bind.")
    return parser


def _collect(args: argparse.Namespace) -> None:
    result = search_leads(
        zip_code=args.zip,
        radius_mi=args.radius_mi,
        include_abc=not args.no_abc,
        include_llm=args.use_llm,
        llm_model=args.llm_model,
        limit=args.limit,
        overpass_url=args.overpass_url,
        overpass_timeout=args.timeout,
    )
    leads = result.leads

    if args.min_score:
        leads = [lead for lead in leads if lead.confidence_score >= args.min_score]

    write_leads(leads, args.out, args.format)
    print(
        f"Wrote {len(leads)} leads near ZIP {result.location.zip_code} "
        f"({result.location.latitude:.5f}, {result.location.longitude:.5f}) to {args.out}"
    )
