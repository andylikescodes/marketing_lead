from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from marketing_lead.artifacts import read_discovery_bundle, write_discovery_bundle
from marketing_lead.customer_snapshot import (
    CUSTOMER_EXPORT_FIELDS,
    DEFAULT_SNAPSHOT_PATH,
    active_customers_for_zip,
    apply_customer_matches,
    refresh_customer_snapshot,
)
from marketing_lead.export import write_leads
from marketing_lead.osm import OVERPASS_URL
from marketing_lead.pipeline import LeadSearchResult, SourceReport, search_leads
from marketing_lead.scoring import score_leads


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "collect":
        _collect(args)
    elif args.command == "discover":
        _discover(args)
    elif args.command == "validate-customers":
        _validate_customers(args)
    elif args.command == "serve":
        from marketing_lead.web import run_server

        run_server(host=args.host, port=args.port)
    elif args.command == "customers":
        _customers(args)
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
    collect.add_argument("--out", type=Path, required=True, help="Output file path.")
    collect.add_argument(
        "--format",
        choices=["auto", "csv", "json", "xlsx"],
        default="auto",
        help="Output format. Auto infers from --out and defaults to xlsx for unknown extensions.",
    )
    collect.add_argument("--min-score", type=int, default=0, help="Only export leads at or above this score.")
    collect.add_argument("--limit", type=int, default=0, help="Maximum number of leads to export.")
    collect.add_argument("--overpass-url", default=OVERPASS_URL, help="Overpass API interpreter URL.")
    collect.add_argument("--timeout", type=int, default=45, help="Overpass timeout in seconds.")
    collect.add_argument("--no-abc", action="store_true", help="Skip California ABC free license data.")
    collect.add_argument("--use-llm", action="store_true", help="Ask local Ollama to annotate top leads.")
    collect.add_argument("--llm-model", default="kimi-k2.6:cloud", help="Ollama model name.")
    collect.add_argument("--llm-limit", type=int, default=0, help="Maximum leads to review with Ollama; 0 means all.")
    collect.add_argument(
        "--log-file",
        type=Path,
        help="Write a detailed run log. Defaults to the output path with a .log extension.",
    )

    discover = subparsers.add_parser(
        "discover",
        help="Run cloud/network lead discovery and write a portable JSON bundle.",
    )
    discover.add_argument("--zip", required=True, help="Five-digit ZIP code.")
    discover.add_argument("--radius-mi", type=float, default=2.0, help="Search radius in miles.")
    discover.add_argument("--out", type=Path, required=True, help="Output discovery JSON bundle path.")
    discover.add_argument("--limit", type=int, default=0, help="Maximum number of discovered leads; 0 means all.")
    discover.add_argument("--overpass-url", default=OVERPASS_URL, help="Overpass API interpreter URL.")
    discover.add_argument("--timeout", type=int, default=45, help="Overpass timeout in seconds.")
    discover.add_argument("--no-abc", action="store_true", help="Skip California ABC free license data.")
    discover.add_argument("--use-llm", action="store_true", help="Ask local Ollama to annotate top leads.")
    discover.add_argument("--llm-model", default="kimi-k2.6:cloud", help="Ollama model name.")
    discover.add_argument("--llm-limit", type=int, default=0, help="Maximum leads to review with Ollama; 0 means all.")
    discover.add_argument(
        "--log-file",
        type=Path,
        help="Write a detailed discovery log. Defaults to the output path with a .log extension.",
    )

    validate = subparsers.add_parser(
        "validate-customers",
        help="Validate a discovery JSON bundle against the local active-customer snapshot.",
    )
    validate.add_argument("--in", dest="input_path", type=Path, required=True, help="Input discovery JSON bundle.")
    validate.add_argument("--out", type=Path, required=True, help="Validated lead output path.")
    validate.add_argument(
        "--format",
        choices=["auto", "csv", "json", "xlsx"],
        default="auto",
        help="Output format. Auto infers from --out and defaults to xlsx for unknown extensions.",
    )
    validate.add_argument(
        "--snapshot",
        type=Path,
        default=DEFAULT_SNAPSHOT_PATH,
        help="Local SQLite customer snapshot path.",
    )
    validate.add_argument("--min-score", type=int, default=0, help="Only export leads at or above this score.")
    validate.add_argument("--limit", type=int, default=0, help="Maximum number of validated leads to export.")
    validate.add_argument(
        "--customer-zip-limit",
        type=int,
        default=10000,
        help="Maximum active customer rows to include for the searched ZIP in Excel output.",
    )
    validate.add_argument(
        "--log-file",
        type=Path,
        help="Write a detailed validation log. Defaults to the output path with a .log extension.",
    )
    validate.add_argument(
        "--use-llm-match",
        action="store_true",
        help="Use Ollama to adjudicate ambiguous customer matches.",
    )
    validate.add_argument(
        "--llm-match-model",
        default="kimi-k2.6:cloud",
        help="Ollama model for ambiguous customer match review.",
    )
    validate.add_argument(
        "--llm-match-limit",
        type=int,
        default=100,
        help="Maximum ambiguous customer matches to send to Ollama; 0 means unlimited.",
    )
    validate.add_argument(
        "--llm-match-timeout",
        type=int,
        default=30,
        help="Ollama customer match review timeout in seconds.",
    )

    serve = subparsers.add_parser("serve", help="Start the local web app.")
    serve.add_argument("--host", default="127.0.0.1", help="Host to bind.")
    serve.add_argument("--port", type=int, default=8787, help="Port to bind.")

    customers = subparsers.add_parser("customers", help="Manage local customer snapshot.")
    customer_subparsers = customers.add_subparsers(dest="customers_command")
    refresh = customer_subparsers.add_parser("refresh", help="Refresh local customer snapshot from Corporate DW.")
    refresh.add_argument("--server", default="CORPORATE-DW", help="SQL Server host.")
    refresh.add_argument("--database", default="GLOBAL", help="SQL Server database.")
    refresh.add_argument("--driver", default="ODBC Driver 17 for SQL Server", help="ODBC driver name.")
    refresh.add_argument("--out", type=Path, default=DEFAULT_SNAPSHOT_PATH, help="SQLite snapshot output path.")
    return parser


