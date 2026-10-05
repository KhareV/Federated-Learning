// CAPSTONE_MONITORING_STORE_V1 (part): strict PRODUCT_LIVE_EVENT_V1 parsing + sequence integrity.
// Arbitrary JSON is never cast: every event is validated field by field and rejected visibly.

import {
	DEVICE_STATES,
	MONITORING_STATE_NAMES,
	QUALITY_STATES,
	SESSION_STATES,
	type LiveEvent
} from './types';

export class LiveEventError extends Error {
	constructor(
		readonly reason: string,
		message?: string
	) {
		super(message ?? reason);
		this.name = 'LiveEventError';
	}
}

type Rec = Record<string, unknown>;

function isRec(value: unknown): value is Rec {
	return typeof value === 'object' && value !== null && !Array.isArray(value);
}
function fail(reason: string): never {
	throw new LiveEventError(reason);
}
function int(value: unknown, name: string, min = 0): number {
	if (typeof value !== 'number' || !Number.isInteger(value) || value < min) fail(`BAD_${name}`);
	return value;
}
function str(value: unknown, name: string): string {
	if (typeof value !== 'string' || value.length === 0) fail(`BAD_${name}`);
	return value;
}
function bool(value: unknown, name: string): boolean {
	if (typeof value !== 'boolean') fail(`BAD_${name}`);
	return value;
}
function numOrNull(value: unknown, name: string): number | null {
	if (value === null || value === undefined) return null;
	if (typeof value !== 'number' || !Number.isFinite(value)) fail(`BAD_${name}`);
	return value;
}
function strOrNull(value: unknown, name: string): string | null {
	if (value === null || value === undefined) return null;
	return str(value, name);
}
function oneOf<T extends string>(value: unknown, allowed: readonly T[], name: string): T {
	if (typeof value !== 'string' || !(allowed as readonly string[]).includes(value)) fail(`BAD_${name}`);
	return value as T;
}
function quality(value: unknown, name: string) {
	return oneOf(value, QUALITY_STATES, name);
}
function qualityOrNull(value: unknown, name: string) {
	return value === null || value === undefined ? null : quality(value, name);
}

function parseContext(raw: unknown) {
	if (!isRec(raw)) fail('BAD_CONTEXT');
	const available = bool(raw.context_available, 'CONTEXT_AVAILABLE');
	const parsed = {
		hr_ecg_bpm: numOrNull(raw.hr_ecg_bpm, 'HR'),
		pr_ppg_bpm: numOrNull(raw.pr_ppg_bpm, 'PR'),
		spo2_pct: numOrNull(raw.spo2_pct, 'SPO2'),
		spo2_valid: bool(raw.spo2_valid, 'SPO2_VALID'),
		context_available: available,
		ppg_quality: qualityOrNull(raw.ppg_quality, 'PPG_QUALITY')
	};
	// Mirrors the backend rule: unavailable context never carries PPG-derived values.
	if (!available && (parsed.pr_ppg_bpm !== null || parsed.spo2_pct !== null || parsed.spo2_valid)) {
		fail('UNAVAILABLE_CONTEXT_CARRIES_PPG_VALUES');
	}
	return parsed;
}

