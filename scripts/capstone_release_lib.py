# ruff: noqa: E501
"""CAPSTONE_RELEASE_VERIFIER_V1 library: pure, side-effect-free checks shared by the release verifier, the clean-clone
harness, the frozen CAPG10 evaluator, the targeted tests and the mutation controls. No training, inference, FL,
SecAgg or scientific calculation; no network."""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = "artifacts/capstone/CAPSTONE_RELEASE_MANIFEST_V1.json"
RELEASE_ID = "CAPSTONE_RELEASE_V1"
SHA40 = re.compile(r"^[0-9a-f]{40}$")

# ---- release claim vocabulary -------------------------------------------------------------------------------------
REQUIRED_STATEMENTS = {
    "release_claim": "clean-clone reproducible, one-laptop research-software/faculty-demonstration release",
    "install_network": "Initial dependency installation may require Internet access",
    "runtime_offline": "requires only loopback networking",
    "not_raw_data_reproduction": "does not claim full raw-data retraining/evaluation from a clean clone",
    "no_raw_dataset_download": "No raw biomedical dataset download is required",
    "no_personal_model": "No personal model is trained",
    "simulated_hardware": "SIMULATED_ONLY",
    "hardware_unverified": "VERIFICATION_REQUIRED",
    "candidate_not_deployed": "never automatically deployed",
    "promotion_distinct": "MODEL_V2_NOT_PROMOTED_RELEASE_CI",
    "system_release_distinct": "SYSTEM_V2_RESEARCH_DEFAULT_ACCEPTED",
    "tested_platform": "Tested platform",
    "not_security_audited": "not security audited",
}
WATCHED = re.compile(
    r"hospital|clinical\w*|diagnos\w*|medical[- ]device|secure\b|private\b|anonym\w*|differential privacy|\bdeployed\b|\bproduction\b|personal model|personali[sz]ed|"
    r"physical wearable|real hardware|on-device|continuous learning|air-gapped|HIPAA|certif\w+|penetration|hardened|raw-data scientific|scientific reproduc\w+|"
    r"Windows|Linux|cross-platform|vendored", re.I)
NEGATION = re.compile(r"\bnon-\w+|\bnot\b|\bno\b|\bnever\b|\bnor\b|without|isn't|n't\b|neither|does not|only on|may require|limited to|is not|absent|VERIFICATION_REQUIRED|simulated|synthetic|logical", re.I)
TECHNICAL = re.compile(r"production frontend|production build|npm run build", re.I)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sentences(text: str) -> list[str]:
    plain = re.sub(r"```.*?```", " ", text, flags=re.S)
    plain = re.sub(r"[*`#>|]", " ", plain)
    return [s.strip() for s in re.split(r"(?<=[.?!])\s+|\n+", plain) if s.strip()]


def audit_release_text(text: str, *, require: bool = True) -> dict[str, Any]:
    """Required statements present AND every watched claim word sits in an accurate negation/limitation."""
    missing = [k for k, phrase in REQUIRED_STATEMENTS.items() if phrase not in text] if require else []
    violations = []
    for sentence in sentences(text):
        if sentence.endswith("?"):
            continue
        for match in WATCHED.finditer(sentence):
            if TECHNICAL.search(sentence) and match.group(0).lower() == "production":
                continue
            if not NEGATION.search(sentence):
                violations.append({"word": match.group(0), "sentence": sentence[:200]})
    return {"missing_required": missing, "unnegated_watched_claims": violations, "ok": not missing and not violations}


def guide_commands(text: str) -> list[str]:
    """Every fenced shell command line of a guide, in order (comments and blanks dropped)."""
    out = []
    for block in re.findall(r"```(?:bash|sh)?\n(.*?)```", text, flags=re.S):
        out += [line.strip() for line in block.splitlines() if line.strip() and not line.strip().startswith("#")]
    return out


