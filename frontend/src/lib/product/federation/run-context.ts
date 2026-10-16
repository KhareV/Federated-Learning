// RUN CONTEXT: one typed, fail-closed interpretation of a validated run descriptor (StudioRun) into the INDEPENDENT axes the UI needs.
// Nothing here is scientific logic and nothing is guessed from an id prefix: every field comes from the backend-validated descriptor.
// An id prefix is only used for a clearly marked PROVISIONAL context while the descriptor of the selected run has not arrived yet.
import type { StudioRun } from '../studio/types';

/** Where the training windows come from. */
export type DataProvenance = 'SYNTHETIC_COHORT' | 'SIMULATED_MONITORED_SITE_00' | 'RECORDED_HARDWARE' | 'UNKNOWN';
/** What this run IS right now (independent of provenance): training that executes, an event replay, or a stored historical record. */
export type ExecutionMode = 'LIVE_TRAINING' | 'EVENT_REPLAY' | 'RECORDED_EVIDENCE' | 'UNKNOWN';
/** Where the labels come from. */
export type LabelProvenance = 'SYNTHETIC_ENGINEERING_EVENTS' | 'SYNTHETIC_ASSIGNED_FOR_DEMO' | 'UNKNOWN';
export type ModelLineage = 'FL_INIT_V2' | 'MODEL_V2_FINAL' | 'HARDWARE_DEMO_FRESH' | 'HARDWARE_DEMO_WARM_START' | 'HARDWARE_V2_PRETRAINED' | 'UNKNOWN';
export type ClientNamespace = 'SIM_FL_SITE' | 'RECORDED_DEMO_CLIENT' | 'UNKNOWN';

export interface Capability { available: boolean; reason: string | null }
export interface RunContext {
	provisional: boolean;
	provenance: DataProvenance;
	execution: ExecutionMode;
	labels: LabelProvenance;
	lineage: ModelLineage;
	clients: ClientNamespace;
	/** Short badge for lists and headers. */
	badge: string;
	/** One honest sentence about what the data is (never "clinical"). */
	dataSentence: string;
	capabilities: {
		ownerBoundClient: Capability; generalisation: Capability; pairedIntervals: Capability; historicalReference: Capability;
		secaggShadow: Capability; exports: Capability; replay: Capability;
	};
}

const NA_HARDWARE_GENERALISATION = 'Not applicable to this recorded-hardware run: it trained the small tabular model, and the unseen-cohort lane scores MODEL_V2_FINAL-compatible ECG windows. Start a pretrained-V2 recorded-hardware run to compare with frozen V2 on the unseen cohort.';
const NA_HARDWARE_PAIRED = 'Not applicable: paired participant-cluster intervals need several independent participants; recorded sessions are not independent clusters.';
const NA_HARDWARE_HISTORICAL = 'Not applicable: no previously examined reference exists for recorded-hardware data.';
const NA_RECORDED_GENERALISATION = 'Recorded evidence runs keep their own recorded diagnostic evaluation; start a new run to score the unseen cohort.';
const UNKNOWN_REASON = 'The run descriptor is missing or not recognised, so no capability is assumed.';

const yes = (): Capability => ({ available: true, reason: null });
const no = (reason: string): Capability => ({ available: false, reason });

const CLOSED: RunContext['capabilities'] = {
	ownerBoundClient: no(UNKNOWN_REASON), generalisation: no(UNKNOWN_REASON), pairedIntervals: no(UNKNOWN_REASON), historicalReference: no(UNKNOWN_REASON),
	secaggShadow: no(UNKNOWN_REASON), exports: no(UNKNOWN_REASON), replay: no(UNKNOWN_REASON)
};

/** Context for a run id whose descriptor has not arrived yet. Only the namespace is inferred (and flagged provisional); every capability stays closed. */
export function provisionalContext(runId: string | null | undefined): RunContext {
	const hardware = (runId ?? '').startsWith('HDFLRUN-');
	return {
		provisional: true, provenance: hardware ? 'RECORDED_HARDWARE' : 'UNKNOWN', execution: 'UNKNOWN', labels: hardware ? 'SYNTHETIC_ASSIGNED_FOR_DEMO' : 'UNKNOWN', lineage: 'UNKNOWN',
		clients: hardware ? 'RECORDED_DEMO_CLIENT' : 'UNKNOWN', badge: hardware ? 'RECORDED HARDWARE' : 'LOADING', dataSentence: 'Loading the selected run…', capabilities: CLOSED
	};
}

