// NHM_UNIFIED_LIVE_FEDERATION_STUDIO_001 -- run-scoped Studio store: the single shared selected-round state of the unified live page, plus the evaluation, figures,
// tables and exports of the CURRENT run. Every response is tagged with the run it was requested for; a response for another run (rapid run switching) is dropped,
// so nothing can bleed between runs. Nothing is extrapolated: an unevaluated round stays pending until the backend reports a measured record.

import { ProductApiError, type ProductClient } from '../api';
import { getProductStore } from '../state.svelte';
import type { GenCurves, GenParticipants, Generalisation, StudioOverview, EvalRoundDetail, EvalSummary, RoundDetail, StudioCapabilities, StudioExports, StudioFigures, StudioRun, StudioTables } from './types';
import { statusFor } from './metrics';

export const ANALYSIS_TABS = ['overview', 'performance', 'training', 'clients', 'matrices', 'comparison', 'generalisation', 'figures'] as const;
export type AnalysisTab = (typeof ANALYSIS_TABS)[number];
const POLL_MS = 2000;
const FIGURE_MIN_INTERVAL_MS = 3000;

const describe = (cause: unknown): string => (cause instanceof ProductApiError ? cause.message || cause.detail : cause instanceof Error ? cause.message : String(cause));

export class StudioStore {
	capabilities = $state<StudioCapabilities | null>(null);
	run = $state<StudioRun | null>(null);
	summary = $state<EvalSummary | null>(null);
	figures = $state.raw<StudioFigures | null>(null);
	tables = $state.raw<StudioTables | null>(null);
	exports = $state<StudioExports | null>(null);
	overview = $state.raw<StudioOverview | null>(null);
	roundEval = $state.raw<Record<number, EvalRoundDetail>>({});
	roundDetail = $state.raw<Record<number, RoundDetail>>({});
	generalisation = $state.raw<Generalisation | null>(null);
	genCurves = $state.raw<Record<number, GenCurves>>({});
	genParticipants = $state.raw<Record<number, GenParticipants>>({});
	genNote = $state<string | null>(null);
	error = $state<string | null>(null);
	loading = $state(false);

	// ---- shared selected-round state ---------------------------------------------------------------------------------
	followLive = $state(true);
	manualRound = $state<number | null>(null);
	selectedClientId = $state<string | null>(null);
	selectedMetric = $state('AUPRC');
	analysisTab = $state<AnalysisTab>('overview');
	/** Pushed by the page from the live federation view (single source of truth for execution progress). */
	executingRound = $state(0);
	latestCommittedRound = $state(0);

	private runId: string | null = null;
	private seq = 0;
	private timer: ReturnType<typeof setTimeout> | null = null;
	private figuresAt = 0;
	private figuresKey = '';
	private overviewKey = '';

	constructor(private readonly getApi: () => ProductClient) {}

	private get api(): ProductClient {
		return this.getApi();
	}

	get trackedRunId(): string | null {
		return this.runId;
	}
	get records() {
		return this.summary?.records ?? [];
	}
	get plannedRounds(): number {
		return this.run?.planned_rounds ?? this.summary?.run_length ?? 0;
	}
	/** Rounds that can be selected: R0..R(planned). Only rounds that are committed or genuinely pending are enabled by the UI. */
	get rounds(): number[] {
		return Array.from({ length: this.plannedRounds + 1 }, (_, i) => i);
	}
	get latestEvaluatedRound(): number | null {
		const done = this.records.filter((r) => r.evaluation_status === 'COMPLETED').map((r) => r.round_id);
		return done.length ? Math.max(...done) : null;
	}
	get isFinished(): boolean {
		return this.run?.status === 'COMPLETED' || this.run?.status === 'FAILED';
	}
	/** The round every synchronized panel shows: the live round while following live, otherwise the user's choice. */
	get selectedRound(): number {
		if (!this.followLive && this.manualRound !== null) return this.manualRound;
		const live = this.run?.origin === 'LIVE' && !this.isFinished ? Math.max(this.executingRound, this.latestCommittedRound) : this.finalRound;
		return Math.min(live, this.plannedRounds);
	}
	get finalRound(): number {
		return this.run?.status === 'COMPLETED' ? this.plannedRounds : Math.max(this.latestCommittedRound, this.executingRound);
	}
	/** The round whose metrics are shown: the selected round, or - while following live and it is not evaluated yet - the latest evaluated round (labelled as such). */
	get metricRound(): number {
		const selected = this.selectedRound;
		if (!this.followLive || statusFor(this.records, selected) === 'COMPLETED') return selected;
		return this.latestEvaluatedRound ?? selected;
	}
	statusOf(round: number) {
		return statusFor(this.records, round);
	}

