import { describe, expect, it } from 'vitest';
import { hardwareStats } from '../hardware-stats';
import type { HardwareReading } from '../api';

const mk = (ms: number, ecg: number, i = ms): HardwareReading => ({ ordinal: i, id: `id${i}`, ingested_at: new Date(1_700_000_000_000 + ms).toISOString(), ecg, bpm: 70, spo2: 97, collection: null });

describe('hardwareStats', () => {
  it('reports exact descriptive values and the arrival rate from stored timestamps', () => {
    const s = hardwareStats([mk(0, 1000), mk(50, 2000), mk(100, 3000)]);
    expect(s.count).toBe(3); expect(s.min).toBe(1000); expect(s.max).toBe(3000); expect(s.mean).toBe(2000);
    expect(s.peakToPeak).toBe(2000); expect(s.arrivalHz).toBeCloseTo(20, 6); expect(s.verdict).toBe('SIGNAL_VARIES');
  });
  it('lists real gaps and never fills them', () => {
    const s = hardwareStats([mk(0, 1000), mk(50, 1500), mk(2050, 1800)]);
    expect(s.gaps).toHaveLength(1); expect(s.gaps[0].seconds).toBe(2); expect(s.verdict).toBe('GAPS_PRESENT');
  });
  it('flags the sketch lead-off fallback value without calling it a diagnosis', () => {
    expect(hardwareStats([mk(0, 2048), mk(50, 2048), mk(100, 2048)]).verdict).toBe('FLAT_OR_LEADS_OFF');
    expect(hardwareStats([]).verdict).toBe('NO_DATA');
  });
});
