// CAPSTONE_PRODUCT_CLIENT_V1 -- typed client for PRODUCT_API_CONTRACT_V2 (CAP-004 routes only).
// Same-origin (/product/v1) through the Vite proxy. The browser never calls /v1/infer-window and
// never sends scientific configuration. A bearer token (CLERK mode) is obtained per request from
// the injected provider and is never stored by this module.

import { parseFl10, parseFl10Job, parseFl10Recorded, type Fl10Job, type Fl10Payload, type Fl10Recorded } from './observatory/fl10';
import { parseLiveLink, parseShowcase, type LiveLinkStatus, type ShowcaseBundle } from './observatory/showcase';
import { parseCandidates, parseGenCurves, parseGenParticipants, parseGeneralisation, parseHardwareDemoRun, parseHardwareDemoSessions, parseHardwareV2Preview, parseOverview, parseCapabilities, parseEvalRound, parseEvalSummary, parseExports, parseFigures, parseRoundDetail, parseStudioRun, parseStudioRuns, parseTables } from './studio/parse';
import type { StudioCandidate, GenCurves, GenParticipants, Generalisation, HardwareDemoChoice, HardwareDemoRun, HardwareDemoSession, HardwareV2Preview, StudioOverview, EvalRoundDetail, EvalSummary, RoundDetail, StudioCapabilities, StudioExports, StudioFigures, StudioRun, StudioRunChoice, StudioTables } from './studio/types';
import type {
	AuthIdentity,
	DeviceDescriptor,
	MonitoringSession,
	ProductErrorBody,
	ProductErrorCode,
	ScenarioId,
	SystemInfoV2
} from './types';
import {
	FROZEN_ROUNDS,
	FROZEN_SCENARIO,
	type AggregationMode,
	type Algorithm,
	type CandidateModel,
	type CreateFederationRunRequest,
	type FederationOverview,
	type FederationRound,
	type FederationRun,
	type FLClientIdentity,
	type ModelRegistryView,
	type ReleasedModelRef,
	type RunType
} from './federation/types';
import { parseHardwareTimeline, parseSessionSummary, parseSessionTimeline, type HardwareSessionTimeline, type SessionSummary, type SessionTimeline } from './history/types';
import { parseFlResearchEvidence, parseMlResearchEvidence, type FlResearchEvidence, type MlResearchEvidence } from './research/types';
import { parseCaptureArm, parseHardwareWindowList, parseScenarioTimeline, parseScenarioList, parseWindowTrace,
	type CaptureArm, type HardwareWindowList, type ScenarioInfo, type ScenarioTimeline, type WindowTrace } from './observatory/types';
import { parseFlClientWindowTrace, parseFrozenCohort, parseRunContributions,
	type FlClientWindowTrace, type FrozenCohort, type RunContributions } from './observatory/federation';
import { parseArchitecture, parseBoundaries, parseCalibration, parseFlCurves, parseFlEval, parseReproducibility, parseXaiCase, parseXaiIndex, parseDatasetPreprocessing, parseActivationInspection,
	type DatasetPreprocessing, type ActivationInspection,
	type XaiCase, type XaiIndex, type Architecture, type Boundaries, type Calibration, type FlCurves, type FlEval, type Reproducibility } from './observatory/evidence';
import { parseResearchRecords, parseResearchWindow,
	type ResearchRecord, type ResearchWindow } from './observatory/research';

export const PRODUCT_BASE = '/product/v1';

export type ProductErrorKind =
	| 'AUTHENTICATION_REQUIRED'
	| 'NOT_PERMITTED'
	| 'UNAVAILABLE'
	| 'INVALID_LIFECYCLE_STATE'
	| 'INVALID_REQUEST'
	| 'BACKEND_ERROR'
	| 'TRANSPORT';

export class ProductApiError extends Error {
	constructor(
		readonly status: number,
		readonly kind: ProductErrorKind,
		readonly code: ProductErrorCode | null,
		readonly detail: string
	) {
		super(describeError(kind, detail));
		this.name = 'ProductApiError';
	}
}

