// CAPSTONE_MONITORING_STORE_V1 -- Svelte 5 product state. Holds product/UI state only; every
// physiological/monitoring value comes from a validated backend event (see live-model.ts).

import { ProductApiError, liveSocketUrl, type ProductClient } from './api';
import { FrontendAuth, type AuthState } from './auth';
import { LiveModel, type MonitoringStateChange, type StreamError } from './live-model';
import { LiveSocket, type LiveSocketStatus } from './socket';
import type { WaveformSegment, GapRun } from './waveform';
import type {
	ContextSnapshotPayload,
	DeviceDescriptor,
	DeviceState,
	InferenceResultPayload,
	LiveEventType,
	MonitoringSession,
	MonitoringStateName,
	QualityStatusPayload,
	ScenarioId,
	SessionState,
	SystemErrorPayload
} from './types';

export interface LiveView {
	eventCount: number;
	countsByType: Partial<Record<LiveEventType, number>>;
	sessionState: SessionState | null;
	sessionElapsedMs: number | null;
	deviceState: DeviceState | null;
	deviceChanges: { sequence_index: number; state: DeviceState; reason: string | null }[];
	quality: (QualityStatusPayload & { window_ts: number | null }) | null;
	qualityCounts: Record<string, number>;
	context: (ContextSnapshotPayload & { window_ts: number | null }) | null;
	contextIsCurrent: boolean;
	contextState: 'CURRENT' | 'PENDING' | 'UNAVAILABLE';
	inference: InferenceResultPayload | null;
	inferenceIsCurrent: boolean;
	inferenceState: 'CURRENT' | 'PENDING' | 'NONE_FOR_WINDOW' | 'NONE';
	monitoringState: MonitoringStateName | null;
	monitoringChanges: MonitoringStateChange[];
	systemErrors: SystemErrorPayload[];
	streamError: StreamError | null;
	segments: WaveformSegment[];
	waveformStart: number;
	waveformEnd: number;
	waveformCapacity: number;
	waveformTotalSamples: number;
	gaps: GapRun[];
	openGap: GapRun | null;
	modelIds: string[];
	calibrationIds: string[];
	inferenceCount: number;
}

export function emptyView(): LiveView {
	return {
		eventCount: 0,
		countsByType: {},
		sessionState: null,
		sessionElapsedMs: null,
		deviceState: null,
		deviceChanges: [],
		quality: null,
		qualityCounts: { VALID: 0, DEGRADED: 0, UNUSABLE: 0 },
		context: null,
		contextIsCurrent: false,
		contextState: 'UNAVAILABLE',
		inference: null,
		inferenceIsCurrent: false,
		inferenceState: 'NONE',
		monitoringState: null,
		monitoringChanges: [],
		systemErrors: [],
		streamError: null,
		segments: [],
		waveformStart: 0,
		waveformEnd: 0,
		waveformCapacity: 0,
		waveformTotalSamples: 0,
		gaps: [],
		openGap: null,
		modelIds: [],
		calibrationIds: [],
		inferenceCount: 0
	};
}

type Frame = (callback: () => void) => unknown;
const defaultFrame: Frame = (callback) =>
	typeof requestAnimationFrame === 'function' ? requestAnimationFrame(callback) : setTimeout(callback, 16);

export class ProductStore {
	readonly auth: FrontendAuth;
	authState = $state<AuthState>({ phase: 'LOADING', mode: null, system: null, identity: null, error: null });
	devices = $state<DeviceDescriptor[]>([]);
	sessions = $state<MonitoringSession[]>([]);
	activeSession = $state<MonitoringSession | null>(null);
	selectedDeviceId = $state<string | null>(null);
	/** scenario chosen when a virtual wearable was attached in this browser session (the device
	 * descriptor itself does not carry it); persisted sessions are the fallback source. */
	deviceScenarios = $state<Record<string, ScenarioId>>({});
	busy = $state(false);
	error = $state<string | null>(null);
	socketStatus = $state<LiveSocketStatus | 'IDLE'>('IDLE');
	live = $state.raw<LiveView>(emptyView());

