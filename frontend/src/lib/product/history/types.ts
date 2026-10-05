import { array, bool, fields, integer, literal, nullable, number, object, string } from '../evidence-validation';

export interface SessionSummary {
	session_id: string; summary_version: 'SESSION_SUMMARY_V1_INFERRED_WINDOWS';
	duration_ms: number; duration_basis: 'PRODUCT_LIFECYCLE_CLOCK';
	windows_inferred: number; windows_inferred_basis: 'PERSISTED_INFERENCE_EVENTS';
	state_counts: Record<string, number>; state_counts_basis: 'PERSISTED_INFERENCE_EVENTS';
	quality_counts: Record<string, number>; quality_counts_basis: 'PERSISTED_INFERENCE_EVENTS';
	hr_min: number | null; hr_mean: number | null; hr_max: number | null;
	spo2_min: number | null; spo2_mean: number | null; spo2_max: number | null;
	reconnect_count: number; disconnect_count: number; generated_at_us: number;
	claim_boundary: 'PERSISTED_RESEARCH_ENGINEERING_SESSION_SUMMARY_NOT_CLINICAL';
}

function counts(value: unknown, label: string): Record<string, number> {
	const source = object(value, label);
	return Object.fromEntries(Object.entries(source).map(([key, val]) => [key, integer(val, `${label}.${key}`)]));
}

export function parseSessionSummary(value: unknown): SessionSummary {
	const o = object(value, 'summary');
	fields(o, ['session_id','summary_version','duration_ms','duration_basis','windows_inferred',
		'windows_inferred_basis','state_counts','state_counts_basis','quality_counts','quality_counts_basis',
		'hr_min','hr_mean','hr_max','spo2_min','spo2_mean','spo2_max','reconnect_count',
		'disconnect_count','generated_at_us','claim_boundary'], 'summary');
	return {
		session_id: string(o.session_id, 'session_id'),
		summary_version: literal(o.summary_version, 'SESSION_SUMMARY_V1_INFERRED_WINDOWS', 'summary_version'),
		duration_ms: integer(o.duration_ms, 'duration_ms'),
		duration_basis: literal(o.duration_basis, 'PRODUCT_LIFECYCLE_CLOCK', 'duration_basis'),
		windows_inferred: integer(o.windows_inferred, 'windows_inferred'),
		windows_inferred_basis: literal(o.windows_inferred_basis, 'PERSISTED_INFERENCE_EVENTS', 'windows_inferred_basis'),
		state_counts: counts(o.state_counts, 'state_counts'),
		state_counts_basis: literal(o.state_counts_basis, 'PERSISTED_INFERENCE_EVENTS', 'state_counts_basis'),
		quality_counts: counts(o.quality_counts, 'quality_counts'),
		quality_counts_basis: literal(o.quality_counts_basis, 'PERSISTED_INFERENCE_EVENTS', 'quality_counts_basis'),
		hr_min: nullable(o.hr_min, number, 'hr_min'), hr_mean: nullable(o.hr_mean, number, 'hr_mean'),
		hr_max: nullable(o.hr_max, number, 'hr_max'),
		spo2_min: nullable(o.spo2_min, number, 'spo2_min'), spo2_mean: nullable(o.spo2_mean, number, 'spo2_mean'),
		spo2_max: nullable(o.spo2_max, number, 'spo2_max'),
		reconnect_count: integer(o.reconnect_count, 'reconnect_count'),
		disconnect_count: integer(o.disconnect_count, 'disconnect_count'),
		generated_at_us: integer(o.generated_at_us, 'generated_at_us'),
		claim_boundary: literal(o.claim_boundary, 'PERSISTED_RESEARCH_ENGINEERING_SESSION_SUMMARY_NOT_CLINICAL', 'claim_boundary')
	};
}

export type SourceKind = 'INFERENCE' | 'MONITORING_STATE_CHANGE' | 'QUALITY_CHANGE' | 'CONTEXT_SNAPSHOT';
export interface SourceTimelineItem {
	kind: SourceKind; sequence_index: number; source_timestamp_us: number;
	payload: Record<string, string | number | boolean | null>;
}
export interface DeviceLifecycleItem {
	event_type: string; device_state: string; reason_code: string | null;
	recoverable: boolean | null; at_us: number; time_domain: 'PRODUCT_CLOCK';
}
export interface WaveformPreview {
	channel: string; source_rate_hz: number; decimation_factor: number;
	point_count: number; start_timestamp_us: number; points: (number | null)[];
	claim_boundary: 'BOUNDED_DECIMATED_PREVIEW_NOT_RAW_STREAM_STORAGE';
}
export interface SessionTimeline {
	session_id: string; timeline_version: 'CAPSTONE_SESSION_TIMELINE_V1';
	source_timeline: SourceTimelineItem[]; device_lifecycle: DeviceLifecycleItem[];
	waveform_previews: WaveformPreview[];
	time_domains: { source_timeline: 'SOURCE_TIMELINE'; device_lifecycle: 'PRODUCT_CLOCK' };
	time_domain_explanation: string;
	claim_boundary: 'PERSISTED_RESEARCH_ENGINEERING_EVIDENCE_NOT_WEBSOCKET_REPLAY';
}