def _collect(args: argparse.Namespace) -> None:
    output_format = _resolve_output_format(args.out, args.format)
    log_file = args.log_file or args.out.with_suffix(".log")
    logger = _configure_logger(log_file)
    started_at = datetime.now(timezone.utc).isoformat()
    run_log: list[dict[str, object]] = []

    base_parameters: dict[str, object] = {
        "started_at": started_at,
        "zip": args.zip,
        "radius_mi": args.radius_mi,
        "min_score": args.min_score,
        "limit": args.limit,
        "include_abc": not args.no_abc,
        "include_llm": args.use_llm,
        "llm_model": args.llm_model,
        "llm_limit": args.llm_limit,
        "overpass_url": args.overpass_url,
        "overpass_timeout": args.timeout,
        "output_path": str(args.out),
        "output_format": output_format,
        "log_file": str(log_file),
    }
    logger.info("Starting lead collection.")
    for name, value in base_parameters.items():
        logger.info("Parameter %s=%s", name, value)

    progress_state = {"progress": 0}

    def progress(update: dict[str, object]) -> None:
        event = _progress_event(update, progress_state["progress"])
        progress_state["progress"] = int(event["progress"])
        run_log.append(event)
        current_lead = event.get("current_lead")
        lead_suffix = f" lead={current_lead}" if current_lead else ""
        logger.info(
            "[%s%%] %s: %s%s",
            event["progress"],
            event["stage"],
            event["message"],
            lead_suffix,
        )

    try:
        result = search_leads(
            zip_code=args.zip,
            radius_mi=args.radius_mi,
            include_abc=not args.no_abc,
            include_llm=args.use_llm,
            llm_model=args.llm_model,
            llm_limit=args.llm_limit,
            limit=args.limit,
            overpass_url=args.overpass_url,
            overpass_timeout=args.timeout,
            include_customer_snapshot=True,
            progress_callback=progress,
        )
    except Exception:
        logger.exception("Lead collection failed.")
        raise

    leads = result.leads
    collected_count = len(leads)

    if args.min_score:
        leads = [lead for lead in leads if lead.confidence_score >= args.min_score]
        logger.info(
            "Applied min_score=%s filter: %s of %s leads remain.",
            args.min_score,
            len(leads),
            collected_count,
        )

    completed_at = datetime.now(timezone.utc).isoformat()
    parameters = {
        **base_parameters,
        "completed_at": completed_at,
        "resolved_zip": result.location.zip_code,
        "latitude": result.location.latitude,
        "longitude": result.location.longitude,
        "location_source": result.location.source,
        "collected_lead_count": collected_count,
        "exported_lead_count": len(leads),
        "merged_duplicate_count": result.merged_count,
    }
    source_reports = [report.__dict__ for report in result.source_reports]

    write_leads(
        leads,
        args.out,
        output_format,
        parameters=parameters,
        source_reports=source_reports,
        run_log=run_log,
    )
    _log_result_summary(logger, result, leads)
    print(
        f"Wrote {len(leads)} leads near ZIP {result.location.zip_code} "
        f"({result.location.latitude:.5f}, {result.location.longitude:.5f}) to {args.out}"
    )
    print(f"Run log: {log_file}")