	private model = new LiveModel(null);
	private socket: LiveSocket | null = null;
	private flushScheduled = false;
	private finishedRefreshed = false;

	constructor(
		auth: FrontendAuth = new FrontendAuth(),
		private readonly frame: Frame = defaultFrame,
		private readonly socketFactory?: (url: string) => import('./socket').SocketLike
	) {
		this.auth = auth;
		auth.subscribe((state) => (this.authState = state));
	}

	get api(): ProductClient {
		return this.auth.api;
	}
	get system() {
		return this.authState.system;
	}
	get selectedDevice(): DeviceDescriptor | null {
		return this.devices.find((d) => d.device_id === this.selectedDeviceId) ?? this.devices[0] ?? null;
	}

	private async run<T>(action: () => Promise<T>): Promise<T | null> {
		this.busy = true;
		this.error = null;
		try {
			return await action();
		} catch (cause) {
			this.error = cause instanceof ProductApiError ? cause.message : cause instanceof Error ? cause.message : String(cause);
			return null;
		} finally {
			this.busy = false;
		}
	}

	async init(): Promise<AuthState> {
		return this.auth.restore();
	}

	async loadDevices(): Promise<void> {
		await this.run(async () => {
			this.devices = await this.api.devices();
		});
	}
	async loadSessions(): Promise<void> {
		await this.run(async () => {
			this.sessions = await this.api.sessions();
		});
	}

	/** Scenario a device was created with, if known (memory, then persisted sessions). */
	scenarioFor(deviceId: string): ScenarioId | null {
		const known = this.deviceScenarios[deviceId];
		if (known) return known;
		const session = this.sessions.find((x) => x.device_id === deviceId && x.simulation_provenance);
		return (session?.simulation_provenance?.scenario_id as ScenarioId | undefined) ?? null;
	}

	private upsertDevice(device: DeviceDescriptor): void {
		const index = this.devices.findIndex((d) => d.device_id === device.device_id);
		this.devices = index < 0 ? [...this.devices, device] : this.devices.map((d, i) => (i === index ? device : d));
		this.selectedDeviceId = device.device_id;
	}

	async attachVirtualWearable(scenario: ScenarioId): Promise<DeviceDescriptor | null> {
		const device = await this.run(() => this.api.createSimulatedDevice(scenario));
		if (device) {
			this.deviceScenarios = { ...this.deviceScenarios, [device.device_id]: scenario };
			this.upsertDevice(device);
		}
		return device;
	}
	async scan(id: string): Promise<void> {
		const device = await this.run(() => this.api.scan(id));
		if (device) this.upsertDevice(device);
	}
	async connect(id: string): Promise<void> {
		const device = await this.run(() => this.api.connect(id));
		if (device) this.upsertDevice(device);
	}
	async disconnect(id: string): Promise<void> {
		const device = await this.run(() => this.api.disconnect(id));
		if (device) this.upsertDevice(device);
	}

	async createSession(deviceId: string, scenario: ScenarioId): Promise<MonitoringSession | null> {
		const session = await this.run(() => this.api.createSession(deviceId, scenario));
		if (session) {
			this.activeSession = session;
			this.sessions = [session, ...this.sessions.filter((s) => s.session_id !== session.session_id)];
			this.openLive(session.session_id);
		}
		return session;
	}
	async startSession(): Promise<void> {
		const active = this.activeSession;
		if (!active) return;
		const session = await this.run(() => this.api.startSession(active.session_id));
		if (session) this.activeSession = session;
	}
	async stopSession(): Promise<void> {
		const active = this.activeSession;
		if (!active) return;
		const session = await this.run(() => this.api.stopSession(active.session_id));
		if (session) this.activeSession = session;
	}
	async refreshActive(): Promise<void> {
		const active = this.activeSession;
		if (!active) return;
		const session = await this.run(() => this.api.session(active.session_id));
		if (session) {
			this.activeSession = session;
			this.sessions = this.sessions.map((s) => (s.session_id === session.session_id ? session : s));
		}
	}

