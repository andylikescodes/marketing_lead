from __future__ import annotations

import csv
import io
import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from marketing_lead.export import CSV_FIELDS
from marketing_lead.pipeline import LeadSearchResult, search_leads

STATIC_DIR = Path(__file__).resolve().parent / "static"
MAX_RADIUS_MI = 50.0
MAX_LIMIT = 2000


@dataclass
class SearchJob:
    id: str
    params: dict[str, list[str]]
    status: str = "queued"
    progress: int = 0
    stage: str = "queued"
    message: str = "Queued."
    current_lead: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    result: LeadSearchResult | None = None
    error: str = ""

    def as_dict(self, include_result: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "id": self.id,
            "status": self.status,
            "progress": self.progress,
            "stage": self.stage,
            "message": self.message,
            "current_lead": self.current_lead,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error": self.error,
        }
        if include_result and self.result:
            payload["result"] = self.result.as_dict()
        return payload


JOBS: dict[str, SearchJob] = {}
JOBS_LOCK = threading.Lock()


def run_server(host: str = "127.0.0.1", port: int = 8787) -> None:
    server = ThreadingHTTPServer((host, port), LeadAppHandler)
    print(f"Lead app running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping lead app.")
    finally:
        server.server_close()


class LeadAppHandler(BaseHTTPRequestHandler):
    server_version = "MarketingLeadHTTP/0.2"

    def do_HEAD(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            path = STATIC_DIR / "index.html"
            if path.exists():
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(path.stat().st_size))
                self.end_headers()
                return
        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/search-jobs":
            self._handle_create_job(parsed.query)
            return
        self._send_json({"error": "not found"}, status=404)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            self._send_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/api/search":
            self._handle_search(parsed.query)
            return
        if parsed.path == "/api/export.csv":
            self._handle_export(parsed.query)
            return
        if parsed.path.startswith("/api/search-jobs/"):
            self._handle_job_get(parsed.path)
            return
        self._send_json({"error": "not found"}, status=404)

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")

    def _handle_create_job(self, query: str) -> None:
        try:
            params = _request_params(self, query)
            _validate_params(params)
            job = _create_job(params)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=400)
            return
        self._send_json(job.as_dict(include_result=False), status=202)

    def _handle_job_get(self, path: str) -> None:
        parts = path.strip("/").split("/")
        if len(parts) not in {3, 4} or parts[:2] != ["api", "search-jobs"]:
            self._send_json({"error": "not found"}, status=404)
            return

        job_id = parts[2]
        with JOBS_LOCK:
            job = JOBS.get(job_id)
        if not job:
            self._send_json({"error": "job not found"}, status=404)
            return

        if len(parts) == 4:
            if parts[3] != "export.csv":
                self._send_json({"error": "not found"}, status=404)
                return
            self._send_job_export(job)
            return

        self._send_json(job.as_dict())

    def _handle_search(self, query: str) -> None:
        try:
            result = _run_query(query)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=400)
            return
        self._send_json(result.as_dict())

    def _handle_export(self, query: str) -> None:
        try:
            result = _run_query(query)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=400)
            return
        self._send_csv(result)

    def _send_job_export(self, job: SearchJob) -> None:
        if job.status != "completed" or not job.result:
            self._send_json({"error": "job is not completed yet"}, status=409)
            return
        self._send_csv(job.result)

    def _send_csv(self, result: LeadSearchResult) -> None:
        payload = _result_to_csv(result).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="leads_{result.zip_code}.csv"')
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_json(self, payload: dict[str, object], status: int = 200) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self._send_json({"error": "file not found"}, status=404)
            return
        payload = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _create_job(params: dict[str, list[str]]) -> SearchJob:
    job = SearchJob(id=uuid.uuid4().hex, params=params)
    with JOBS_LOCK:
        JOBS[job.id] = job
    thread = threading.Thread(target=_run_job, args=(job.id,), daemon=True)
    thread.start()
    return job


