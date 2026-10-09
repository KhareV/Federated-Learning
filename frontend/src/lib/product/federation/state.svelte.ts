// CAPSTONE_FEDERATION_STORE_UI_V1 -- Svelte 5 federation product state, deliberately SEPARATE from the
// monitoring store: it consumes only federation events (FederationLiveModel) and CAP-007 REST responses.
// The dashboard is an observer: closing the socket never stops a run (it executes on the backend).

import { ProductApiError, federationSocketUrl, type ProductClient } from '../api';
import { LiveSocket, type LiveSocketStatus, type SocketLike } from '../socket';
import { FederationLiveModel, type FederationView } from './live-model';
import type { CandidateModel, FederationOverview, FederationRound, FederationRun, FLClientIdentity, ModelRegistryView } from './types';
import type { FederationRunChoice } from '../api';
import type { StudioRun, StudioRunChoice } from '../studio/types';

/** Ten-round Studio runs have their own typed journal and descriptor; every other run id keeps the original federation routes untouched. */
export const isStudioRunId = (runId: string): boolean => runId.startsWith('FL10RUN-') || runId.startsWith('recorded-');

/** Presentation adapter: the Studio descriptor in the shape the original Federation Studio components already consume. No field is invented. */
export function studioRunToFederationRun(d: StudioRun): FederationRun {
	return { run_id: d.run_id, run_type: d.run_type, base_model_id: 'FL_INIT_V2', federation_protocol_id: d.engine === 'FL10_10R' ? 'NHM_FL10_SYNTHETIC_ENGINEERING_V1' : 'CAPSTONE_FEDERATION_PROTOCOL_V1',
		algorithm: d.algorithm as FederationRun['algorithm'], client_ids: d.client_ids, planned_rounds: d.planned_rounds, current_round: d.current_round, started_at_us: null, completed_at_us: null, status: d.status,
		secagg_mode: d.secagg_mode as FederationRun['secagg_mode'], candidate_ids: [], engineering_only: true };
}

export type ClientsPhase = 'IDLE' | 'PREPARING' | 'READY' | 'ERROR';
export const REPLAY_NO_SOURCE = 'NO COMPATIBLE LIVE RUN EXISTS YET. COMPLETE A LIVE RUN WITH THIS CONFIGURATION FIRST.';

type Frame = (callback: () => void) => unknown;
const defaultFrame: Frame = (cb) => (typeof requestAnimationFrame === 'function' ? requestAnimationFrame(cb) : setTimeout(cb, 16));

function describe(cause: unknown): string {
	return cause instanceof ProductApiError ? cause.message : cause instanceof Error ? cause.message : String(cause);
}

export class FederationStore {
	overview = $state<FederationOverview | null>(null);
	clients = $state<FLClientIdentity[]>([]);
	clientsPhase = $state<ClientsPhase>('IDLE');
	runs = $state<FederationRun[]>([]);
	run = $state<FederationRun | null>(null);
	rounds = $state<FederationRound[]>([]);
	registry = $state<ModelRegistryView | null>(null);
	socketStatus = $state<LiveSocketStatus | 'IDLE'>('IDLE');
	busy = $state(false);
	error = $state<string | null>(null);
	replayNoSource = $state(false);
	view = $state.raw<FederationView>(new FederationLiveModel(null).snapshot);
	/** Validated events of the CURRENT run, in order: the source of truth for historical (selected-round) views. */
	eventLog = $state.raw<unknown[]>([]);

	private model = new FederationLiveModel(null);
	private socket: LiveSocket | null = null;
	private flushScheduled = false;
	private finishedRefreshed = false;
	private clientsInFlight: Promise<void> | null = null;
	private roundViews = new Map<string, FederationView>();

	constructor(
		private readonly getApi: () => ProductClient,
		private readonly frame: Frame = defaultFrame,
		private readonly socketFactory?: (url: string) => SocketLike
	) {}

	private get api(): ProductClient {
		return this.getApi();
	}