	// ---- live stream -----------------------------------------------------------------------
	openLive(sessionId: string): void {
		this.closeLive();
		this.model = new LiveModel(sessionId);
		this.flush();
		const url = liveSocketUrl(sessionId, location);
		this.socket = new LiveSocket({
			url,
			factory: this.socketFactory,
			handlers: {
				onReset: () => {
					this.finishedRefreshed = false;
					this.model.reset();
					this.flush();
				},
				onMessage: (data) => this.onMessage(data),
				onStatus: (status) => {
					this.socketStatus = status;
					if (status === 'CLOSED_NORMAL') {
						this.flush();
						void this.refreshActive();
						void this.loadDevices(); // the device ends STOPPED; do not keep showing CONNECTED
					}
				}
			}
		});
		this.socket.connect();
	}

	reconnectLive(): void {
		this.socket?.reconnect();
	}

	closeLive(): void {
		this.socket?.close();
		this.socket = null;
		this.socketStatus = 'IDLE';
	}

	private onMessage(data: unknown): void {
		let raw: unknown;
		try {
			raw = typeof data === 'string' ? JSON.parse(data) : undefined;
		} catch {
			raw = undefined;
		}
		const ok = this.model.applyRaw(raw);
		if (!ok) {
			// PRODUCT STREAM ERROR: stop consuming; never fabricate missing events. Explicit reconnect only.
			this.socket?.close();
			this.socketStatus = 'DISCONNECTED';
			this.flush();
			return;
		}
		if ((this.model.sessionState === 'COMPLETED' || this.model.sessionState === 'FAILED') && !this.finishedRefreshed) {
			this.finishedRefreshed = true;
			void this.refreshActive();
			void this.loadDevices();
		}
		this.schedule();
	}

	private schedule(): void {
		if (this.flushScheduled) return;
		this.flushScheduled = true;
		this.frame(() => {
			this.flushScheduled = false;
			this.flush();
		});
	}

	/** Copy the bounded model into reactive state. */
	flush(): void {
		const m = this.model;
		this.live = {
			eventCount: m.eventCount,
			countsByType: { ...m.countsByType },
			sessionState: m.sessionState,
			sessionElapsedMs: m.sessionElapsedMs,
			deviceState: m.deviceState,
			deviceChanges: m.deviceChanges.slice(-12),
			quality: m.latestQuality,
			qualityCounts: { ...m.qualityCounts },
			context: m.latestContext,
			contextIsCurrent: m.contextIsCurrent,
			contextState: m.contextState,
			inference: m.latestInference,
			inferenceIsCurrent: m.inferenceIsCurrent,
			inferenceState: m.inferenceState,
			monitoringState: m.monitoringState,
			monitoringChanges: m.monitoringChanges.slice(-20),
			systemErrors: m.systemErrors.slice(-5),
			streamError: m.streamError,
			segments: m.waveform.segments(),
			waveformStart: m.waveform.start,
			waveformEnd: m.waveform.end,
			waveformCapacity: m.waveform.capacity,
			waveformTotalSamples: m.waveform.totalSamples,
			gaps: [...m.waveform.gaps],
			openGap: m.waveform.openGap,
			modelIds: [...m.modelIds],
			calibrationIds: [...m.calibrationIds],
			inferenceCount: m.inferenceCount
		};
	}

	resetLive(): void {
		this.closeLive();
		this.model = new LiveModel(null);
		this.activeSession = null;
		this.flush();
	}
}

let singleton: ProductStore | null = null;
export function getProductStore(): ProductStore {
	singleton ??= new ProductStore();
	return singleton;
}

/** Test seam: replace the app-wide store (component tests inject a store with a fake backend). */
export function setProductStore(store: ProductStore | null): void {
	singleton = store;
}