# ---- manifest -----------------------------------------------------------------------------------------------------
def verify_manifest(manifest: dict[str, Any], root: Path = ROOT) -> dict[str, Any]:
    """Name every failed manifest check; ``root`` may be a temporary copy tree (mutation controls)."""
    failures: list[str] = []
    if manifest.get("release_id") != RELEASE_ID:
        failures.append("manifest_release_id")
    if manifest.get("released_monitoring", {}).get("default_model") != "MODEL_V2_FINAL":
        failures.append("manifest_default_model")
    if manifest.get("released_monitoring", {}).get("candidate_used_for_monitoring") is not False:
        failures.append("manifest_candidate_monitoring")
    if manifest.get("candidate", {}).get("production_deployed") is not False:
        failures.append("manifest_candidate_deployed")
    if manifest.get("hardware", {}).get("hardware_mode") != "SIMULATED_ONLY" or manifest.get("hardware", {}).get("physical_hardware_available") is not False:
        failures.append("manifest_hardware")
    if manifest.get("manual_override_allowed") is not False:
        failures.append("manifest_override")
    for group in ("key_artifacts", "dependency_locks"):
        for rel, expected in manifest.get(group, {}).items():
            path = root / rel
            if not path.is_file():
                failures.append(f"{group}:missing:{rel}")
            elif sha256_file(path) != expected:
                failures.append(f"{group}:hash:{rel}")
    return {"ok": not failures, "failures": failures}


# ---- clean-clone input isolation ----------------------------------------------------------------------------------
FORBIDDEN_PRE_INSTALL = (
    (".venv", "copied_python_environment"), ("venv", "copied_python_environment"), ("frontend/node_modules", "copied_node_modules"), ("frontend/clerk-sdk/node_modules", "copied_node_modules"),
    ("frontend/build", "copied_frontend_build"), ("frontend/.svelte-kit", "copied_frontend_build"), (".env", "developer_dotenv"), (".env.local", "developer_dotenv"),
    ("frontend/.env", "developer_dotenv"), ("data/raw", "copied_raw_data"), ("data/processed", "copied_raw_data"), ("data/downloads", "copied_raw_data"),
)
SQLITE_SUFFIX = (".sqlite", ".sqlite3", ".db")


def pre_install_audit(clone: Path, tracked: list[str]) -> dict[str, Any]:
    """Run immediately after checkout, BEFORE any install: anything not tracked is a contaminant."""
    violations: list[dict[str, str]] = []
    tracked_set = set(tracked)
    for rel, kind in FORBIDDEN_PRE_INSTALL:
        p = clone / rel
        if p.exists() and not any(t == rel or t.startswith(rel + "/") for t in tracked_set):
            violations.append({"path": rel, "kind": kind})
    for p in clone.rglob("*"):
        rel = p.relative_to(clone).as_posix()
        if ".git/" in rel + "/" and rel.split("/")[0] == ".git":
            continue
        if p.is_file() and rel not in tracked_set:
            if p.suffix in SQLITE_SUFFIX or p.name in ("state.bin",):
                violations.append({"path": rel, "kind": "copied_runtime_state"})
            elif "candidate" in rel.lower() and rel.startswith(("artifacts", "checkpoints", "reports")):
                violations.append({"path": rel, "kind": "copied_candidate_artifact"})
            elif p.suffix in (".dat", ".hea", ".atr", ".mat"):
                violations.append({"path": rel, "kind": "copied_raw_data"})
            else:
                violations.append({"path": rel, "kind": "untracked_file_manual_injection"})
    return {"ok": not violations, "violations": violations[:50]}


def check_python_env(python: Path, clone: Path, dev_root: Path | None = None) -> dict[str, Any]:
    """The only acceptable interpreter is the venv this run created inside the fresh clone."""
    failures = []
    try:
        resolved = python.absolute()
        inside = clone.resolve() in resolved.parents or clone.absolute() in resolved.parents
    except OSError:
        inside = False
    if not inside or ".venv" not in python.parts:
        failures.append("python_not_in_clone_venv")
    if dev_root is not None and (dev_root.resolve() in python.resolve().parents):
        failures.append("python_in_development_checkout")
    return {"ok": not failures, "failures": failures}