const PAYLOAD: Record<SourceKind, Record<string, 'string' | 'number' | 'boolean'>> = {
	INFERENCE: { model_id: 'string', calibration_domain: 'string', ecg_quality: 'string',
		monitoring_state: 'string', raw_probability: 'number', source_domain_calibrated_probability: 'number',
		threshold: 'number', latency_ms: 'number', probability_role: 'string' },
	MONITORING_STATE_CHANGE: { monitoring_state: 'string', previous_state: 'string', reason_code: 'string' },
	QUALITY_CHANGE: { ecg_quality: 'string', ppg_quality: 'string', storage_basis: 'string' },
	CONTEXT_SNAPSHOT: { hr_ecg_bpm: 'number', pr_ppg_bpm: 'number', spo2_pct: 'number',
		spo2_valid: 'boolean', context_available: 'boolean', ppg_quality: 'string' }
};

function sourceItem(value: unknown, label: string): SourceTimelineItem {
	const o = object(value, label);
	fields(o, ['kind','sequence_index','source_timestamp_us','payload'], label);
	const kind = string(o.kind, `${label}.kind`);
	if (!(kind in PAYLOAD)) throw new Error(`MALFORMED_EVIDENCE:${label}:kind`);
	const typedKind = kind as SourceKind;
	const p = object(o.payload, `${label}.payload`);
	fields(p, Object.keys(PAYLOAD[typedKind]), `${label}.payload`);
	const payload: SourceTimelineItem['payload'] = {};
	for (const [key, expected] of Object.entries(PAYLOAD[typedKind])) {
		const v = p[key];
		payload[key] = v === null ? null : expected === 'number' ? number(v, key)
			: expected === 'boolean' ? bool(v, key) : string(v, key);
	}
	if (typedKind === 'INFERENCE') literal(payload.probability_role, 'RESEARCH_TECHNICAL_METADATA', 'probability_role');
	if (typedKind === 'QUALITY_CHANGE') literal(payload.storage_basis, 'CHANGE_ONLY', 'storage_basis');
	return { kind: typedKind, sequence_index: integer(o.sequence_index, `${label}.sequence_index`),
		source_timestamp_us: integer(o.source_timestamp_us, `${label}.source_timestamp_us`), payload };
}

function lifecycle(value: unknown, label: string): DeviceLifecycleItem {
	const o = object(value, label);
	fields(o, ['event_type','device_state','reason_code','recoverable','at_us','time_domain'], label);
	return { event_type: string(o.event_type, 'event_type'), device_state: string(o.device_state, 'device_state'),
		reason_code: nullable(o.reason_code, string, 'reason_code'),
		recoverable: nullable(o.recoverable, bool, 'recoverable'), at_us: integer(o.at_us, 'at_us'),
		time_domain: literal(o.time_domain, 'PRODUCT_CLOCK', 'time_domain') };
}

function preview(value: unknown, label: string): WaveformPreview {
	const o = object(value, label);
	fields(o, ['channel','source_rate_hz','decimation_factor','point_count','start_timestamp_us',
		'points','claim_boundary'], label);
	const points = array(o.points, (v, l) => nullable(v, integer, l), `${label}.points`);
	const count = integer(o.point_count, 'point_count');
	if (count !== points.length || count > 4000) throw new Error('MALFORMED_EVIDENCE:preview:bound');
	return { channel: string(o.channel, 'channel'), source_rate_hz: integer(o.source_rate_hz, 'source_rate_hz'),
		decimation_factor: integer(o.decimation_factor, 'decimation_factor'), point_count: count,
		start_timestamp_us: integer(o.start_timestamp_us, 'start_timestamp_us'), points,
		claim_boundary: literal(o.claim_boundary, 'BOUNDED_DECIMATED_PREVIEW_NOT_RAW_STREAM_STORAGE', 'preview.claim_boundary') };
}

export function parseSessionTimeline(value: unknown): SessionTimeline {
	const o = object(value, 'timeline');
	fields(o, ['session_id','timeline_version','source_timeline','device_lifecycle','waveform_previews',
		'time_domains','time_domain_explanation','claim_boundary'], 'timeline');
	const domains = object(o.time_domains, 'time_domains');
	fields(domains, ['source_timeline','device_lifecycle'], 'time_domains');
	const sources = array(o.source_timeline, sourceItem, 'source_timeline');
	for (let i = 1; i < sources.length; i++)
		if (sources[i].sequence_index < sources[i - 1].sequence_index)
			throw new Error('MALFORMED_EVIDENCE:timeline:order');
	return { session_id: string(o.session_id, 'session_id'),
		timeline_version: literal(o.timeline_version, 'CAPSTONE_SESSION_TIMELINE_V1', 'timeline_version'),
		source_timeline: sources, device_lifecycle: array(o.device_lifecycle, lifecycle, 'device_lifecycle'),
		waveform_previews: array(o.waveform_previews, preview, 'waveform_previews'),
		time_domains: { source_timeline: literal(domains.source_timeline, 'SOURCE_TIMELINE', 'source_timeline'),
			device_lifecycle: literal(domains.device_lifecycle, 'PRODUCT_CLOCK', 'device_lifecycle') },
		time_domain_explanation: string(o.time_domain_explanation, 'time_domain_explanation'),
		claim_boundary: literal(o.claim_boundary, 'PERSISTED_RESEARCH_ENGINEERING_EVIDENCE_NOT_WEBSOCKET_REPLAY', 'timeline.claim_boundary') };
}
