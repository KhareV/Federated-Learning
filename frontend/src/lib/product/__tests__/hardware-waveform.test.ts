import { describe, expect, it } from 'vitest';
import { hardwareWaveform } from '../hardware-waveform';
import type { HardwareReading } from '../api';

const at = (id: string, ecg: number, ms: number): HardwareReading => ({
  id, ecg, ordinal: Number(id), bpm: 70, spo2: 97,
  ingested_at: new Date(Date.UTC(2026, 9, 14, 0, 0, 0, ms)).toISOString(), collection: 'nhm_integration_test'
});

describe('actual MongoDB waveform geometry', () => {
  it('maps each injected value and timestamp exactly, without added samples', () => {
    const result = hardwareWaveform([at('1', 0, 0), at('2', 2048, 50), at('3', 4095, 100)]);
    expect(result.points.map((p) => [p.id, p.ecg, p.x])).toEqual([
      ['1', 0, 0], ['2', 2048, 500], ['3', 4095, 1000]
    ]);
    expect(result.points.map((p) => p.y)).toEqual([170, 170 - 2048 / 4095 * 150, 20]);
    expect(result.paths).toHaveLength(1);
    expect(result.paths[0]).toContain('500.0 95.0');
  });
  it('sorts delayed ingestion timestamps and breaks long gaps without flat fill', () => {
    const result = hardwareWaveform([at('3', 2200, 0), at('2', 2100, 0), {
      ...at('4', 2300, 0), ingested_at: new Date(Date.UTC(2026, 9, 14, 0, 0, 3)).toISOString()
    }]);
    expect(result.points.map((p) => p.id)).toEqual(['2', '3', '4']);
    expect(result.paths).toHaveLength(2);
    expect(result.points).toHaveLength(3);
  });
  it('shows one real point and rejects invalid chart values', () => {
    const result = hardwareWaveform([at('1', 2048, 0), at('2', Number.NaN, 50)]);
    expect(result.points).toHaveLength(1);
    expect(result.points[0].x).toBe(500);
  });
});
