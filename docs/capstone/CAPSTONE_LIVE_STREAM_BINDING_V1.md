# CAPSTONE_LIVE_STREAM_BINDING_V1

Machine-readable form: `configs/capstone/cap_003_live_stream_binding_v1.json`. This is an
**implementation binding / clarification**. It does not modify any CAP-001 contract and does not
change the scientific model path.

## The apparent tension (audited before implementation)
* `PRODUCT_LIVE_EVENT_V1.waveform.chunk` is a **360 Hz**, **ADC_COUNTS**, 36-72 samples/chunk UI
  transport, independent of PREPROC_V1.
* The CAP-001 connection table lists `WearableStreamRuntime -> Product Event Adapter` for waveform
  transport, but `WearableStreamRuntime`'s output is the **filtered, 250 Hz, amplitude-preserving**
  model/API window - not raw 360 Hz counts.

## Resolution: a tee at the coordinator
```
ObservedRecord (360 Hz, ADC counts)
    |
    +--A--> WaveformChunker --> waveform.chunk  (360 Hz ADC_COUNTS, UI only, None for gaps)
    |
    +--B--> unchanged WearableStreamRuntime --> 250 Hz scientific window --> inference
```
Both branches receive the SAME `ObservedRecord` objects, unmodified. The waveform chunk is produced
from the raw 360 Hz records, never from the runtime's 250 Hz window. The connection-table edge
`WearableStreamRuntime -> Product Event Adapter` is therefore realised for the **window-derived**
events only (`quality.status`); `waveform.chunk` is realised by the record tee (branch A). No
CAP-001 file is edited; this document records the binding.

## Policies frozen by CAP-003
* **Chunk size:** 60 samples = 6 waveform events/s (frozen contract range: 5-10/s, 36-72 nominal,
  hard max 144). No per-sample WebSocket messages. ECG channel only (the simulated device has
  `supports_ppg = false`; no PPG waveform is ever fabricated).
* **Gap policy:** a chunk covers a fixed, contiguous block of sample-index positions. A position with
  no delivered record (link outage / dropped samples) or `ecg_raw is None` is `None` **inside
  waveform.chunk only** - never `0`, never last-value hold, never interpolation.
* **Isolation:** `None` placeholders never enter `WearableStreamRuntime` or `/v1/infer-window`; the
  scientific path receives exactly the delivered records (same gaps as CAP-002).
* **Gap timing:** at a source event with a source timestamp (e.g. `DEVICE_RECONNECTED`) the chunker
  first fills the known gap up to that time, so outage chunks precede the reconnect `device.status`.
* **Dual-stream:** records and device events are merged by the deterministic multiplexer
  (`product/monitoring/mux.py`) using only the public `DeviceSource` interface.
* **Waveform and model path independence:** the 360->250 PREPROC_V1 path is unchanged and
  independent of UI chunking (tested: window count, sample digest and quality counts equal CAP-002).

## Context snapshot clarification (found with the real released service)
`PRODUCT_LIVE_EVENT_V1.context.snapshot` rejects an unavailable context that carries PPG-derived
values, but the released system can answer `context_available = false` while a pulse rate is present
(e.g. SpO2 invalid). CAP-001 is not modified and no value is invented: when `context_available` is
false the adapter **withholds** `pr_ppg_bpm`, `spo2_pct` and `spo2_valid` (set to null/false), keeps
`hr_ecg_bpm`/`ppg_quality`, and counts each occurrence in session telemetry
(`context_values_withheld`). `context_available` itself is always the released response's value.
