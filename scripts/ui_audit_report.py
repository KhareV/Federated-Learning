"""Render before/after UI tour measurements as markdown (reproducible, no hand-typed numbers).

usage: python -m scripts.ui_audit_report --before <tour.json.tour.json> --after <tour.json.tour.json> --out docs/ui/UI_AUDIT_MEASUREMENTS.md
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load(path: Path) -> dict[tuple[str, str], dict]:
    report = json.loads(path.read_text())["report"]
    def key(route: str) -> str:
        base, _, query = route.partition("?")
        if query.startswith("run="):
            run = query[4:]
            kind = "hardware (HDFLRUN)" if run.startswith("HDFLRUN-") else "synthetic live (FL10RUN)" if run.startswith("FL10RUN-") else "recorded evidence" if run.startswith("recorded-") else "other"
            return f"{base} ?run={kind}"
        if base.startswith("/app/history/"):
            return "/app/history/<session>"
        return base

    return {(key(e["route"]), e["viewport"]): e for e in report if "error" not in e}


def cell(e: dict | None, key: str) -> str:
    return "–" if e is None or key not in e else str(e[key])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", required=True)
    parser.add_argument("--after", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--before-label", default=None, help="human label for the before run (default: its path)")
    args = parser.parse_args()
    before, after = load(Path(args.before)), load(Path(args.after))
    routes = sorted({r for r, _ in after})
    lines = ["# UI tour measurements (generated)", "",
             f"- before: {args.before_label or '`' + args.before + '`'}",
             f"- after: `{args.after}`",
             "- routes are measured at desktop (1440 px); `–` = not measured in that run.", "",
             "| route | words before → after | small-text elements (<10.5 px) | long paragraphs (≥45 words) | heading skips | HTTP | keyboard stops without focus ring |",
             "|---|---|---|---|---|---|---|"]
    for route in routes:
        a, b = after.get((route, "desktop")), before.get((route, "desktop"))
        if a is None:
            continue
        kb = a.get("keyboard") or {}
        lines.append(f"| `{route}` | {cell(b, 'words')} → {a['words']} | {cell(b, 'tinyTextElements')} → {a['tinyTextElements']} | {len((b or {}).get('longParagraphs', [])) if b else '–'} → {len(a['longParagraphs'])} | "
                     f"{cell(b, 'headingSkips')} → {a['headingSkips']} | {a.get('httpStatus', '–')} | {kb.get('noRing', '–')}/{kb.get('stops', '–')} |")
    viewports = sorted({v for _, v in after})
    lines += ["", "## Layout health by viewport (after)", "", "| viewport | routes | horizontal overflow | console errors | failed requests |", "|---|---|---|---|---|"]
    for vp in viewports:
        rows = [e for (r, v), e in after.items() if v == vp]
        lines.append(f"| {vp} | {len(rows)} | {sum(1 for e in rows if e.get('horizontalOverflow'))} | {sum(1 for e in rows if e.get('consoleErrors'))} | {sum(len(e.get('failedRequests', [])) for e in rows)} |")
    hosts = sorted({h for e in after.values() for h in e.get("externalHosts", [])})
    lines += ["", f"External hosts contacted: {', '.join(f'`{h}`' for h in hosts) or 'none'}"]
    Path(args.out).write_text("\n".join(lines) + "\n")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
