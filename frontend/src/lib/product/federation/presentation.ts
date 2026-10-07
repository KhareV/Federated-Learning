// UI-ENH-001 -- PURE presentation derivations over the existing FederationView. No I/O, no timers, no randomness, no interpolation:
// every value is taken from, or counted over, data the backend already reports. Nothing here invents a metric.
import type { ClientView, FederationView, RoundView } from './live-model';
import type { Algorithm, RoundState } from './types';

export type StageStatus = 'done' | 'active' | 'pending' | 'failed';
export interface Stage { id: string; label: string; status: StageStatus }

export const STAGE_LABELS = [
	['INITIALIZE', 'Initialize'], ['DISTRIBUTE', 'Distribute global state'], ['LOCAL_TRAINING', 'Local training'], ['COLLECT', 'Collect model updates'],
	['AGGREGATE', 'Aggregate'], ['NEW_STATE', 'New global state'], ['NEXT', 'Next round / candidate']
] as const;

/** Index of the stage a round is in, derived ONLY from the backend round state (and whether its aggregation event arrived). */
export function stageIndexForRound(state: RoundState, aggregated: boolean): number {
	switch (state) {
		case 'CREATED': case 'COLLECTING': return 1;
		case 'LOCAL_TRAINING': return 2;
		case 'UPDATES_READY': return 3;
		case 'AGGREGATING': return aggregated ? 5 : 4;
		default: return 6; // CANDIDATE_CREATED / VALIDATING / ACCEPTED_TO_SANDBOX / REJECTED / COMPLETED (a FAILED round is handled by the caller)
	}
}

export function currentRoundView(v: FederationView): RoundView | undefined {
	return v.rounds.find((r) => r.roundId === v.currentRound) ?? v.rounds[v.rounds.length - 1];
}

/** The seven-stage stepper for the CURRENT round. Completed stages precede the active one; future stages are pending. */
export function stageProgress(v: FederationView): Stage[] {
	const failed = v.runStatus === 'FAILED' || v.errors.length > 0;
	let active = -1;
	if (v.runStatus === 'COMPLETED') active = STAGE_LABELS.length;           // every stage done
	else if (v.eventCount === 0 || v.runStatus === null) active = -1;       // nothing reported yet
	else if (v.runStatus === 'CREATED' || v.currentRound === 0) active = 0;
	else {
		const r = currentRoundView(v);
		active = r ? stageIndexForRound(r.state, r.aggregationMode !== null && r.stateDigest !== null) : 1;
	}
	return STAGE_LABELS.map(([id, label], i) => ({ id, label, status: active === -1 ? 'pending' : i < active ? 'done' : i === active ? (failed && v.runStatus === 'FAILED' ? 'failed' : 'active') : 'pending' }));
}

export interface RoundCounts { roundId: number; total: number; trainingComplete: number; updatesReady: number; accepted: number; state: RoundState | null }
/** Counts taken from reported milestones / update digests / the backend's accepted count for one round. */
export function roundCounts(v: FederationView, roundId: number): RoundCounts {
	const r = v.rounds.find((x) => x.roundId === roundId);
	const total = r?.expected ?? v.clientCount ?? 8;
	return { roundId, total, trainingComplete: v.clients.filter((c) => c.milestones[roundId] === 1).length, updatesReady: v.clients.filter((c) => c.updateDigests[roundId] !== undefined).length, accepted: r?.accepted ?? 0, state: r?.state ?? null };
}

export function algorithmName(a: Algorithm | null | undefined): string { return a === 'FEDPROX' ? 'FedProx' : a === 'FEDAVG' ? 'FedAvg' : '--'; }