export function describeError(kind: ProductErrorKind, detail: string): string {
	const text: Record<ProductErrorKind, string> = {
		AUTHENTICATION_REQUIRED: 'Authentication required',
		NOT_PERMITTED: 'Not permitted (this resource belongs to another user)',
		UNAVAILABLE: 'Resource unavailable',
		INVALID_LIFECYCLE_STATE: 'Not allowed in the current lifecycle state',
		INVALID_REQUEST: 'Invalid product request',
		BACKEND_ERROR: 'Product backend error',
		TRANSPORT: 'Product backend unavailable'
	};
	return detail ? `${text[kind]}: ${detail}` : text[kind];
}

export function kindForStatus(status: number): ProductErrorKind {
	if (status === 401) return 'AUTHENTICATION_REQUIRED';
	if (status === 403) return 'NOT_PERMITTED';
	if (status === 404) return 'UNAVAILABLE';
	if (status === 409) return 'INVALID_LIFECYCLE_STATE';
	if (status === 400 || status === 422) return 'INVALID_REQUEST';
	return 'BACKEND_ERROR';
}

export type TokenProvider = () => Promise<string | null>;

export interface ProductClientOptions {
	base?: string;
	fetchImpl?: typeof fetch;
	getToken?: TokenProvider;
}

export interface ProductClient {
	hardwareStart(): Promise<HardwareSession>;
	hardwarePoll(id: string, after: number): Promise<HardwareSession>;
	hardwareStop(id: string): Promise<HardwareSession>;
	hardwareSessions(): Promise<HardwareSession[]>;
	hardwareSession(id: string): Promise<HardwareSession>;
	hardwareV2Experimental(id: string): Promise<import('./hardware-v2').HardwareV2Experimental>;
	system(): Promise<SystemInfoV2>;
	me(): Promise<AuthIdentity>;
	devices(): Promise<DeviceDescriptor[]>;
	createSimulatedDevice(scenarioId: ScenarioId, displayName?: string): Promise<DeviceDescriptor>;
	scan(deviceId: string): Promise<DeviceDescriptor>;
	connect(deviceId: string): Promise<DeviceDescriptor>;
	disconnect(deviceId: string): Promise<DeviceDescriptor>;
	createSession(deviceId: string, scenarioId: ScenarioId): Promise<MonitoringSession>;
	sessions(): Promise<MonitoringSession[]>;
	session(sessionId: string): Promise<MonitoringSession>;
	sessionSummary(sessionId: string): Promise<SessionSummary>;
	sessionTimeline(sessionId: string): Promise<SessionTimeline>;
	researchMl(): Promise<MlResearchEvidence>;
	researchFl(): Promise<FlResearchEvidence>;
	observatoryScenarios(): Promise<ScenarioInfo[]>;
	observatoryScenarioWindow(scenarioId: string, windowIndex: number): Promise<WindowTrace>;
	observatorySessionWindow(sessionId: string, windowIndex: number): Promise<WindowTrace>;
	/** Recorded-hardware sessions (experimental, resampled): the windows a session emitted, one window's stage trace, and the replay timeline (scored in bounded batches). */
	observatoryHardwareWindows(sessionId: string): Promise<HardwareWindowList>;
	observatoryHardwareWindow(sessionId: string, windowIndex: number): Promise<WindowTrace>;
	hardwareSessionTimeline(sessionId: string, budget?: number): Promise<HardwareSessionTimeline>;
	observatoryCohort(): Promise<FrozenCohort>;
	observatoryRunContributions(runId: string): Promise<RunContributions>;
	observatoryFlClientWindow(clientId: string, windowIndex: number): Promise<FlClientWindowTrace>;
	observatoryResearchRecords(): Promise<ResearchRecord[]>;
	observatoryResearchWindow(recordId: string, windowIndex: number): Promise<ResearchWindow>;
	observatoryArmSessionCapture(sessionId: string, windowIndex: number): Promise<CaptureArm>;
	observatoryCapturedSessionWindow(sessionId: string): Promise<WindowTrace>;
	observatoryScenarioTimeline(scenarioId: string): Promise<ScenarioTimeline>;
	observatoryFlEval(): Promise<FlEval>;
	observatoryShowcase(): Promise<ShowcaseBundle>;
	fl10Recorded(): Promise<Fl10Recorded[]>;
	fl10RecordedBundle(key: string): Promise<Fl10Payload>;
	fl10Start(mode: 'A' | 'B'): Promise<Fl10Job>;
	fl10Status(id: string): Promise<Fl10Job>;
	fl10JobBundle(id: string): Promise<Fl10Payload>;
	fl10ExportFile(key: string, item: string, fmt: string): Promise<{ blob: Blob; sha256: string | null }>;
	// NHM_UNIFIED_LIVE_FEDERATION_STUDIO_001: unified, owner-scoped run observation (3-round runs are still created through the frozen federation routes)
	studioCapabilities(): Promise<StudioCapabilities>;
	hardwareDemoSessions(): Promise<HardwareDemoSession[]>;
	hardwareV2Preview(sessionIds: string[]): Promise<HardwareV2Preview>;
	hardwareDemoRuns(): Promise<HardwareDemoRun[]>;
	hardwareDemoStart(choice: HardwareDemoChoice): Promise<StudioRun>;
	hardwareDemoRun(runId: string): Promise<HardwareDemoRun>;
	studioRuns(): Promise<StudioRun[]>;
	studioRun(runId: string): Promise<StudioRun>;
	studioStartTenRound(choice: StudioRunChoice): Promise<StudioRun>;
	studioCandidates(): Promise<StudioCandidate[]>;
	studioOverview(runId: string): Promise<StudioOverview>;
	studioEvaluation(runId: string): Promise<EvalSummary>;
	studioEvaluationRound(runId: string, round: number): Promise<EvalRoundDetail>;
	studioRoundDetail(runId: string, round: number): Promise<RoundDetail>;
	studioGeneralisation(runId: string): Promise<Generalisation>;
	studioGeneralisationCurves(runId: string, round: number): Promise<GenCurves>;
	studioGeneralisationParticipants(runId: string, round: number): Promise<GenParticipants>;
	studioFigures(runId: string, round?: number | null): Promise<StudioFigures>;
	studioTables(runId: string): Promise<StudioTables>;
	studioExports(runId: string): Promise<StudioExports>;
	studioExportFile(runId: string, item: string, fmt: string): Promise<{ blob: Blob; sha256: string | null }>;
	observatoryLiveLinkStart(): Promise<LiveLinkStatus>;
	observatoryLiveLinkStatus(id: string): Promise<LiveLinkStatus>;
	observatoryFlCurves(dataset: string, modelId: string): Promise<FlCurves>;
	observatoryExplainability(): Promise<XaiIndex>;
	observatoryExplainabilityCase(caseType: string): Promise<XaiCase>;
	observatoryDatasetPreprocessing(): Promise<DatasetPreprocessing>;
	observatoryActivations(scenarioId: string, windowIndex: number, layer?: string): Promise<ActivationInspection>;
	observatoryArchitecture(): Promise<Architecture>;
	observatoryCalibration(): Promise<Calibration>;
	observatoryBoundaries(): Promise<Boundaries>;
	observatoryReproducibility(): Promise<Reproducibility>;
	startSession(sessionId: string): Promise<MonitoringSession>;
	stopSession(sessionId: string): Promise<MonitoringSession>;
	// CAPSTONE_FEDERATION_PRODUCT_CLIENT_V1 (CAP-008): CAP-007 routes only
	federationOverview(): Promise<FederationOverview>;
	federationClients(): Promise<FLClientIdentity[]>;
	createFederationRun(choice: FederationRunChoice): Promise<FederationRun>;
	federationRuns(): Promise<FederationRun[]>;
	federationRun(runId: string): Promise<FederationRun>;
	startFederationRun(runId: string): Promise<FederationRun>;
	federationRounds(runId: string): Promise<FederationRound[]>;
	models(): Promise<ModelRegistryView>;
	model(modelId: string): Promise<ReleasedModelRef | CandidateModel>;
}

