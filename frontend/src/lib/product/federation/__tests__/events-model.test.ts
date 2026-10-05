import { describe, expect, it } from 'vitest';
import { FederationEventError, parseFederationEvent } from '../events';
import { FederationLiveModel } from '../live-model';
import { FEDERATION_EVENT_KINDS } from '../types';
import { CAND, CLIENT_IDS, RUN_ID, eventStream } from './fixtures';

const feed = (m: FederationLiveModel, evs: unknown[]) => evs.map((e) => m.applyRaw(e));

describe('federation event parser', () => {
	it('accepts every one of the exactly 12 federation kinds from a full real-shaped stream', () => {
		const seen = new Set<string>();
		for (const e of eventStream({ mode: 'SECAGG_SHADOW', failAfterRound: undefined })) seen.add(parseFederationEvent(e).event_type);
		const failing = eventStream({ failAfterRound: 1 });
		for (const e of failing) seen.add(parseFederationEvent(e).event_type);
		expect([...seen].sort()).toEqual([...FEDERATION_EVENT_KINDS].sort());
		expect(FEDERATION_EVENT_KINDS).toHaveLength(12);
	});
	it('rejects every monitoring event kind and unknown kinds', () => {
		const base = eventStream()[0];
		for (const kind of ['device.status', 'session.status', 'waveform.chunk', 'context.snapshot', 'quality.status', 'inference.result', 'monitoring.state', 'system.error', 'not.a.kind']) {
			expect(() => parseFederationEvent({ ...base, event_type: kind })).toThrow(FederationEventError);
		}
	});
	it('rejects malformed payloads', () => {
		const e = eventStream();
		const bad = [{ ...e[0], payload: { ...e[0].payload, run_status: 'WEIRD' } }, { ...e[0], contract_version: 'X' }, { ...e[0], sequence_index: -1 }, null, 5, [],
			{ ...e.find((x) => x.event_type === 'client.training_progress')!, payload: { client_id: 'a', round_id: 1, progress_fraction: 1.5, examples_seen: 0 } },
			{ ...e.find((x) => x.event_type === 'candidate.created')!, payload: { candidate_id: CAND, parent_model_id: 'FL_INIT_V2', round_id: 3, state_digest: 'ab'.repeat(32), production_deployed: true } },
			{ ...e.find((x) => x.event_type === 'secagg.status')!, payload: { round_id: 1, mode: 'PLAIN', status: 'SHADOW_VERIFIED', claim_scope: 'PROTECTED_AGGREGATION_INTERFACE_ONLY' } }];
		for (const b of bad) expect(() => parseFederationEvent(b)).toThrow();
	});
});

