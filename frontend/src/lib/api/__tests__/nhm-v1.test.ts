import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it, vi } from 'vitest';
import {
	CONTRACT_VERSION,
	ECG_WINDOW_SAMPLE_COUNT,
	MONITORING_STATES,
	TARGET_ID,
	createNhmApiClient,
	type InferWindowRequest
} from '../nhm-v1';

// Section 9: the frontend must not silently drift from contracts/openapi_v1.json. This walks
// up from the test file to find the repository root rather than hardcoding a directory depth.
function findRepoRoot(startDir: string): string {
	let dir = startDir;
	for (let i = 0; i < 10; i += 1) {
		try {
			readFileSync(path.join(dir, 'contracts/openapi_v1.json'));
			return dir;
		} catch {
			dir = path.dirname(dir);
		}
	}
	throw new Error('Could not locate contracts/openapi_v1.json by walking up from ' + startDir);
}

const REPO_ROOT = findRepoRoot(__dirname);
const OPENAPI = JSON.parse(readFileSync(path.join(REPO_ROOT, 'contracts/openapi_v1.json'), 'utf-8'));

function schemaProperties(schemaName: string): Record<string, unknown> {
	const schema = OPENAPI.components.schemas[schemaName];
	expect(schema, `components.schemas.${schemaName} must exist in contracts/openapi_v1.json`).toBeTruthy();
	return schema.properties as Record<string, unknown>;
}

describe('nhm-v1 client: OpenAPI contract parity (Section 9)', () => {
	it('InferWindowResponse field names match contracts/openapi_v1.json exactly', () => {
		const backendFields = Object.keys(schemaProperties('InferWindowResponse')).sort();
		const frontendFields = [
			'contract_version',
			'timestamp_us',
			'model_id',
			'target',
			'raw_probability',
			'source_domain_calibrated_probability',
			'calibration_domain',
			'calibration_patient_count',
			'calibration_id',
			'threshold',
			'ecg_quality',
			'monitoring_state',
			'context',
			'latency_ms',
			'preprocess_version',
			'alert_policy_id'
		].sort();
		expect(frontendFields).toEqual(backendFields);
	});

	it('InferWindowRequest field names match contracts/openapi_v1.json exactly', () => {
		const backendFields = Object.keys(schemaProperties('InferWindowRequest')).sort();
		const frontendFields = [
			'contract_version',
			'session_id',
			'timestamp_us',
			'ecg',
			'ecg_quality',
			'ppg_context',
			'model_id'
		].sort();
		expect(frontendFields).toEqual(backendFields);
	});

	it('ErrorResponse field names match contracts/openapi_v1.json exactly', () => {
		const backendFields = Object.keys(schemaProperties('ErrorResponse')).sort();
		expect(['contract_version', 'status_code', 'error_type', 'message'].sort()).toEqual(backendFields);
	});

	it('monitoring_state enum matches contracts/openapi_v1.json exactly (five states)', () => {
		const monitoringStateSchema = OPENAPI.components.schemas.MonitoringState;
		expect(monitoringStateSchema.enum.slice().sort()).toEqual([...MONITORING_STATES].sort());
		expect(MONITORING_STATES).toHaveLength(5);
	});

	it('the route POST /v1/infer-window exists in the frozen OpenAPI contract', () => {
		expect(OPENAPI.paths['/v1/infer-window']).toBeTruthy();
		expect(OPENAPI.paths['/v1/infer-window'].post).toBeTruthy();
	});

	it('CONTRACT_VERSION and TARGET_ID match the OpenAPI info/schema constants', () => {
		expect(CONTRACT_VERSION).toBe('API_SCHEMA_V1');
		expect(OPENAPI.info.version).toBe(CONTRACT_VERSION);
		expect(TARGET_ID).toBe('AAMI_SVF_WINDOW_V1');
	});
});

function makeRequest(): InferWindowRequest {
	return {
		contract_version: 'API_SCHEMA_V1',
		session_id: 'test-session',
		timestamp_us: 1_000_000,
		ecg: { samples: new Array(ECG_WINDOW_SAMPLE_COUNT).fill(0), target_hz: 250, window_seconds: 10 },
		ecg_quality: 'VALID',
		ppg_context: null,
		model_id: 'MODEL_V1'
	};
}

describe('nhm-v1 client: HTTP status mapping (Section 17)', () => {
	it('maps HTTP 200 to a success result', async () => {
		const fetchImpl = vi.fn(async () => new Response(JSON.stringify({ monitoring_state: 'NORMAL_MONITORED_PATTERN' }), { status: 200 }));
		const client = createNhmApiClient({ fetchImpl: fetchImpl as unknown as typeof fetch });
		const result = await client.inferWindow(makeRequest());
		expect(result.kind).toBe('success');
		expect(result.status).toBe(200);
	});

	it('maps HTTP 400 to a request_error result, never a monitoring state', async () => {
		const fetchImpl = vi.fn(async () => new Response(JSON.stringify({ status_code: 400, error_type: 'REQUEST_SCHEMA_ERROR', message: 'bad' }), { status: 400 }));
		const client = createNhmApiClient({ fetchImpl: fetchImpl as unknown as typeof fetch });
		const result = await client.inferWindow(makeRequest());
		expect(result.kind).toBe('request_error');
		if (result.kind === 'request_error') expect(result.error.error_type).toBe('REQUEST_SCHEMA_ERROR');
	});

	it('maps HTTP 422 to a signal_window_error result', async () => {
		const fetchImpl = vi.fn(async () => new Response(JSON.stringify({ status_code: 422, error_type: 'UNUSABLE_OR_INCOMPLETE_SIGNAL_WINDOW', message: 'bad window' }), { status: 422 }));
		const client = createNhmApiClient({ fetchImpl: fetchImpl as unknown as typeof fetch });
		const result = await client.inferWindow(makeRequest());
		expect(result.kind).toBe('signal_window_error');
	});

	it('maps HTTP 500 to a server_error result', async () => {
		const fetchImpl = vi.fn(async () => new Response(JSON.stringify({ status_code: 500, error_type: 'INTERNAL_SERVER_ERROR', message: 'boom' }), { status: 500 }));
		const client = createNhmApiClient({ fetchImpl: fetchImpl as unknown as typeof fetch });
		const result = await client.inferWindow(makeRequest());
		expect(result.kind).toBe('server_error');
	});

	it('maps a network failure to a transport_error result, never a fabricated success', async () => {
		const fetchImpl = vi.fn(async () => {
			throw new Error('network down');
		});
		const client = createNhmApiClient({ fetchImpl: fetchImpl as unknown as typeof fetch });
		const result = await client.inferWindow(makeRequest());
		expect(result.kind).toBe('transport_error');
	});
});