export interface HardwareReading {
	ordinal: number; id: string; ingested_at: string; ecg: number; bpm: number | null; spo2: number | null; collection: string | null;
}
export interface HardwareSession {
	version: 'HARDWARE_TELEMETRY_V1'; session_id: string; source: string; collection: string;
	started_at: string; stopped_at: string | null; status: string; source_state: string;
	record_count: number; last_received_at: string | null; readings: HardwareReading[];
	trace_limit: number; stale_threshold_seconds: number;
	summary?: { stored_readings: number; first_reading_at: string | null; last_reading_at: string | null; span_seconds: number | null; arrival_hz: number | null; ecg_min: number | null; ecg_max: number | null; bpm_mean: number | null; spo2_mean: number | null };
}

/** The only three user-controlled run options; scenario and rounds are frozen constants. */
export interface FederationRunChoice {
	run_type: RunType;
	algorithm: Algorithm;
	secagg_mode: AggregationMode;
}

/** Exactly the five frozen request fields - no model, checkpoint, mu, learning rate, optimizer, batch size. */
export function federationRunBody(choice: FederationRunChoice): CreateFederationRunRequest {
	return {
		run_type: choice.run_type,
		algorithm: choice.algorithm,
		secagg_mode: choice.secagg_mode,
		planned_rounds: FROZEN_ROUNDS,
		scenario_id: FROZEN_SCENARIO
	};
}

