"""Render before/after accessibility-audit measurements as markdown (no hand-typed numbers).

usage: python -m scripts.ui_a11y_report --before <a11y.json> --after <a11y.json> --out docs/ui/A11Y_MEASUREMENTS.md
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

CLERK = "development keys"


def load(path: str) -> list[dict]:
    return [e for e in json.loads(Path(path).read_text())["report"] if "error" not in e]


def focus_totals(rows: list[dict]) -> dict[str, int]:
    return {
        "routes": len(rows),
        "outside": sum(len(e["focus"]["outside"]) for e in rows),
        "under_sticky": sum(len(e["focus"]["underSticky"]) for e in rows),
        "hidden": sum(len(e["focus"]["hidden"]) for e in rows),
        "no_ring": sum(e["focus"]["noRing"] for e in rows),
        "stops_max": max((e["focus"]["stops"] for e in rows), default=0),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", required=True)
    parser.add_argument("--after", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    before, after = load(args.before), load(args.after)
    lines = ["# Accessibility audit measurements (generated)", "",
             f"- before: `{args.before}` (settled-scroll measurement of the tree at `21a5fad` plus only the direct-route fix)",
             f"- after: `{args.after}`", "- note: the Tab-press limit was 90 for the baseline and 160 for the after run, so the last column compares caps, not behaviour; the baseline hit its cap on the dense pages", "- method: real Chrome + Clerk test user, hardware source disabled, no data seeded; Tab pressed up to the stated limit per route, scroll allowed to settle before each measurement", "",
             "## Keyboard journey (all routes)", "",
             "| viewport | routes before → after | stops outside the viewport | obscured by sticky header | in a closed/hidden container | without a focus indicator | largest tab-stop count |", "|---|---|---|---|---|---|---|"]
    for vp in sorted({e["viewport"] for e in after}):
        b = focus_totals([e for e in before if e["viewport"] == vp])
        a = focus_totals([e for e in after if e["viewport"] == vp])
        lines.append(f"| {vp} | {b['routes']} → {a['routes']} | {b['outside']} → {a['outside']} | {b['under_sticky']} → {a['under_sticky']} | {b['hidden']} → {a['hidden']} | {b['no_ring']} → {a['no_ring']} | {b['stops_max']} → {a['stops_max']} |")

    def sem(rows: list[dict]) -> dict[str, int]:
        d = [e for e in rows if e["viewport"] == "desktop"]
        return {
            "routes": len(d),
            "heading_skips": sum(len(e["semantics"]["headingSkips"]) for e in d),
            "tables_unnamed": sum(e["semantics"]["tablesNoCaption"] for e in d),
            "th_no_scope": sum(e["semantics"]["thNoScope"] for e in d),
            "controls_unlabelled": sum(len(e["semantics"]["controlsNoLabel"]) for e in d),
            "unnamed_interactive": sum(len(e["semantics"]["unnamedInteractive"]) for e in d),
            "charts_unnamed": sum(len(e["semantics"]["svgNoName"]) for e in d),
            "duplicate_ids": sum(e["semantics"]["duplicateIds"] for e in d),
            "routes_not_one_h1": sum(1 for e in d if e["semantics"]["h1"] != 1),
            "not_200_direct": sum(1 for e in d if e.get("httpStatus") != 200),
        }

    sb, sa = sem(before), sem(after)
    lines += ["", "## Semantics (desktop, all routes)", "", "| check | before | after |", "|---|---|---|"]
    names = {"heading_skips": "heading level skips", "tables_unnamed": "tables without a name", "th_no_scope": "table headers without scope", "controls_unlabelled": "unlabelled form controls",
             "unnamed_interactive": "interactive elements without a name", "charts_unnamed": "charts without an accessible name", "duplicate_ids": "duplicate ids", "routes_not_one_h1": "routes without exactly one h1",
             "not_200_direct": "routes whose direct HTTP load is not 200"}
    for key, label in names.items():
        lines.append(f"| {label} | {sb[key]} | {sa[key]} |")

    def net(rows: list[dict]) -> tuple[int, int, int]:
        d = [e for e in rows if e["viewport"] == "desktop"]
        console = sum(1 for e in d for m in e["console"] if CLERK not in m)
        failed = sum(len(e["failedRequests"]) for e in d)
        return console, failed, sum(len(e["networkErrors"]) for e in d)

    nb, na = net(before), net(after)
    lines += ["", "## Console and network (desktop, excluding the Clerk development-keys notice)", "", "| | before | after |", "|---|---|---|",
              f"| console errors/warnings | {nb[0]} | {na[0]} |", f"| failed requests (HTTP ≥ 400) | {nb[1]} | {na[1]} |", f"| transport failures | {nb[2]} | {na[2]} |"]
    remaining = sorted({(e["route"], m.split(" [")[0][:110]) for e in after if e["viewport"] == "desktop" for m in e["console"] if CLERK not in m})
    if remaining:
        lines += ["", "Remaining (explained in the audit): " + "; ".join(f"`{r}` — {m}" for r, m in remaining)]
    hosts = sorted({h for e in after for h in e.get("externalHosts", [])})
    lines += ["", f"External hosts contacted: {', '.join(f'`{h}`' for h in hosts) or 'none'}", ""]
    d_after = [e for e in after if e["viewport"] == "desktop" and "chartTabStopsMax" in e["semantics"]]
    charts = [(e["route"], e["semantics"]["chartsWithPoints"], e["semantics"]["chartTabStopsTotal"], e["semantics"]["chartPointsFocusable"]) for e in d_after if e["semantics"]["chartsWithPoints"]]
    if charts:
        lines += ["## Charts: tab stops (after)", "", "| route | charts with points | chart tab stops | focusable points (arrow keys) |", "|---|---|---|---|"]
        lines += [f"| `{r}` | {c} | {t} | {p} |" for r, c, t, p in charts]
    Path(args.out).write_text("\n".join(lines) + "\n")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