def verify_checkout(head_sha: str, target_sha: str) -> dict[str, Any]:
    failures = []
    if not SHA40.match(target_sha or ""):
        failures.append("target_not_full_sha")
    if head_sha != target_sha:
        failures.append("wrong_checkout_sha")
    return {"ok": not failures, "failures": failures}


# ---- clone result tamper / completeness ---------------------------------------------------------------------------
RESULT_REQUIRED = ("release_target_sha", "label", "status", "kind")


def verify_clone_result(result: dict[str, Any], target_sha: str, required: tuple[str, ...] = RESULT_REQUIRED) -> dict[str, Any]:
    failures = []
    if not isinstance(result, dict):
        return {"ok": False, "failures": ["result_not_an_object"]}
    for key in required:
        if key not in result:
            failures.append(f"missing:{key}")
    if result.get("release_target_sha") != target_sha:
        failures.append("release_target_sha_mismatch")
    if result.get("status") not in ("PASS", "FAIL"):
        failures.append("status_malformed")
    return {"ok": not failures, "failures": failures}


# ---- target vs final diff -----------------------------------------------------------------------------------------
FINAL_ALLOWED = ("reports/capstone/cap_011/", "manifests/capstone/task_registry_v1.csv", "manifests/capstone/gate_registry_v1.csv")


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


def verify_final_diff(repo: Path, target_sha: str, final_sha: str | None = None) -> dict[str, Any]:
    """``final_sha=None`` audits the working tree (tracked changes + untracked files) against the release target."""
    if final_sha is None:
        rows = [r for r in git(repo, "diff", "--name-status", target_sha).splitlines() if r]
        rows += [f"A\t{p}" for p in git(repo, "ls-files", "--others", "--exclude-standard").splitlines() if p]
    else:
        rows = [r for r in git(repo, "diff", "--name-status", target_sha, final_sha).splitlines() if r]
    bad = []
    for row in rows:
        status, *paths = row.split("\t")
        for path in paths:
            if not path.startswith(FINAL_ALLOWED[0]) and path not in FINAL_ALLOWED[1:]:
                bad.append(f"{status}:{path}")
    return {"ok": not bad, "changed": [r.replace("\t", " ") for r in rows], "disallowed": bad}


# ---- portability --------------------------------------------------------------------------------------------------
PORTABILITY_DIRS = ("api", "product", "capstone_persistence", "src", "federated", "simulation", "privacy", "deployment", "frontend/src", "scripts", "Makefile", "pyproject.toml")
PORTABILITY_EXCLUDE = re.compile(r"^scripts/(generate_t\d+|cap_0\d\d_|run_v2_|verify_v2_|v2_0)")
ABSOLUTE = re.compile("/" + "Users/[A-Za-z0-9._-]+|/" + "home/[a-z][A-Za-z0-9._-]+|/" + "private/" + "tmp/|C:" + r"\\" + "Users")


def portability_audit(repo: Path = ROOT) -> dict[str, Any]:
    tracked = [p for p in git(repo, "ls-files").splitlines() if any(p == d or p.startswith(d + "/") for d in PORTABILITY_DIRS)]
    hits = []
    for rel in tracked:
        if PORTABILITY_EXCLUDE.match(rel) or not rel.endswith((".py", ".mjs", ".ts", ".js", ".svelte", ".json", ".yaml", ".yml", ".toml", ".sh", "Makefile")):
            continue
        try:
            text = (repo / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for match in ABSOLUTE.finditer(text):
            hits.append({"path": rel, "match": match.group(0)})
    return {"ok": not hits, "scope": "release-facing executable/config files (historical task-evidence generators and prior-phase evidence scripts excluded)", "files_scanned": len(tracked), "hits": hits[:40]}


def case_audit(repo: Path = ROOT) -> dict[str, Any]:
    names = git(repo, "ls-files").splitlines()
    seen: dict[str, str] = {}
    clashes = []
    for name in names:
        low = name.lower()
        if low in seen and seen[low] != name:
            clashes.append([seen[low], name])
        seen[low] = name
    return {"ok": not clashes, "tracked_files": len(names), "case_collisions": clashes[:20], "note": "no two tracked paths differ only by case; release imports use exact-case paths on the tested platform"}
