# Repository Map

T001 adapts the requested logical responsibilities without relocating user work.

| Logical responsibility | Repository location | T001 status |
|---|---|---|
| contracts | `contracts/` | Run-manifest v1 schema implemented. |
| configs | `configs/` | Locked, non-hardware base metadata only. |
| datasets / manifests | `data/`, `data/manifests/`, `manifests/` | Existing 5.6 GB data tree preserved; payloads not modified or accepted. |
| preprocessing through deployment | same-named root directories | Placeholder package boundaries only. |
| dashboard | `frontend/` | Existing SvelteKit UI preserved; no dashboard implementation in T001. |
| Python source | `src/nhm/` | T001 reproducibility, hashing, config, and manifest utilities only. |
| tests and fixtures | `tests/` | Offline T001 contracts and sanitized observation fixture. |
| reports | `reports/t001/` | Generated Phase-01 evidence. |

## Existing-scope conflict

`CONFLICT`

- existing behavior: the frontend contains pages for later dashboard, model, federated, and sensor
  responsibilities and visible strings that assert hardware details such as a 24-bit ADC and 360 Hz
  sampling;
- planned behavior: T001 must not implement the dashboard or declare unverified hardware constants;
- scientific impact: displaying unverified device specifications can turn design mockup text into an
  unsupported hardware claim;
- recommended resolution: preserve the user-owned frontend in T001, do not treat it as evidence, and
  audit/correct its claims only in the authorized future dashboard/hardware-contract task.

Existing PTB-XL and BIDMC files/manifests are likewise preserved. They are not downloaded,
preprocessed, verified, or used by T001. Their role and any apparent mismatch with v2.2 are
`DEFERRED_TO_PHASE` under the appropriate future requirement/dataset tasks.

