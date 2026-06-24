from __future__ import annotations

import json
import sys
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

DEMO_DIR = Path(__file__).resolve().parent
REPO_ROOT = DEMO_DIR.parents[2]
SRC_DIR = REPO_ROOT / "src"
PUBLIC_DIR = DEMO_DIR / "public"
OUTPUT_DIR = DEMO_DIR / "output"
DEFAULT_URL = "https://vinfastauto.com/vn_vi/ve-chung-toi"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(DEMO_DIR) not in sys.path:
    sys.path.insert(0, str(DEMO_DIR))

from run_review import run_single_url_review  # noqa: E402


class UrlArtifactReviewHandler(SimpleHTTPRequestHandler):
    def __init__(self, request: Any, client_address: Any, server: Any) -> None:
        super().__init__(request, client_address, server, directory=str(PUBLIC_DIR))

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def do_GET(self) -> None:
        if self.path == "/api/health":
            self._send_json(
                {
                    "ok": True,
                    "server": "python",
                    "mode": "single_url_artifact_review",
                    "default_url": DEFAULT_URL,
                }
            )
            return
        super().do_GET()

    def do_POST(self) -> None:
        if self.path == "/api/discover":
            self._send_json(
                {"error": "Discovery was removed. This demo reviews exactly one URL per run."},
                status=HTTPStatus.GONE,
            )
            return
        if self.path != "/api/review":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        try:
            payload = self._read_json()
            url = str(payload.get("url") or "").strip()
            if not url:
                self._send_json({"error": "url is required"}, status=HTTPStatus.BAD_REQUEST)
                return

            response_payload = run_single_url_review(
                url,
                output_dir=OUTPUT_DIR,
                use_browser_extractor=not bool(payload.get("no_browser")),
                include_interactions=bool(payload.get("include_interactions")),
            )
            response_payload["server"] = "python"
            self._send_json(response_payload)
        except Exception as exc:
            self._send_json(
                {"error": f"{type(exc).__name__}: {exc}"},
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            return {}
        raw_body = self.rfile.read(length).decode("utf-8")
        value = json.loads(raw_body)
        return value if isinstance(value, dict) else {}

    def _send_json(self, payload: dict[str, object], *, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", 8782), UrlArtifactReviewHandler)
    print("URL artifact review app: http://127.0.0.1:8782")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down URL artifact review server...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