export interface TimelineLine { key: string; text: string }
/** Human-readable summary, derived from the reported round/client/candidate state (not from wall-clock time: none is invented). */
export function humanTimeline(v: FederationView): TimelineLine[] {
	const out: TimelineLine[] = [];
	const total = v.clientCount || 8;
	for (const r of v.rounds) {
		const c = roundCounts(v, r.roundId);
		out.push({ key: `r${r.roundId}-start`, text: `Round ${r.roundId} started` });
		if (c.trainingComplete > 0) out.push({ key: `r${r.roundId}-train`, text: `${c.trainingComplete} / ${total} clients completed local training` });
		if (c.updatesReady > 0) out.push({ key: `r${r.roundId}-ready`, text: `${c.updatesReady} / ${total} model updates became ready` });
		if (r.accepted > 0) out.push({ key: `r${r.roundId}-accepted`, text: `${r.accepted} / ${r.expected} model updates accepted` });
		if (r.aggregationMode) out.push({ key: `r${r.roundId}-agg`, text: `${algorithmName(v.algorithm)} aggregation completed` });
		if (r.stateDigest) out.push({ key: `r${r.roundId}-state`, text: `Round ${r.roundId} global state created` });
	}
	if (v.candidate) out.push({ key: 'cand', text: v.runType === 'REPLAY' ? 'Historical candidate event replayed (no new candidate created)' : 'Final engineering candidate created' });
	if (v.candidate?.validation === 'PASSED') out.push({ key: 'val', text: 'Structural checks passed' });
	if (v.candidate?.governance === 'ACCEPTED_TO_SANDBOX') out.push({ key: 'gov', text: 'Candidate placed in the engineering sandbox (not deployed)' });
	if (v.runStatus === 'COMPLETED') out.push({ key: 'done', text: 'Run completed' });
	return out;
}

export interface StateTransition { roundId: number; before: string | null; after: string | null; accepted: number; expected: number }
/** Global-state digests before / after each aggregation: round 1 starts from the base state; round N starts from round N-1's result. */
export function stateTransitions(v: FederationView, baseDigest: string | null): StateTransition[] {
	let before = baseDigest;
	return v.rounds.map((r) => { const t = { roundId: r.roundId, before, after: r.stateDigest, accepted: r.accepted, expected: r.expected }; before = r.stateDigest ?? before; return t; });
}

export type NodeState = 'READY' | 'TRAINING' | 'TRAINING_COMPLETE' | 'UPDATE_READY' | 'ACCEPTED' | 'COMPLETE' | 'WAITING' | 'FAILED';
/** Friendly node state from the existing client events only (no intermediate state is interpolated). */
export function nodeState(c: ClientView | undefined, roundId: number, runDone: boolean): NodeState {
	if (!c) return 'WAITING';
	if (c.state === 'FAILED' || c.state === 'REJECTED') return 'FAILED';
	if (runDone && c.updateDigests[roundId] !== undefined) return 'COMPLETE';
	if (c.state === 'SUBMITTED') return 'ACCEPTED';
	if (c.state === 'UPDATE_READY') return 'UPDATE_READY';
	if (c.state === 'TRAINING') return c.milestones[roundId] === 1 ? 'TRAINING_COMPLETE' : 'TRAINING';
	if (c.state === 'DATA_READY') return 'READY';
	return 'WAITING';
}
export const NODE_LABEL: Record<NodeState, string> = { WAITING: 'WAITING', READY: 'READY', TRAINING: 'TRAINING', TRAINING_COMPLETE: 'TRAINING COMPLETE', UPDATE_READY: 'UPDATE READY', ACCEPTED: 'ACCEPTED', COMPLETE: 'COMPLETE', FAILED: 'FAILED' };
export const NODE_MARK: Record<NodeState, string> = { WAITING: '○', READY: '◔', TRAINING: '●', TRAINING_COMPLETE: '◕', UPDATE_READY: '◉', ACCEPTED: '✓', COMPLETE: '✓', FAILED: '✕' };

export type LocalStep = 'BUFFER' | 'ARCHITECTURE' | 'OPTIMIZATION' | 'UPDATE' | 'SENT';
export const LOCAL_STEPS: { id: LocalStep; label: string }[] = [
	{ id: 'BUFFER', label: 'Local synthetic buffer' }, { id: 'ARCHITECTURE', label: 'MODEL_V2 architecture' }, { id: 'OPTIMIZATION', label: 'Local optimization' },
	{ id: 'UPDATE', label: 'Model update created' }, { id: 'SENT', label: 'Update sent to coordinator' }
];
/** Index of the local-training step a client is at, from its reported state (-1 = not started). */
export function localStepIndex(c: ClientView | undefined): number {
	if (!c) return -1;
	if (c.state === 'SUBMITTED') return 4;
	if (c.state === 'UPDATE_READY') return 3;
	if (c.state === 'TRAINING') return 2;
	if (c.state === 'DATA_READY') return 0;
	return -1;
}