def _discover(args: argparse.Namespace) -> None:
    log_file = args.log_file or args.out.with_suffix(".log")
    logger = _configure_logger(log_file)
    started_at = datetime.now(timezone.utc).isoformat()
    run_log: list[dict[str, object]] = []
    parameters: dict[str, object] = {
        "workflow_part": "cloud_discovery",
        "started_at": started_at,
        "zip": args.zip,
        "radius_mi": args.radius_mi,
        "limit": args.limit,
        "include_abc": not args.no_abc,
        "include_llm": args.use_llm,
        "llm_model": args.llm_model,
        "llm_limit": args.llm_limit,
        "include_customer_snapshot": False,
        "overpass_url": args.overpass_url,
        "overpass_timeout": args.timeout,
        "output_path": str(args.out),
        "log_file": str(log_file),
    }
    logger.info("Starting cloud/network lead discovery.")
    for name, value in parameters.items():
        logger.info("Parameter %s=%s", name, value)

    progress_state = {"progress": 0}

    def progress(update: dict[str, object]) -> None:
        event = _progress_event(update, progress_state["progress"])
        progress_state["progress"] = int(event["progress"])
        run_log.append(event)
        logger.info("[%s%%] %s: %s", event["progress"], event["stage"], event["message"])

    try:
        result = search_leads(
            zip_code=args.zip,
            radius_mi=args.radius_mi,
            include_abc=not args.no_abc,
            include_llm=args.use_llm,
            llm_model=args.llm_model,
            llm_limit=args.llm_limit,
            limit=args.limit,
            overpass_url=args.overpass_url,
            overpass_timeout=args.timeout,
            include_customer_snapshot=False,
            progress_callback=progress,
        )
    except Exception:
        logger.exception("Lead discovery failed.")
        raise

    parameters.update(
        {
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "resolved_zip": result.location.zip_code,
            "latitude": result.location.latitude,
            "longitude": result.location.longitude,
            "location_source": result.location.source,
            "discovered_lead_count": len(result.leads),
            "merged_duplicate_count": result.merged_count,
        }
    )
    write_discovery_bundle(args.out, result, parameters, run_log)
    _log_result_summary(logger, result, result.leads)
    print(
        f"Wrote discovery bundle with {len(result.leads)} leads near ZIP {result.location.zip_code} "
        f"to {args.out}"
    )
    print(f"Discovery log: {log_file}")


