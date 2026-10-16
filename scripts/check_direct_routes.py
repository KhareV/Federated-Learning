"""Real HTTP check of direct loads against the production build served by `vite preview` (the launcher's frontend server).

Dynamic routes must answer 200 with the SPA shell; static routes 200; paths that are not routes keep answering 404.
  python -m scripts.check_direct_routes [--out reports/ui/direct_routes.json]
Requires a built frontend (`npm run build` in frontend/). Needs no backend, no Clerk and no data.
"""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"

EXPECTED: list[tuple[str, int, str]] = [
    ("/app", 200, "static route"),
    ("/app/history", 200, "static route"),
    ("/app/history/HW-0123456789abcdef", 200, "dynamic route: direct load / reload"),
    ("/app/history/SESSION-1", 200, "dynamic route: direct load / reload"),
    ("/app/observatory/federation", 200, "static route"),
    ("/app/observatory/federation/SIM_FL_SITE_00", 200, "dynamic route: direct load / reload"),
    ("/app/federation/live", 200, "static route"),
    ("/app/federation/live?run=HDFLRUN-ABC", 200, "static route with a query"),
    ("/app/nonexistent-page", 404, "not a route: stays 404"),
    ("/nonexistent-root", 404, "not a route: stays 404"),
]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def status(url: str) -> tuple[int, int, str]:
    request = urllib.request.Request(url, headers={"Accept": "text/html"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = response.read()
            return response.status, len(body), response.headers.get("content-type", "")
    except urllib.error.HTTPError as error:
        body = error.read()
        return error.code, len(body), error.headers.get("content-type", "")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    if not (FRONTEND / ".svelte-kit/output/server").is_dir():
        print("frontend is not built (run `npm run build` in frontend/)")
        return 2
    port = free_port()
    server = subprocess.Popen(["npx", "vite", "preview", "--port", str(port), "--strictPort", "--host", "127.0.0.1"], cwd=FRONTEND, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                status(f"http://127.0.0.1:{port}/app")
                break
            except OSError:
                time.sleep(0.5)
        rows = []
        for path, expected, why in EXPECTED:
            code, size, content_type = status(f"http://127.0.0.1:{port}{path}")
            rows.append({"path": path, "expected": expected, "status": code, "ok": code == expected, "bytes": size, "content_type": content_type, "why": why})
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
    verdict = {"status": "PASS" if all(r["ok"] for r in rows) else "FAIL", "server": "vite preview (production build)", "rows": rows}
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(verdict, indent=2) + "\n")
    for r in rows:
        print(f"{'ok  ' if r['ok'] else 'FAIL'} {r['status']} (expected {r['expected']}) {r['path']}")
    print(verdict["status"])
    return 0 if verdict["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
