# ruff: noqa: E501
"""Shared CAP-010 test helpers: tiny real HTTP servers/processes stand in for services ONLY in orchestrator unit tests."""

from __future__ import annotations

import json
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import httpx

from scripts.run_capstone_faculty_demo import ServiceSpec

ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def http_service(name: str, port: int, log: Path, *, delay_s: float = 0.0, extra: str = "") -> ServiceSpec:
    """A real child process serving 200 on `/` after `delay_s`; `extra` is appended to its code."""
    code = (f"import socket,time,sys\ntime.sleep({delay_s})\n{extra}\n"
            "s=socket.socket(); s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)\n"
            f"s.bind(('127.0.0.1',{port})); s.listen(16)\n"
            "while True:\n    c,_=s.accept(); c.recv(2000); c.sendall(b'HTTP/1.0 200 OK\\r\\nContent-Length: 2\\r\\n\\r\\nok'); c.close()\n")

    def ready() -> tuple[bool, str]:
        try:
            return httpx.get(f"http://127.0.0.1:{port}/", timeout=1).status_code == 200, "ok"
        except httpx.HTTPError:
            return False, "not ready"

    return ServiceSpec(name, [sys.executable, "-c", code], {}, ROOT, log, ready, port)


class FakeProduct:
    """Records every request; serves the read endpoints the prewarm uses."""

    def __init__(self, runs: int = 0, candidates: int = 0) -> None:
        self.requests: list[tuple[str, str]] = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def _send(self, body):
                data = json.dumps(body).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                outer.requests.append(("GET", self.path))
                if self.path.endswith("/federation/clients"):
                    time.sleep(0.2)
                    return self._send([{"client_id": f"SIM_FL_SITE_0{i}"} for i in range(8)])
                if self.path.endswith("/federation/runs"):
                    return self._send([{}] * runs)
                if self.path.endswith("/federation"):
                    return self._send({"candidate_count": candidates, "active_live_run": False})
                if self.path.endswith("/models"):
                    return self._send({"capstone_fl_candidates": [{}] * candidates, "released_default_model_id": "MODEL_V2_FINAL"})
                self._send({})

            def do_POST(self):
                outer.requests.append(("POST", self.path))
                self._send({})

            def log_message(self, *a):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), H)
        self.port = self.server.server_port
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
