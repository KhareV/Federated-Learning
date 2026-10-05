// CAPSTONE_MONITORING_STORE_V1 (part): bounded rolling ECG display buffer for the 360 Hz
// ADC_COUNTS source-waveform transport. null samples are source gaps: they stay gaps (never 0,
// never interpolated, never flat-lined). The buffer never grows past `capacity` samples.

export const SOURCE_RATE_HZ = 360;
export const DISPLAY_SECONDS = 10;
export const DEFAULT_CAPACITY = SOURCE_RATE_HZ * DISPLAY_SECONDS;

export interface GapRun {
	start: number; // inclusive source sample index
	end: number; // inclusive source sample index
}

export interface WaveformSegment {
	/** source sample index of the first point in this contiguous non-null run */
	start: number;
	values: number[];
}

export class WaveformContinuityError extends Error {
	constructor(
		readonly expected: number,
		readonly received: number
	) {
		super(`WAVEFORM_INDEX_DISCONTINUITY (expected ${expected}, received ${received})`);
		this.name = 'WaveformContinuityError';
	}
}

export class RollingWaveform {
	private samples: (number | null)[] = [];
	private firstIndex = 0; // source index of samples[0]
	private nextIndex = 0;
	private openGapStart: number | null = null;
	/** every null run observed this session (bounded by the number of outages, not by time) */
	readonly gaps: GapRun[] = [];
	totalSamples = 0;

	constructor(readonly capacity: number = DEFAULT_CAPACITY) {}

	get length(): number {
		return this.samples.length;
	}
	get start(): number {
		return this.firstIndex;
	}
	get end(): number {
		return this.nextIndex;
	}

	push(firstSampleIndex: number, chunk: readonly (number | null)[]): void {
		if (firstSampleIndex !== this.nextIndex) {
			throw new WaveformContinuityError(this.nextIndex, firstSampleIndex);
		}
		for (let i = 0; i < chunk.length; i += 1) {
			const value = chunk[i];
			const index = firstSampleIndex + i;
			if (value === null) {
				if (this.openGapStart === null) this.openGapStart = index;
			} else if (this.openGapStart !== null) {
				this.gaps.push({ start: this.openGapStart, end: index - 1 });
				this.openGapStart = null;
			}
			this.samples.push(value);
		}
		this.nextIndex = firstSampleIndex + chunk.length;
		this.totalSamples += chunk.length;
		const overflow = this.samples.length - this.capacity;
		if (overflow > 0) {
			this.samples.splice(0, overflow);
			this.firstIndex += overflow;
		}
	}

	/** Gap currently in progress (the last samples are null), if any. */
	get openGap(): GapRun | null {
		return this.openGapStart === null ? null : { start: this.openGapStart, end: this.nextIndex - 1 };
	}

	/** Contiguous non-null runs inside the display window; nulls separate segments. */
	segments(): WaveformSegment[] {
		const out: WaveformSegment[] = [];
		let current: WaveformSegment | null = null;
		for (let i = 0; i < this.samples.length; i += 1) {
			const value = this.samples[i];
			if (value === null) {
				current = null;
			} else {
				if (!current) {
					current = { start: this.firstIndex + i, values: [] };
					out.push(current);
				}
				current.values.push(value);
			}
		}
		return out;
	}

	nullCountInWindow(): number {
		let count = 0;
		for (const value of this.samples) if (value === null) count += 1;
		return count;
	}

	reset(): void {
		this.samples = [];
		this.firstIndex = 0;
		this.nextIndex = 0;
		this.openGapStart = null;
		this.gaps.length = 0;
		this.totalSamples = 0;
	}
}