	/** Federation controls are enabled only when /system reports the CAP-007 runtime. */
	static backendEnabled(federationRuntime: string | null | undefined): boolean {
		return federationRuntime === 'ENABLED_ENGINEERING';
	}

	get candidates(): CandidateModel[] {
		return this.registry?.capstone_fl_candidates ?? [];
	}

	async loadOverview(): Promise<void> {
		try {
			this.overview = await this.api.federationOverview();
		} catch (cause) {
			this.error = describe(cause);
		}
	}

	/** Cold start can legitimately take ~14 s (eight deterministic datasets are built once per process):
	 * one request at a time, no retry, no error merely because it is slow. */
	loadClients(): Promise<void> {
		if (this.clientsPhase === 'READY') return Promise.resolve();
		this.clientsInFlight ??= (async () => {
			this.clientsPhase = 'PREPARING';
			try {
				this.clients = await this.api.federationClients();
				this.clientsPhase = 'READY';
			} catch (cause) {
				this.error = describe(cause);
				this.clientsPhase = 'ERROR';
			} finally {
				this.clientsInFlight = null;
			}
		})();
		return this.clientsInFlight;
	}

	async loadRuns(): Promise<void> {
		try {
			const product = (await this.api.federationRuns()).slice().reverse();
			let studio: FederationRun[] = [];
			try {
				studio = (await this.api.studioRuns()).filter((r) => r.engine === 'FL10_10R').map(studioRunToFederationRun).reverse();
			} catch {
				studio = [];   // a backend without the Studio routes simply has no 10-round runs
			}
			this.runs = [...studio, ...product];
		} catch (cause) {
			this.error = describe(cause);
		}
	}

	async loadModels(): Promise<void> {
		try {
			this.registry = await this.api.models();
		} catch (cause) {
			this.error = describe(cause);
		}
	}

	async loadRun(runId: string): Promise<FederationRun | null> {
		try {
			if (isStudioRunId(runId)) {
				this.run = studioRunToFederationRun(await this.api.studioRun(runId));
				this.rounds = [];
				return this.run;
			}
			this.run = await this.api.federationRun(runId);
			this.rounds = await this.api.federationRounds(runId);
			return this.run;
		} catch (cause) {
			this.error = describe(cause);
			return null;
		}
	}

	/** Select a run (URL-addressable): reload from the backend and rebuild live state from sequence 0. */
	async selectRun(runId: string): Promise<void> {
		this.error = null;
		const live = this.model.snapshot.runId === runId && (this.socketStatus === 'OPEN' || this.socketStatus === 'CONNECTING' || this.socketStatus === 'RECONNECTING' || this.socketStatus === 'CLOSED_NORMAL');
		if (live) {
			await this.loadRun(runId); // the live socket for this run already exists: refresh REST state only
			return;
		}
		const run = await this.loadRun(runId);
		if (run) this.openLive(run.run_id);
	}

	/** create -> open WebSocket -> start (the journal replays from 0, so ordering needs no timing luck). */
	async createAndStart(choice: FederationRunChoice): Promise<FederationRun | null> {
		this.busy = true;
		this.error = null;
		this.replayNoSource = false;
		try {
			const created = await this.api.createFederationRun(choice);
			this.run = created;
			this.rounds = [];
			this.openLive(created.run_id);
			this.run = await this.api.startFederationRun(created.run_id);
			void this.loadRuns();
			return this.run;
		} catch (cause) {
			if (cause instanceof ProductApiError && cause.status === 409 && /NO_COMPLETED_SOURCE_RUN_FOR_REPLAY/.test(cause.detail)) {
				this.replayNoSource = true; // never silently switch to LIVE_RUN
			} else {
				this.error = describe(cause);
			}
			return null;
		} finally {
			this.busy = false;
		}
	}

	/** 10-round extended run: the backend creates AND starts it (separate engine); the typed journal replays from sequence 0 so ordering needs no timing luck. */
	async startTenRound(choice: StudioRunChoice): Promise<FederationRun | null> {
		this.busy = true;
		this.error = null;
		this.replayNoSource = false;
		try {
			const created = await this.api.studioStartTenRound(choice);
			this.run = studioRunToFederationRun(created);
			this.rounds = [];
			this.openLive(created.run_id);
			void this.loadRuns();
			return this.run;
		} catch (cause) {
			this.error = describe(cause);
			return null;
		} finally {
			this.busy = false;
		}
	}

