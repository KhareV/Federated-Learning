import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { LiveModel } from '../live-model';
import { LiveEventError, SequenceError, SequenceTracker, parseLiveEvent } from '../events';
import { DEFAULT_CAPACITY, RollingWaveform, WaveformContinuityError } from '../waveform';
import { ev, resetSeq } from './support';

function repoRoot(start: string): string {
	let dir = start;
	for (let i = 0; i < 10; i += 1) {
		try {
			readFileSync(path.join(dir, 'reports/capstone/cap_004/canonical_event_stream_run_1.jsonl'));
			return dir;
		} catch {
			dir = path.dirname(dir);
		}
	}
	throw new Error('repo root not found');
}
// The REAL canonical CAP-004 live stream (3157 PRODUCT_LIVE_EVENT_V1 events, MIXED scenario).
const STREAM = readFileSync(
	path.join(repoRoot(__dirname), 'reports/capstone/cap_004/canonical_event_stream_run_1.jsonl'),
	'utf-8'
)
	.trim()
	.split('\n')
	.map((line) => JSON.parse(line));

describe('LiveModel on the real canonical MIXED stream', () => {
	const model = new LiveModel('S');
	let maxBuffered = 0;
	for (const raw of STREAM) {
		expect(model.applyRaw(raw)).toBe(true);
		maxBuffered = Math.max(maxBuffered, model.waveform.length);
	}

	it('consumes every event kind with a contiguous sequence', () => {
		expect(model.eventCount).toBe(3157);
		expect(model.countsByType).toEqual({
			'waveform.chunk': 2880, 'quality.status': 93, 'context.snapshot': 86, 'inference.result': 86,
			'device.status': 6, 'session.status': 3, 'monitoring.state': 3
		});
		expect(model.tracker.expected).toBe(3157);
		expect(model.streamError).toBeNull();
		expect(model.sessionState).toBe('COMPLETED');
	});
	it('records 93 windows as 86 VALID / 7 UNUSABLE and 86 inference results', () => {
		expect(model.qualityCounts).toEqual({ VALID: 86, DEGRADED: 0, UNUSABLE: 7 });
		expect(model.inferenceCount).toBe(86);
		expect([...model.modelIds]).toEqual(['MODEL_V2_FINAL']);
		expect([...model.calibrationIds]).toEqual(['CAL_V2']);
	});
	it('shows ONLY backend monitoring.state changes: normal -> context unavailable -> normal', () => {
		expect(model.monitoringChanges.map((c) => c.state)).toEqual([
			'NORMAL_MONITORED_PATTERN', 'CONTEXT_UNAVAILABLE', 'NORMAL_MONITORED_PATTERN'
		]);
		expect(model.monitoringChanges.map((c) => c.sequence_index)).toEqual([101, 663, 1324]);
		expect(model.monitoringChanges.some((c) => c.state === 'RECHECK_SENSOR')).toBe(false);
		expect(model.monitoringChanges.some((c) => c.state === 'POTENTIAL_ECTOPY_ASSOCIATED_PATTERN')).toBe(false);
	});
	it('observes the canonical outage as the gap [118800, 124199]', () => {
		expect(model.gaps).toEqual([{ start: 118800, end: 124199 }]);
	});
	it('keeps the rolling waveform buffer bounded (never all 2880 chunks)', () => {
		expect(model.waveform.totalSamples).toBe(2880 * 60);
		expect(maxBuffered).toBeLessThanOrEqual(DEFAULT_CAPACITY);
		expect(model.waveform.length).toBe(DEFAULT_CAPACITY);
	});
	it('replay from sequence 0 is deterministic: reset + replay rebuilds identical state (no double counting)', () => {
		const summary = (m: LiveModel) =>
			JSON.stringify([m.eventCount, m.countsByType, m.qualityCounts, m.monitoringChanges, m.gaps, m.waveform.segments().length, m.sessionState, m.inferenceCount]);
		const before = summary(model);
		model.reset();
		expect(model.eventCount).toBe(0);
		for (const raw of STREAM) model.applyRaw(raw);
		expect(summary(model)).toBe(before);
	});
});

