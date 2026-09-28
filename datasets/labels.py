"""AAMI_SVF_MAP_V1 -- the single shared beat-symbol mapper for MIT-BIH and INCART, plus the
frozen AAMI_SVF_WINDOW_V1 window-target decision rule.

Owns: WFDB annotation-symbol -> AAMI superclass mapping (identical for both source datasets),
beat vs. non-beat classification, and the pure eligibility rule from
`contracts/LABEL_SCHEMA_V1.md` Section 3. Does NOT own patient splitting (T009), real signal
window construction/striding (T013), preprocessing/resampling/filtering (T011-T012), signal
quality assessment, or model training. `classify_window_target` takes an already-computed
sequence of mapped beat classes for one candidate window; it never touches raw signal samples,
timestamps, or record/patient identity.

Every mapping table here is immutable (`MappingProxyType`/`frozenset`/tuple). A change to
`AAMI_CLASSES`, `BEAT_SYMBOLS`, or `NON_BEAT_SYMBOLS` is a scientific/methodological revision
(Class C under docs/CHANGE_CONTROL.md) requiring a new mapping version (`AAMI_SVF_MAP_V2`),
never a local refactor.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

MAP_ID = "AAMI_SVF_MAP_V1"
TARGET_ID = "AAMI_SVF_WINDOW_V1"
SPEC_VERSION = "2.2"

UNMAPPABLE = "UNMAPPABLE"
NOT_A_BEAT = "NOT_A_BEAT"

# Frozen allowlist -- contracts/LABEL_SCHEMA_V1.md Section 5. Any beat symbol not listed here
# is UNMAPPABLE and excluded from the core target; it is never coerced to the "closest" class.
AAMI_CLASSES: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "N": ("N", "L", "R", "e", "j"),
        "S": ("A", "a", "J", "S"),
        "V": ("V", "E"),
        "F": ("F",),
        "Q": ("/", "f", "Q"),
    }
)

_SYMBOL_TO_CLASS: Mapping[str, str] = MappingProxyType(
    {symbol: cls for cls, symbols in AAMI_CLASSES.items() for symbol in symbols}
)

# Beat vs. non-beat classification, sourced from WFDB 4.3.1's own authoritative
# `wfdb.io.annotation.is_qrs` / `ann_label_table` (the complete standard PhysioBank annotation
# symbol vocabulary), not guessed. Hardcoded (rather than read from wfdb at import time) so the
# frozen scientific table has no runtime dependency on a third-party module's internal
# attribute; `tests/test_aami_svf_map_v1.py::test_beat_non_beat_tables_match_wfdb_is_qrs_table`
# cross-checks this table against the live wfdb table so any library upgrade that changes it is
# caught, not silently inherited. The blank placeholder symbol (label_store 0, "Not an actual
# annotation") is included for completeness; it does not occur in real annotation arrays.
BEAT_SYMBOLS: frozenset[str] = frozenset(
    {
        "N", "L", "R", "a", "V", "F", "J", "A", "S", "E", "j", "/", "Q", "B", "?", "!", "e",
        "n", "f", "r",
    }
)
NON_BEAT_SYMBOLS: frozenset[str] = frozenset(
    {
        " ", "~", "|", "s", "T", "*", "D", '"', "=", "p", "^", "t", "+", "u", "[", "]", "@",
        "x", "(", ")",
    }
)

CORE_HANDLING_BY_CLASS: Mapping[str, str] = MappingProxyType(
    {
        "N": "REFERENCE",
        "S": "POSITIVE_SVF",
        "V": "POSITIVE_SVF",
        "F": "POSITIVE_SVF",
        "Q": "EXCLUDE_Q",
        UNMAPPABLE: "EXCLUDE_UNMAPPABLE",
        NOT_A_BEAT: "IGNORE_NON_BEAT",
    }
)

MIN_MAPPABLE_BEATS = 5


@dataclass(frozen=True)
class MappedAnnotation:
    symbol: str
    annotation_kind: str  # "BEAT" | "NON_BEAT"
    mapped_class: str  # "N" | "S" | "V" | "F" | "Q" | UNMAPPABLE | NOT_A_BEAT
    core_handling: str
    map_id: str = MAP_ID


@dataclass(frozen=True)
class WindowTargetResult:
    target: int | None  # 1, 0, or None if excluded
    label: str  # "SVF_CONTAINING_WINDOW" | "N_ONLY_WINDOW" | "EXCLUDED"
    exclusion_reason: str | None
    mappable_beat_count: int
    target_id: str = TARGET_ID


def classify_annotation_kind(symbol: str) -> str:
    """Return "BEAT" or "NON_BEAT" for one raw WFDB annotation symbol.

    Raises ValueError for a symbol outside the entire WFDB 4.3.1 standard annotation
    vocabulary (`BEAT_SYMBOLS | NON_BEAT_SYMBOLS`) -- a genuine data anomaly to investigate,
    never silently classified either way.
    """
    if symbol in BEAT_SYMBOLS:
        return "BEAT"
    if symbol in NON_BEAT_SYMBOLS:
        return "NON_BEAT"
    raise ValueError(
        f"UNRECOGNIZED_WFDB_ANNOTATION_SYMBOL: {symbol!r} is not in the WFDB 4.3.1 standard "
        "annotation symbol table (BEAT_SYMBOLS | NON_BEAT_SYMBOLS)."
    )


def map_annotation_symbol(symbol: str) -> MappedAnnotation:
    """Pure, deterministic, dataset-independent classification of one raw annotation symbol.

    Never inspects dataset, patient, record, or signal information -- identical behavior for
    MIT-BIH and INCART, which is exactly what R01 (AAMI SVF target and map) requires.
    """
    kind = classify_annotation_kind(symbol)
    mapped_class = NOT_A_BEAT if kind == "NON_BEAT" else _SYMBOL_TO_CLASS.get(symbol, UNMAPPABLE)
    return MappedAnnotation(
        symbol=symbol,
        annotation_kind=kind,
        mapped_class=mapped_class,
        core_handling=CORE_HANDLING_BY_CLASS[mapped_class],
    )


def classify_window_target(mapped_classes: Sequence[str]) -> WindowTargetResult:
    """Pure eligibility decision over an already-computed sequence of AAMI_SVF_MAP_V1 mapped
    beat classes ("N"/"S"/"V"/"F"/"Q"/UNMAPPABLE; NOT_A_BEAT entries must already be filtered
    out by the caller) for one candidate window.

    contracts/LABEL_SCHEMA_V1.md Section 3: positive requires >=1 mapped S/V/F beat and no
    Q/unmappable beat; negative requires only mapped N beats and no excluded beat; both require
    at least `MIN_MAPPABLE_BEATS` mappable beats. This function never touches raw signal,
    timestamps, or record/patient identity -- real signal window construction and striding is
    T013's job. Signal-quality-driven "UNUSABLE training window" exclusion is likewise out of
    scope here: it depends on preprocessing/quality information this pure beat-class rule does
    not have, and is implemented where that information exists (T011-T013).
    """
    if any(cls in ("Q", UNMAPPABLE) for cls in mapped_classes):
        return WindowTargetResult(
            target=None,
            label="EXCLUDED",
            exclusion_reason="EXCLUDE_Q_OR_UNMAPPABLE_BEAT_PRESENT",
            mappable_beat_count=len(mapped_classes),
        )
    mappable = [cls for cls in mapped_classes if cls in ("N", "S", "V", "F")]
    if len(mappable) < MIN_MAPPABLE_BEATS:
        return WindowTargetResult(
            target=None,
            label="EXCLUDED",
            exclusion_reason="EXCLUDE_FEWER_THAN_MIN_MAPPABLE_BEATS",
            mappable_beat_count=len(mappable),
        )
    if any(cls in ("S", "V", "F") for cls in mappable):
        return WindowTargetResult(
            target=1,
            label="SVF_CONTAINING_WINDOW",
            exclusion_reason=None,
            mappable_beat_count=len(mappable),
        )
    return WindowTargetResult(
        target=0,
        label="N_ONLY_WINDOW",
        exclusion_reason=None,
        mappable_beat_count=len(mappable),
    )
