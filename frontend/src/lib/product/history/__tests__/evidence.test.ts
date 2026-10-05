import { describe, expect, it } from 'vitest';
import { parseSessionSummary, parseSessionTimeline } from '../types';

const summary = {
	session_id: 'S', summary_version: 'SESSION_SUMMARY_V1_INFERRED_WINDOWS',
	duration_ms: 5999, duration_basis: 'PRODUCT_LIFECYCLE_CLOCK', windows_inferred: 1,
	windows_inferred_basis: 'PERSISTED_INFERENCE_EVENTS', state_counts: { NORMAL_MONITORED_PATTERN: 1 },
	state_counts_basis: 'PERSISTED_INFERENCE_EVENTS', quality_counts: { VALID: 1 },
	quality_counts_basis: 'PERSISTED_INFERENCE_EVENTS', hr_min: null, hr_mean: null, hr_max: null,
	spo2_min: null, spo2_mean: null, spo2_max: null, reconnect_count: 0, disconnect_count: 0,
	generated_at_us: 12_000_000,
	claim_boundary: 'PERSISTED_RESEARCH_ENGINEERING_SESSION_SUMMARY_NOT_CLINICAL'
};
const timeline = {
	session_id: 'S', timeline_version: 'CAPSTONE_SESSION_TIMELINE_V1',
	source_timeline: [{ kind: 'QUALITY_CHANGE', sequence_index: 2, source_timestamp_us: 50_000_000,
		payload: { ecg_quality: 'UNUSABLE', ppg_quality: null, storage_basis: 'CHANGE_ONLY' } }],
	device_lifecycle: [{ event_type: 'DEVICE_DISCONNECTED', device_state: 'DISCONNECTED',
		reason_code: null, recoverable: true, at_us: 12_000_000, time_domain: 'PRODUCT_CLOCK' }],
	waveform_previews: [{ channel: 'ECG', source_rate_hz: 360, decimation_factor: 3,
		point_count: 3, start_timestamp_us: 49_000_000, points: [12, null, -3],
		claim_boundary: 'BOUNDED_DECIMATED_PREVIEW_NOT_RAW_STREAM_STORAGE' }],
	time_domains: { source_timeline: 'SOURCE_TIMELINE', device_lifecycle: 'PRODUCT_CLOCK' },
	time_domain_explanation: 'Different origins.',
	claim_boundary: 'PERSISTED_RESEARCH_ENGINEERING_EVIDENCE_NOT_WEBSOCKET_REPLAY'
};

describe('CAP-009 strict history payloads', () => {
	it('accepts count/time basis and keeps preview null gaps', () => {
		expect(parseSessionSummary(summary).quality_counts).toEqual({ VALID: 1 });
		expect(parseSessionTimeline(timeline).waveform_previews[0].points).toEqual([12, null, -3]);
	});
	it('rejects all-window count or merged time domains', () => {
		expect(() => parseSessionSummary({ ...summary, windows_inferred_basis: 'ALL_WINDOWS' })).toThrow();
		expect(() => parseSessionTimeline({ ...timeline, time_domains: { source_timeline: 'PRODUCT_CLOCK', device_lifecycle: 'PRODUCT_CLOCK' } })).toThrow();
	});
	it('rejects raw context and preview gap replacement', () => {
		expect(() => parseSessionTimeline({ ...timeline, source_timeline: [{ ...timeline.source_timeline[0], payload: { ...timeline.source_timeline[0].payload, context_json: '{"secret":1}' } }] })).toThrow();
		expect(() => parseSessionTimeline({ ...timeline, waveform_previews: [{ ...timeline.waveform_previews[0], point_count: 4 }] })).toThrow();
	});
});