export function runContext(run: StudioRun | null | undefined, routeRunId?: string | null): RunContext {
	if (!run || (routeRunId && run.run_id !== routeRunId)) return provisionalContext(routeRunId ?? run?.run_id);   // never present another run's descriptor as this run's
	let provenance: DataProvenance = 'UNKNOWN';
	if (run.engine === 'HARDWARE_DEMO' && run.source_mode === 'RECORDED_HARDWARE') provenance = 'RECORDED_HARDWARE';
	else if ((run.engine === 'FL10_10R' || run.engine === 'PRODUCT_3R') && run.source_mode === 'CANONICAL_SYNTHETIC') provenance = 'SYNTHETIC_COHORT';
	else if ((run.engine === 'FL10_10R' || run.engine === 'PRODUCT_3R') && run.source_mode === 'LIVE_MONITORED_SITE_00') provenance = 'SIMULATED_MONITORED_SITE_00';
	if (provenance === 'UNKNOWN') return { ...provisionalContext(run.run_id), provisional: false, badge: 'UNKNOWN SOURCE', dataSentence: UNKNOWN_REASON };

	const execution: ExecutionMode = run.origin === 'RECORDED' ? 'RECORDED_EVIDENCE' : run.run_type === 'REPLAY' || run.origin === 'REPLAY' ? 'EVENT_REPLAY' : run.run_type === 'LIVE_RUN' ? 'LIVE_TRAINING' : 'UNKNOWN';
	const hardware = provenance === 'RECORDED_HARDWARE';
	const modelId = run.base_model?.model_id ?? null;
	const warm = (run.base_model as { initialisation?: string } | null)?.initialisation === 'WARM_START';
	const lineage: ModelLineage = hardware ? (modelId === 'MODEL_V2_FINAL' ? 'HARDWARE_V2_PRETRAINED' : warm ? 'HARDWARE_DEMO_WARM_START' : 'HARDWARE_DEMO_FRESH') : modelId === 'MODEL_V2_FINAL' ? 'MODEL_V2_FINAL' : modelId === 'FL_INIT_V2' ? 'FL_INIT_V2' : 'UNKNOWN';
	const recorded = execution === 'RECORDED_EVIDENCE';
	const live = execution === 'LIVE_TRAINING';
	const badge = hardware ? 'RECORDED HARDWARE' : recorded ? 'RECORDED SYNTHETIC EVIDENCE' : execution === 'EVENT_REPLAY' ? 'REPLAY' : provenance === 'SIMULATED_MONITORED_SITE_00' ? `SIMULATED SITE_${String(run.monitored_site ?? 0).padStart(2, '0')}` : 'SYNTHETIC COHORT';
	const dataSentence = hardware
		? lineage === 'HARDWARE_V2_PRETRAINED'
			? 'Your recorded telemetry resampled onto the V2 source grid into 10 s V2 windows (only windows the quality gate grades VALID) with deterministic synthetic labels, split across eight logical clients on one machine.'
			: 'Your recorded telemetry windows (real features) with deterministic synthetic labels, split across eight logical clients on one machine.'
		: provenance === 'SIMULATED_MONITORED_SITE_00'
			? `A genuinely executed simulated monitoring stream feeds SITE_${String(run.monitored_site ?? 0).padStart(2, '0')}; the other seven clients are synthetic. No real physiology.`
			: 'Synthetic engineering data on eight logical clients on one machine. No real physiology.';
	return {
		provisional: false, provenance, execution, lineage,
		labels: hardware ? 'SYNTHETIC_ASSIGNED_FOR_DEMO' : 'SYNTHETIC_ENGINEERING_EVENTS',
		clients: hardware ? 'RECORDED_DEMO_CLIENT' : 'SIM_FL_SITE',
		badge, dataSentence,
		capabilities: {
			ownerBoundClient: !hardware && live ? yes() : no(hardware ? 'Every recorded-hardware client holds your own recorded windows; there is no single owner-bound client.' : 'Only a live run executes on behalf of the signed-in owner.'),
			generalisation: hardware ? (lineage === 'HARDWARE_V2_PRETRAINED' ? yes() : no(NA_HARDWARE_GENERALISATION)) : recorded ? no(NA_RECORDED_GENERALISATION) : yes(),
			pairedIntervals: hardware ? no(NA_HARDWARE_PAIRED) : yes(),
			historicalReference: hardware ? no(NA_HARDWARE_HISTORICAL) : yes(),
			secaggShadow: run.secagg_mode === 'SECAGG_SHADOW' ? yes() : no('Plain aggregation was used for this run.'),
			exports: run.export_status === 'READY' ? yes() : no(run.export_status === 'PREPARING' ? 'Exports are being prepared.' : 'Exports are generated when the run completes and every evaluation has settled.'),
			replay: no(hardware ? 'Recorded-hardware runs are opened from their saved journal; replay is not offered.' : 'Open a completed run from "Your federation runs" to replay it.')
		}
	};
}

export const isHardwareContext = (c: RunContext): boolean => c.provenance === 'RECORDED_HARDWARE';
