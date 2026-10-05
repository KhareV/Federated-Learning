// CAPSTONE_FEDERATION_PRODUCT_CLIENT_V1 (events): strict PRODUCT_LIVE_EVENT_V1 federation parsing.
// Exactly the 12 federation kinds are legal; every monitoring kind and every unknown kind is rejected.
// Nothing is cast: each field is validated.

import {
	AGGREGATION_MODES, ALGORITHMS, CANDIDATE_STATES, CLIENT_STATES, FEDERATION_EVENT_KINDS, ROUND_STATES, RUN_STATES,
	RUN_TYPES, SANDBOX_STATUSES, SECAGG_STATUSES, VALIDATION_STATUSES, type FederationEvent
} from './types';

export class FederationEventError extends Error {
	constructor(readonly reason: string) {
		super(reason);
		this.name = 'FederationEventError';
	}
}
type Rec = Record<string, unknown>;
const isRec = (v: unknown): v is Rec => typeof v === 'object' && v !== null && !Array.isArray(v);
const fail = (reason: string): never => { throw new FederationEventError(reason); };
const int = (v: unknown, n: string, min = 0): number => (typeof v === 'number' && Number.isInteger(v) && v >= min ? v : fail(`BAD_${n}`));
const str = (v: unknown, n: string): string => (typeof v === 'string' && v.length > 0 ? v : fail(`BAD_${n}`));
const strOrNull = (v: unknown, n: string): string | null => (v === null || v === undefined ? null : str(v, n));
const bool = (v: unknown, n: string): boolean => (typeof v === 'boolean' ? v : fail(`BAD_${n}`));
const literalFalse = (v: unknown, n: string): false => (v === false ? false : fail(`BAD_${n}`));
function oneOf<T extends string>(v: unknown, allowed: readonly T[], n: string): T {
	return typeof v === 'string' && (allowed as readonly string[]).includes(v) ? (v as T) : fail(`BAD_${n}`);
}
const digest = (v: unknown, n: string): string => (typeof v === 'string' && /^[0-9a-f]{64}$/.test(v) ? v : fail(`BAD_${n}`));
const candidateId = (v: unknown, n: string): string => (typeof v === 'string' && /^CAPSTONE_FL_CANDIDATE_\d{4}$/.test(v) ? v : fail(`BAD_${n}`));