def _validate_customers(args: argparse.Namespace) -> None:
    output_format = _resolve_output_format(args.out, args.format)
    log_file = args.log_file or args.out.with_suffix(".log")
    logger = _configure_logger(log_file)
    logger.info("Starting local customer validation for discovery bundle %s.", args.input_path)

    result, discovery_parameters, run_log = read_discovery_bundle(args.input_path)
    local_events: list[dict[str, object]] = []

    def log_event(progress: int, stage: str, message: str) -> None:
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "progress": progress,
            "stage": stage,
            "message": message,
            "current_lead": "",
        }
        local_events.append(event)
        logger.info("[%s%%] %s: %s", progress, stage, message)

    log_event(10, "load_discovery", f"Loaded {len(result.leads)} discovered leads.")
    log_event(35, "customer_snapshot", f"Matching against local customer snapshot at {args.snapshot}.")
    llm_match_state = {"used": 0}
    match_reviewer = None
    if args.use_llm_match:
        from marketing_lead.customer_match_llm import review_customer_match_with_ollama

        if ":cloud" in args.llm_match_model:
            logger.warning(
                "LLM customer match review is using cloud-backed Ollama model %s. "
                "Customer records may leave the local machine.",
                args.llm_match_model,
            )

        def match_reviewer(lead, customer, candidate_reason):
            if args.llm_match_limit and llm_match_state["used"] >= args.llm_match_limit:
                return None
            llm_match_state["used"] += 1
            try:
                review = review_customer_match_with_ollama(
                    lead,
                    customer,
                    candidate_reason=candidate_reason,
                    model=args.llm_match_model,
                    timeout_seconds=args.llm_match_timeout,
                )
            except Exception as exc:
                logger.warning(
                    "LLM match review failed for lead=%s customer_id=%s reason=%s error=%s",
                    lead.name,
                    customer.get("customer_id", ""),
                    candidate_reason,
                    exc,
                )
                return None
            if review:
                logger.info(
                    "LLM match review lead=%s customer_id=%s candidate=%s same=%s confidence=%s reason=%s",
                    lead.name,
                    customer.get("customer_id", ""),
                    candidate_reason,
                    review[0],
                    review[1],
                    review[2],
                )
            return review

    customer_count, customer_detail = apply_customer_matches(
        result.leads,
        snapshot_path=args.snapshot,
        match_reviewer=match_reviewer,
    )
    customer_status = "ok"
    if "not found" in customer_detail.lower():
        customer_status = "warning"

    source_reports = [
        report
        for report in result.source_reports
        if report.name != "customer_snapshot"
    ]
    source_reports.append(
        SourceReport(
            name="customer_snapshot",
            label="Internal Active Customer Snapshot",
            count=customer_count,
            status=customer_status,
            detail=customer_detail,
        )
    )

    log_event(65, "scoring", "Rescoring leads after active-customer validation.")
    scored = score_leads(result.leads)
    collected_count = len(scored)
    if args.min_score:
        scored = [lead for lead in scored if lead.confidence_score >= args.min_score]
        logger.info(
            "Applied min_score=%s filter: %s of %s leads remain.",
            args.min_score,
            len(scored),
            collected_count,
        )
    if args.limit:
        scored = scored[: args.limit]
        logger.info("Applied output limit=%s; exporting %s leads.", args.limit, len(scored))

    active_customers = active_customers_for_zip(
        result.zip_code,
        snapshot_path=args.snapshot,
        limit=args.customer_zip_limit,
    )
    branch_counts = Counter(str(row.get("branch") or "") for row in active_customers if row.get("branch"))
    log_event(
        85,
        "customer_zip_context",
        f"Loaded {len(active_customers)} active customers in ZIP {result.zip_code}.",
    )

    final_result = LeadSearchResult(
        zip_code=result.zip_code,
        radius_mi=result.radius_mi,
        location=result.location,
        source_reports=source_reports,
        leads=scored,
        merged_count=result.merged_count,
    )
    validation_parameters = {
        **{f"discovery_{key}": value for key, value in discovery_parameters.items()},
        "workflow_part": "local_customer_validation",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "discovery_input_path": str(args.input_path),
        "customer_snapshot_path": str(args.snapshot),
        "output_path": str(args.out),
        "output_format": output_format,
        "min_score": args.min_score,
        "limit": args.limit,
        "discovered_lead_count": collected_count,
        "matched_active_customer_count": customer_count,
        "new_lead_count": sum(1 for lead in scored if lead.lead_status != "existing_customer"),
        "existing_customer_count": sum(1 for lead in scored if lead.lead_status == "existing_customer"),
        "active_customers_in_zip": len(active_customers),
        "active_customer_branch_distribution": _format_counter(branch_counts),
        "llm_match_review_enabled": args.use_llm_match,
        "llm_match_model": args.llm_match_model if args.use_llm_match else "",
        "llm_match_reviews_used": llm_match_state["used"],
        "log_file": str(log_file),
    }

    log_event(100, "complete", f"Validation complete with {len(scored)} exported leads.")
    write_leads(
        scored,
        args.out,
        output_format,
        parameters=validation_parameters,
        source_reports=[report.__dict__ for report in source_reports],
        run_log=[*run_log, *local_events],
        extra_sheets=[
            ("Active Customers in ZIP", CUSTOMER_EXPORT_FIELDS, active_customers),
        ]
        if output_format == "xlsx"
        else None,
    )
    _log_result_summary(logger, final_result, scored)
    print(
        f"Wrote {len(scored)} validated leads to {args.out}; "
        f"{customer_count} matched active customers."
    )
    print(f"Validation log: {log_file}")


