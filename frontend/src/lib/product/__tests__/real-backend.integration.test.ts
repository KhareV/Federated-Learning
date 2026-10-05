// REAL-BACKEND frontend integration (CAPG4 criterion 70). No fake JSON: the actual frontend product
// client, live-event parser and LiveModel talk to the real CAP-004 DEMO backend, which talks to a
// fresh SOFTWARE_SYSTEM_V2 process. Skipped unless scripts/run_capstone_frontend_e2e.py provides:
//   NHM_REAL_PRODUCT_URL=http://127.0.0.1:<port>   NHM_REAL_EVIDENCE_PATH=<json file>
import { writeFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { createProductClient } from '../api';
import { LiveModel } from '../live-model';
import { LiveSocket } from '../socket';

const URL_BASE = process.env.NHM_REAL_PRODUCT_URL;
const EVIDENCE = process.env.NHM_REAL_EVIDENCE_PATH;

describe.skipIf(!URL_BASE)('frontend product client against the REAL CAP-004 DEMO backend', () => {
	it('system -> me -> device -> scan -> connect -> session -> start -> live WebSocket -> completion -> reload', async () => {
		const client = createProductClient({ base: `${URL_BASE}/product/v1` });
		const system = await client.system();
		expect(system.auth_provider).toBe('DEMO');
		expect(system.demo_mode).toBe(true);
		expect(system.model_id).toBe('MODEL_V2_FINAL');
		expect(system.physical_hardware_available).toBe(false);
		const me = await client.me();
		expect(me.user_id).toBe('demo:faculty');

		const device = await client.createSimulatedDevice('MIXED_MONITORING_SESSION');
		const states = [device.connection_state];
		const scanned = await client.scan(device.device_id); states.push(scanned.connection_state);
		const connected = await client.connect(device.device_id); states.push(connected.connection_state);
		expect(connected.connection_state).toBe('CONNECTED');
		expect(connected.simulation).toBe(true);

		const created = await client.createSession(device.device_id, 'MIXED_MONITORING_SESSION');
		expect(created.state).toBe('DEVICE_READY');
		expect(created.runtime.model_id).toBe('MODEL_V2_FINAL');

		const model = new LiveModel(created.session_id);
		let ended: (code: string) => void = () => {};
		const closed = new Promise<string>((resolve) => (ended = resolve));
		let resets = 0;
		const wsUrl = `${URL_BASE!.replace('http', 'ws')}/product/v1/sessions/${created.session_id}/live`;
		const live = new LiveSocket({
			url: wsUrl,
			handlers: {
				onReset: () => { resets += 1; model.reset(); },
				onMessage: (data) => { if (!model.applyRaw(JSON.parse(String(data)))) ended('STREAM_ERROR'); },
				onStatus: (status) => { if (status === 'CLOSED_NORMAL' || status === 'DISCONNECTED') ended(status); }
			}
		});
		live.connect();
		await new Promise((r) => setTimeout(r, 300));
		const started = await client.startSession(created.session_id);
		expect(['MONITORING', 'COMPLETED']).toContain(started.state);
		const outcome = await Promise.race([closed, new Promise<string>((r) => setTimeout(() => r('TIMEOUT'), 150_000))]);
		expect(outcome).toBe('CLOSED_NORMAL');
		expect(model.streamError).toBeNull();

		const finalSession = await client.session(created.session_id);
		expect(finalSession.state).toBe('COMPLETED');
		const listed = await client.sessions();
		expect(listed.map((s) => s.session_id)).toContain(created.session_id);

		// scientific invariants as seen by the frontend consumer
		expect(model.eventCount).toBe(3157);
		expect(model.qualityCounts).toEqual({ VALID: 86, DEGRADED: 0, UNUSABLE: 7 });
		expect(model.inferenceCount).toBe(86);
		expect([...model.modelIds]).toEqual(['MODEL_V2_FINAL']);
		expect([...model.calibrationIds]).toEqual(['CAL_V2']);
		expect(model.monitoringChanges.map((c) => c.state)).toEqual(['NORMAL_MONITORED_PATTERN', 'CONTEXT_UNAVAILABLE', 'NORMAL_MONITORED_PATTERN']);
		expect(model.gaps).toEqual([{ start: 118800, end: 124199 }]);
		expect(model.waveform.length).toBeLessThanOrEqual(model.waveform.capacity);

		if (EVIDENCE) {
			writeFileSync(EVIDENCE, JSON.stringify({
				system: { auth_provider: system.auth_provider, demo_mode: system.demo_mode, model_id: system.model_id, software_system: system.software_system, hardware_mode: system.hardware_mode },
				identity: me.user_id, device_id: device.device_id, device_state_sequence_rest: states,
				session_id: created.session_id, session_states_rest: [created.state, started.state, finalSession.state],
				event_count: model.eventCount, counts_by_type: model.countsByType, sequence_continuous: model.tracker.expected === model.eventCount,
				waveform_chunks: model.countsByType['waveform.chunk'], gaps: model.gaps, quality_counts: model.qualityCounts,
				inference_count: model.inferenceCount, model_ids: [...model.modelIds], calibration_ids: [...model.calibrationIds],
				monitoring_state_changes: model.monitoringChanges, device_status_sequence: model.deviceChanges.map((c) => c.state),
				socket_resets: resets, completed: finalSession.state === 'COMPLETED', listed_after_completion: true
			}, null, 1));
		}
	}, 200_000);
});
