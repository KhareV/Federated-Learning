// CAPSTONE_PRODUCT_CLIENT_V1 -- explicit types mirroring PRODUCT_API_CONTRACT_V2 and
// PRODUCT_LIVE_EVENT_V1 (product/api/models*.py, product/events.py, product/session.py,
// product/devices/base.py). No frontend alias changes a backend meaning.

export type AuthProviderName = 'CLERK' | 'DEMO';

export interface SystemInfoV2 {
	product_api_version: string;
	capstone_protocol: string;
	monitoring_protocol: string;
	software_system: string;
	model_id: string;
	calibration_id: string;
	api_contract_version: string;
	hardware_mode: string;
	physical_hardware_available: boolean;
	persistence_mode: string;
	federation_runtime: string;
	auth_status: string;
	claim: string;
	product_api_implementation: string;
	auth_provider: AuthProviderName;
	demo_mode: boolean;
}

export interface AuthIdentity {
	user_id: string;
	display_name: string | null;
	email: string | null;
	auth_provider: AuthProviderName;
	auth_session_id: string | null;
	roles: string[];
	demo_mode: boolean;
}

export const DEVICE_STATES = [
	'DETACHED',
	'SCANNING',
	'FOUND',
	'PAIRING',
	'CONNECTED',
	'STREAMING',
	'DISCONNECTED',
	'RECONNECTING',
	'STOPPED',
	'ERROR'
] as const;
export type DeviceState = (typeof DEVICE_STATES)[number];

export const SESSION_STATES = [
	'CREATED',
	'DEVICE_READY',
	'MONITORING',
	'STOPPING',
	'COMPLETED',
	'FAILED'
] as const;
export type SessionState = (typeof SESSION_STATES)[number];

export const QUALITY_STATES = ['VALID', 'DEGRADED', 'UNUSABLE'] as const;
export type QualityState = (typeof QUALITY_STATES)[number];

export const MONITORING_STATE_NAMES = [
	'NORMAL_MONITORED_PATTERN',
	'POTENTIAL_ECTOPY_ASSOCIATED_PATTERN',
	'RECHECK_SENSOR',
	'CONTEXT_UNAVAILABLE',
	'SYSTEM_ERROR'
] as const;
export type MonitoringStateName = (typeof MONITORING_STATE_NAMES)[number];

export type AdapterType = 'SIMULATED' | 'FUTURE_REAL';

export interface DeviceCapabilities {
	nominal_source_rates_hz: Record<string, number>;
	supports_device_events: boolean;
	supports_ecg: boolean;
	supports_ppg: boolean;
	supports_spo2_context: boolean;
}

export interface DeviceDescriptor {
	device_id: string;
	display_name: string;
	adapter_type: AdapterType;
	source_dataset_id: string | null;
	source_mode: string | null;
	connection_state: DeviceState;
	capabilities: DeviceCapabilities;
	simulation: boolean;
	simulation_version: string | null;
	hardware_specific_fields_status: 'VERIFICATION_REQUIRED' | 'NOT_APPLICABLE';
}

export interface RuntimeIdentity {
	software_system_id: string;
	model_id: string;
	calibration_id: string;
	preprocess_id: string;
	alert_policy_id: string;
	alert_policy_binding_id: string;
	gateway_artifact_id: string;
	api_contract_version: string;
}

export interface SimulationProvenance {
	scenario_id: string;
	seed: number | null;
	simulation_version: string;
}

export interface MonitoringSession {
	session_id: string;
	user_id: string;
	device_id: string;
	device_adapter_type: AdapterType;
	source_dataset_id: string | null;
	source_mode: string | null;
	created_at_us: number;
	started_at_us: number | null;
	ended_at_us: number | null;
	state: SessionState;
	runtime: RuntimeIdentity;
	simulation_provenance: SimulationProvenance | null;
}

export type ProductErrorCode =
	| 'UNAUTHENTICATED'
	| 'FORBIDDEN'
	| 'NOT_FOUND'
	| 'INVALID_STATE'
	| 'INVALID_REQUEST'
	| 'INFERENCE_INTEGRATION_ERROR'
	| 'INTERNAL_PRODUCT_ERROR';

export interface ProductErrorBody {
	code: ProductErrorCode;
	message: string;
}

