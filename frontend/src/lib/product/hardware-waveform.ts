import type { HardwareReading } from './api';

export interface HardwarePlotPoint {
  id: string;
  ingested_at: string;
  ecg: number;
  x: number;
  y: number;
}

/** Exact stored ADC values against stored timestamps; no interpolation or resampling. */
export function hardwareWaveform(readings: HardwareReading[], gapMs = 1000): {
  points: HardwarePlotPoint[]; paths: string[];
} {
  const ordered = [...readings].filter((r) => Number.isFinite(r.ecg) && r.ecg >= 0 && r.ecg <= 4095 &&
    Number.isFinite(Date.parse(r.ingested_at))).sort((a, b) =>
    Date.parse(a.ingested_at) - Date.parse(b.ingested_at) || a.id.localeCompare(b.id));
  if (!ordered.length) return { points: [], paths: [] };
  const first = Date.parse(ordered[0].ingested_at);
  const last = Date.parse(ordered.at(-1)!.ingested_at);
  const span = Math.max(1, last - first);
  const points = ordered.map((r) => ({
    id: r.id, ingested_at: r.ingested_at, ecg: r.ecg,
    x: ordered.length === 1 ? 500 : (Date.parse(r.ingested_at) - first) / span * 1000,
    y: 170 - r.ecg / 4095 * 150
  }));
  const paths: string[] = [];
  let path = '';
  let previous = first;
  for (const point of points) {
    const time = Date.parse(point.ingested_at);
    if (time - previous > gapMs && path) { paths.push(path); path = ''; }
    path += `${path ? ' L' : 'M'}${point.x.toFixed(1)} ${point.y.toFixed(1)}`;
    previous = time;
  }
  if (path) paths.push(path);
  return { points, paths };
}
