/** Response types of the EXPERIMENTAL resampled-V2 route. Kept out of api.ts: that file must not carry model selectors. */
export interface HardwareV2Inference {
	raw_probability: number | null; source_domain_calibrated_probability: number | null; threshold: number | null;
	monitoring_state: string; model_id: string | null; calibration_id: string | null; calibration_domain: string | null;
	calibration_patient_count: number | null; latency_ms: number | null; preprocess_version: string | null;
	alert_policy_id: string | null; context: Record<string, unknown> | null; ecg_quality: string;
}
export interface HardwareV2Window {
	window_id: string; wall_time: string; stream_seconds: number; ecg_quality: string; quality_reasons: string[];
	short_gap: boolean; long_gap_or_missing: boolean; missing_slots: number;
	ppg_context: { quality: string | null; pr_bpm: number | null; spo2_pct: number | null; spo2_valid: boolean } | null;
	result: { outcome: string; detail: string | null; inference: HardwareV2Inference | null };
}
export interface HardwareV2Experimental {
	version: 'HARDWARE_V2_EXPERIMENTAL_V1'; label: string; valid: false; diagnostic: false; model_id: string;
	assumptions: Record<string, string | number>; min_seconds_for_first_window: number;
	summary: { input_readings: number; resampled_records: number; windows?: number; stream_start: string | null };
	windows: HardwareV2Window[]; session_status: string;
}