def _customers(args: argparse.Namespace) -> None:
    if args.customers_command == "refresh":
        count = refresh_customer_snapshot(
            output_path=args.out,
            server=args.server,
            database=args.database,
            driver=args.driver,
        )
        print(f"Wrote {count} customer records to {args.out}")
    else:
        raise SystemExit("Expected a customers subcommand, such as: marketing-lead customers refresh")


def _resolve_output_format(output_path: Path, requested: str) -> str:
    if requested != "auto":
        return requested
    suffix = output_path.suffix.lower().lstrip(".")
    if suffix in {"csv", "json", "xlsx"}:
        return suffix
    return "xlsx"


def _configure_logger(log_file: Path) -> logging.Logger:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("marketing_lead.collect")
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    logger.setLevel(logging.INFO)
    logger.propagate = False

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    logger.addHandler(console)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger


def _progress_event(update: dict[str, object], previous_progress: int) -> dict[str, object]:
    stage = str(update.get("stage") or "")
    percent = update.get("progress")
    if percent is None and stage == "llm":
        index = int(update.get("review_index") or 0)
        total = max(1, int(update.get("review_total") or 1))
        percent = 76 + int(18 * min(index, total) / total)
    progress = max(previous_progress, min(100, int(percent or previous_progress)))
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "progress": progress,
        "stage": stage,
        "message": str(update.get("message") or ""),
        "current_lead": str(update.get("current_lead") or ""),
    }


def _log_result_summary(
    logger: logging.Logger,
    result,
    exported_leads,
) -> None:
    summary = result.as_dict()["summary"]
    logger.info(
        "Result summary: exported=%s collected=%s merged_duplicates=%s high_score=%s review_first=%s existing_customers=%s",
        len(exported_leads),
        summary["lead_count"],
        result.merged_count,
        summary["high_score_count"],
        summary["review_first_count"],
        summary["existing_customer_count"],
    )
    for report in result.source_reports:
        logger.info(
            "Source %s status=%s count=%s detail=%s",
            report.name,
            report.status,
            report.count,
            report.detail,
        )
    for lead in exported_leads[:10]:
        logger.info(
            "Lead score=%s status=%s name=%s source=%s address=%s",
            lead.confidence_score,
            lead.lead_status,
            lead.name,
            lead.source,
            _lead_address(lead),
        )
    if len(exported_leads) > 10:
        logger.info("Lead log truncated after top 10 exported leads; workbook contains all %s.", len(exported_leads))


def _lead_address(lead) -> str:
    return ", ".join(part for part in [lead.address_1, lead.city, lead.state, lead.postcode] if part)


def _format_counter(counter: Counter[str]) -> str:
    return "; ".join(f"{key}:{value}" for key, value in counter.most_common())
