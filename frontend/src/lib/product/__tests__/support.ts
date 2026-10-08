// Test helpers: an in-memory product backend (unit/component tests ONLY - the canonical proof uses the
// real CAP-004 backend, see scripts/run_capstone_frontend_e2e.py) and a scriptable fake socket.
import { ProductApiError, federationRunBody, type ProductClient } from '../api';
import { candidateFixture, clientsFixture, overviewFixture, registryFixture, roundsFixture, runFixture } from '../federation/__tests__/fixtures';
import type { FederationOverview, FederationRun, ModelRegistryView } from '../federation/types';
import type { SocketLike } from '../socket';
import type {
	AuthIdentity,
	DeviceDescriptor,
	DeviceState,
	LiveEvent,
	MonitoringSession,
	SystemInfoV2
} from '../types';

export function systemInfo(over: Partial<SystemInfoV2> = {}): SystemInfoV2 {
	return {
		product_api_version: 'PRODUCT_API_V2',
		capstone_protocol: 'CAPSTONE_PRODUCT_PROTOCOL_V1',
		monitoring_protocol: 'CAPSTONE_PRODUCT_MONITORING_PROTOCOL_V1',
		software_system: 'SOFTWARE_SYSTEM_V2',
		model_id: 'MODEL_V2_FINAL',
		calibration_id: 'CAL_V2',
		api_contract_version: 'API_SCHEMA_V1',
		hardware_mode: 'SIMULATED_ONLY',
		physical_hardware_available: false,
		persistence_mode: 'SQLITE',
		federation_runtime: 'NOT_IMPLEMENTED',
		auth_status: 'CONFIGURED',
		claim: 'research prototype; simulated device; not diagnostic; no clinical claim',
		product_api_implementation: 'CAPSTONE_PRODUCT_API_V1_1',
		auth_provider: 'DEMO',
		demo_mode: true,
		...over
	};
}

export const DEMO_IDENTITY: AuthIdentity = {
	user_id: 'demo:faculty',
	display_name: 'Faculty Demo User',
	email: null,
	auth_provider: 'DEMO',
	auth_session_id: 'DEMO_OFFLINE_SESSION',
	roles: [],
	demo_mode: true
};

export function device(state: DeviceState = 'DETACHED', id = 'NHM_VIRTUAL_WEARABLE_01'): DeviceDescriptor {
	return {
		device_id: id,
		display_name: 'NHM Virtual Wearable',
		adapter_type: 'SIMULATED',
		source_dataset_id: 'WEARABLE_SIM_V1',
		source_mode: 'SYNTHETIC_PHYSIOLOGY',
		connection_state: state,
		capabilities: {
			nominal_source_rates_hz: { ECG_SIMULATION_CONVENTION: 360 },
			supports_device_events: true,
			supports_ecg: true,
			supports_ppg: false,
			supports_spo2_context: true
		},
		simulation: true,
		simulation_version: 'WEARABLE_SIM_V1',
		hardware_specific_fields_status: 'NOT_APPLICABLE'
	};
}

export function session(state: MonitoringSession['state'] = 'DEVICE_READY', id = 'SESS-1'): MonitoringSession {
	return {
		session_id: id,
		user_id: 'demo:faculty',
		device_id: 'NHM_VIRTUAL_WEARABLE_01',
		device_adapter_type: 'SIMULATED',
		source_dataset_id: 'WEARABLE_SIM_V1',
		source_mode: 'SYNTHETIC_PHYSIOLOGY',
		created_at_us: 1_700_000_000_000_000,
		started_at_us: state === 'DEVICE_READY' ? null : 1_700_000_001_000_000,
		ended_at_us: state === 'COMPLETED' ? 1_700_000_009_000_000 : null,
		state,
		runtime: {
			software_system_id: 'SOFTWARE_SYSTEM_V2',
			model_id: 'MODEL_V2_FINAL',
			calibration_id: 'CAL_V2',
			preprocess_id: 'PREPROC_V1',
			alert_policy_id: 'ALERT_POLICY_V1',
			alert_policy_binding_id: 'ALERT_POLICY_V1_MODEL_V2_BINDING',
			gateway_artifact_id: 'GATEWAY_ARTIFACT_V2',
			api_contract_version: 'API_SCHEMA_V1'
		},
		simulation_provenance: { scenario_id: 'MIXED_MONITORING_SESSION', seed: 1, simulation_version: 'WEARABLE_SIM_V1' }
	};
}

export interface FakeBackend extends ProductClient {
	calls: string[];
	federationBodies: unknown[];
	fed: { overview: FederationOverview; runs: FederationRun[]; registry: ModelRegistryView; createError: ProductApiError | null; clientsDelayMs: number };
	setState(state: DeviceState): void;
}