export function createProductClient(options: ProductClientOptions = {}): ProductClient {
	const base = options.base ?? PRODUCT_BASE;
	const doFetch = options.fetchImpl ?? ((...args: Parameters<typeof fetch>) => fetch(...args));

	async function call<T>(method: 'GET' | 'POST', path: string, body?: unknown): Promise<T> {
		const headers: Record<string, string> = { Accept: 'application/json' };
		const token = options.getToken ? await options.getToken() : null;
		if (token) headers.Authorization = `Bearer ${token}`;
		if (body !== undefined) headers['Content-Type'] = 'application/json';
		let response: Response;
		try {
			response = await doFetch(`${base}${path}`, {
				method,
				headers,
				credentials: 'same-origin',
				body: body === undefined ? undefined : JSON.stringify(body)
			});
		} catch (cause) {
			throw new ProductApiError(0, 'TRANSPORT', null, cause instanceof Error ? cause.message : '');
		}
		if (!response.ok) {
			let parsed: ProductErrorBody | null = null;
			try {
				const data = (await response.json()) as { error?: ProductErrorBody };
				parsed = data.error ?? null;
			} catch {
				parsed = null;
			}
			throw new ProductApiError(
				response.status,
				kindForStatus(response.status),
				parsed?.code ?? null,
				parsed?.message ?? ''
			);
		}
		return (await response.json()) as T;
	}

	const enc = encodeURIComponent;
	return {
		hardwareStart: () => call('POST', '/hardware/sessions'),
		hardwarePoll: (id, after) => call('GET', `/hardware/sessions/${enc(id)}/poll?after=${after}`),
		hardwareStop: (id) => call('POST', `/hardware/sessions/${enc(id)}/stop`),
		hardwareSessions: () => call('GET', '/hardware/sessions'),
		hardwareSession: (id) => call('GET', `/hardware/sessions/${enc(id)}`),
		hardwareV2Experimental: (id) => call('GET', `/hardware/sessions/${enc(id)}/v2-experimental`),
		system: () => call('GET', '/system'),
		me: () => call('GET', '/me'),
		devices: () => call('GET', '/devices'),
		createSimulatedDevice: (scenarioId, displayName) =>
			call('POST', '/devices/simulated', {
				scenario_id: scenarioId,
				...(displayName ? { display_name: displayName } : {})
			}),
		scan: (id) => call('POST', `/devices/${enc(id)}/scan`),
		connect: (id) => call('POST', `/devices/${enc(id)}/connect`),
		disconnect: (id) => call('POST', `/devices/${enc(id)}/disconnect`),
		createSession: (deviceId, scenarioId) =>
			call('POST', '/sessions', { device_id: deviceId, scenario_id: scenarioId }),
		sessions: () => call('GET', '/sessions'),
		session: (id) => call('GET', `/sessions/${enc(id)}`),
		sessionSummary: async (id) => parseSessionSummary(await call<unknown>('GET', `/sessions/${enc(id)}/summary`)),
		sessionTimeline: async (id) => parseSessionTimeline(await call<unknown>('GET', `/sessions/${enc(id)}/timeline`)),
		researchMl: async () => parseMlResearchEvidence(await call<unknown>('GET', '/research/ml')),
		researchFl: async () => parseFlResearchEvidence(await call<unknown>('GET', '/research/fl')),
		observatoryScenarios: async () => parseScenarioList(await call<unknown>('GET', '/observatory/scenarios')),
		observatoryScenarioWindow: async (id, index) => parseWindowTrace(await call<unknown>('GET',
			`/observatory/scenarios/${enc(id)}/windows/${enc(String(index))}`)),
		observatorySessionWindow: async (id, index) => parseWindowTrace(await call<unknown>('GET',
			`/observatory/sessions/${enc(id)}/windows/${enc(String(index))}`)),
		observatoryHardwareWindows: async (id) => parseHardwareWindowList(await call<unknown>('GET', `/hardware/sessions/${enc(id)}/observatory/windows`)),
		observatoryHardwareWindow: async (id, index) => parseWindowTrace(await call<unknown>('GET', `/hardware/sessions/${enc(id)}/observatory/windows/${enc(String(index))}`)),
		hardwareSessionTimeline: async (id, budget = 24) => parseHardwareTimeline(await call<unknown>('GET', `/hardware/sessions/${enc(id)}/observatory/timeline?budget=${budget}`)),
		observatoryCohort: async () => parseFrozenCohort(await call<unknown>('GET', '/observatory/federation/cohort')),
		observatoryRunContributions: async (id) => parseRunContributions(await call<unknown>('GET',
			`/observatory/federation/runs/${enc(id)}/contributions`)),
		observatoryFlClientWindow: async (id, index) => parseFlClientWindowTrace(await call<unknown>('GET',
			`/observatory/federation/clients/${enc(id)}/windows/${enc(String(index))}`)),
		observatoryResearchRecords: async () => parseResearchRecords(await call<unknown>('GET',
			'/observatory/research/records')),
		observatoryResearchWindow: async (id, index) => parseResearchWindow(await call<unknown>('GET',
			`/observatory/research/records/${enc(id)}/windows/${enc(String(index))}`)),
		observatoryArmSessionCapture: async (id, index) => parseCaptureArm(await call<unknown>('POST',
			`/observatory/sessions/${enc(id)}/capture/${enc(String(index))}`)),
		observatoryCapturedSessionWindow: async (id) => parseWindowTrace(await call<unknown>('GET',
			`/observatory/sessions/${enc(id)}/capture`)),
		observatoryScenarioTimeline: async (id) => parseScenarioTimeline(await call<unknown>('GET', `/observatory/scenarios/${enc(id)}/timeline`)),
		observatoryLiveLinkStart: async () => parseLiveLink(await call<unknown>('POST', '/observatory/live-link/runs')),
		observatoryLiveLinkStatus: async (id) => parseLiveLink(await call<unknown>('GET', `/observatory/live-link/runs/${enc(id)}`)),
		fl10Recorded: async () => parseFl10Recorded(await call<unknown>('GET', '/observatory/fl10/recorded')),
		fl10RecordedBundle: async (key) => parseFl10(await call<unknown>('GET', `/observatory/fl10/recorded/${enc(key)}`)),
		fl10Start: async (mode) => parseFl10Job(await call<unknown>('POST', '/observatory/fl10/runs', { mode })),
		fl10Status: async (id) => parseFl10Job(await call<unknown>('GET', `/observatory/fl10/runs/${enc(id)}`)),
		fl10JobBundle: async (id) => parseFl10(await call<unknown>('GET', `/observatory/fl10/runs/${enc(id)}/bundle`)),
		fl10ExportFile: async (key, item, fmt) => {
			const headers: Record<string, string> = {};
			const token = options.getToken ? await options.getToken() : null;
			if (token) headers.Authorization = `Bearer ${token}`;
			const path = key.startsWith('recorded-')
				? `/observatory/fl10/recorded/${enc(key)}/exports/${enc(item)}/${enc(fmt)}`
				: `/observatory/fl10/runs/${enc(key)}/exports/${enc(item)}/${enc(fmt)}`;
			const response = await doFetch(`${base}${path}`, { method: 'GET', headers, credentials: 'same-origin' });
			if (!response.ok) throw new ProductApiError(response.status, kindForStatus(response.status), null, 'export failed');
			return { blob: await response.blob(), sha256: response.headers.get('X-Content-SHA256') };
		},
		studioCapabilities: async () => parseCapabilities(await call<unknown>('GET', '/studio/capabilities')),
		hardwareDemoSessions: async () => parseHardwareDemoSessions(await call<unknown>('GET', '/studio/hardware-demo/sessions')),
		hardwareV2Preview: async (sessionIds) => parseHardwareV2Preview(await call<unknown>('GET', `/studio/hardware-demo/v2-preview?session_ids=${encodeURIComponent(sessionIds.join(','))}`)),
		hardwareDemoRuns: async () => (await call<unknown[]>('GET', '/studio/hardware-demo/runs')).filter((r) => (r as { status?: unknown } | null)?.status === 'COMPLETED').map(parseHardwareDemoRun),   // running / failed runs are not warm-start sources (and must not break the list)
		hardwareDemoStart: async (choice) => parseStudioRun(await call<unknown>('POST', '/studio/hardware-demo/runs', choice)),
		hardwareDemoRun: async (id) => parseHardwareDemoRun(await call<unknown>('GET', `/studio/hardware-demo/runs/${enc(id)}`)),
		studioRuns: async () => parseStudioRuns(await call<unknown>('GET', '/studio/runs')),
		studioCandidates: async () => parseCandidates(await call<unknown>('GET', '/studio/candidates')),
		studioRun: async (id) => parseStudioRun(await call<unknown>('GET', `/studio/runs/${enc(id)}`)),
		studioStartTenRound: async (choice) => parseStudioRun(await call<unknown>('POST', '/studio/runs', { run_length: choice.run_length, source_mode: choice.source_mode, ...(choice.monitored_site ? { monitored_site: choice.monitored_site } : {}), ...(choice.signal_session_id ? { signal_session_id: choice.signal_session_id } : {}), ...(choice.initialisation ? { initialisation: choice.initialisation } : {}), ...(choice.cohort ? { cohort: choice.cohort } : {}), ...(choice.candidate_id ? { candidate_id: choice.candidate_id } : {}), algorithm: choice.algorithm ?? 'FEDAVG', secagg_mode: choice.secagg_mode ?? 'PLAIN' })),
		studioOverview: async (id) => parseOverview(await call<unknown>('GET', `/studio/runs/${enc(id)}/overview`)),
		studioEvaluation: async (id) => parseEvalSummary(await call<unknown>('GET', `/studio/runs/${enc(id)}/evaluation`)),
		studioEvaluationRound: async (id, round) => parseEvalRound(await call<unknown>('GET', `/studio/runs/${enc(id)}/evaluation/${round}`)),
		studioGeneralisation: async (id) => parseGeneralisation(await call<unknown>('GET', `/studio/runs/${enc(id)}/generalisation`)),
		studioGeneralisationCurves: async (id, round) => parseGenCurves(await call<unknown>('GET', `/studio/runs/${enc(id)}/generalisation/curves/${round}`)),
		studioGeneralisationParticipants: async (id, round) => parseGenParticipants(await call<unknown>('GET', `/studio/runs/${enc(id)}/generalisation/participants/${round}`)),
		studioRoundDetail: async (id, round) => parseRoundDetail(await call<unknown>('GET', `/studio/runs/${enc(id)}/rounds/${round}`)),
		studioFigures: async (id, round) => parseFigures(await call<unknown>('GET', `/studio/runs/${enc(id)}/figures${round === null || round === undefined ? '' : `?round=${round}`}`)),
		studioTables: async (id) => parseTables(await call<unknown>('GET', `/studio/runs/${enc(id)}/tables`)),
		studioExports: async (id) => parseExports(await call<unknown>('GET', `/studio/runs/${enc(id)}/exports`)),
		studioExportFile: async (id, item, fmt) => {
			const headers: Record<string, string> = {};
			const token = options.getToken ? await options.getToken() : null;
			if (token) headers.Authorization = `Bearer ${token}`;
			const response = await doFetch(`${base}/studio/runs/${enc(id)}/exports/${enc(item)}/${enc(fmt)}`, { method: 'GET', headers, credentials: 'same-origin' });
			if (!response.ok) throw new ProductApiError(response.status, kindForStatus(response.status), null, 'export failed');
			return { blob: await response.blob(), sha256: response.headers.get('X-Content-SHA256') };
		},
		observatoryShowcase: async () => parseShowcase(await call<unknown>('GET', '/observatory/showcase/bundle')),
		observatoryFlEval: async () => parseFlEval(await call<unknown>('GET', '/observatory/evidence/fl-eval')),
		observatoryFlCurves: async (dataset, modelId) => parseFlCurves(await call<unknown>('GET',
			`/observatory/evidence/fl-eval/curves/${enc(dataset)}/${enc(modelId)}`)),
		observatoryExplainability: async () => parseXaiIndex(await call<unknown>('GET', '/observatory/evidence/explainability')),
		observatoryExplainabilityCase: async (c) => parseXaiCase(await call<unknown>('GET', `/observatory/evidence/explainability/${enc(c)}`)),
		observatoryDatasetPreprocessing: async () => parseDatasetPreprocessing(await call<unknown>('GET', '/observatory/research/preprocessing')),
		observatoryActivations: async (id, index, layer) => parseActivationInspection(await call<unknown>('GET', `/observatory/model/activations/${enc(id)}/${enc(String(index))}${layer ? `?layer=${enc(layer)}` : ''}`)),
		observatoryArchitecture: async () => parseArchitecture(await call<unknown>('GET', '/observatory/model/architecture')),
		observatoryCalibration: async () => parseCalibration(await call<unknown>('GET', '/observatory/model/calibration')),
		observatoryBoundaries: async () => parseBoundaries(await call<unknown>('GET', '/observatory/evidence/boundaries')),
		observatoryReproducibility: async () => parseReproducibility(await call<unknown>('GET', '/observatory/reproducibility')),
		startSession: (id) => call('POST', `/sessions/${enc(id)}/start`),
		stopSession: (id) => call('POST', `/sessions/${enc(id)}/stop`),
		federationOverview: () => call('GET', '/federation'),
		federationClients: () => call('GET', '/federation/clients'),
		createFederationRun: (choice) => call('POST', '/federation/runs', federationRunBody(choice)),
		federationRuns: () => call('GET', '/federation/runs'),
		federationRun: (id) => call('GET', `/federation/runs/${enc(id)}`),
		startFederationRun: (id) => call('POST', `/federation/runs/${enc(id)}/start`),
		federationRounds: (id) => call('GET', `/federation/runs/${enc(id)}/rounds`),
		models: () => call('GET', '/models'),
		model: (id) => call('GET', `/models/${enc(id)}`)
	};
}