describe('product monitoring state is never fabricated from quality / 422-style windows', () => {
	it('quality UNUSABLE with no monitoring.state event leaves the monitoring state untouched', () => {
		resetSeq();
		const m = new LiveModel('SESS-1');
		m.applyRaw(ev('session.status', { session_state: 'MONITORING', elapsed_ms: 0, reason_code: null }));
		m.applyRaw(ev('quality.status', { ecg_quality: 'UNUSABLE', ppg_quality: null, ui_label: 'Recheck Sensor' }, { ts: 5_000_000 }));
		expect(m.latestQuality?.ecg_quality).toBe('UNUSABLE');
		expect(m.latestQuality?.ui_label).toBe('Recheck Sensor');
		expect(m.monitoringState).toBeNull();
		expect(m.monitoringChanges).toEqual([]);
		expect(m.inferenceIsCurrent).toBe(false);
	});
	it('after a real NORMAL state, an UNUSABLE window does not change it to RECHECK_SENSOR', () => {
		resetSeq();
		const m = new LiveModel('SESS-1');
		m.applyRaw(ev('monitoring.state', { monitoring_state: 'NORMAL_MONITORED_PATTERN', previous_state: null, reason_code: null }));
		m.applyRaw(ev('quality.status', { ecg_quality: 'UNUSABLE', ppg_quality: null, ui_label: 'Recheck Sensor' }, { ts: 9 }));
		expect(m.monitoringState).toBe('NORMAL_MONITORED_PATTERN');
		m.applyRaw(ev('monitoring.state', { monitoring_state: 'RECHECK_SENSOR', previous_state: 'NORMAL_MONITORED_PATTERN', reason_code: 'QUALITY' }));
		expect(m.monitoringState).toBe('RECHECK_SENSOR'); // only because the BACKEND sent it
	});
});

describe('context and inference are never shown as current when stale', () => {
	const q = (m: LiveModel, quality: 'VALID' | 'UNUSABLE', ts: number) => m.applyRaw(ev('quality.status', { ecg_quality: quality, ppg_quality: null, ui_label: quality === 'VALID' ? 'Signal Good' : 'Recheck Sensor' }, { ts }));
	const ctx = (m: LiveModel, ts: number, available = true) => m.applyRaw(ev('context.snapshot', available ? { hr_ecg_bpm: 71, pr_ppg_bpm: 70, spo2_pct: 98, spo2_valid: true, context_available: true, ppg_quality: 'VALID' } : { hr_ecg_bpm: 70, pr_ppg_bpm: null, spo2_pct: null, spo2_valid: false, context_available: false, ppg_quality: null }, { ts }));
	const inf = (m: LiveModel, ts: number) => m.applyRaw(ev('inference.result', { timestamp_us: ts, model_id: 'MODEL_V2_FINAL', calibration_id: 'CAL_V2', calibration_domain: 'D', preprocess_version: 'PREPROC_V1', alert_policy_id: 'ALERT_POLICY_V1', ecg_quality: 'VALID', monitoring_state: 'NORMAL_MONITORED_PATTERN', context: null, latency_ms: 1, raw_probability: 0.1, source_domain_calibrated_probability: 0.1, threshold: 0.6, probability_role: 'RESEARCH_TECHNICAL_METADATA' }, { ts }));
	it('a window waiting for its follow-ups is PENDING (previous values are not current, but no false "unavailable")', () => {
		resetSeq();
		const m = new LiveModel('SESS-1');
		q(m, 'VALID', 100);
		expect(m.contextState).toBe('PENDING'); expect(m.inferenceState).toBe('PENDING');
		ctx(m, 100); expect(m.contextState).toBe('CURRENT'); expect(m.inferenceState).toBe('PENDING');
		inf(m, 100); expect(m.inferenceState).toBe('CURRENT');
	});
	it('an UNUSABLE window settles immediately: earlier context is unavailable, earlier inference is "none for window"', () => {
		resetSeq();
		const m = new LiveModel('SESS-1');
		q(m, 'VALID', 100); ctx(m, 100); inf(m, 100);
		q(m, 'UNUSABLE', 200);
		expect(m.contextState).toBe('UNAVAILABLE');
		expect(m.inferenceState).toBe('NONE_FOR_WINDOW');
		expect(m.contextIsCurrent).toBe(false);
		expect(m.latestContext?.spo2_pct).toBe(98); // retained internally, never presented as current
	});
	it('context_available=false is unavailable even for the latest window', () => {
		resetSeq();
		const m = new LiveModel('SESS-1');
		q(m, 'VALID', 1); ctx(m, 1, false);
		expect(m.contextState).toBe('UNAVAILABLE');
	});
	it('on the real canonical stream the settled states match: 7 UNUSABLE windows end as NONE_FOR_WINDOW, never CURRENT', () => {
		const m = new LiveModel('S');
		const settled: string[] = [];
		for (const raw of STREAM) {
			m.applyRaw(raw);
			if (raw.event_type === 'quality.status' && raw.payload.ecg_quality === 'UNUSABLE') settled.push(`${m.contextState}/${m.inferenceState}`);
		}
		expect(settled).toEqual(Array(7).fill('UNAVAILABLE/NONE_FOR_WINDOW'));
	});
});