export function parseFederationEvent(raw: unknown): FederationEvent {
	if (!isRec(raw)) return fail('NOT_AN_OBJECT');
	if (raw.contract_version !== 'PRODUCT_LIVE_EVENT_V1') fail('BAD_CONTRACT_VERSION');
	const kind = raw.event_type;
	if (typeof kind !== 'string' || !(FEDERATION_EVENT_KINDS as readonly string[]).includes(kind)) return fail('UNKNOWN_OR_NON_FEDERATION_EVENT_KIND');
	const p = raw.payload;
	if (!isRec(p)) return fail('BAD_PAYLOAD');
	const base = { contract_version: 'PRODUCT_LIVE_EVENT_V1' as const, event_id: str(raw.event_id, 'EVENT_ID'), sequence_index: int(raw.sequence_index, 'SEQUENCE'), emitted_at_us: int(raw.emitted_at_us, 'EMITTED_AT'), run_id: str(raw.run_id, 'RUN_ID') };
	switch (kind) {
		case 'federation.status':
			return { ...base, event_type: kind, payload: { run_type: oneOf(p.run_type, RUN_TYPES, 'RUN_TYPE'), run_status: oneOf(p.run_status, RUN_STATES, 'RUN_STATUS'), algorithm: oneOf(p.algorithm, ALGORITHMS, 'ALGORITHM'), current_round: int(p.current_round, 'CURRENT_ROUND'), planned_rounds: int(p.planned_rounds, 'PLANNED_ROUNDS', 1), client_count: int(p.client_count, 'CLIENT_COUNT', 1), engineering_only: p.engineering_only === true ? true : fail('BAD_ENGINEERING_ONLY') } };
		case 'round.status':
			return { ...base, event_type: kind, payload: { round_id: int(p.round_id, 'ROUND_ID', 1), round_state: oneOf(p.round_state, ROUND_STATES, 'ROUND_STATE'), accepted_updates: int(p.accepted_updates, 'ACCEPTED'), expected_updates: int(p.expected_updates, 'EXPECTED', 1) } };
		case 'client.status':
			return { ...base, event_type: kind, payload: { client_id: str(p.client_id, 'CLIENT_ID'), client_state: oneOf(p.client_state, CLIENT_STATES, 'CLIENT_STATE'), local_example_count: int(p.local_example_count, 'LOCAL_EXAMPLES'), reason_code: strOrNull(p.reason_code, 'REASON') } };
		case 'client.training_progress': {
			const f = p.progress_fraction;
			if (typeof f !== 'number' || !Number.isFinite(f) || f < 0 || f > 1) fail('BAD_PROGRESS');
			return { ...base, event_type: kind, payload: { client_id: str(p.client_id, 'CLIENT_ID'), round_id: int(p.round_id, 'ROUND_ID', 1), progress_fraction: f as number, examples_seen: int(p.examples_seen, 'EXAMPLES') } };
		}
		case 'client.update_ready':
			return { ...base, event_type: kind, payload: { client_id: str(p.client_id, 'CLIENT_ID'), round_id: int(p.round_id, 'ROUND_ID', 1), update_digest: digest(p.update_digest, 'DIGEST'), examples_seen: int(p.examples_seen, 'EXAMPLES', 1) } };
		case 'aggregation.status':
			return { ...base, event_type: kind, payload: { round_id: int(p.round_id, 'ROUND_ID', 1), algorithm: oneOf(p.algorithm, ALGORITHMS, 'ALGORITHM'), aggregation_mode: oneOf(p.aggregation_mode, AGGREGATION_MODES, 'AGG_MODE'), accepted_updates: int(p.accepted_updates, 'ACCEPTED'), state_digest: p.state_digest === null || p.state_digest === undefined ? null : digest(p.state_digest, 'STATE_DIGEST') } };
		case 'secagg.status': {
			const mode = oneOf(p.mode, AGGREGATION_MODES, 'MODE');
			const status = oneOf(p.status, SECAGG_STATUSES, 'SECAGG_STATUS');
			if ((mode === 'PLAIN') !== (status === 'NOT_USED')) fail('SECAGG_MODE_STATUS_MISMATCH');
			if (p.claim_scope !== 'PROTECTED_AGGREGATION_INTERFACE_ONLY') fail('BAD_CLAIM_SCOPE');
			return { ...base, event_type: kind, payload: { round_id: int(p.round_id, 'ROUND_ID', 1), mode, status, claim_scope: 'PROTECTED_AGGREGATION_INTERFACE_ONLY' } };
		}
		case 'candidate.created':
			return { ...base, event_type: kind, payload: { candidate_id: candidateId(p.candidate_id, 'CANDIDATE_ID'), parent_model_id: str(p.parent_model_id, 'PARENT'), round_id: int(p.round_id, 'ROUND_ID', 1), state_digest: digest(p.state_digest, 'STATE_DIGEST'), production_deployed: literalFalse(p.production_deployed, 'PRODUCTION_DEPLOYED') } };
		case 'candidate.validation': {
			if (!Array.isArray(p.checks)) fail('BAD_CHECKS');
			return { ...base, event_type: kind, payload: { candidate_id: candidateId(p.candidate_id, 'CANDIDATE_ID'), validation_status: oneOf(p.validation_status, VALIDATION_STATUSES, 'VALIDATION'), checks: (p.checks as unknown[]).map((c) => str(c, 'CHECK')) } };
		}
		case 'candidate.governance':
			return { ...base, event_type: kind, payload: { candidate_id: candidateId(p.candidate_id, 'CANDIDATE_ID'), governance_status: oneOf(p.governance_status, CANDIDATE_STATES, 'GOVERNANCE'), sandbox_status: oneOf(p.sandbox_status, SANDBOX_STATUSES, 'SANDBOX'), production_deployed: literalFalse(p.production_deployed, 'PRODUCTION_DEPLOYED') } };
		case 'federation.completed': {
			if (!Array.isArray(p.candidate_ids)) fail('BAD_CANDIDATE_IDS');
			return { ...base, event_type: kind, payload: { rounds_completed: int(p.rounds_completed, 'ROUNDS'), candidate_ids: (p.candidate_ids as unknown[]).map((c) => candidateId(c, 'CANDIDATE_ID')), production_deployed: literalFalse(p.production_deployed, 'PRODUCTION_DEPLOYED') } };
		}
		default:
			return { ...base, event_type: 'federation.error', payload: { error_code: str(p.error_code, 'ERROR_CODE'), message: str(p.message, 'MESSAGE').slice(0, 300), recoverable: bool(p.recoverable, 'RECOVERABLE'), round_id: p.round_id === null || p.round_id === undefined ? null : int(p.round_id, 'ROUND_ID', 1) } };
	}
}
