from __future__ import annotations

import csv
import io
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from marketing_lead.export import CSV_FIELDS
from marketing_lead.pipeline import search_leads

STATIC_DIR = Path(__file__).resolve().parent / "static"


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
    server_version = "MarketingLeadHTTP/0.1"

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
        self._send_json({"error": "not found"}, status=404)

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")

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

        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for lead in result.leads:
            writer.writerow(lead.as_dict())

        payload = buffer.getvalue().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="leads_{result.zip_code}.csv"')
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


def _run_query(query: str):
    params = parse_qs(query)
    zip_code = _param(params, "zip", required=True)
    radius_mi = float(_param(params, "radius_mi", default="1.0"))
    limit = int(_param(params, "limit", default="100"))
    include_abc = _bool_param(params, "include_abc", default=True)
    include_llm = _bool_param(params, "include_llm", default=False)
    llm_model = _param(params, "llm_model", default="kimi-k2.6:cloud")
    llm_limit = int(_param(params, "llm_limit", default="15"))

    if radius_mi <= 0 or radius_mi > 15:
        raise ValueError("Radius must be between 0 and 15 miles.")
    if limit < 0 or limit > 500:
        raise ValueError("Limit must be between 0 and 500.")

    return search_leads(
        zip_code=zip_code,
        radius_mi=radius_mi,
        include_abc=include_abc,
        include_llm=include_llm,
        llm_model=llm_model,
        llm_limit=llm_limit,
        limit=limit,
    )


def _param(params: dict[str, list[str]], name: str, default: str = "", required: bool = False) -> str:
    value = params.get(name, [default])[0].strip()
    if required and not value:
        raise ValueError(f"Missing required parameter: {name}")
    return value


def _bool_param(params: dict[str, list[str]], name: str, default: bool = False) -> bool:
    if name not in params:
        return default
    return params[name][0].lower() in {"1", "true", "yes", "on"}
