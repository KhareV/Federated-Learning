// CAPSTONE_FEDERATION_LIVE_MODEL_V1 -- derives UI state ONLY from validated federation events.
// Strict per-run sequence (0,1,2,...), foreign run ids and malformed events fail visibly (never
// fabricated, never trusted afterwards). Reconnect = reset() then replay from sequence 0.
// Training progress is exactly what arrives (0 or 1): nothing is interpolated.

import { FederationEventError, parseFederationEvent } from './events';
import type { AggregationMode, Algorithm, CandidateState, ClientState, FederationEvent, FederationEventKind, RoundState, RunState, RunType, SandboxStatus, SecAggStatus, ValidationStatus } from './types';

export const TIMELINE_CAP = 2000;

export interface FederationStreamError { reason: string; atSequence: number }
export interface ClientView { clientId: string; state: ClientState; localExamples: number; updateDigests: Record<number, string>; milestones: Record<number, 0 | 1>; reason: string | null }
export interface RoundView { roundId: number; state: RoundState; accepted: number; expected: number; aggregationMode: AggregationMode | null; stateDigest: string | null }
export interface SecAggView { roundId: number; mode: AggregationMode; status: SecAggStatus }
export interface CandidateView { candidateId: string; parentModelId: string; roundId: number; stateDigest: string; validation: ValidationStatus | null; checksPassed: string[]; governance: CandidateState | null; sandbox: SandboxStatus | null; productionDeployed: false; historical: boolean }
export interface TimelineEntry { sequence: number; kind: FederationEventKind; summary: string }

export interface FederationView {
	runId: string | null;
	eventCount: number;
	countsByKind: Partial<Record<FederationEventKind, number>>;
	runStatus: RunState | null;
	runType: RunType | null;
	algorithm: Algorithm | null;
	currentRound: number;
	plannedRounds: number;
	clientCount: number;
	rounds: RoundView[];
	clients: ClientView[];
	updateReadyCount: number;
	submittedCount: number;
	secagg: SecAggView[];
	candidate: CandidateView | null;
	newCandidatesCreatedByThisRun: number;
	completedCandidateIds: string[];
	errors: { code: string; message: string; recoverable: boolean; roundId: number | null }[];
	streamError: FederationStreamError | null;
	timeline: TimelineEntry[];
}

export class FederationLiveModel {
	private expected = 0;
	private broken: FederationStreamError | null = null;
	private view!: FederationView;

	constructor(private readonly runId: string | null) {
		this.reset();
	}

	reset(): void {
		this.expected = 0;
		this.broken = null;
		this.view = {
			runId: this.runId, eventCount: 0, countsByKind: {}, runStatus: null, runType: null, algorithm: null, currentRound: 0, plannedRounds: 0,
			clientCount: 0, rounds: [], clients: [], updateReadyCount: 0, submittedCount: 0, secagg: [], candidate: null, newCandidatesCreatedByThisRun: 0,
			completedCandidateIds: [], errors: [], streamError: null, timeline: []
		};
	}

	get snapshot(): FederationView {
		return this.view;
	}
	get streamError(): FederationStreamError | null {
		return this.broken;
	}

	private stop(reason: string): false {
		this.broken = { reason, atSequence: this.expected };
		this.view.streamError = this.broken;
		return false;
	}

	/** Validate and apply one raw event. Returns false (and freezes the model) on any integrity failure. */
	applyRaw(raw: unknown): boolean {
		if (this.broken) return false;
		let event: FederationEvent;
		try {
			event = parseFederationEvent(raw);
		} catch (error) {
			return this.stop(error instanceof FederationEventError ? error.reason : 'MALFORMED_EVENT');
		}
		if (this.runId !== null && event.run_id !== this.runId) return this.stop('FOREIGN_RUN_ID');
		if (event.sequence_index !== this.expected) return this.stop(event.sequence_index < this.expected ? 'DUPLICATE_SEQUENCE' : 'SEQUENCE_GAP');
		this.expected += 1;
		this.apply(event);
		return true;
	}

	private round(id: number): RoundView {
		let r = this.view.rounds.find((x) => x.roundId === id);
		if (!r) {
			r = { roundId: id, state: 'CREATED', accepted: 0, expected: 8, aggregationMode: null, stateDigest: null };
			this.view.rounds = [...this.view.rounds, r].sort((a, b) => a.roundId - b.roundId);
		}
		return r;
	}
	private client(id: string): ClientView {
		let c = this.view.clients.find((x) => x.clientId === id);
		if (!c) {
			c = { clientId: id, state: 'IDLE', localExamples: 0, updateDigests: {}, milestones: {}, reason: null };
			this.view.clients = [...this.view.clients, c].sort((a, b) => a.clientId.localeCompare(b.clientId));
		}
		return c;
	}

