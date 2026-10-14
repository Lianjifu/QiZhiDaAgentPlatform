"""
QZDAP dev mock sandbox — implements the /internal/jobs endpoint that
HttpSandboxRuntimeClient posts to (sandbox_runtime_url = 127.0.0.1:9158).

Writes the requested files to a temp dir, runs `python main.py` (or `sh entry.sh`)
in a subprocess with the provided stdin/timeout/network/memory constraints, and
returns the canonical response shape.

Run with:
    python3 qzdap-mock-sandbox.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from http.server import BaseHTTPRequestHandler, HTTPServer


def run_job(payload: dict) -> dict:
    kind = payload.get("kind", "skill")
    command = payload.get("command") or ["python", "/work/main.py"]
    files = payload.get("files") or {}
    stdin = payload.get("stdin") or ""
    timeout_ms = int(payload.get("timeout_ms") or 30_000)
    limits = payload.get("limits") or {}
    memory_mb = int(limits.get("memory_mb") or 256)
    network = limits.get("network") or "none"
    image = payload.get("image") or "qzdap/sandbox-python:latest"

    if network != "none":
        # Mock 不会真出网,只标注状态
        pass

    workdir = tempfile.mkdtemp(prefix="qzdap-sandbox-")
    try:
        for path, content in files.items():
            full = os.path.join(workdir, path.lstrip("/"))
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as f:
                f.write(content)

        # command = ["python", "/work/main.py"] → 转成本地路径;
        # 第一项是解释器(可能是 "python" / "python3"),替换为当前 sys.executable
        resolved_command = []
        for i, c in enumerate(command):
            if i == 0 and c in {"python", "python3", "python3.9", "python3.10", "python3.11", "python3.12", "python3.13"}:
                resolved_command.append(sys.executable)
            elif c.startswith("/work/"):
                resolved_command.append(os.path.join(workdir, c[len("/work/"):]))
            else:
                resolved_command.append(c)

        # 资源限制(尽力而为;mock 不强求)
        try:
            import resource
            rss_limit = memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (rss_limit * 4, rss_limit * 4))
        except Exception:
            pass

        started = time.monotonic()
        try:
            proc = subprocess.run(
                resolved_command,
                cwd=workdir,
                input=stdin if stdin else None,
                capture_output=True,
                text=True,
                timeout=timeout_ms / 1000,
                env={**os.environ, "QZDAP_SANDBOX_KIND": kind},
            )
            latency = int((time.monotonic() - started) * 1000)
            return {
                "status": "succeeded" if proc.returncode == 0 else "failed",
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "latency_ms": latency,
            }
        except subprocess.TimeoutExpired:
            latency = int((time.monotonic() - started) * 1000)
            return {
                "status": "timeout",
                "exit_code": None,
                "stdout": "",
                "stderr": f"timeout after {timeout_ms}ms",
                "latency_ms": latency,
            }
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


class SandboxHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/internal/jobs":
            self.send_error(404, "not found")
            return
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            self.send_error(401, "missing bearer token")
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self.send_error(400, "invalid json")
            return
        result = run_job(payload)
        body = json.dumps(result, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") in ("", "/health", "/healthz"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok","runtime":"qzdap-mock-sandbox"}')
            return
        self.send_error(404, "not found")

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        pass  # quiet


def main() -> None:
    host = os.environ.get("QZDAP_MOCK_SANDBOX_HOST", "127.0.0.1")
    port = int(os.environ.get("QZDAP_MOCK_SANDBOX_PORT", "9158"))
    server = HTTPServer((host, port), SandboxHandler)
    print(f"[qzdap-mock-sandbox] listening on {host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