	// ---- selection actions -------------------------------------------------------------------------------------------
	selectRound(round: number): void {
		if (round < 0 || round > this.plannedRounds) return;
		this.manualRound = round;
		this.followLive = false;          // new events can no longer move the user's selection
		void this.loadRound(round);
	}
	returnToLive(): void {
		this.followLive = true;
		this.manualRound = null;
	}
	selectClient(id: string | null): void {
		this.selectedClientId = id;
	}

	// ---- data ----------------------------------------------------------------------------------------------------------
	async loadCapabilities(): Promise<void> {
		try {
			this.capabilities = await this.api.studioCapabilities();
		} catch {
			this.capabilities = null;     // a backend without Studio routes: 10-round stays disabled with an explanation
		}
	}

	/** Switch to a run (or null). Everything run-scoped is cleared FIRST so nothing from the previous run can remain visible. */
	track(runId: string | null): void {
		if (runId === this.runId) return;
		this.seq += 1;
		this.stopPolling();
		this.runId = runId;
		this.run = null; this.summary = null; this.figures = null; this.tables = null; this.exports = null; this.overview = null; this.overviewKey = '';
		this.roundEval = {}; this.roundDetail = {}; this.generalisation = null; this.genCurves = {}; this.genParticipants = {}; this.genNote = null;
		this.error = null; this.followLive = true; this.manualRound = null; this.selectedClientId = null;
		this.executingRound = 0; this.latestCommittedRound = 0; this.figuresKey = ''; this.figuresAt = 0;
		if (runId) void this.refresh();
	}

	stopPolling(): void {
		if (this.timer) clearTimeout(this.timer);
		this.timer = null;
	}

	setProgress(executing: number, committed: number): void {
		const advanced = committed > this.latestCommittedRound;
		this.executingRound = executing;
		this.latestCommittedRound = committed;
		if (advanced) void this.refresh();          // a committed round: ask for its (queued) evaluation record immediately, no waiting for the next poll
	}

	private pending(): boolean {
		const run = this.run;
		if (!run) return false;
		if (run.status === 'CREATED' || run.status === 'RUNNING') return true;
		if (run.phase === 'EVALUATING' || run.phase === 'EXPORTING' || run.export_status === 'PREPARING') return true;
		if (this.records.some((r) => r.evaluation_status === 'QUEUED' || r.evaluation_status === 'EVALUATING')) return true;
		return this.genPending();
	}

	/** The generalisation lane is still working: the baseline or a round is queued/evaluating, or a finished round still waits for its paired comparison. */
	private genPending(): boolean {
		const g = this.generalisation;
		if (!g || this.run?.origin === 'RECORDED') return false;
		const working = (s: string | undefined) => s === 'QUEUED' || s === 'EVALUATING';
		const base = g.baseline.record;
		if (!base) return !this.isFinished;
		if (working(base.evaluation_status)) return true;
		return g.rounds.some((r) => working(r.record?.evaluation_status) || (base.evaluation_status === 'COMPLETED' && r.record?.evaluation_status === 'COMPLETED' && r.paired_vs_v2 === null));
	}

	async refresh(): Promise<void> {
		const id = this.runId;
		if (!id) return;
		const token = this.seq;
		try {
			const run = await this.api.studioRun(id);
			if (token !== this.seq) return;
			this.run = run;
			if (run.evaluation.available) {
				const summary = await this.api.studioEvaluation(id);
				if (token !== this.seq) return;
				this.summary = summary;
				await this.loadGeneralisation(id, token);
			}
			if (run.export_status === 'READY' || run.export_status === 'PREPARING') {
				const exports = await this.api.studioExports(id);
				if (token !== this.seq) return;
				this.exports = exports;
			}
			this.error = null;
		} catch (cause) {
			if (token === this.seq) this.error = describe(cause);
		}
		if (token !== this.seq) return;
		this.stopPolling();
		if (this.pending()) this.timer = setTimeout(() => void this.refresh(), POLL_MS);
	}

