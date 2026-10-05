// REAL-BACKEND federation integration (CAPG7). No fake JSON: the actual frontend product client, federation
// event parser and FederationLiveModel talk to the real CAP-007 DEMO backend running real local training.
// Skipped unless scripts/run_capstone_federation_ui_e2e.py provides NHM_REAL_PRODUCT_URL and NHM_REAL_EVIDENCE_PATH.
import { writeFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { createProductClient } from '../../api';
import { LiveSocket } from '../../socket';
import { FederationLiveModel } from '../live-model';

const URL_BASE = process.env.NHM_REAL_PRODUCT_URL;
const EVIDENCE = process.env.NHM_REAL_EVIDENCE_PATH;

describe.skipIf(!URL_BASE)('frontend federation client against the REAL CAP-007 DEMO backend', () => {
	it('overview -> clients -> create -> WebSocket -> start -> 3 rounds -> candidate -> rounds -> models', async () => {
		const client = createProductClient({ base: `${URL_BASE}/product/v1` });
		const system = await client.system();
		expect(system.federation_runtime).toBe('ENABLED_ENGINEERING');
		expect(system.model_id).toBe('MODEL_V2_FINAL');
		const before = await client.federationOverview();
		expect(before.federation_runtime).toBe('ENABLED_ENGINEERING');
		expect(before.candidate_count).toBe(0);
		const clients = await client.federationClients(); // cold start: builds the 8 datasets (slow, once)
		expect(clients.map((c) => c.client_id)).toEqual(Array.from({ length: 8 }, (_, i) => `SIM_FL_SITE_0${i}`));
		const created = await client.createFederationRun({ run_type: 'LIVE_RUN', algorithm: 'FEDAVG', secagg_mode: 'SECAGG_SHADOW' });
		expect(created).toMatchObject({ status: 'CREATED', planned_rounds: 3, base_model_id: 'FL_INIT_V2', secagg_mode: 'SECAGG_SHADOW' });

		const model = new FederationLiveModel(created.run_id);
		let ended: (code: string) => void = () => {};
		const closed = new Promise<string>((resolve) => (ended = resolve));
		let resets = 0;
		const live = new LiveSocket({
			url: `${URL_BASE!.replace('http', 'ws')}/product/v1/federation/runs/${created.run_id}/live`,
			handlers: {
				onReset: () => { resets += 1; model.reset(); },
				onMessage: (data) => { if (!model.applyRaw(JSON.parse(String(data)))) ended('STREAM_ERROR'); },
				onStatus: (status) => { if (status === 'CLOSED_NORMAL' || status === 'DISCONNECTED') ended(status); }
			}
		});
		live.connect();
		await new Promise((r) => setTimeout(r, 300));
		const started = await client.startFederationRun(created.run_id);
		expect(['RUNNING', 'COMPLETED']).toContain(started.status);
		const outcome = await Promise.race([closed, new Promise<string>((r) => setTimeout(() => r('TIMEOUT'), 400_000))]);
		expect(outcome).toBe('CLOSED_NORMAL');
		expect(model.streamError).toBeNull();
		const v = model.snapshot;
		expect(v.runStatus).toBe('COMPLETED');
		expect(v.updateReadyCount).toBe(24);
		expect(v.submittedCount).toBe(24);
		expect(v.rounds.map((r) => r.aggregationMode)).toEqual(['PLAIN', 'PLAIN', 'PLAIN']);
		expect(v.secagg.map((s) => s.status)).toEqual(['SHADOW_RUNNING', 'SHADOW_VERIFIED']);
		expect(v.candidate).toMatchObject({ candidateId: 'CAPSTONE_FL_CANDIDATE_0001', parentModelId: 'FL_INIT_V2', validation: 'PASSED', governance: 'ACCEPTED_TO_SANDBOX', sandbox: 'IN_SANDBOX', productionDeployed: false });

		const run = await client.federationRun(created.run_id);
		expect(run.status).toBe('COMPLETED');
		expect((await client.federationRuns()).map((r) => r.run_id)).toContain(created.run_id);
		const rounds = await client.federationRounds(created.run_id);
		expect(rounds.map((r) => [r.state, r.accepted_update_count, r.candidate_id])).toEqual([['COMPLETED', 8, null], ['COMPLETED', 8, null], ['COMPLETED', 8, 'CAPSTONE_FL_CANDIDATE_0001']]);
		const registry = await client.models();
		expect(registry.released_default_model_id).toBe('MODEL_V2_FINAL');
		expect(registry.capstone_fl_candidates).toHaveLength(1);
		expect(registry.capstone_fl_candidates[0].state_digest).toBe(v.candidate?.stateDigest);
		expect(registry.capstone_fl_candidates[0].production_deployed).toBe(false);
		expect(((await client.model('MODEL_V2_FINAL')) as { model_id: string }).model_id).toBe('MODEL_V2_FINAL');
		if (EVIDENCE) {
			writeFileSync(EVIDENCE, JSON.stringify({ system: { federation_runtime: system.federation_runtime, model_id: system.model_id, auth_provider: system.auth_provider }, overview_before: before, clients: clients.length,
				run, rounds, models: registry, events: v.eventCount, countsByKind: v.countsByKind, update_ready: v.updateReadyCount, submitted: v.submittedCount, secagg: v.secagg,
				aggregation_modes: v.rounds.map((r) => r.aggregationMode), resets, candidate: v.candidate, outcome }, null, 1));
		}
	}, 450_000);
});