describe('federation live model', () => {
	it('derives the full canonical run only from events', () => {
		const m = new FederationLiveModel(RUN_ID);
		expect(feed(m, eventStream({ mode: 'SECAGG_SHADOW' })).every(Boolean)).toBe(true);
		const v = m.snapshot;
		expect(v.runStatus).toBe('COMPLETED');
		expect(v.updateReadyCount).toBe(24);
		expect(v.submittedCount).toBe(24);
		expect(v.clients.map((c) => c.clientId)).toEqual(CLIENT_IDS);
		expect(v.rounds.map((r) => r.state)).toEqual(['COMPLETED', 'COMPLETED', 'COMPLETED']);
		expect(v.rounds.every((r) => r.aggregationMode === 'PLAIN' && r.accepted === 8)).toBe(true);
		expect(v.secagg.map((s) => `${s.roundId}:${s.status}`)).toEqual(['1:SHADOW_RUNNING', '1:SHADOW_VERIFIED']);
		expect(v.candidate).toMatchObject({ candidateId: CAND, validation: 'PASSED', governance: 'ACCEPTED_TO_SANDBOX', sandbox: 'IN_SANDBOX', productionDeployed: false, historical: false });
		expect(v.candidate?.checksPassed).toHaveLength(5);
		expect(v.newCandidatesCreatedByThisRun).toBe(1);
		expect(v.completedCandidateIds).toEqual([CAND]);
		expect(v.countsByKind['client.update_ready']).toBe(24);
	});
	it('progress is exactly 0 or 1 per round - never interpolated', () => {
		const m = new FederationLiveModel(RUN_ID);
		feed(m, eventStream());
		for (const c of m.snapshot.clients) for (const r of [1, 2, 3]) expect(c.milestones[r]).toBe(1);
		const m2 = new FederationLiveModel(RUN_ID);
		const evs = eventStream();
		const cut = evs.findIndex((e) => e.event_type === 'client.training_progress' && e.payload.progress_fraction === 0);
		feed(m2, evs.slice(0, cut + 1));
		expect(m2.snapshot.clients.find((c) => c.milestones[1] === 0)).toBeTruthy();
		expect(Object.values(m2.snapshot.clients.flatMap((c) => Object.values(c.milestones))).every((x) => x === 0 || x === 1)).toBe(true);
	});
	it('rejects sequence gaps, duplicates, foreign run ids and malformed events and then stays failed', () => {
		const evs = eventStream();
		let m = new FederationLiveModel(RUN_ID);
		feed(m, [evs[0], evs[1]]);
		expect(m.applyRaw(evs[3])).toBe(false);
		expect(m.streamError?.reason).toBe('SEQUENCE_GAP');
		expect(m.applyRaw(evs[2])).toBe(false); // frozen after an integrity failure
		m = new FederationLiveModel(RUN_ID);
		feed(m, [evs[0]]);
		expect(m.applyRaw(evs[0])).toBe(false);
		expect(m.streamError?.reason).toBe('DUPLICATE_SEQUENCE');
		m = new FederationLiveModel(RUN_ID);
		expect(m.applyRaw({ ...evs[0], run_id: 'OTHER' })).toBe(false);
		expect(m.streamError?.reason).toBe('FOREIGN_RUN_ID');
		m = new FederationLiveModel(RUN_ID);
		expect(m.applyRaw({ ...evs[0], event_type: 'inference.result' })).toBe(false);
	});
	it('a monitoring event can never enter federation live state', () => {
		const m = new FederationLiveModel(RUN_ID);
		feed(m, eventStream().slice(0, 3));
		const before = JSON.stringify(m.snapshot);
		expect(m.applyRaw({ contract_version: 'PRODUCT_LIVE_EVENT_V1', event_id: 'x', sequence_index: 3, emitted_at_us: 1, run_id: RUN_ID, event_type: 'inference.result', payload: {} })).toBe(false);
		expect(JSON.stringify({ ...m.snapshot, streamError: null })).toBe(JSON.stringify({ ...JSON.parse(before), streamError: null }));
	});
	it('reconnect: reset then replay from 0 rebuilds identically and never double-counts', () => {
		const evs = eventStream({ mode: 'SECAGG_SHADOW' });
		const m = new FederationLiveModel(RUN_ID);
		feed(m, evs.slice(0, 90));
		m.reset();
		feed(m, evs);
		const fresh = new FederationLiveModel(RUN_ID);
		feed(fresh, evs);
		expect(JSON.stringify(m.snapshot)).toBe(JSON.stringify(fresh.snapshot));
		expect(m.snapshot.updateReadyCount).toBe(24);
		expect(m.snapshot.newCandidatesCreatedByThisRun).toBe(1);
	});
	it('REPLAY: candidate events are historical and create no new candidate', () => {
		const m = new FederationLiveModel(RUN_ID);
		feed(m, eventStream({ runType: 'REPLAY' }));
		expect(m.snapshot.runType).toBe('REPLAY');
		expect(m.snapshot.candidate?.historical).toBe(true);
		expect(m.snapshot.newCandidatesCreatedByThisRun).toBe(0);
		expect(m.snapshot.timeline.some((t) => t.summary.startsWith('HISTORICAL candidate'))).toBe(true);
	});
	it('PLAIN runs report NOT_USED; a failed run keeps the error and fabricates no candidate', () => {
		const m = new FederationLiveModel(RUN_ID);
		feed(m, eventStream({ failAfterRound: 1 }));
		expect(m.snapshot.runStatus).toBe('FAILED');
		expect(m.snapshot.errors[0]).toMatchObject({ code: 'TEST_FAILURE', roundId: 1 });
		expect(m.snapshot.candidate).toBeNull();
		expect(m.snapshot.secagg.every((s) => s.status === 'NOT_USED')).toBe(true);
	});
	it('the timeline is bounded', () => {
		const m = new FederationLiveModel(RUN_ID);
		feed(m, eventStream());
		expect(m.snapshot.timeline.length).toBeLessThanOrEqual(2000);
	});
});