	openLive(runId: string): void {
		this.closeLive();
		this.model = new FederationLiveModel(runId);
		this.eventLog = [];
		this.roundViews.clear();
		this.flush();
		this.socket = new LiveSocket({
			url: federationSocketUrl(runId, location),
			factory: this.socketFactory,
			handlers: {
				onReset: () => {
					this.finishedRefreshed = false;
					this.model.reset(); // the backend replays from sequence 0: rebuild, never append
					this.eventLog = [];
					this.roundViews.clear();
					this.flush();
				},
				onMessage: (data) => this.onMessage(data),
				onStatus: (status) => {
					this.socketStatus = status;
					if (status === 'CLOSED_NORMAL') {
						this.flush();
						void this.refreshAfterRun();
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
		if (!this.model.applyRaw(raw)) {
			this.socket?.close();
			this.socketStatus = 'DISCONNECTED';
			this.flush();
			return;
		}
		this.eventLog = [...this.eventLog, raw];
		const status = this.model.snapshot.runStatus;
		if ((status === 'COMPLETED' || status === 'FAILED') && !this.finishedRefreshed) {
			this.finishedRefreshed = true;
			void this.refreshAfterRun();
		}
		this.schedule();
	}

	private async refreshAfterRun(): Promise<void> {
		const id = this.model.snapshot.runId;
		if (id) await this.loadRun(id);
		await Promise.all([this.loadRuns(), this.loadOverview(), this.loadModels()]);
	}

	private schedule(): void {
		if (this.flushScheduled) return;
		this.flushScheduled = true;
		this.frame(() => {
			this.flushScheduled = false;
			this.flush();
		});
	}

	flush(): void {
		this.view = JSON.parse(JSON.stringify(this.model.snapshot)) as FederationView;
	}

	resetLive(): void {
		this.closeLive();
		this.model = new FederationLiveModel(null);
		this.run = null;
		this.rounds = [];
		this.eventLog = [];
		this.roundViews.clear();
		this.flush();
	}

	/** Event index (inclusive) at which round `round` finished, or null while it has not. Round 0 = everything before the first round event. */
	roundEndIndex(round: number): number | null {
		const log = this.eventLog as { event_type: string; payload: { round_id?: number; round_state?: string } }[];
		if (round === 0) {
			const first = log.findIndex((e) => e.event_type === 'round.status');
			return first === -1 ? (log.length ? log.length - 1 : null) : first - 1;
		}
		const index = log.findIndex((e) => e.event_type === 'round.status' && e.payload.round_id === round && e.payload.round_state === 'COMPLETED');
		return index === -1 ? null : index;
	}

	/** The federation view exactly as it was when `round` finished, rebuilt ONLY from this run's validated events (never from current state). null while the round has not finished. */
	viewAtRound(round: number): FederationView | null {
		const runId = this.model.snapshot.runId;
		const end = this.roundEndIndex(round);
		if (runId === null || end === null) return null;
		const key = `${runId}|${round}|${end}`;
		const cached = this.roundViews.get(key);
		if (cached) return cached;
		const replay = new FederationLiveModel(runId);
		for (let i = 0; i <= end; i++) if (!replay.applyRaw(this.eventLog[i])) return null;
		const view = JSON.parse(JSON.stringify(replay.snapshot)) as FederationView;
		this.roundViews.set(key, view);
		return view;
	}
}

let singleton: FederationStore | null = null;
export function getFederationStore(getApi: () => ProductClient): FederationStore {
	singleton ??= new FederationStore(getApi);
	return singleton;
}
export function setFederationStore(store: FederationStore | null): void {
	singleton = store;
}

import { getProductStore } from '../state.svelte';
/** App-wide federation store bound to the product store's typed client. */
export function useFederation(): FederationStore {
	return getFederationStore(() => getProductStore().api);
}
