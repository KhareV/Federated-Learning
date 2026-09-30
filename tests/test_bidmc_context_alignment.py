from __future__ import annotations

import numpy as np

from evaluation.bidmc_context import context_window_at, verify_bidmc_source


def test_source_clock_contract() -> None:
    source = verify_bidmc_source()
    assert source["records"] == 53
    assert source["waveform_hz"] == 125
    assert source["numeric_hz"] == 1


def test_ten_second_context_is_right_edge_inclusive_without_future() -> None:
    stream = np.arange(1002, dtype=float)
    window = context_window_at(stream, 10, 100)
    assert window.shape == (1000,)
    assert window[0] == 1
    assert window[-1] == 1000
    stream[1001] = -999999
    assert np.array_equal(context_window_at(stream, 10, 100), window)


def test_warmup_and_numeric_second_alignment() -> None:
    stream = np.arange(2501, dtype=float)
    assert context_window_at(stream, 9, 250).size == 0
    window = context_window_at(stream, 10, 250)
    assert window[0] == 1 and window[-1] == 2500