	private apply(e: FederationEvent): void {
		const v = this.view;
		v.eventCount += 1;
		v.countsByKind[e.event_type] = (v.countsByKind[e.event_type] ?? 0) + 1;
		let summary: string = e.event_type;
		switch (e.event_type) {
			case 'federation.status':
				v.runStatus = e.payload.run_status; v.runType = e.payload.run_type; v.algorithm = e.payload.algorithm;
				v.currentRound = e.payload.current_round; v.plannedRounds = e.payload.planned_rounds; v.clientCount = e.payload.client_count;
				summary = `run ${e.payload.run_status} / round ${e.payload.current_round}`;
				break;
			case 'round.status': {
				const r = this.round(e.payload.round_id);
				r.state = e.payload.round_state; r.accepted = e.payload.accepted_updates; r.expected = e.payload.expected_updates;
				summary = `round ${r.roundId} ${r.state}`;
				break;
			}
			case 'client.status': {
				const c = this.client(e.payload.client_id);
				c.state = e.payload.client_state; c.localExamples = e.payload.local_example_count; c.reason = e.payload.reason_code;
				if (e.payload.client_state === 'SUBMITTED') v.submittedCount += 1;
				summary = `${c.clientId} ${c.state}`;
				break;
			}
			case 'client.training_progress': {
				const c = this.client(e.payload.client_id);
				const f = e.payload.progress_fraction;
				if (f === 0 || f === 1) c.milestones = { ...c.milestones, [e.payload.round_id]: f };
				summary = `${c.clientId} milestone ${f}`;
				break;
			}
			case 'client.update_ready': {
				const c = this.client(e.payload.client_id);
				c.updateDigests = { ...c.updateDigests, [e.payload.round_id]: e.payload.update_digest };
				v.updateReadyCount += 1;
				summary = `${c.clientId} update ready (round ${e.payload.round_id})`;
				break;
			}
			case 'aggregation.status': {
				const r = this.round(e.payload.round_id);
				r.aggregationMode = e.payload.aggregation_mode; r.stateDigest = e.payload.state_digest;
				summary = `round ${r.roundId} aggregation ${e.payload.aggregation_mode}`;
				break;
			}
			case 'secagg.status':
				v.secagg = [...v.secagg, { roundId: e.payload.round_id, mode: e.payload.mode, status: e.payload.status }];
				summary = `round ${e.payload.round_id} secagg ${e.payload.status}`;
				break;
			case 'candidate.created': {
				const historical = v.runType === 'REPLAY';
				v.candidate = { candidateId: e.payload.candidate_id, parentModelId: e.payload.parent_model_id, roundId: e.payload.round_id, stateDigest: e.payload.state_digest, validation: null, checksPassed: [], governance: null, sandbox: null, productionDeployed: false, historical };
				if (!historical) v.newCandidatesCreatedByThisRun += 1; // a REPLAY re-emits history: it creates nothing
				summary = historical ? `HISTORICAL candidate ${e.payload.candidate_id}` : `candidate ${e.payload.candidate_id}`;
				break;
			}
			case 'candidate.validation':
				if (v.candidate && v.candidate.candidateId === e.payload.candidate_id) { v.candidate = { ...v.candidate, validation: e.payload.validation_status, checksPassed: e.payload.checks }; }
				summary = `validation ${e.payload.validation_status}`;
				break;
			case 'candidate.governance':
				if (v.candidate && v.candidate.candidateId === e.payload.candidate_id) { v.candidate = { ...v.candidate, governance: e.payload.governance_status, sandbox: e.payload.sandbox_status }; }
				summary = `governance ${e.payload.governance_status}`;
				break;
			case 'federation.completed':
				v.completedCandidateIds = e.payload.candidate_ids;
				summary = `completed (${e.payload.rounds_completed} rounds)`;
				break;
			case 'federation.error':
				v.errors = [...v.errors, { code: e.payload.error_code, message: e.payload.message, recoverable: e.payload.recoverable, roundId: e.payload.round_id }].slice(-10);
				summary = `error ${e.payload.error_code}`;
				break;
		}
		v.timeline = [...v.timeline, { sequence: e.sequence_index, kind: e.event_type, summary }].slice(-TIMELINE_CAP);
	}
}
