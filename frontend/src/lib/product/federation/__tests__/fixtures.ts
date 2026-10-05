// Unit/component fixtures ONLY (the canonical proof uses the real CAP-007 backend). The event generator
// follows the documented backend ordering so reducer tests exercise realistic streams.
import type { CandidateModel, FederationEvent, FederationRound, FederationRun, FLClientIdentity, ModelRegistryView, RunType, AggregationMode, Algorithm, FederationOverview } from '../types';

export const RUN_ID = 'FEDRUN-TEST01';
export const CLIENT_IDS = Array.from({ length: 8 }, (_, i) => `SIM_FL_SITE_0${i}`);
export const h = (n: number): string => n.toString(16).padStart(2, '0').repeat(32);
export const CAND = 'CAPSTONE_FL_CANDIDATE_0001';

export function runFixture(over: Partial<FederationRun> = {}): FederationRun {
	return { run_id: RUN_ID, run_type: 'LIVE_RUN', base_model_id: 'FL_INIT_V2', federation_protocol_id: 'V2_FL_WEARABLE_SYSTEM_PROTOCOL_V1', algorithm: 'FEDAVG', client_ids: CLIENT_IDS, planned_rounds: 3, current_round: 0, started_at_us: null, completed_at_us: null, status: 'CREATED', secagg_mode: 'PLAIN', candidate_ids: [], engineering_only: true, ...over };
}
export function overviewFixture(over: Partial<FederationOverview> = {}): FederationOverview {
	return { federation_runtime: 'ENABLED_ENGINEERING', engineering_only: true, scientific_evidence: false, production_deployed: false, banner: 'FL ENGINEERING DEMO', client_count: 8, cohort_id: 'WEARABLE_SIM_FL_COHORT_V1', active_live_run: false, candidate_count: 0, released_model_id: 'MODEL_V2_FINAL', secagg_claim_scope: 'PROTECTED_AGGREGATION_INTERFACE_ONLY', ...over };
}
export function clientsFixture(): FLClientIdentity[] {
	return CLIENT_IDS.map((id, i) => ({ client_id: id, edge_node_id: `EDGE_${i}`, base_model_id: 'FL_INIT_V2', global_round: 0, local_example_count: 100 + i, client_state: 'IDLE', update_digest: null, eligible: true, ineligible_reason: null }));
}
export function candidateFixture(over: Partial<CandidateModel> = {}): CandidateModel {
	return { candidate_id: CAND, parent_model_id: 'FL_INIT_V2', federation_run_id: RUN_ID, round: 3, algorithm: 'FEDAVG', client_count: 8, created_at_us: 1, state_digest: h(0xab), validation_status: 'PASSED', governance_status: 'ACCEPTED_TO_SANDBOX', sandbox_status: 'IN_SANDBOX', production_deployed: false, claim_boundary: 'CAPSTONE_ENGINEERING_SANDBOX_CANDIDATE_NOT_SCIENTIFIC_RELEASE', ...over };
}
export function registryFixture(candidates: CandidateModel[] = []): ModelRegistryView {
	return { registry_id: 'CAPSTONE_MODEL_REGISTRY_V1', released_default_model_id: 'MODEL_V2_FINAL', released_scientific: [{ model_id: 'MODEL_V2_FINAL', namespace: 'RELEASED_SCIENTIFIC', role: 'RELEASED_DEFAULT' }, { model_id: 'MODEL_V1', namespace: 'RELEASED_SCIENTIFIC', role: 'ROLLBACK_REFERENCE' }], capstone_fl_candidates: candidates };
}
export function roundsFixture(): FederationRound[] {
	return [1, 2, 3].map((r) => ({ run_id: RUN_ID, round_id: r, state: 'COMPLETED', participating_client_ids: CLIENT_IDS, base_state_digest: h(r), algorithm: 'FEDAVG', accepted_update_count: 8, candidate_id: r === 3 ? CAND : null }));
}

