const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api';

export type Session = { session_id: string; subject_id: string; device_id: string; status: string; start_time: string | null; end_time: string | null; total_samples: number };
export type Prediction = { id: string; prediction: string; confidence: number; probability_abnormal: number; signal_quality: string; timestamp: string | null };
export type MonitoringEvent = { id: string; state: string; source: string; start_time: string | null; end_time: string | null; peak_probability: number; n_windows: number };
export type InferenceMessage = { type: 'inference'; session_id: string; source: 'LIVE' | 'REPLAY' | 'HISTORICAL'; timestamp: string; model_version: string; prediction: string; confidence: number; probability_abnormal: number; signal_quality: string; latency_ms: number };

async function request<T>(path: string, options: RequestInit = {}) {
	const headers = new Headers(options.headers);
	if (options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
	const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
	if (!response.ok) throw new Error((await response.text()) || `Request failed with status ${response.status}`);
	return response.status === 204 ? undefined as T : await response.json() as T;
}

const json = <T>(path: string, method: string, body?: unknown) => request<T>(path, { method, body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
	request,
	health: () => request<{ status: string; ml_service: string }>('/system/health'),
	model: () => request<{ available: boolean; model_version: string | null; mode: string; release_status: string; disclaimer: string }>('/system/model'),
	monitoring: {
		getSessions: () => request<Session[]>('/monitoring/sessions'),
		startSession: (subject_id: string, device_id: string) => json<Session>('/monitoring/sessions/start', 'POST', { subject_id, device_id }),
		stopSession: (id: string) => json<Session>(`/monitoring/sessions/${id}/stop`, 'PUT'),
		getPredictions: (id: string) => request<Prediction[]>(`/monitoring/sessions/${id}/predictions`),
		getEvents: (id: string) => request<MonitoringEvent[]>(`/monitoring/sessions/${id}/events`),
		ingestChunk: (id: string, samples: number[], source: 'LIVE' | 'REPLAY' | 'HISTORICAL' = 'REPLAY') => json<{ emitted_inferences: InferenceMessage[] }>(`/monitoring/sessions/${id}/chunks`, 'POST', { samples, sampling_rate: 250, source })
	}
};

export { API_BASE };
