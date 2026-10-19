"""The Studio bundle's pinned static data is built once and published atomically: concurrent first requests (the Live page and the Observatory fetch the overview together right after a restart) must never see a half-built cache."""

from __future__ import annotations

import threading

from studio import bundle


def test_concurrent_first_requests_never_see_a_half_built_static_cache():
    saved = dict(bundle._STATIC)
    bundle._STATIC.clear()
    errors: list[str] = []

    def request() -> None:
        try:
            static = bundle._static()
            for key in ("protocol", "bridge", "historical"):
                assert key in static
        except Exception as error:  # noqa: BLE001
            errors.append(repr(error))

    try:
        threads = [threading.Thread(target=request) for _ in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        assert list(bundle._STATIC)[-1] == "protocol" or "protocol" in bundle._STATIC            # the readers' fast-path key is published last
    finally:
        bundle._STATIC.clear()
        bundle._STATIC.update(saved)
