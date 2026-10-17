// Recorded-hardware views of the Observatory: strict parsing of the new payloads and the capability-gated session list.
import { describe, expect, it } from 'vitest';
import { parseHardwareTimeline } from '../history/types';
import { parseHardwareWindowList, parseWindowTrace } from '../observatory/types';
import { loadHardwareSessions, observatoryReady } from '../hardware-sessions';

const BOUNDARY = 'RECORDED_HARDWARE_RESAMPLED_EXPERIMENTAL_DERIVED_TIMELINE_NOT_VALID_NOT_DIAGNOSTIC';
const timeline = (over: Record<string, unknown> = {}) => ({
	session_id: 'HW-1', timeline_version: 'CAPSTONE_SESSION_TIMELINE_V1', device_lifecycle: [], waveform_previews: [],
	time_domains: { source_timeline: 'SOURCE_TIMELINE', device_lifecycle: 'PRODUCT_CLOCK' }, time_domain_explanation: 'x', claim_boundary: BOUNDARY, label: 'EXPERIMENTAL', source_kind: 'RECORDED_HARDWARE_RESAMPLED',
	assumptions: { adc_scaling: 'unverified' }, windows_total: 3, windows_scored: 2, windows_pending: 0, windows_unusable: 1, unusable_reasons: { LONG_GAP_SPAN: 1, FLATLINE: 1 }, complete: true,
	source_timeline: [
		{ kind: 'QUALITY_CHANGE', sequence_index: 0, source_timestamp_us: 15e6, payload: { ecg_quality: 'VALID', ppg_quality: null, storage_basis: 'CHANGE_ONLY' } },
		{ kind: 'INFERENCE', sequence_index: 1, source_timestamp_us: 15e6, payload: { model_id: 'MODEL_V2_FINAL', calibration_domain: 'D', ecg_quality: 'VALID', monitoring_state: 'NORMAL_MONITORED_PATTERN', raw_probability: 0.2, source_domain_calibrated_probability: 0.1, threshold: 0.35, latency_ms: 3, probability_role: 'RESEARCH_TECHNICAL_METADATA' } },
		{ kind: 'MONITORING_STATE_CHANGE', sequence_index: 2, source_timestamp_us: 15e6, payload: { monitoring_state: 'NORMAL_MONITORED_PATTERN', previous_state: null, reason_code: 'DERIVED_FROM_CONSECUTIVE_WINDOW_RESULTS' } }
	], ...over
});

describe('recorded-hardware timeline', () => {
	it('parses the derived replay timeline with its progress counters', () => {
		const t = parseHardwareTimeline(timeline());
		expect(t).toMatchObject({ windows_total: 3, windows_scored: 2, windows_unusable: 1, complete: true, claim_boundary: BOUNDARY });
		expect(t.source_timeline.map((i) => i.kind)).toEqual(['QUALITY_CHANGE', 'INFERENCE', 'MONITORING_STATE_CHANGE']);
	});
	it('carries the quality-gate rejection reasons, and an older response without them parses as none', () => {
		expect(parseHardwareTimeline(timeline()).unusable_reasons).toEqual({ LONG_GAP_SPAN: 1, FLATLINE: 1 });
		const { unusable_reasons: _drop, ...older } = timeline() as Record<string, unknown>;
		expect(parseHardwareTimeline(older).unusable_reasons).toEqual({});
	});
	it('rejects a timeline that claims persisted-session evidence, a wrong source kind, or an unknown field', () => {
		expect(() => parseHardwareTimeline(timeline({ claim_boundary: 'PERSISTED_RESEARCH_ENGINEERING_EVIDENCE_NOT_WEBSOCKET_REPLAY' }))).toThrow();
		expect(() => parseHardwareTimeline(timeline({ source_kind: 'SYNTHETIC_VIRTUAL_WEARABLE' }))).toThrow();
		expect(() => parseHardwareTimeline(timeline({ extra: 1 }))).toThrow();
	});
});

describe('recorded-hardware windows', () => {
	it('parses the emitted window list and refuses a malformed one', () => {
		const list = { session_id: 'HW-1', label: 'L', source_kind: 'RECORDED_HARDWARE_RESAMPLED', claim_boundary: 'B', input_readings: 4800, assumptions: { adc_scaling: 'x', runtime_counts_per_adc_count: 8.06 },
			windows: [{ window_index: 0, window_id: 'HW-1-W0000', right_timestamp_us: 15e6, ecg_quality: 'VALID', quality_reasons: [] }] };
		expect(parseHardwareWindowList(list).windows[0].window_id).toBe('HW-1-W0000');
		expect(() => parseHardwareWindowList({ ...list, source_kind: 'X' })).toThrow();
		expect(() => parseHardwareWindowList({ ...list, windows: [{ window_index: 'a' }] })).toThrow();
	});
	it('the window trace parser now accepts the recorded-hardware classification and source, and nothing else new', () => {
		const stage = { stage_id: 'SOURCE_OBSERVED', unit: 'u', sample_rate_hz: 360, actual_point_count: 1, displayed_point_count: 1, display_is_decimated: false, points: [{ timestamp_us: 0, value: 1, source_index: 0 }] };
		const trace = { trace_version: 'NHM_PIPELINE_TRACE_V1', classification: 'RECORDED_HARDWARE_RECONSTRUCTION', source_kind: 'RECORDED_HARDWARE_RESAMPLED', scenario_id: 'RECORDED_HARDWARE:HW-1', session_id: 'HW-1', window_index: 0, window_id: 'w',
			left_timestamp_us: 5e6, right_timestamp_us: 15e6, source_rate_hz: 360, target_rate_hz: 250, window_sample_count: 2500, cadence_us: 5e6, quality_state: 'VALID', quality_reasons: [], missing_slots: 0, context_available: true, gaps: [], stages: [stage],
			normalization: { status: 'NOT_APPLIED_UNUSABLE', identity: 'i', mean: null, std: null, epsilon: 1e-6, shape: null, dtype: null, tensor_sha256: null }, persisted_inference: null, inference_evidence_status: 'S', claim_boundary: 'C', limitations: ['l'] };
		expect(parseWindowTrace(trace).source_kind).toBe('RECORDED_HARDWARE_RESAMPLED');
		expect(() => parseWindowTrace({ ...trace, source_kind: 'SOMETHING_ELSE' })).toThrow();
		expect(() => parseWindowTrace({ ...trace, classification: 'MADE_UP' })).toThrow();
	});
});

describe('hardware session list', () => {
	const session = (over: Record<string, unknown>) => ({ session_id: 'HW-1', status: 'STOPPED', record_count: 10, summary: { stored_readings: 10 }, ...over }) as never;
	it('asks for hardware sessions only when the backend advertises the source (no avoidable 404)', async () => {
		let asked = 0;
		const api = (available: boolean) => ({ studioCapabilities: () => Promise.resolve({ hardware_demo: { available } } as never), hardwareSessions: () => { asked++; return Promise.resolve([session({})]); } });
		expect(await loadHardwareSessions(api(false))).toEqual([]);
		expect(asked).toBe(0);
		expect(await loadHardwareSessions(api(true))).toHaveLength(1);
		expect(await loadHardwareSessions({ studioCapabilities: () => Promise.reject(new Error('x')), hardwareSessions: () => Promise.resolve([]) })).toEqual([]);
	});
	it('only a finished session with stored readings is offered to the Observatory', () => {
		expect(observatoryReady(session({}))).toBe(true);
		expect(observatoryReady(session({ status: 'ACTIVE' }))).toBe(false);
		expect(observatoryReady(session({ summary: { stored_readings: 0 } }))).toBe(false);
	});
});