	/** The Generalisation lane never blocks the main refresh: its failure is shown in its own tab, not as a run error. Recorded evidence runs have no such lane. */
	private async loadGeneralisation(id: string, token: number): Promise<void> {
		if (this.run?.origin === 'RECORDED') { this.genNote = 'Recorded evidence runs keep their own recorded diagnostic evaluation; start a new run to score the unseen cohort.'; return; }
		try {
			const g = await this.api.studioGeneralisation(id);
			if (token !== this.seq) return;
			this.generalisation = g;
			this.genNote = null;
		} catch (cause) {
			if (token === this.seq) this.genNote = describe(cause);
		}
	}

	/** Curves and per-participant metrics of a finished round are immutable: fetched once per round, never re-requested, dropped with the run. */
	async ensureGenDetail(round: number): Promise<void> {
		const id = this.runId;
		const g = this.generalisation;
		const record = g?.rounds.find((r) => r.round_id === round)?.record;
		if (!id || !g || record?.evaluation_status !== 'COMPLETED') return;
		const token = this.seq;
		try {
			if (!this.genCurves[round]) {
				const curves = await this.api.studioGeneralisationCurves(id, round);
				if (token !== this.seq) return;
				this.genCurves = { ...this.genCurves, [round]: curves };
			}
			if (!this.genParticipants[round]) {
				const participants = await this.api.studioGeneralisationParticipants(id, round);
				if (token !== this.seq) return;
				this.genParticipants = { ...this.genParticipants, [round]: participants };
			}
		} catch (cause) {
			if (token === this.seq) this.genNote = describe(cause);
		}
	}

	async loadRound(round: number): Promise<void> {
		const id = this.runId;
		if (!id || this.run?.evaluation.available === false) return;
		const token = this.seq;
		const have = this.roundEval[round];
		if (have && have.evaluation_status === 'COMPLETED') return;
		try {
			const [evaluation, detail] = await Promise.all([this.api.studioEvaluationRound(id, round), this.api.studioRoundDetail(id, round)]);
			if (token !== this.seq) return;
			this.roundEval = { ...this.roundEval, [round]: evaluation };
			this.roundDetail = { ...this.roundDetail, [round]: detail };
		} catch (cause) {
			if (token === this.seq) this.error = describe(cause);
		}
	}

	/** Heavy payloads are fetched lazily, once per evaluation revision and at most every few seconds while a run advances. */
	async ensureFigures(force = false): Promise<void> {
		const id = this.runId;
		if (!id || this.run?.evaluation.available === false) return;
		const key = `${id}|${this.summary?.revision ?? -1}|${this.selectedRound}|${this.run?.current_round ?? 0}`;
		if (!force && key === this.figuresKey) return;
		const now = Date.now();
		if (!force && now - this.figuresAt < FIGURE_MIN_INTERVAL_MS && this.figures) return;
		this.figuresAt = now;
		this.figuresKey = key;
		const token = this.seq;
		try {
			const figures = await this.api.studioFigures(id, this.metricRound);
			if (token !== this.seq) return;
			this.figures = figures;
		} catch (cause) {
			if (token === this.seq) { this.error = describe(cause); this.figuresKey = ''; }
		}
	}

	/** Run facts / limits / evidence boundary: refetched only when the run's status or committed round count changes. */
	async ensureOverview(): Promise<void> {
		const id = this.runId;
		if (!id || this.run?.evaluation.available === false) return;
		const key = `${id}|${this.run?.status}|${this.latestCommittedRound}|${this.run?.phase}`;
		if (key === this.overviewKey && this.overview) return;
		this.overviewKey = key;
		const token = this.seq;
		try {
			const overview = await this.api.studioOverview(id);
			if (token !== this.seq) return;
			this.overview = overview;
		} catch (cause) {
			if (token === this.seq) { this.error = describe(cause); this.overviewKey = ''; }
		}
	}

	async ensureTables(force = false): Promise<void> {
		const id = this.runId;
		if (!id || this.run?.evaluation.available === false) return;
		if (!force && this.tables && this.tables.revision === (this.summary?.revision ?? null)) return;
		const token = this.seq;
		try {
			const tables = await this.api.studioTables(id);
			if (token !== this.seq) return;
			this.tables = tables;
		} catch (cause) {
			if (token === this.seq) this.error = describe(cause);
		}
	}
}

let singleton: StudioStore | null = null;
export function getStudioStore(getApi: () => ProductClient): StudioStore {
	singleton ??= new StudioStore(getApi);
	return singleton;
}
export function setStudioStore(store: StudioStore | null): void {
	singleton = store;
}
export function useStudio(): StudioStore {
	return getStudioStore(() => getProductStore().api);
}