type Opts = { runType?: RunType; algorithm?: Algorithm; mode?: AggregationMode; run?: string; failAfterRound?: number };
/** A backend-faithful event stream (3 rounds x 8 clients). Returns raw JSON objects. */
export function eventStream(o: Opts = {}): FederationEvent[] {
	const runType = o.runType ?? 'LIVE_RUN', algorithm = o.algorithm ?? 'FEDAVG', mode = o.mode ?? 'PLAIN', run = o.run ?? RUN_ID;
	const out: FederationEvent[] = [];
	const push = (event_type: FederationEvent['event_type'], payload: unknown) => {
		const i = out.length;
		out.push({ contract_version: 'PRODUCT_LIVE_EVENT_V1', event_id: `${run}-FEV${String(i).padStart(6, '0')}`, sequence_index: i, emitted_at_us: 1000 + i, run_id: run, event_type, payload } as FederationEvent);
	};
	const status = (run_status: string, current_round: number) => push('federation.status', { run_type: runType, run_status, algorithm, current_round, planned_rounds: 3, client_count: 8, engineering_only: true });
	status('CREATED', 0); status('RUNNING', 0);
	for (let r = 1; r <= 3; r++) {
		status('RUNNING', r);
		const rs = (round_state: string, accepted = 0) => push('round.status', { round_id: r, round_state, accepted_updates: accepted, expected_updates: 8 });
		rs('COLLECTING');
		for (const c of CLIENT_IDS) push('client.status', { client_id: c, client_state: 'DATA_READY', local_example_count: 100, reason_code: null });
		rs('LOCAL_TRAINING');
		for (const c of CLIENT_IDS) {
			push('client.status', { client_id: c, client_state: 'TRAINING', local_example_count: 100, reason_code: null });
			push('client.training_progress', { client_id: c, round_id: r, progress_fraction: 0, examples_seen: 0 });
			push('client.training_progress', { client_id: c, round_id: r, progress_fraction: 1, examples_seen: 100 });
			push('client.status', { client_id: c, client_state: 'UPDATE_READY', local_example_count: 100, reason_code: null });
			push('client.update_ready', { client_id: c, round_id: r, update_digest: h(r * 16 + CLIENT_IDS.indexOf(c)), examples_seen: 100 });
			push('client.status', { client_id: c, client_state: 'SUBMITTED', local_example_count: 100, reason_code: null });
		}
		rs('UPDATES_READY', 8); rs('AGGREGATING', 8);
		if (mode === 'PLAIN') push('secagg.status', { round_id: r, mode: 'PLAIN', status: 'NOT_USED', claim_scope: 'PROTECTED_AGGREGATION_INTERFACE_ONLY' });
		else if (r === 1) { push('secagg.status', { round_id: 1, mode: 'SECAGG_SHADOW', status: 'SHADOW_RUNNING', claim_scope: 'PROTECTED_AGGREGATION_INTERFACE_ONLY' }); push('secagg.status', { round_id: 1, mode: 'SECAGG_SHADOW', status: 'SHADOW_VERIFIED', claim_scope: 'PROTECTED_AGGREGATION_INTERFACE_ONLY' }); }
		push('aggregation.status', { round_id: r, algorithm, aggregation_mode: 'PLAIN', accepted_updates: 8, state_digest: h(0x30 + r) });
		if (r < 3) rs('COMPLETED', 8);
		else {
			rs('CANDIDATE_CREATED', 8);
			push('candidate.created', { candidate_id: CAND, parent_model_id: 'FL_INIT_V2', round_id: 3, state_digest: h(0xab), production_deployed: false });
			rs('VALIDATING', 8);
			push('candidate.validation', { candidate_id: CAND, validation_status: 'RUNNING', checks: [] });
			push('candidate.validation', { candidate_id: CAND, validation_status: 'PASSED', checks: ['STATE_FINITE', 'STATE_SPEC_MATCHES_BASE', 'UPDATE_DIGESTS_RECONCILE', 'ROUND_ACCEPTED_UPDATE_COUNT_COMPLETE', 'BASE_STATE_LINEAGE_VERIFIED'] });
			push('candidate.governance', { candidate_id: CAND, governance_status: 'ACCEPTED_TO_SANDBOX', sandbox_status: 'IN_SANDBOX', production_deployed: false });
			rs('ACCEPTED_TO_SANDBOX', 8); rs('COMPLETED', 8);
		}
		if (o.failAfterRound === r) { push('federation.error', { error_code: 'TEST_FAILURE', message: 'induced', recoverable: false, round_id: r }); status('FAILED', r); return out; }
	}
	status('COMPLETED', 3);
	push('federation.completed', { rounds_completed: 3, candidate_ids: [CAND], production_deployed: false });
	return out;
}