export function fakeBackend(system: SystemInfoV2 = systemInfo({ federation_runtime: 'ENABLED_ENGINEERING' })): FakeBackend {
	const federationBodies: unknown[] = [];
	const fed = { overview: overviewFixture(), runs: [] as FederationRun[], registry: registryFixture(), createError: null as ProductApiError | null, clientsDelayMs: 0 };
	let dev = device('DETACHED');
	let created = false;
	let sess = session('DEVICE_READY');
	const calls: string[] = [];
	const rec = <T>(name: string, value: T) => {
		calls.push(name);
		return Promise.resolve(value);
	};
	return {
		calls,
		federationBodies,
		fed,
		federationOverview: () => rec('federationOverview', fed.overview),
		federationClients: () => { calls.push('federationClients'); return new Promise((resolve) => setTimeout(() => resolve(clientsFixture()), fed.clientsDelayMs)); },
		createFederationRun: (choice) => {
			calls.push('createFederationRun');
			federationBodies.push(federationRunBody(choice));
			if (fed.createError) return Promise.reject(fed.createError);
			const run = runFixture({ run_type: choice.run_type, algorithm: choice.algorithm, secagg_mode: choice.secagg_mode });
			fed.runs = [run, ...fed.runs.filter((r) => r.run_id !== run.run_id)];
			return Promise.resolve(run);
		},
		federationRuns: () => rec('federationRuns', fed.runs),
		federationRun: (id) => rec('federationRun', fed.runs.find((r) => r.run_id === id) ?? runFixture({ run_id: id })),
		startFederationRun: (id) => rec('startFederationRun', runFixture({ run_id: id, status: 'RUNNING' })),
		federationRounds: () => rec('federationRounds', roundsFixture()),
		models: () => rec('models', fed.registry),
		model: (id) => rec('model', fed.registry.released_scientific.find((m) => m.model_id === id) ?? candidateFixture()),
		// Unit-test backend intentionally has no CAP-009 evidence fixture. Canonical evidence
		// flows use the real V1_3 backend; accidental fake-history use must fail visibly.
		sessionSummary: () => Promise.reject(new Error('NO_FAKE_HISTORY_EVIDENCE')),
		sessionTimeline: () => Promise.reject(new Error('NO_FAKE_HISTORY_EVIDENCE')),
		researchMl: () => Promise.reject(new Error('NO_FAKE_RESEARCH_EVIDENCE')),
		researchFl: () => Promise.reject(new Error('NO_FAKE_RESEARCH_EVIDENCE')),
		observatoryScenarios: () => Promise.reject(new Error('NO_FAKE_OBSERVATORY_TRACE')),
		observatoryScenarioWindow: () => Promise.reject(new Error('NO_FAKE_OBSERVATORY_TRACE')),
		observatorySessionWindow: () => Promise.reject(new Error('NO_FAKE_OBSERVATORY_TRACE')),
		observatoryCohort: () => Promise.reject(new Error('NO_FAKE_OBSERVATORY_COHORT')),
		observatoryRunContributions: () => Promise.reject(new Error('NO_FAKE_OBSERVATORY_CONTRIBUTIONS')),
		observatoryFlClientWindow: () => Promise.reject(new Error('NO_FAKE_OBSERVATORY_CLIENT_WINDOW')),
		observatoryScenarioTimeline: () => Promise.reject(new Error('NO_FAKE_OBSERVATORY_EVIDENCE')),
		observatoryExplainability: () => Promise.reject(new Error('NO_FAKE_OBSERVATORY_EVIDENCE')),
		observatoryExplainabilityCase: () => Promise.reject(new Error('NO_FAKE_OBSERVATORY_EVIDENCE')),
		observatoryDatasetPreprocessing: () => Promise.reject(new Error('NO_FAKE_OBSERVATORY_EVIDENCE')),
		observatoryActivations: () => Promise.reject(new Error('NO_FAKE_OBSERVATORY_EVIDENCE')),
		observatoryLiveLinkStart: () => Promise.reject(new Error('NO_FAKE_OBSERVATORY_EVIDENCE')),
		observatoryLiveLinkStatus: () => Promise.reject(new Error('NO_FAKE_OBSERVATORY_EVIDENCE')),
		fl10Recorded: () => Promise.reject(new Error('NO_FAKE_OBSERVATORY_EVIDENCE')),
		fl10RecordedBundle: () => Promise.reject(new Error('NO_FAKE_OBSERVATORY_EVIDENCE')),
		fl10Start: () => Promise.reject(new Error('NO_FAKE_OBSERVATORY_EVIDENCE')),
		fl10Status: () => Promise.reject(new Error('NO_FAKE_OBSERVATORY_EVIDENCE')),
		fl10JobBundle: () => Promise.reject(new Error('NO_FAKE_OBSERVATORY_EVIDENCE')),
		fl10ExportFile: () => Promise.reject(new Error('NO_FAKE_OBSERVATORY_EVIDENCE')),
		observatoryShowcase: () => Promise.reject(new Error('NO_FAKE_OBSERVATORY_EVIDENCE')),
		observatoryFlEval: () => Promise.reject(new Error('NO_FAKE_OBSERVATORY_EVIDENCE')),
		observatoryFlCurves: () => Promise.reject(new Error('NO_FAKE_OBSERVATORY_EVIDENCE')),
		observatoryArchitecture: () => Promise.reject(new Error('NO_FAKE_OBSERVATORY_EVIDENCE')),
		observatoryCalibration: () => Promise.reject(new Error('NO_FAKE_OBSERVATORY_EVIDENCE')),
		observatoryBoundaries: () => Promise.reject(new Error('NO_FAKE_OBSERVATORY_EVIDENCE')),
		observatoryReproducibility: () => Promise.reject(new Error('NO_FAKE_OBSERVATORY_EVIDENCE')),
		observatoryResearchRecords: () => Promise.reject(new Error('NO_FAKE_OBSERVATORY_RESEARCH_RECORDS')),
		observatoryResearchWindow: () => Promise.reject(new Error('NO_FAKE_OBSERVATORY_RESEARCH_WINDOW')),
		observatoryArmSessionCapture: () => Promise.reject(new Error('NO_FAKE_OBSERVATORY_LIVE_CAPTURE')),
		observatoryCapturedSessionWindow: () => Promise.reject(new Error('NO_FAKE_OBSERVATORY_LIVE_CAPTURE')),
		setState: (state) => (dev = device(state)),
		system: () => rec('system', system),
		me: () => rec('me', DEMO_IDENTITY),
		devices: () => rec('devices', created ? [dev] : []),
		createSimulatedDevice: () => {
			created = true;
			dev = device('DETACHED');
			return rec('createSimulatedDevice', dev);
		},
		scan: () => rec('scan', (dev = device('FOUND'))),
		connect: () => rec('connect', (dev = device('CONNECTED'))),
		disconnect: () => rec('disconnect', (dev = device('DETACHED'))),
		createSession: () => rec('createSession', (sess = session('DEVICE_READY'))),
		sessions: () => rec('sessions', created ? [sess] : []),
		session: () => rec('session', sess),
		startSession: () => rec('startSession', (sess = session('MONITORING'))),
		stopSession: () => rec('stopSession', (sess = session('COMPLETED')))
	};
}

