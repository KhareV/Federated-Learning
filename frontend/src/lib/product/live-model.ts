// CAPSTONE_MONITORING_STORE_V1 -- pure, framework-free reducer for the monitoring live stream.
// It records backend events and NOTHING else: no model inference, no threshold comparison, no alert
// debouncing, no quality classification, no HR/SpO2 computation, and no locally synthesised
// monitoring state. A monitoring state exists here only if a `monitoring.state` event carried it.
// Quality (`quality.status`), monitoring state (`monitoring.state`), context (`context.snapshot`)
// and inference (`inference.result`) are four independent, separately labelled channels.

import { SequenceError, SequenceTracker, LiveEventError, parseLiveEvent } from './events';
import { RollingWaveform, WaveformContinuityError, type GapRun } from './waveform';
import type {
	ContextSnapshotPayload,
	DeviceState,
	InferenceResultPayload,
	LiveEvent,
	LiveEventType,
	MonitoringStateName,
	QualityStatusPayload,
	SessionState,
	SystemErrorPayload
} from './types';

export interface StreamError {
	kind: 'MALFORMED_EVENT' | 'SEQUENCE_GAP' | 'SEQUENCE_DUPLICATE' | 'WAVEFORM_DISCONTINUITY' | 'FOREIGN_SESSION';
	message: string;
}

export interface MonitoringStateChange {
	sequence_index: number;
	state: MonitoringStateName;
	previous: MonitoringStateName | null;
}

export const MAX_STATE_CHANGES = 200;
export const MAX_DEVICE_CHANGES = 200;
export const MAX_SYSTEM_ERRORS = 50;

export class LiveModel {
	readonly tracker = new SequenceTracker();
	readonly waveform = new RollingWaveform();
	eventCount = 0;
	countsByType: Partial<Record<LiveEventType, number>> = {};
	sessionState: SessionState | null = null;
	sessionElapsedMs: number | null = null;
	deviceState: DeviceState | null = null;
	deviceChanges: { sequence_index: number; state: DeviceState; reason: string | null }[] = [];
	latestWindowTs: number | null = null;
	latestQuality: (QualityStatusPayload & { window_ts: number | null }) | null = null;
	qualityCounts: Record<string, number> = { VALID: 0, DEGRADED: 0, UNUSABLE: 0 };
	latestContext: (ContextSnapshotPayload & { window_ts: number | null }) | null = null;
	latestInference: InferenceResultPayload | null = null;
	monitoringState: MonitoringStateName | null = null;
	monitoringChanges: MonitoringStateChange[] = [];
	systemErrors: SystemErrorPayload[] = [];
	streamError: StreamError | null = null;
	/** model / calibration ids observed on real inference results (distinct) */
	modelIds = new Set<string>();
	calibrationIds = new Set<string>();
	inferenceCount = 0;
	/** true while the latest window still expects its context/inference (it is not UNUSABLE) */
	private pending = false;

	constructor(private readonly sessionId: string | null = null) {}

	/** Validate and apply one raw WebSocket message. Returns false if the stream is now errored. */
	applyRaw(raw: unknown): boolean {
		if (this.streamError) return false;
		let event: LiveEvent;
		try {
			event = parseLiveEvent(raw);
		} catch (cause) {
			const reason = cause instanceof LiveEventError ? cause.reason : String(cause);
			this.streamError = { kind: 'MALFORMED_EVENT', message: `PRODUCT STREAM ERROR: ${reason}` };
			return false;
		}
		if (this.sessionId !== null && event.session_id !== this.sessionId) {
			this.streamError = {
				kind: 'FOREIGN_SESSION',
				message: 'PRODUCT STREAM ERROR: event belongs to another session'
			};
			return false;
		}
		try {
			this.tracker.accept(event.sequence_index);
		} catch (cause) {
			if (cause instanceof SequenceError) {
				this.streamError = {
					kind: cause.kind === 'GAP' ? 'SEQUENCE_GAP' : 'SEQUENCE_DUPLICATE',
					message: cause.message
				};
				return false;
			}
			throw cause;
		}
		try {
			this.apply(event);
		} catch (cause) {
			if (cause instanceof WaveformContinuityError) {
				this.streamError = { kind: 'WAVEFORM_DISCONTINUITY', message: `PRODUCT STREAM ERROR: ${cause.message}` };
				return false;
			}
			throw cause;
		}
		return true;
	}

