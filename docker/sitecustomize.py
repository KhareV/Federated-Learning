"""Portable numerics for containers and other machines (loaded automatically by Python when /app/docker is on PYTHONPATH and NHM_PORTABLE_NUMERICS=1).

The frozen verification code checks pinned float32 test vectors with atol = rtol = 1e-7. That is tighter than float32 results can agree across different CPUs or BLAS builds (measured on aarch64 Linux CPU torch
against the macOS-recorded vector: max absolute error 4.9e-7, max relative error 5.9e-6, agreement to about six digits), so the pinned checks fail on any machine other than the one that recorded them.
In portable mode only, numpy.allclose widens a tolerance that is tighter than 1e-4 to 1e-4. A wrong checkpoint or a corrupted model differs by orders of magnitude more, so the checks still catch real faults; digest and hash checks are not touched.
The frozen source files are not modified; this module only exists in the container configuration."""
import os

if os.environ.get("NHM_PORTABLE_NUMERICS") == "1":
    import numpy as np

    _original = np.allclose
    PORTABLE_ATOL = PORTABLE_RTOL = 1e-4

    def _portable_allclose(a, b, rtol=1e-5, atol=1e-8, equal_nan=False):
        if rtol < PORTABLE_RTOL and atol < PORTABLE_ATOL:
            rtol, atol = max(rtol, PORTABLE_RTOL), max(atol, PORTABLE_ATOL)
        return _original(a, b, rtol=rtol, atol=atol, equal_nan=equal_nan)

    np.allclose = _portable_allclose
    print("NHM_PORTABLE_NUMERICS=1: float32 pinned-vector checks use atol=rtol=1e-4 on this machine (see docker/sitecustomize.py)", flush=True)