/** The only scenarios CAP-002 implements (contracts/capstone/demo_scenarios_v1.json). */
export const MONITORING_SCENARIOS = [
	{ id: 'NORMAL_MONITORING', label: 'Normal monitoring' },
	{ id: 'CONTEXT_LOSS', label: 'Context loss' },
	{ id: 'POOR_SIGNAL', label: 'Poor signal' },
	{ id: 'DISCONNECT_RECONNECT', label: 'Disconnect / reconnect' },
	{ id: 'MIXED_MONITORING_SESSION', label: 'Mixed monitoring session (recommended for the faculty demo)' }
] as const;
export type ScenarioId = (typeof MONITORING_SCENARIOS)[number]['id'];
export const RECOMMENDED_SCENARIO: ScenarioId = 'MIXED_MONITORING_SESSION';

// ---- PRODUCT_LIVE_EVENT_V1 (monitoring kinds only) ------------------------------------------
export interface SessionStatusPayload {
	session_state: SessionState;
	elapsed_ms: number;
	reason_code: string | null;
}
export interface DeviceStatusPayload {
	device_id: string;
	device_state: DeviceState;
	adapter_type: AdapterType;
	reason_code: string | null;
	recoverable: boolean;
}
export interface WaveformChunkPayload {
	channel: 'ECG' | 'PPG_RED' | 'PPG_IR';
	unit: 'ADC_COUNTS';
	source_rate_hz: 360;
	first_sample_index: number;
	first_sample_timestamp_us: number;
	sample_count: number;
	samples: (number | null)[];
}
export interface ContextSnapshotPayload {
	hr_ecg_bpm: number | null;
	pr_ppg_bpm: number | null;
	spo2_pct: number | null;
	spo2_valid: boolean;
	context_available: boolean;
	ppg_quality: QualityState | null;
}
export interface QualityStatusPayload {
	ecg_quality: QualityState;
	ppg_quality: QualityState | null;
	ui_label: string;
}
export interface InferenceResultPayload {
	timestamp_us: number;
	model_id: string | null;
	calibration_id: string | null;
	calibration_domain: string | null;
	preprocess_version: string | null;
	alert_policy_id: string | null;
	ecg_quality: QualityState;
	monitoring_state: MonitoringStateName;
	context: ContextSnapshotPayload | null;
	latency_ms: number | null;
	raw_probability: number | null;
	source_domain_calibrated_probability: number | null;
	threshold: number | null;
	probability_role: 'RESEARCH_TECHNICAL_METADATA';
}
export interface MonitoringStatePayload {
	monitoring_state: MonitoringStateName;
	previous_state: MonitoringStateName | null;
	reason_code: string | null;
}
export interface SystemErrorPayload {
	error_code: string;
	message: string;
	recoverable: boolean;
	origin: 'DEVICE' | 'STREAM' | 'INFERENCE' | 'PRODUCT_API' | 'STORAGE';
}

export interface EventEnvelope {
	contract_version: 'PRODUCT_LIVE_EVENT_V1';
	event_id: string;
	sequence_index: number;
	emitted_at_us: number;
	session_id: string;
	source_timestamp_us: number | null;
}

export type LiveEvent =
	| (EventEnvelope & { event_type: 'session.status'; payload: SessionStatusPayload })
	| (EventEnvelope & { event_type: 'device.status'; payload: DeviceStatusPayload })
	| (EventEnvelope & { event_type: 'waveform.chunk'; payload: WaveformChunkPayload })
	| (EventEnvelope & { event_type: 'context.snapshot'; payload: ContextSnapshotPayload })
	| (EventEnvelope & { event_type: 'quality.status'; payload: QualityStatusPayload })
	| (EventEnvelope & { event_type: 'inference.result'; payload: InferenceResultPayload })
	| (EventEnvelope & { event_type: 'monitoring.state'; payload: MonitoringStatePayload })
	| (EventEnvelope & { event_type: 'system.error'; payload: SystemErrorPayload });

export type LiveEventType = LiveEvent['event_type'];
export const LIVE_EVENT_TYPES: readonly LiveEventType[] = [
	'session.status',
	'device.status',
	'waveform.chunk',
	'context.snapshot',
	'quality.status',
	'inference.result',
	'monitoring.state',
	'system.error'
];
