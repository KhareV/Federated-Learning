"""C-V2-PRE006-AUTHORITY-REPAIR: pure-function tests of the final-inner-split selection
algorithm (scripts/build_model_v2_final_inner_v2_v1.py), frozen BEFORE the real 27-group
TRAIN result is generated. Uses small synthetic aggregate data only -- never the real
MITDB_TRAIN_CV_V2_V1 population -- so these tests are meaningful and pass independently of
whether the actual MITDB_TRAIN_FINAL_INNER_V2_V1 manifest has been generated yet.
"""

from __future__ import annotations

import itertools

from scripts.build_model_v2_final_inner_v2_v1 import (
    FINAL_INNER_SIZE,
    select_final_inner_validation,
)


def _synthetic_aggregates(n: int) -> dict[str, dict[str, int]]:
    # 1-indexed synthetic patient groups with varied, deterministic window counts so the
    # objective function has a genuine, non-trivial optimum.
    return {
        f"SYN_P{i:02d}": {
            "eligible": 100 + 7 * i,
            "positive": 20 + (i % 5) * 3,
            "negative": (100 + 7 * i) - (20 + (i % 5) * 3),
        }
        for i in range(1, n + 1)
    }


def test_selects_exactly_final_inner_size_groups() -> None:
    aggregates = _synthetic_aggregates(12)
    combo, _objective = select_final_inner_validation(list(aggregates), aggregates)
    assert len(combo) == FINAL_INNER_SIZE


def test_deterministic_repeat_byte_identical() -> None:
    aggregates = _synthetic_aggregates(12)
    groups = list(aggregates)
    combo1, obj1 = select_final_inner_validation(groups, aggregates)
    combo2, obj2 = select_final_inner_validation(groups, aggregates)
    assert combo1 == combo2
    assert obj1 == obj2


def test_input_order_does_not_affect_selection() -> None:
    aggregates = _synthetic_aggregates(12)
    groups = list(aggregates)
    combo_forward, _ = select_final_inner_validation(groups, aggregates)
    combo_reversed, _ = select_final_inner_validation(list(reversed(groups)), aggregates)
    assert combo_forward == combo_reversed


def test_selected_combo_is_sorted_and_lexicographically_first_among_ties() -> None:
    aggregates = _synthetic_aggregates(10)
    groups = list(aggregates)
    combo, objective = select_final_inner_validation(groups, aggregates)
    assert combo == tuple(sorted(combo))

    # Re-derive the true minimum via brute force and confirm the lexicographically-first
    # combination (in itertools.combinations(sorted(...)) enumeration order) is returned
    # whenever a tie exists.
    all_results = []
    totals = {
        "windows": sum(aggregates[pg]["eligible"] for pg in groups),
        "positive": sum(aggregates[pg]["positive"] for pg in groups),
        "negative": sum(aggregates[pg]["negative"] for pg in groups),
    }
    n = len(groups)
    targets = {k: v * FINAL_INNER_SIZE / n for k, v in totals.items()}
    for c in itertools.combinations(sorted(groups), FINAL_INNER_SIZE):
        pos = sum(aggregates[pg]["positive"] for pg in c)
        neg = sum(aggregates[pg]["negative"] for pg in c)
        if pos == 0 or neg == 0:
            continue
        if totals["positive"] - pos == 0 or totals["negative"] - neg == 0:
            continue
        win = sum(aggregates[pg]["eligible"] for pg in c)
        obj = (
            ((win - targets["windows"]) / targets["windows"]) ** 2
            + ((pos - targets["positive"]) / targets["positive"]) ** 2
            + ((neg - targets["negative"]) / targets["negative"]) ** 2
        )
        all_results.append((obj, c))

    min_obj = min(r[0] for r in all_results)
    tied = [c for obj, c in all_results if obj < min_obj + 1e-15]
    assert combo == min(tied)
    assert abs(objective - min_obj) < 1e-12


def test_roles_are_disjoint_and_union_is_full_population() -> None:
    aggregates = _synthetic_aggregates(14)
    groups = sorted(aggregates)
    combo, _ = select_final_inner_validation(groups, aggregates)
    final_inner = set(combo)
    optimise = set(groups) - final_inner
    assert final_inner.isdisjoint(optimise)
    assert final_inner | optimise == set(groups)
    assert len(final_inner) == FINAL_INNER_SIZE
    assert len(optimise) == len(groups) - FINAL_INNER_SIZE


def test_both_roles_retain_positive_and_negative_windows() -> None:
    aggregates = _synthetic_aggregates(14)
    groups = sorted(aggregates)
    combo, _ = select_final_inner_validation(groups, aggregates)
    final_inner = set(combo)
    optimise = set(groups) - final_inner

    final_inner_pos = sum(aggregates[pg]["positive"] for pg in final_inner)
    final_inner_neg = sum(aggregates[pg]["negative"] for pg in final_inner)
    optimise_pos = sum(aggregates[pg]["positive"] for pg in optimise)
    optimise_neg = sum(aggregates[pg]["negative"] for pg in optimise)

    assert final_inner_pos > 0
    assert final_inner_neg > 0
    assert optimise_pos > 0
    assert optimise_neg > 0


def test_eligible_window_counts_conserved() -> None:
    aggregates = _synthetic_aggregates(14)
    groups = sorted(aggregates)
    combo, _ = select_final_inner_validation(groups, aggregates)
    final_inner = set(combo)
    optimise = set(groups) - final_inner

    total_eligible = sum(aggregates[pg]["eligible"] for pg in groups)
    split_eligible = sum(aggregates[pg]["eligible"] for pg in final_inner) + sum(
        aggregates[pg]["eligible"] for pg in optimise
    )
    assert split_eligible == total_eligible

    total_positive = sum(aggregates[pg]["positive"] for pg in groups)
    split_positive = sum(aggregates[pg]["positive"] for pg in final_inner) + sum(
        aggregates[pg]["positive"] for pg in optimise
    )
    assert split_positive == total_positive

    total_negative = sum(aggregates[pg]["negative"] for pg in groups)
    split_negative = sum(aggregates[pg]["negative"] for pg in final_inner) + sum(
        aggregates[pg]["negative"] for pg in optimise
    )
    assert split_negative == total_negative


def test_does_not_select_based_on_any_v2_004_or_validation_signal() -> None:
    # The function signature accepts only patient-group IDs and frozen TRAIN window-count
    # aggregates -- there is no parameter through which a model score, V2-004 result, or
    # VALIDATION/CALIBRATION metric could be supplied.
    import inspect

    sig = inspect.signature(select_final_inner_validation)
    assert list(sig.parameters) == ["train_groups", "aggregates"]