	private apply(event: LiveEvent): void {
		this.eventCount += 1;
		this.countsByType[event.event_type] = (this.countsByType[event.event_type] ?? 0) + 1;
		switch (event.event_type) {
			case 'session.status':
				this.sessionState = event.payload.session_state;
				this.sessionElapsedMs = event.payload.elapsed_ms;
				if (event.payload.session_state === 'COMPLETED' || event.payload.session_state === 'FAILED') this.pending = false;
				break;
			case 'device.status':
				this.deviceState = event.payload.device_state;
				this.deviceChanges.push({
					sequence_index: event.sequence_index,
					state: event.payload.device_state,
					reason: event.payload.reason_code
				});
				if (this.deviceChanges.length > MAX_DEVICE_CHANGES) this.deviceChanges.shift();
				break;
			case 'waveform.chunk':
				if (event.payload.channel === 'ECG') {
					this.waveform.push(event.payload.first_sample_index, event.payload.samples);
				}
				break;
			case 'quality.status':
				this.latestWindowTs = event.source_timestamp_us;
				// An UNUSABLE window has no context/inference by design; any other window is followed by
				// its context.snapshot / inference.result within the same backend tick.
				this.pending = event.payload.ecg_quality !== 'UNUSABLE';
				this.latestQuality = { ...event.payload, window_ts: event.source_timestamp_us };
				this.qualityCounts[event.payload.ecg_quality] =
					(this.qualityCounts[event.payload.ecg_quality] ?? 0) + 1;
				break;
			case 'context.snapshot':
				this.latestContext = { ...event.payload, window_ts: event.source_timestamp_us };
				break;
			case 'inference.result':
				this.latestInference = event.payload;
				if (event.payload.timestamp_us === this.latestWindowTs) this.pending = false;
				this.inferenceCount += 1;
				if (event.payload.model_id) this.modelIds.add(event.payload.model_id);
				if (event.payload.calibration_id) this.calibrationIds.add(event.payload.calibration_id);
				break;
			case 'monitoring.state':
				this.monitoringState = event.payload.monitoring_state;
				this.monitoringChanges.push({
					sequence_index: event.sequence_index,
					state: event.payload.monitoring_state,
					previous: event.payload.previous_state
				});
				if (this.monitoringChanges.length > MAX_STATE_CHANGES) this.monitoringChanges.shift();
				break;
			case 'system.error':
				this.systemErrors.push(event.payload);
				if (this.systemErrors.length > MAX_SYSTEM_ERRORS) this.systemErrors.shift();
				break;
		}
	}

	/** CURRENT: belongs to the latest window and is available. PENDING: the latest window is still
	 * waiting for its context (the previous values are NOT current). UNAVAILABLE: otherwise. */
	get contextState(): 'CURRENT' | 'PENDING' | 'UNAVAILABLE' {
		const c = this.latestContext;
		if (c && c.window_ts === this.latestWindowTs) return c.context_available ? 'CURRENT' : 'UNAVAILABLE';
		return this.pending ? 'PENDING' : 'UNAVAILABLE';
	}
	get inferenceState(): 'CURRENT' | 'PENDING' | 'NONE_FOR_WINDOW' | 'NONE' {
		const i = this.latestInference;
		if (i && i.timestamp_us === this.latestWindowTs) return 'CURRENT';
		if (this.pending) return 'PENDING';
		return i ? 'NONE_FOR_WINDOW' : 'NONE';
	}
	get contextIsCurrent(): boolean {
		return this.contextState === 'CURRENT';
	}
	get inferenceIsCurrent(): boolean {
		return this.inferenceState === 'CURRENT';
	}
	get gaps(): GapRun[] {
		return this.waveform.gaps;
	}

	/** Reconnect / replay: rebuild everything deterministically from sequence 0. */
	reset(): void {
		this.tracker.reset();
		this.waveform.reset();
		this.eventCount = 0;
		this.countsByType = {};
		this.sessionState = null;
		this.sessionElapsedMs = null;
		this.deviceState = null;
		this.deviceChanges = [];
		this.latestWindowTs = null;
		this.latestQuality = null;
		this.qualityCounts = { VALID: 0, DEGRADED: 0, UNUSABLE: 0 };
		this.latestContext = null;
		this.latestInference = null;
		this.monitoringState = null;
		this.monitoringChanges = [];
		this.systemErrors = [];
		this.streamError = null;
		this.modelIds = new Set();
		this.calibrationIds = new Set();
		this.inferenceCount = 0;
		this.pending = false;
	}
}