export class FakeSocket implements SocketLike {
	static instances: FakeSocket[] = [];
	onopen: ((ev: unknown) => void) | null = null;
	onmessage: ((ev: { data: unknown }) => void) | null = null;
	onclose: ((ev: { code?: number }) => void) | null = null;
	onerror: ((ev: unknown) => void) | null = null;
	closed = false;
	constructor(readonly url: string) {
		FakeSocket.instances.push(this);
	}
	close(): void {
		this.closed = true;
	}
	open(): void {
		this.onopen?.({});
	}
	send(event: unknown): void {
		this.onmessage?.({ data: typeof event === 'string' ? event : JSON.stringify(event) });
	}
	drop(code = 1006): void {
		this.onclose?.({ code });
	}
	static reset(): void {
		FakeSocket.instances = [];
	}
	static get last(): FakeSocket {
		return FakeSocket.instances[FakeSocket.instances.length - 1];
	}
}

let seq = 0;
export function ev<T extends LiveEvent['event_type']>(
	type: T,
	payload: Extract<LiveEvent, { event_type: T }>['payload'],
	opts: { seq?: number; ts?: number | null; session?: string } = {}
): LiveEvent {
	const sequence = opts.seq ?? seq++;
	return {
		contract_version: 'PRODUCT_LIVE_EVENT_V1',
		event_id: `S-PEV${String(sequence).padStart(6, '0')}`,
		sequence_index: sequence,
		emitted_at_us: 1000 * (sequence + 1),
		session_id: opts.session ?? 'SESS-1',
		source_timestamp_us: opts.ts ?? null,
		event_type: type,
		payload
	} as LiveEvent;
}
export function resetSeq(): void {
	seq = 0;
}

/** Spy-able in-memory Storage: lets tests prove nothing (no token) is ever written. */
export function memoryStorage() {
	const data = new Map<string, string>();
	return {
		writes: 0,
		get length() { return data.size; },
		clear() { data.clear(); },
		getItem: (k: string) => data.get(k) ?? null,
		key: (i: number) => [...data.keys()][i] ?? null,
		removeItem(k: string) { data.delete(k); },
		setItem(this: { writes: number }, k: string, v: string) { this.writes += 1; data.set(k, v); }
	};
}
