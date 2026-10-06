# ruff: noqa: E501
"""Pure analysis of the FER-002 real-browser audit observations (landing + product pages). Re-derived by the frozen FERG1 evaluator; recorded verdicts are never trusted."""

from __future__ import annotations

import re
from typing import Any

F201_WORDING = re.compile(r"99\.8|LIVE EDGE|real-time feature|SYNAPSE|Normal \d+ BPM|Hours Unmonitored|0\.52 R|54\.2 ms|0\.96 \(Nominal\)|reports/\S+\.json", re.I)
WIDTHS = ("1440", "1024", "768", "390")


def analyze_landing(obs: dict[str, Any]) -> dict[str, bool]:
    r = next(x for x in obs["routes"] if x["route"] == "/")
    w = r["widths"]
    kb = r["keyboard"]
    rm = r["reducedMotion"]
    return {
        "all_widths_audited": sorted(w) == sorted(WIDTHS), "zero_console_errors": all(w[k]["errors"] == 0 for k in w) and r["consoleErrors"] == [], "zero_failed_assets": all(w[k]["failed"] == [] and w[k]["bad"] == [] for k in w),
        "zero_overflow": not any(w[k]["overflow"] for k in w), "one_main": r["main"] == 1, "one_h1": sum(1 for h in r["headings"] if h.startswith("H1:")) == 1, "no_f201_wording": not F201_WORDING.search(r["textSample"]),
        "skip_link_present": r["skipLinkPresent"] is True, "skip_link_first_focus_visible": bool(kb["firstFocus"]) and kb["firstFocus"]["visible"] is True and re.search(r"skip to (main )?content", kb["firstFocus"]["text"], re.I) is not None,
        "skip_link_moves_focus_to_main": bool(kb["afterActivate"]) and kb["afterActivate"]["isMain"] is True,
        "nav_labelled": bool(r["navs"]) and all(n for n in r["navs"]),
        "reduced_motion_no_raf_loops": rm["rafDelta3s"] <= 2, "reduced_motion_no_running_animations": rm["runningAnimations"] == 0, "reduced_motion_text_retained": rm["textLen"] > 2000, "reduced_motion_no_blank_canvases": rm["blankCanvases"] == 0,
        "touch_targets_390_none_under_24": w["390"]["under24"] == [], "images_have_alt": r["imgNoAlt"] == 0,
    }


def analyze_product(obs: dict[str, Any]) -> dict[str, bool]:
    rs = obs["routes"]
    return {
        "every_page_audited": len(rs) >= 14, "zero_console_errors": all(all(v["errors"] == 0 for v in r["widths"].values()) for r in rs), "zero_overflow": not any(v["overflow"] for r in rs for v in r["widths"].values()),
        "one_main_each": all(r["main"] == 1 for r in rs), "one_h1_each": all(sum(1 for h in r["headings"] if h.startswith("H1:")) == 1 for r in rs),
        "touch_targets_390_none_under_24": all(r["widths"]["390"]["under24"] == [] for r in rs), "skip_link_each_product_page": all(r["skipLinkPresent"] for r in rs if r["route"].startswith("/app")),
        "reduced_motion_no_raf_loops": all(r["reducedMotion"]["rafDelta3s"] <= 2 for r in rs), "labelled_navs": all(all(n for n in r["navs"]) for r in rs if r["route"].startswith("/app")),
    }


def under24_report(obs: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for r in obs["routes"]:
        for t in r["widths"].get("390", {}).get("under24", []):
            out.append({"route": r["route"], **t})
    return out