/** Same-origin monitoring WebSocket URL. NEVER carries a token. CLERK mode sends a fresh
 * verified session token in the first WebSocket frame, not in the URL. */
export function liveSocketUrl(sessionId: string, location: { protocol: string; host: string }): string {
	const scheme = location.protocol === 'https:' ? 'wss:' : 'ws:';
	return `${scheme}//${location.host}${PRODUCT_BASE}/sessions/${encodeURIComponent(sessionId)}/live`;
}

/** Same-origin federation WebSocket URL. NEVER carries a token, cookie, user id or secret;
 * CLERK mode authenticates in the first WebSocket frame. */
export function federationSocketUrl(runId: string, location: { protocol: string; host: string }): string {
	const scheme = location.protocol === 'https:' ? 'wss:' : 'ws:';
	// 10-round Studio runs have their own typed event journal; every 3-round run keeps the original product route unchanged.
	if (runId.startsWith('FL10RUN-') || runId.startsWith('HDFLRUN-') || runId.startsWith('recorded-')) return `${scheme}//${location.host}${PRODUCT_BASE}/studio/runs/${encodeURIComponent(runId)}/live`;
	return `${scheme}//${location.host}${PRODUCT_BASE}/federation/runs/${encodeURIComponent(runId)}/live`;
}