describe('typed PRODUCT_LIVE_EVENT_V1 union and sequence integrity', () => {
	const ok = () => ev('session.status', { session_state: 'MONITORING', elapsed_ms: 0, reason_code: null }, { seq: 0 });
	it('accepts a valid event and rejects malformed / foreign payloads visibly', () => {
		expect(parseLiveEvent(ok()).event_type).toBe('session.status');
		const bad: unknown[] = [
			null, 'x', { ...ok(), contract_version: 'PRODUCT_LIVE_EVENT_V2' },
			{ ...ok(), event_type: 'federation.status' }, { ...ok(), event_type: 'not.a.kind' },
			{ ...ok(), sequence_index: -1 }, { ...ok(), payload: { session_state: 'HEALTHY', elapsed_ms: 0, reason_code: null } },
			{ ...ok(), payload: null }
		];
		for (const raw of bad) expect(() => parseLiveEvent(raw)).toThrow(LiveEventError);
	});
	it('rejects an unavailable context that carries PPG values and a mismatched waveform count', () => {
		const ctx = ev('context.snapshot', { hr_ecg_bpm: 70, pr_ppg_bpm: 71, spo2_pct: null, spo2_valid: false, context_available: false, ppg_quality: null }, { seq: 1 });
		expect(() => parseLiveEvent(ctx)).toThrow(LiveEventError);
		const wf = ev('waveform.chunk', { channel: 'ECG', unit: 'ADC_COUNTS', source_rate_hz: 360, first_sample_index: 0, first_sample_timestamp_us: 0, sample_count: 3, samples: [1, 2] }, { seq: 2 });
		expect(() => parseLiveEvent(wf)).toThrow(LiveEventError);
	});
	it('requires next = previous + 1 and flags gaps and duplicates', () => {
		const t = new SequenceTracker();
		t.accept(0); t.accept(1);
		expect(() => t.accept(3)).toThrow(SequenceError);
		expect(() => t.accept(1)).toThrow(SequenceError);
		try { t.accept(5); } catch (e) { expect((e as SequenceError).kind).toBe('GAP'); }
		try { t.accept(0); } catch (e) { expect((e as SequenceError).kind).toBe('DUPLICATE'); }
	});
	it('a sequence gap puts the model into a visible PRODUCT STREAM ERROR and stops consuming', () => {
		resetSeq();
		const m = new LiveModel('SESS-1');
		expect(m.applyRaw(ev('session.status', { session_state: 'MONITORING', elapsed_ms: 0, reason_code: null }))).toBe(true);
		expect(m.applyRaw(ev('device.status', { device_id: 'D', device_state: 'STREAMING', adapter_type: 'SIMULATED', reason_code: null, recoverable: true }, { seq: 5 }))).toBe(false);
		expect(m.streamError?.kind).toBe('SEQUENCE_GAP');
		expect(m.streamError?.message).toContain('PRODUCT STREAM ERROR');
		expect(m.deviceState).toBeNull(); // the missing/late event was not fabricated or applied
		expect(m.applyRaw(ev('session.status', { session_state: 'COMPLETED', elapsed_ms: 1, reason_code: null }, { seq: 1 }))).toBe(false);
	});
	it('rejects an event from another session and a federation event on the monitoring socket', () => {
		resetSeq();
		const m = new LiveModel('SESS-1');
		expect(m.applyRaw(ev('session.status', { session_state: 'MONITORING', elapsed_ms: 0, reason_code: null }, { session: 'OTHER' }))).toBe(false);
		expect(m.streamError?.kind).toBe('FOREIGN_SESSION');
		const fed = new LiveModel('SESS-1');
		expect(fed.applyRaw({ ...ok(), event_type: 'federation.status' })).toBe(false);
		expect(fed.streamError?.kind).toBe('MALFORMED_EVENT');
	});
	it('system.error is kept as a technical error, not a monitoring state', () => {
		resetSeq();
		const m = new LiveModel('SESS-1');
		m.applyRaw(ev('system.error', { error_code: 'INFERENCE_FAILED', message: 'boom', recoverable: false, origin: 'INFERENCE' }));
		expect(m.systemErrors).toHaveLength(1);
		expect(m.monitoringState).toBeNull();
	});
});

describe('RollingWaveform: bounded, null gaps stay gaps', () => {
	it('never grows past capacity and drops the oldest samples', () => {
		const w = new RollingWaveform(100);
		for (let i = 0; i < 50; i += 1) w.push(i * 10, Array.from({ length: 10 }, (_, k) => i * 10 + k));
		expect(w.length).toBe(100);
		expect(w.start).toBe(400);
		expect(w.end).toBe(500);
	});
	it('keeps null as a gap: never zero-filled, never interpolated, separate segments', () => {
		const w = new RollingWaveform(1000);
		w.push(0, [5, 6, null, null, null, 9, 10]);
		expect(w.segments()).toEqual([{ start: 0, values: [5, 6] }, { start: 5, values: [9, 10] }]);
		expect(w.gaps).toEqual([{ start: 2, end: 4 }]);
		expect(w.nullCountInWindow()).toBe(3);
		expect(w.segments().flatMap((s) => s.values)).not.toContain(0);
	});
	it('tracks an open gap and refuses an index discontinuity instead of fabricating samples', () => {
		const w = new RollingWaveform(1000);
		w.push(0, [1, null, null]);
		expect(w.openGap).toEqual({ start: 1, end: 2 });
		expect(() => w.push(10, [1])).toThrow(WaveformContinuityError);
	});
});
