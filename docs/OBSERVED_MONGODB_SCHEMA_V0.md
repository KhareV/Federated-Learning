# Observed MongoDB Schema V0

The following is an example supplied from the currently operating hardware path. It records only
the observed BSON shape and literal example values; it is not proof of units, sampling behavior, or
physiological validity.

```javascript
{
  _id: ObjectId("6aa7ab815ad3c23195df147b"),
  bpm: NumberInt("1024"),
  spo2: NumberInt("1024"),
  ecg: NumberInt("2048"),
  timestamp: ISODate("2026-09-14T08:08:33.011Z")
}
```

| Field | Observed BSON type | Current interpretation | Scientific/unit meaning | Status |
|---|---|---|---|---|
| `_id` | ObjectId | MongoDB document identifier | none | OBSERVED |
| `bpm` | int32 | firmware/backend field named bpm | unknown | VERIFICATION_REQUIRED |
| `spo2` | int32 | firmware/backend field named spo2 | unknown | VERIFICATION_REQUIRED |
| `ecg` | int32 | firmware/backend field named ecg | unknown/raw | VERIFICATION_REQUIRED |
| `timestamp` | Date | stored timestamp | origin/clock semantics unknown | VERIFICATION_REQUIRED |

The numeric examples may be raw, default, ADC, intermediate, or something else. No conclusion is
made in T001. In particular, a MongoDB document is not assumed to be a synchronized sample, and no
sampling frequency, calibration, losslessness, algorithm, unit, or clock semantics are assumed.

## Verification questions

- Which component generates `timestamp`?
- Is `timestamp` inserted on device, API server, or MongoDB?
- What is the ECG acquisition frequency?
- Does each MongoDB document represent one ECG sample?
- What does `ecg=2048` correspond to electrically?
- What is the ADC resolution?
- What is the ADC reference voltage?
- What is the AD8232 output range?
- Is any gain or scaling applied before storage?
- How are `bpm` and `spo2` calculated?
- Are the values `1024` sentinel, default, or raw values?
- What is the MAX30102 register configuration?
- What is the packet-loss behavior?
- What is the reconnect behavior?
- Can documents be duplicated?
- What timestamp jitter is present?
- What ordering guarantees exist?
- Is batching used?
- What are the collection and database names?
- Why are participant, session, and device identities currently absent from the observed shape?

All answers remain `VERIFICATION_REQUIRED` until firmware, backend, database configuration, or
measured hardware evidence establishes them.

