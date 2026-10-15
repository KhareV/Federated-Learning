// The run context keeps provenance, execution mode, labels, lineage and capabilities INDEPENDENT and fails closed.
import { describe, expect, it } from 'vitest';
import { provisionalContext, runContext } from '../run-context';
import type { StudioRun } from '../../studio/types';

const base = (over: Partial<StudioRun>): StudioRun => ({
	run_id: 'FL10RUN-A', run_length: 3, engine: 'FL10_10R', origin: 'LIVE', run_type: 'LIVE_RUN', algorithm: 'FEDAVG', secagg_mode: 'PLAIN', source_mode: 'CANONICAL_SYNTHETIC',
	status: 'COMPLETED', phase: 'DONE', current_round: 3, planned_rounds: 3, client_ids: [], candidate: null, failure: null, label: 'x',
	base_model: { model_id: 'MODEL_V2_FINAL', label: 'V2' }, source_label: 's', replay_of: null,
	evaluation: { available: true, source: 'LIVE', evaluation_run_id: 'FL10RUN-A', reason: null, revision: 1 }, export_status: 'READY', created_at: null, ...over
} as StudioRun);

describe('run context axes are independent', () => {
	it('canonical synthetic live run', () => {
		const c = runContext(base({}), 'FL10RUN-A');
		expect(c).toMatchObject({ provisional: false, provenance: 'SYNTHETIC_COHORT', execution: 'LIVE_TRAINING', labels: 'SYNTHETIC_ENGINEERING_EVENTS', lineage: 'MODEL_V2_FINAL', clients: 'SIM_FL_SITE' });
		expect(c.capabilities.ownerBoundClient.available && c.capabilities.generalisation.available && c.capabilities.pairedIntervals.available).toBe(true);
	});
	it('recorded hardware is real features + synthetic labels, never replay and never owner-bound', () => {
		const c = runContext(base({ run_id: 'HDFLRUN-X', engine: 'HARDWARE_DEMO', source_mode: 'RECORDED_HARDWARE', base_model: { model_id: 'HARDWARE_DEMO_MODEL_V1', label: 'fresh' } }), 'HDFLRUN-X');
		expect(c).toMatchObject({ provenance: 'RECORDED_HARDWARE', execution: 'LIVE_TRAINING', labels: 'SYNTHETIC_ASSIGNED_FOR_DEMO', lineage: 'HARDWARE_DEMO_FRESH', clients: 'RECORDED_DEMO_CLIENT', badge: 'RECORDED HARDWARE' });
		expect(c.capabilities.ownerBoundClient.available).toBe(false);
		for (const k of ['generalisation', 'pairedIntervals', 'historicalReference'] as const) { expect(c.capabilities[k].available).toBe(false); expect(c.capabilities[k].reason).toMatch(/Not applicable/); }
	});
	it('a historically recorded SYNTHETIC evidence run is recorded evidence but not hardware', () => {
		const c = runContext(base({ run_id: 'recorded-A', origin: 'RECORDED', run_type: 'REPLAY' }), 'recorded-A');
		expect(c).toMatchObject({ provenance: 'SYNTHETIC_COHORT', execution: 'RECORDED_EVIDENCE', badge: 'RECORDED SYNTHETIC EVIDENCE' });
		expect(c.capabilities.ownerBoundClient.available).toBe(false);
	});
	it('an event replay of a synthetic run is a replay, not new training', () => {
		const c = runContext(base({ origin: 'REPLAY', run_type: 'REPLAY' }), 'FL10RUN-A');
		expect(c).toMatchObject({ provenance: 'SYNTHETIC_COHORT', execution: 'EVENT_REPLAY', badge: 'REPLAY' });
	});
	it('a hardware warm start is distinct from the synthetic pretrained V2 lineage', () => {
		const c = runContext(base({ run_id: 'HDFLRUN-W', engine: 'HARDWARE_DEMO', source_mode: 'RECORDED_HARDWARE', base_model: { model_id: 'HARDWARE_DEMO_MODEL_V1', label: 'w', initialisation: 'WARM_START' } as never }), 'HDFLRUN-W');
		expect(c.lineage).toBe('HARDWARE_DEMO_WARM_START');
	});
	it('simulated SITE_00 is its own provenance', () => {
		expect(runContext(base({ source_mode: 'LIVE_MONITORED_SITE_00' }), 'FL10RUN-A').provenance).toBe('SIMULATED_MONITORED_SITE_00');
	});
});

describe('run context fails closed', () => {
	it('is provisional (all capabilities closed) before the descriptor arrives', () => {
		const c = runContext(null, 'FL10RUN-A');
		expect(c.provisional).toBe(true);
		expect(Object.values(c.capabilities).every((x) => !x.available)).toBe(true);
	});
	it('never presents another run\'s descriptor as the selected run', () => {
		const c = runContext(base({ run_id: 'FL10RUN-OLD' }), 'HDFLRUN-NEW');
		expect(c.provisional).toBe(true);
		expect(c.provenance).toBe('RECORDED_HARDWARE');             // from the selected id only, flagged provisional
		expect(c.capabilities.generalisation.available).toBe(false);
	});
	it('an unrecognised engine / source mode yields UNKNOWN with no capability', () => {
		const c = runContext(base({ engine: 'SOMETHING_NEW' as never }), 'FL10RUN-A');
		expect(c.provenance).toBe('UNKNOWN');
		expect(Object.values(c.capabilities).every((x) => !x.available)).toBe(true);
	});
	it('an id prefix alone never opens a capability', () => {
		const c = provisionalContext('FL10RUN-ZZ');
		expect(c.provenance).toBe('UNKNOWN');
		expect(Object.values(c.capabilities).every((x) => !x.available)).toBe(true);
	});
});