def _run_job(job_id: str) -> None:
    with JOBS_LOCK:
        job = JOBS[job_id]
        job.status = "running"
        job.progress = 1
        job.message = "Starting search."
        job.updated_at = time.time()

    def progress(update: dict[str, object]) -> None:
        with JOBS_LOCK:
            active = JOBS[job_id]
            percent = update.get("progress")
            if percent is None and update.get("stage") == "llm":
                index = int(update.get("review_index") or 0)
                total = max(1, int(update.get("review_total") or 1))
                percent = 76 + int(18 * min(index, total) / total)
            active.progress = max(active.progress, min(99, int(percent or active.progress)))
            active.stage = str(update.get("stage") or active.stage)
            active.message = str(update.get("message") or active.message)
            active.current_lead = str(update.get("current_lead") or "")
            active.updated_at = time.time()

    try:
        result = _run_query_params(job.params, progress_callback=progress)
    except Exception as exc:
        with JOBS_LOCK:
            job = JOBS[job_id]
            job.status = "failed"
            job.error = str(exc)
            job.message = str(exc)
            job.updated_at = time.time()
        return

    with JOBS_LOCK:
        job = JOBS[job_id]
        job.status = "completed"
        job.progress = 100
        job.stage = "complete"
        job.message = f"Search complete with {len(result.leads)} leads."
        job.current_lead = ""
        job.result = result
        job.updated_at = time.time()


def _run_query(query: str) -> LeadSearchResult:
    return _run_query_params(parse_qs(query))


def _run_query_params(
    params: dict[str, list[str]],
    progress_callback=None,
) -> LeadSearchResult:
    _validate_params(params)
    zip_code = _param(params, "zip", required=True)
    radius_mi = float(_param(params, "radius_mi", default="1.0"))
    limit = int(_param(params, "limit", default="100"))
    include_abc = _bool_param(params, "include_abc", default=True)
    include_llm = _bool_param(params, "include_llm", default=False)
    llm_model = _param(params, "llm_model", default="kimi-k2.6:cloud")
    llm_limit = int(_param(params, "llm_limit", default="0"))

    return search_leads(
        zip_code=zip_code,
        radius_mi=radius_mi,
        include_abc=include_abc,
        include_llm=include_llm,
        llm_model=llm_model,
        llm_limit=llm_limit,
        limit=limit,
        progress_callback=progress_callback,
    )


def _validate_params(params: dict[str, list[str]]) -> None:
    radius_mi = float(_param(params, "radius_mi", default="1.0"))
    limit = int(_param(params, "limit", default="100"))
    llm_limit = int(_param(params, "llm_limit", default="0"))
    if radius_mi <= 0 or radius_mi > MAX_RADIUS_MI:
        raise ValueError(f"Radius must be between 0 and {int(MAX_RADIUS_MI)} miles.")
    if limit < 0 or limit > MAX_LIMIT:
        raise ValueError(f"Limit must be between 0 and {MAX_LIMIT}.")
    if llm_limit < 0 or llm_limit > MAX_LIMIT:
        raise ValueError(f"LLM limit must be between 0 and {MAX_LIMIT}; 0 means all returned leads.")


def _request_params(handler: BaseHTTPRequestHandler, query: str) -> dict[str, list[str]]:
    params = parse_qs(query)
    length = int(handler.headers.get("Content-Length") or 0)
    if length <= 0:
        return params
    raw_body = handler.rfile.read(length).decode("utf-8")
    content_type = handler.headers.get("Content-Type", "")
    if "application/json" in content_type:
        body = json.loads(raw_body or "{}")
        for key, value in body.items():
            params[key] = [str(value)]
    else:
        for key, value in parse_qs(raw_body).items():
            params[key] = value
    return params


def _param(params: dict[str, list[str]], name: str, default: str = "", required: bool = False) -> str:
    value = params.get(name, [default])[0].strip()
    if required and not value:
        raise ValueError(f"Missing required parameter: {name}")
    return value


def _bool_param(params: dict[str, list[str]], name: str, default: bool = False) -> bool:
    if name not in params:
        return default
    return params[name][0].lower() in {"1", "true", "yes", "on"}


def _result_to_csv(result: LeadSearchResult) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS)
    writer.writeheader()
    for lead in result.leads:
        writer.writerow(lead.as_dict())
    return buffer.getvalue()
