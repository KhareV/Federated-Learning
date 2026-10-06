# ruff: noqa: E501
"""FINAL_EVALUATOR_PRESENTATION_V2: detects the CLASS 'unsourced / fabricated / misleading quantitative or live-state presentation' on current evaluator surfaces, and verifies
EVALUATOR_PRESENTATION_PROVENANCE_V1. Pure functions over a repository ROOT (real tree or disposable shadow). Extends (never edits) the FER-001 presentation guard."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from scripts import final_eval_repair_lib as lib
from scripts import final_eval_repair_presentation as pres

ROOT = lib.ROOT
SRC = "frontend/src"
CONTRACT = "configs/final_eval_repair/presentation_provenance_v1.json"
PROVENANCE_TYPES = {"RUNTIME", "FROZEN_PROJECT_EVIDENCE", "EXTERNAL_SOURCE", "ILLUSTRATIVE"}
CLAIM_TYPES = {"LIVE_STATE", "QUANTITATIVE", "PERCENTAGE", "SCORE", "PHYSIOLOGICAL_VALUE", "STATUS_LABEL", "EDGE_INFERENCE", "HARDWARE_DATA", "FILE_REFERENCE"}
# Qualification vocabulary: text in the SAME rendered string that makes a figure/label unmistakably non-live and non-measured.
MARKER = re.compile(r"illustrat|synthetic|simulat|concept|hypothetical|scenario|not live|unverified|example|decorative|not a measurement|accelerated", re.I)
NEG = re.compile(r"\b(not|no|never|nor|without|neither|isn't|cannot|n't|unverified|unavailable|absent)\b", re.I)
PHYS = r"(?:bpm|ms|mmHg|LF/HF|SpO[₂2]|breaths?|br/min|kbps|kb|mb|hz|khz|nm|mv|fps)"
RULES: tuple[tuple[str, str, str, bool | str], ...] = (
    # (id, claim_type, regex, needs_marker_or_negation_or_provenance)
    ("percentage", "PERCENTAGE", r"\b\d+(?:\.\d+)?\s?%", "strict"),
    ("quantified_duration", "QUANTITATIVE", r"\b\d+(?:\.\d+)?\s?(?:hours?|hrs?|minutes?|mins?|days?)\b", "strict"),
    ("live_or_realtime", "LIVE_STATE", r"\b(?:live|real-?time)\b", True),
    ("current_value", "LIVE_STATE", r"\b(?:current|latest)\s+(?:value|reading|spo[₂2]|heart rate|bpm)\b", True),
    ("physiological_value", "PHYSIOLOGICAL_VALUE", rf"\b\d+(?:\.\d+)?\s?{PHYS}\b", True),
    ("score_with_number", "SCORE", r"\b(?:confidence|anomaly(?: score)?|risk(?: score)?|accuracy|coverage|sensitivity|specificity)\b[^.<]{0,28}\d|\d[^.<]{0,14}\b(?:confidence|anomaly|accuracy|coverage)\b", "strict"),
    ("normal_label", "STATUS_LABEL", r"\bnormal(?:\s+(?:sinus|rhythm|ecg|range|value|reading|cardiac))?\b(?!\s*[_-]?monitored)", True),
    ("optimal_or_nominal", "STATUS_LABEL", r"\b(?:optimal|nominal)\b", True),
    ("patient_live_data", "HARDWARE_DATA", r"\b(?:live|real|actual)\s+(?:patient|wearable|sensor|participant)\s+(?:data|stream|signal|feed)\b|\breal wearable stream\b|\blive patient data\b", True),
    ("edge_inference", "EDGE_INFERENCE", r"\b(?:on-?device|edge)\b[^.<]{0,32}\b(?:inference|model|ml|running|firmware|detect\w*)\b|\bedge model\b|\bmodel running on (?:the )?wearable\b", True),
    ("clinical_monitoring", "STATUS_LABEL", r"\bclinical(?:[- ](?:grade|monitoring|deployment|decision|use))\b|\bclinical-grade\b", True),
    ("detection_claim", "STATUS_LABEL", r"\b(?:detected|detects?|detection)\b", True),
    ("file_reference", "FILE_REFERENCE", r"\b(?:reports|docs|artifacts|checkpoints)/[\w./-]+", "strict"),
)
CSSISH = re.compile(r"^[\s\w.#:\-\[\]>*+~,%()]*[;{}]|\b(?:width|height|min-width|max-width|min-height|max-height|opacity|top|left|right|bottom|inset|margin|padding|flex|flex-basis|translate|background-size|background-position)\s*:\s*[\d.]+%|\$\{|calc\(|gradient\(|translate|rotate\(|\bpx\b|\bem\b|\[[^\]]*\]|^(?:transparent|currentColor|#[0-9a-f]{3,8})\s+\d+%")
HARD_QUANT = {"percentage", "score_with_number", "file_reference", "quantified_duration"}     # also enforced on every current surface (product pages included)


def read(root: Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8")


def landing_files(root: Path = ROOT) -> list[str]:
    """Static import closure of the PUBLIC landing page."""
    seen: set[str] = set()
    stack = [f"{SRC}/routes/+page.svelte"]
    while stack:
        f = stack.pop()
        if f in seen or not (root / f).exists():
            continue
        seen.add(f)
        t = read(root, f)
        for a, b in re.findall(r"from\s+['\"]([^'\"]+)['\"]|import\s+['\"]([^'\"]+)['\"]", t):
            spec = a or b
            base = root / SRC / "lib" / spec[5:] if spec.startswith("$lib/") else (root / f).parent / spec if spec.startswith(".") else None
            if base is None:
                continue
            for cand in (base, Path(str(base) + ".ts"), Path(str(base) + ".svelte"), base / "index.ts"):
                if cand.is_file():
                    stack.append(cand.resolve().relative_to(root.resolve()).as_posix())
                    break
    return sorted(seen)


def visible_strings(text: str) -> list[str]:
    """Rendered-text candidates: template text nodes, user-facing attribute values and multi-word script string literals (CSS, comments and imports excluded)."""
    text = re.sub(r"<style[\s\S]*?</style>", " ", text)
    text = pres.strip_comments(text)
    template = re.sub(r"<script[\s\S]*?</script>", " ", text)
    out: list[str] = []
    for m in re.finditer(r">([^<>{}]*)(?=<)", template):
        out.append(m.group(1))
    for m in re.finditer(r"""\b(?:aria-label|title|alt|content|label|placeholder)=["']([^"']+)["']""", text):
        out.append(m.group(1))
    for m in re.finditer(r"""(["'`])((?:\\.|(?!\1)[^\\\n]){4,300})\1""", text):
        s = m.group(2)
        if re.search(r"[A-Za-z]{3,}", s) and (" " in s or re.search(r"\d", s)) and not s.startswith(("$lib", ".", "/", "http", "#")):
            out.append(s)
    return [re.sub(r"\s+", " ", s).strip() for s in out if s.strip() and not CSSISH.search(s)]


def scan_text(text: str, scope: str = "landing") -> list[dict[str, str]]:
    hits = []
    for s in visible_strings(text):
        for rid, ctype, pat, needs in RULES:
            if scope != "landing" and rid not in HARD_QUANT:
                continue
            if not re.search(pat, s, re.I):
                continue
            if needs is True and (MARKER.search(s) or NEG.search(s)):
                continue                # qualified/negated in its own string; "strict" rules (figures, scores, paths) are never excused by wording
            hits.append({"rule": rid, "claim_type": ctype, "text": s[:140]})
    return hits


def contract(root: Path = ROOT) -> dict[str, Any]:
    return json.loads(read(root, CONTRACT))


def scan_tree(root: Path = ROOT) -> dict[str, Any]:
    """Every uncovered high-risk hit across the landing graph (full rule set) and every other current surface (hard quantitative rules)."""
    entries = contract(root)["claims"]
    landing = set(landing_files(root))
    uncovered, covered = [], []
    for f in sorted(set(pres.current_files(root)) | landing):
        if not f.endswith((".svelte", ".ts")) or f.endswith(".test.ts") or "/__tests__/" in f:
            continue
        for h in scan_text(read(root, f), "landing" if f in landing else "current"):
            ent = next((e for e in entries if e["surface"] == f and re.search(e["text_pattern"], h["text"], re.I)), None)
            (covered if ent else uncovered).append({"file": f, **h, **({"claim_id": ent["claim_id"]} if ent else {})})
    return {"ok": not uncovered, "uncovered": uncovered, "covered": covered, "landing_files": len(landing)}


def provenance_ok(root: Path = ROOT) -> dict[str, Any]:
    c = contract(root)
    problems = []
    keys = {"claim_id", "surface", "claim_type", "text_pattern", "provenance_type", "source", "required_qualification", "allowed_context"}
    ids = set()
    for e in c["claims"]:
        if not keys <= set(e):
            problems.append({"claim": e.get("claim_id"), "problem": "missing_keys"})
            continue
        if e["claim_id"] in ids:
            problems.append({"claim": e["claim_id"], "problem": "duplicate_id"})
        ids.add(e["claim_id"])
        if e["provenance_type"] not in PROVENANCE_TYPES or e["claim_type"] not in CLAIM_TYPES:
            problems.append({"claim": e["claim_id"], "problem": "bad_type"})
        if not (root / e["surface"]).exists():
            problems.append({"claim": e["claim_id"], "problem": "surface_missing"})
            continue
        text = read(root, e["surface"])
        if not re.search(e["text_pattern"], " ".join(visible_strings(text)), re.I):
            problems.append({"claim": e["claim_id"], "problem": "stale_entry_text_not_found"})
        for q in e["required_qualification"]:
            if not re.search(q, text, re.I):
                problems.append({"claim": e["claim_id"], "problem": "qualification_missing", "qualification": q})
        if e["provenance_type"] == "ILLUSTRATIVE" and not e["required_qualification"]:
            problems.append({"claim": e["claim_id"], "problem": "illustrative_without_qualification"})
        if e["provenance_type"] in {"FROZEN_PROJECT_EVIDENCE", "EXTERNAL_SOURCE"} and (not e["source"] or (e["provenance_type"] == "FROZEN_PROJECT_EVIDENCE" and not (root / e["source"]).exists())):
            problems.append({"claim": e["claim_id"], "problem": "source_not_verifiable"})
        if e["provenance_type"] == "RUNTIME" and not e["source"]:
            problems.append({"claim": e["claim_id"], "problem": "runtime_source_missing"})
    return {"ok": not problems, "problems": problems, "entries": len(c["claims"])}


def a11y_static_ok(root: Path = ROOT) -> dict[str, Any]:
    t = read(root, f"{SRC}/routes/+page.svelte")
    boot = read(root, f"{SRC}/routes/app/+layout.svelte")
    checks = {"landing_skip_link_first": bool(re.search(r'<a class="skip-link" href="#top">Skip to main content</a>\s*\{#if preloaderMounted\}', t)), "skip_target_focusable_main": '<main id="top" tabindex="-1">' in t,
              "landing_nav_labelled": bool(re.search(r'<nav class="nav" aria-label="[^"]{4,}"', t)), "skip_link_hidden_until_focus": ".skip-link:focus" in t and "top: -64px" in t,
              "neural_graph_reduced_motion": "prefers-reduced-motion" in read(root, f"{SRC}/lib/components/landing/NeuralGraph.svelte") and "if (!reducedMotion) animId" in read(root, f"{SRC}/lib/components/landing/NeuralGraph.svelte"),
              "multimodal_reduced_motion": "prefers-reduced-motion" in read(root, f"{SRC}/lib/components/signals/MultimodalStudio.svelte") and "if (!reducedMotion) animId" in read(root, f"{SRC}/lib/components/signals/MultimodalStudio.svelte"),
              "watch_reduced_motion": "prefers-reduced-motion" in read(root, f"{SRC}/lib/components/landing/WatchScene.svelte"), "globe_reduced_motion": "prefers-reduced-motion" in read(root, f"{SRC}/lib/components/magic/globe/globe.svelte"),
              "morphing_text_reduced_motion": "prefers-reduced-motion" in read(root, f"{SRC}/lib/components/magic/morphing-text/morphing-text.svelte"), "animated_beam_reduced_motion": "prefers-reduced-motion" in read(root, f"{SRC}/lib/components/magic/animated-beam/animated-beam.svelte"),
              "grid_pattern_reduced_motion": "prefers-reduced-motion" in read(root, f"{SRC}/lib/components/magic/animated-grid-pattern/animated-grid-pattern.svelte"), "watch_static_poster_under_reduced_motion": "{#if reducedMotion}" in read(root, f"{SRC}/lib/components/landing/WatchScene.svelte") and "watch-poster.jpg" in read(root, f"{SRC}/lib/components/landing/WatchScene.svelte"),
              "landing_css_reduced_motion": "federation-path-line span { animation: none" in t, "boot_loader_has_heading": "<h1>Opening the NHM workspace" in boot and 'role="status"' in boot and "<main" in boot}
    return {"ok": all(checks.values()), "checks": checks}


def verify_all(root: Path = ROOT) -> dict[str, Any]:
    parts = {"claims_scan": scan_tree(root), "provenance": provenance_ok(root), "a11y_static": a11y_static_ok(root)}
    return {"ok": all(p["ok"] for p in parts.values()), "parts": parts}


if __name__ == "__main__":
    r = verify_all()
    print(json.dumps({"ok": r["ok"], **{k: v["ok"] for k, v in r["parts"].items()}}))
    if not r["ok"]:
        for k, v in r["parts"].items():
            if not v["ok"]:
                print(k, json.dumps(v)[:2500])
        raise SystemExit(1)
