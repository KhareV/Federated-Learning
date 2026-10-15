import type { HardwareReading } from './api';

export interface HardwareStats {
  count: number; spanSeconds: number; arrivalHz: number | null; min: number | null; max: number | null;
  mean: number | null; std: number | null; peakToPeak: number | null; flatFraction: number;
  railFraction: number; gaps: { from: string; to: string; seconds: number }[]; maxGapSeconds: number;
  verdict: 'NO_DATA' | 'FLAT_OR_LEADS_OFF' | 'RAIL_SATURATED' | 'GAPS_PRESENT' | 'SIGNAL_VARIES';
}

/** Descriptive statistics of the stored readings only; not a clinical or model quality verdict. */
export function hardwareStats(readings: HardwareReading[], gapMs = 1000): HardwareStats {
  const r = readings.filter((x) => Number.isFinite(x.ecg) && Number.isFinite(Date.parse(x.ingested_at)))
    .sort((a, b) => Date.parse(a.ingested_at) - Date.parse(b.ingested_at));
  if (!r.length) return { count: 0, spanSeconds: 0, arrivalHz: null, min: null, max: null, mean: null, std: null,
    peakToPeak: null, flatFraction: 0, railFraction: 0, gaps: [], maxGapSeconds: 0, verdict: 'NO_DATA' };
  const values = r.map((x) => x.ecg);
  const mean = values.reduce((a, b) => a + b, 0) / values.length;
  const std = Math.sqrt(values.reduce((a, b) => a + (b - mean) ** 2, 0) / values.length);
  const min = Math.min(...values), max = Math.max(...values);
  const spanMs = Date.parse(r.at(-1)!.ingested_at) - Date.parse(r[0].ingested_at);
  const gaps: HardwareStats['gaps'] = [];
  for (let i = 1; i < r.length; i += 1) {
    const dt = Date.parse(r[i].ingested_at) - Date.parse(r[i - 1].ingested_at);
    if (dt > gapMs) gaps.push({ from: r[i - 1].ingested_at, to: r[i].ingested_at, seconds: dt / 1000 });
  }
  // The sketch writes 2048 when either lead-off pin is high; the payload has no lead-off flag.
  const flat = values.filter((v) => v === 2048).length / values.length;
  const rail = values.filter((v) => v <= 5 || v >= 4090).length / values.length;
  const maxGap = gaps.reduce((a, g) => Math.max(a, g.seconds), 0);
  const verdict = flat > 0.9 || max - min < 4 ? 'FLAT_OR_LEADS_OFF' : rail > 0.1 ? 'RAIL_SATURATED'
    : gaps.length ? 'GAPS_PRESENT' : 'SIGNAL_VARIES';
  return { count: r.length, spanSeconds: spanMs / 1000, arrivalHz: spanMs > 0 ? (r.length - 1) / (spanMs / 1000) : null,
    min, max, mean, std, peakToPeak: max - min, flatFraction: flat, railFraction: rail, gaps, maxGapSeconds: maxGap, verdict };
}