function parsePayload(type: LiveEvent['event_type'], raw: unknown): LiveEvent['payload'] {
	if (!isRec(raw)) fail('BAD_PAYLOAD');
	switch (type) {
		case 'session.status':
			return {
				session_state: oneOf(raw.session_state, SESSION_STATES, 'SESSION_STATE'),
				elapsed_ms: int(raw.elapsed_ms, 'ELAPSED_MS'),
				reason_code: strOrNull(raw.reason_code, 'REASON_CODE')
			};
		case 'device.status':
			return {
				device_id: str(raw.device_id, 'DEVICE_ID'),
				device_state: oneOf(raw.device_state, DEVICE_STATES, 'DEVICE_STATE'),
				adapter_type: oneOf(raw.adapter_type, ['SIMULATED', 'FUTURE_REAL'] as const, 'ADAPTER'),
				reason_code: strOrNull(raw.reason_code, 'REASON_CODE'),
				recoverable: bool(raw.recoverable, 'RECOVERABLE')
			};
		case 'waveform.chunk': {
			const samples = raw.samples;
			if (!Array.isArray(samples)) fail('BAD_SAMPLES');
			const count = int(raw.sample_count, 'SAMPLE_COUNT', 1);
			if (samples.length !== count) fail('WAVEFORM_SAMPLE_COUNT_MISMATCH');
			for (const sample of samples) {
				if (sample !== null && (typeof sample !== 'number' || !Number.isFinite(sample))) {
					fail('BAD_SAMPLE_VALUE');
				}
			}
			if (raw.source_rate_hz !== 360) fail('BAD_SOURCE_RATE');
			if (raw.unit !== 'ADC_COUNTS') fail('BAD_UNIT');
			return {
				channel: oneOf(raw.channel, ['ECG', 'PPG_RED', 'PPG_IR'] as const, 'CHANNEL'),
				unit: 'ADC_COUNTS',
				source_rate_hz: 360,
				first_sample_index: int(raw.first_sample_index, 'FIRST_SAMPLE_INDEX'),
				first_sample_timestamp_us: int(raw.first_sample_timestamp_us, 'FIRST_SAMPLE_TS'),
				sample_count: count,
				samples: samples as (number | null)[]
			};
		}
		case 'context.snapshot':
			return parseContext(raw);
		case 'quality.status':
			return {
				ecg_quality: quality(raw.ecg_quality, 'ECG_QUALITY'),
				ppg_quality: qualityOrNull(raw.ppg_quality, 'PPG_QUALITY'),
				ui_label: str(raw.ui_label, 'UI_LABEL')
			};
		case 'inference.result':
			return {
				timestamp_us: int(raw.timestamp_us, 'TIMESTAMP_US'),
				model_id: strOrNull(raw.model_id, 'MODEL_ID'),
				calibration_id: strOrNull(raw.calibration_id, 'CALIBRATION_ID'),
				calibration_domain: strOrNull(raw.calibration_domain, 'CALIBRATION_DOMAIN'),
				preprocess_version: strOrNull(raw.preprocess_version, 'PREPROCESS'),
				alert_policy_id: strOrNull(raw.alert_policy_id, 'ALERT_POLICY'),
				ecg_quality: quality(raw.ecg_quality, 'ECG_QUALITY'),
				monitoring_state: oneOf(raw.monitoring_state, MONITORING_STATE_NAMES, 'MONITORING_STATE'),
				context: raw.context === null || raw.context === undefined ? null : parseContext(raw.context),
				latency_ms: numOrNull(raw.latency_ms, 'LATENCY'),
				raw_probability: numOrNull(raw.raw_probability, 'RAW_PROB'),
				source_domain_calibrated_probability: numOrNull(
					raw.source_domain_calibrated_probability,
					'CAL_PROB'
				),
				threshold: numOrNull(raw.threshold, 'THRESHOLD'),
				probability_role: oneOf(
					raw.probability_role,
					['RESEARCH_TECHNICAL_METADATA'] as const,
					'PROBABILITY_ROLE'
				)
			};
		case 'monitoring.state':
			return {
				monitoring_state: oneOf(raw.monitoring_state, MONITORING_STATE_NAMES, 'MONITORING_STATE'),
				previous_state:
					raw.previous_state === null || raw.previous_state === undefined
						? null
						: oneOf(raw.previous_state, MONITORING_STATE_NAMES, 'PREVIOUS_STATE'),
				reason_code: strOrNull(raw.reason_code, 'REASON_CODE')
			};
		case 'system.error':
			return {
				error_code: str(raw.error_code, 'ERROR_CODE'),
				message: str(raw.message, 'MESSAGE'),
				recoverable: bool(raw.recoverable, 'RECOVERABLE'),
				origin: oneOf(
					raw.origin,
					['DEVICE', 'STREAM', 'INFERENCE', 'PRODUCT_API', 'STORAGE'] as const,
					'ORIGIN'
				)
			};
	}
}

const MONITORING_KINDS: readonly string[] = [
	'session.status',
	'device.status',
	'waveform.chunk',
	'context.snapshot',
	'quality.status',
	'inference.result',
	'monitoring.state',
	'system.error'
];

/** Validate one raw WebSocket message. Throws LiveEventError for anything malformed or foreign
 * (federation / unknown kinds are rejected on the monitoring socket, never ignored silently). */
export function parseLiveEvent(raw: unknown): LiveEvent {
	if (!isRec(raw)) fail('NOT_AN_OBJECT');
	if (raw.contract_version !== 'PRODUCT_LIVE_EVENT_V1') fail('BAD_CONTRACT_VERSION');
	const type = raw.event_type;
	if (typeof type !== 'string' || !MONITORING_KINDS.includes(type)) fail('UNKNOWN_EVENT_TYPE');
	const kind = type as LiveEvent['event_type'];
	const envelope = {
		contract_version: 'PRODUCT_LIVE_EVENT_V1' as const,
		event_id: str(raw.event_id, 'EVENT_ID'),
		sequence_index: int(raw.sequence_index, 'SEQUENCE_INDEX'),
		emitted_at_us: int(raw.emitted_at_us, 'EMITTED_AT'),
		session_id: str(raw.session_id, 'SESSION_ID'),
		source_timestamp_us:
			raw.source_timestamp_us === null || raw.source_timestamp_us === undefined
				? null
				: int(raw.source_timestamp_us, 'SOURCE_TS')
	};
	return { ...envelope, event_type: kind, payload: parsePayload(kind, raw.payload) } as LiveEvent;
}

export class SequenceError extends Error {
	constructor(
		readonly kind: 'GAP' | 'DUPLICATE',
		readonly expected: number,
		readonly received: number
	) {
		super(`PRODUCT STREAM ERROR: ${kind} (expected ${expected}, received ${received})`);
		this.name = 'SequenceError';
	}
}

/** next event must equal previous + 1; the backend replays from 0 on every (re)connect. */
export class SequenceTracker {
	private next = 0;
	get expected(): number {
		return this.next;
	}
	accept(sequenceIndex: number): void {
		if (sequenceIndex < this.next) throw new SequenceError('DUPLICATE', this.next, sequenceIndex);
		if (sequenceIndex > this.next) throw new SequenceError('GAP', this.next, sequenceIndex);
		this.next += 1;
	}
	reset(): void {
		this.next = 0;
	}
}
