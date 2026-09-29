from __future__ import annotations

from preprocessing.windowing import summarize_annotations


def test_window_labels_reuse_frozen_mapper_and_preserve_reasons() -> None:
    positive = summarize_annotations(["N", "N", "N", "N", "V", "+"])
    assert positive.label == 1
    assert positive.label_status == "ELIGIBLE_POSITIVE"
    assert positive.svf_beat_count == 1

    negative = summarize_annotations(["N", "L", "R", "e", "j"])
    assert negative.label == 0
    assert negative.label_status == "ELIGIBLE_NEGATIVE"

    q = summarize_annotations(["N", "N", "N", "N", "N", "/"])
    assert q.label is None
    assert q.exclusion_reasons == ("EXCLUDE_Q",)

    unmappable = summarize_annotations(["N", "N", "N", "N", "N", "?"])
    assert unmappable.label is None
    assert unmappable.exclusion_reasons == ("EXCLUDE_UNMAPPABLE",)

    too_few = summarize_annotations(["N", "N", "V", "N"])
    assert too_few.label is None
    assert too_few.exclusion_reasons == ("EXCLUDE_LT5_MAPPABLE_BEATS",)

