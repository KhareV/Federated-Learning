"""The accessibility report generator turns audit JSON into stable markdown (no hand-typed numbers)."""

from __future__ import annotations

import json
from pathlib import Path

from scripts import ui_a11y_report


def _entry(route: str, viewport: str, *, outside: int = 0, skips: int = 0, unnamed_tables: int = 0, status: int = 200) -> dict:
    return {
        "route": route, "viewport": viewport, "httpStatus": status,
        "focus": {"stops": 10, "outside": [{}] * outside, "underSticky": [], "hidden": [], "noRing": 0},
        "semantics": {"headingSkips": [{}] * skips, "tablesNoCaption": unnamed_tables, "thNoScope": 0, "controlsNoLabel": [], "unnamedInteractive": [], "svgNoName": [],
                      "duplicateIds": 0, "h1": 1, "chartsWithPoints": 0, "chartTabStopsTotal": 0, "chartPointsFocusable": 0, "chartTabStopsMax": 0},
        "console": ["warning: Clerk: Clerk has been loaded with development keys."], "failedRequests": [], "networkErrors": [], "externalHosts": ["clerk.example"],
    }


def test_report_counts_before_and_after_and_excludes_the_clerk_notice(tmp_path: Path, capsys, monkeypatch) -> None:
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    before.write_text(json.dumps({"report": [_entry("/app", "phone", outside=11), _entry("/app", "desktop", skips=2, unnamed_tables=3)]}))
    after.write_text(json.dumps({"report": [_entry("/app", "phone"), _entry("/app", "desktop")]}))
    out = tmp_path / "out.md"
    monkeypatch.setattr("sys.argv", ["ui_a11y_report", "--before", str(before), "--after", str(after), "--out", str(out)])
    assert ui_a11y_report.main() == 0
    text = out.read_text()
    assert "| phone | 1 → 1 | 11 → 0 |" in text
    assert "| heading level skips | 2 | 0 |" in text and "| tables without a name | 3 | 0 |" in text
    assert "| console errors/warnings | 0 | 0 |" in text          # the Clerk development-keys notice is excluded by design
    assert "`clerk.example`" in text


def test_device_lifecycle_table_in_the_frontend_matches_the_frozen_contract():
    """The Device page disables any button the frozen device lifecycle forbids (STOPPED -> SCANNING was reachable before)."""
    import json
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    contract = json.loads((root / "contracts/capstone/device_source_v1.json").read_text())["device_transitions"]
    source = (root / "frontend/src/lib/product/device-lifecycle.ts").read_text()
    block = source.split("DEVICE_TRANSITIONS", 1)[1].split("};", 1)[0]
    parsed = {m.group(1): re.findall(r"'([A-Z]+)'", m.group(2)) for m in re.finditer(r"(\w+):\s*\[([^\]]*)\]", block)}
    assert parsed == {state: list(edges) for state, edges in contract.items()}
