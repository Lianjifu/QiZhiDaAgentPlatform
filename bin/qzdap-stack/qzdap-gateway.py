#!/usr/bin/env python3
"""QZDAP gateway — HTTP pass-through proxy with path-prefix routing.

  * reads QZDAP_LISTEN_PORT / QZDAP_BACKEND_PORT / QZDAP_BACKEND_HOST from env
  * path-prefix routing: QZDAP_APP_PATH_PREFIXES (CSV) → QZDAP_APP_HOST:PORT;
    everything else → QZDAP_BACKEND_HOST:QZDAP_BACKEND_PORT
    (defaults point both at qzdap-app)
  * strips duplicate Content-Length / Transfer-Encoding / Connection headers
  * logs to stderr AND QZDAP_LOG_DIR/qzdap-gateway-{LISTEN_PORT}.log
"""
from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LISTEN_PORT = int(os.environ.get("QZDAP_LISTEN_PORT", "9200"))
BACKEND_PORT = int(os.environ.get("QZDAP_BACKEND_PORT", "8200"))
BACKEND_HOST = os.environ.get("QZDAP_BACKEND_HOST", "127.0.0.1")
APP_HOST = os.environ.get("QZDAP_APP_HOST", "127.0.0.1")
APP_PORT = int(os.environ.get("QZDAP_APP_PORT", "8200"))
APP_PATH_PREFIXES = [
    p.strip()
    for p in os.environ.get(
        "QZDAP_APP_PATH_PREFIXES",
        "/v1/identity,/api/admin,/api/catalog,/api/user/skills,/api/user/automations,/api/knowledge",
    ).split(",")
    if p.strip()
]
LOG_DIR = os.environ.get(
    "QZDAP_LOG_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs"),
)
LOG_FILE = os.path.join(LOG_DIR, f"qzdap-gateway-{LISTEN_PORT}.log")

SKIP = {"transfer-encoding", "connection", "content-length"}


def _route_for(path: str) -> tuple[str, int, str]:
    """Return (host, port, label) for the given request path.

    ``label`` is the human-readable backend name used in logs.
    """
    for prefix in APP_PATH_PREFIXES:
        if path == prefix or path.startswith(prefix + "/"):
            return APP_HOST, APP_PORT, "qzdap-app"
    return BACKEND_HOST, BACKEND_PORT, "qzdap-fallback"


class GatewayHandler(BaseHTTPRequestHandler):
    def _proxy(self, method: str) -> None:
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length) if length else b""
        upstream_host, upstream_port, label = _route_for(self.path)
        url = f"http://{upstream_host}:{upstream_port}{self.path}"
        req = urllib.request.Request(url, data=body if body else None, method=method)
        for k, v in self.headers.items():
            if k.lower() in ("host", "content-length"):
                continue
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = resp.read()
                self.send_response(resp.status)
                for k, v in resp.headers.items():
                    if k.lower() in SKIP:
                        continue
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
        except urllib.error.HTTPError as e:
            payload = e.read() if hasattr(e, "read") else b""
            self.send_response(e.code)
            for k, v in (e.headers or {}).items():
                if k.lower() in SKIP:
                    continue
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except Exception as e:  # noqa: BLE001
            msg = f"qzdap-gateway error ({label}): {e}".encode()
            self.send_response(502)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)

    def do_GET(self): self._proxy("GET")
    def do_POST(self): self._proxy("POST")
    def do_PUT(self): self._proxy("PUT")
    def do_PATCH(self): self._proxy("PATCH")
    def do_DELETE(self): self._proxy("DELETE")
    def do_OPTIONS(self): self._proxy("OPTIONS")

    def log_message(self, fmt, *args):  # noqa: ANN001
        upstream_host, upstream_port, label = _route_for(self.path)
        line = (
            f"[qzdap-gw :{LISTEN_PORT}→{label}:{upstream_port}] "
            f"{self.command} {self.path} — {fmt % args}\n"
        )
        sys.stderr.write(line)
        try:
            os.makedirs(LOG_DIR, exist_ok=True)
            with open(LOG_FILE, "a") as f:
                f.write(line)
        except Exception:
            pass


if __name__ == "__main__":
    print(
        f"qzdap-gateway :{LISTEN_PORT} "
        f"→ qzdap-app {APP_HOST}:{APP_PORT} "
        f"({','.join(APP_PATH_PREFIXES)}), "
        f"fallback {BACKEND_HOST}:{BACKEND_PORT} (else)",
        flush=True,
    )
    ThreadingHTTPServer(("127.0.0.1", LISTEN_PORT), GatewayHandler).serve_forever()