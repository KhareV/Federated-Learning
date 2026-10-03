// @vitest-environment jsdom
//
// V2-013 actual replay-to-dashboard E2E (frontend half). Runs ONLY when the Python orchestrator
// (scripts/run_v2_013_replay.py) provides a live stack:
//   NHM_V2_E2E_FRONTEND_BASE  = the real built-frontend `vite preview` origin, whose /v1 proxy
//                               forwards to the real localhost API_RUNTIME_V2 process;
//   NHM_V2_E2E_OUT            = file to which the captured evidence is written.
// It uses the REAL typed nhmApi client over REAL HTTP, the REAL runCanonicalRecordedReplay
// controller, the REAL DashboardSession store, loads the replay bundle from the real preview
// server's static assets, and renders the SAME shared dashboard components the /monitoring route
// uses (Panel, MetricTile, MultiLine) from the resulting session state. (Rendering the SvelteKit
// route component itself under Vitest is not possible -- documented in the C034 evidence -- and no
// browser-automation stack exists in this repository.) When the env vars are absent it is skipped.

import { writeFileSync } from 'node:fs';
import { render } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import Panel from '$lib/components/dashboard/Panel.svelte';
import MetricTile from '$lib/components/dashboard/MetricTile.svelte';
import MultiLine from '$lib/components/dashboard/MultiLine.svelte';
import { createNhmApiClient } from '$lib/api/nhm-v1';
import type { InferWindowRequest, InferWindowResult } from '$lib/api/nhm-v1';
import { createDashboardSession } from '$lib/dashboard/session.svelte';
import { loadReplayBundle, runCanonicalRecordedReplay } from '$lib/dashboard/replay';
import { PROHIBITED_WORDING, STATE_PRESENTATION, httpErrorPresentation } from '$lib/dashboard/state-presentation';

const BASE = process.env.NHM_V2_E2E_FRONTEND_BASE;
const OUT = process.env.NHM_V2_E2E_OUT;
const REPLAY_ID = process.env.NHM_V2_E2E_REPLAY_ID ?? 'WEARABLE_SIM_V2_REPLAY_V1';

describe.skipIf(!BASE || !OUT)('V2 research runtime: real replay through the real frontend path', () => {
	it('replays the simulated-wearable stream through real HTTP and renders real session state', async () => {
		const realFetch: typeof fetch = (input, init) =>
			fetch(typeof input === 'string' && input.startsWith('/') ? `${BASE}${input}` : input, init);
		const client = createNhmApiClient({ baseUrl: BASE, fetchImpl: realFetch });
		const captured: Array<{
			timestamp_us: number;
			ecg_quality: string;
			ppg_context_present: boolean;
			samples: number;
			result: InferWindowResult;
		}> = [];
		const recordingClient = {
			async inferWindow(request: InferWindowRequest) {
				const result = await client.inferWindow(request);
				captured.push({
					timestamp_us: request.timestamp_us,
					ecg_quality: request.ecg_quality,
					ppg_context_present: request.ppg_context !== null,
					samples: request.ecg.samples.length,
					result
				});
				return result;
			}
		};

		const bundle = await loadReplayBundle(REPLAY_ID, realFetch);
		const session = createDashboardSession(`V2-013-E2E-${process.pid}`);
		await runCanonicalRecordedReplay(session, bundle, { stepDelayMs: 0, apiClient: recordingClient });

		expect(captured).toHaveLength(bundle.events.length);
		expect(session.requestCount).toBe(bundle.events.length);
		expect(captured.every((c) => c.samples === 2500)).toBe(true);

		// Waveform: the session holds the real 2500-sample window of the last ACCEPTED window.
		const events = [...bundle.events].sort((a, b) => a.sequence_index - b.sequence_index);
		const lastOk = [...captured].reverse().find((c) => c.result.kind === 'success');
		expect(lastOk).toBeTruthy();
		const lastOkEvent = events.find((e) => e.timestamp_us === lastOk!.timestamp_us)!;
		expect(session.latestEcgWindow).toHaveLength(2500);
		expect(session.latestEcgWindow).toEqual(lastOkEvent.ecg.samples);

		// Render the shared dashboard components from the REAL session state.
		const outcome = session.latestOutcome!;
		expect(outcome.kind).toBe('success');
		if (outcome.kind !== 'success') throw new Error('expected success');
		const r = outcome.response;
		const presentation = STATE_PRESENTATION[r.monitoring_state];
		const wave = render(MultiLine, {
			props: { series: [{ name: 'ECG (model input)', color: '#2bb8b0', values: session.latestEcgWindow! }], height: 160, yMin: -2, yMax: 2 }
		});
		const polylinePoints = (wave.container.querySelector('polyline')?.getAttribute('points') ?? '').split(' ').length;
		const tiles = ['model_id', 'calibration_id', 'calibration_domain', 'alert_policy_id', 'preprocess_version'] as const;
		const rendered: Record<string, string> = {};
		for (const key of tiles) {
			const tile = render(MetricTile, { props: { label: key, value: String((r as unknown as Record<string, unknown>)[key]) } });
			rendered[key] = tile.container.textContent ?? '';
		}
		const history = render(Panel, { props: { eyebrow: '05 / RESEARCH ONLY', title: 'Window probability / history' } });
		const state = render(Panel, { props: { eyebrow: '03 / CURRENT MONITORING STATE', title: presentation.title } });
		const unusable = captured.find((c) => c.result.kind === 'signal_window_error');
		const unusablePresentation =
			unusable && unusable.result.kind === 'signal_window_error'
				? httpErrorPresentation(422, unusable.result.error.message)
				: null;

		expect(r.model_id).toBe('MODEL_V2_FINAL');
		expect(r.calibration_id).toBe('CAL_V2');
		expect(r.calibration_domain).toBe('MIT-BIH-v1.0.0');
		expect(r.alert_policy_id).toBe('ALERT_POLICY_V1');
		expect(rendered.model_id).toContain('MODEL_V2_FINAL');
		expect(rendered.calibration_id).toContain('CAL_V2');
		expect(polylinePoints).toBe(2500);
		expect(history.getByText('05 / RESEARCH ONLY')).toBeTruthy();
		expect(state.getByText(presentation.title)).toBeTruthy();
		expect(STATE_PRESENTATION.POTENTIAL_ECTOPY_ASSOCIATED_PATTERN.text.toLowerCase()).toContain('not a diagnosis');
		expect(Object.keys(STATE_PRESENTATION)).toHaveLength(5);
		for (const entry of Object.values(STATE_PRESENTATION)) {
			const copy = `${entry.title} ${entry.text}`.toLowerCase();
			expect(PROHIBITED_WORDING.some((w) => copy.includes(w))).toBe(false);
		}
		if (unusablePresentation) {
			expect(unusablePresentation.text).not.toContain('MODEL_V1');
			expect(unusablePresentation.text).toContain('No model inference was run');
		}

		const route = await realFetch(`/monitoring?mode=replay&replay=${REPLAY_ID}`);
		writeFileSync(
			OUT!,
			JSON.stringify(
				{
					replay_id: REPLAY_ID,
					bundle_window_count: bundle.events.length,
					captured: captured.map((c) => ({
						timestamp_us: c.timestamp_us,
						request_ecg_quality: c.ecg_quality,
						ppg_context_present: c.ppg_context_present,
						samples: c.samples,
						kind: c.result.kind,
						status: c.result.status,
						response: c.result.kind === 'success' ? c.result.data : null,
						error: c.result.kind === 'success' || c.result.kind === 'transport_error' ? null : c.result.error
					})),
					session: {
						request_count: session.requestCount,
						history_length: session.history.length,
						gap_markers: session.history.filter((h) => h.kind === 'gap').length,
						latest_ecg_window_length: session.latestEcgWindow!.length,
						latest_ecg_equals_last_accepted_request_window: true,
						final_state: r.monitoring_state
					},
					dom: {
						waveform_polyline_points: polylinePoints,
						rendered_tiles: rendered,
						research_panel_eyebrow_present: true,
						state_panel_title: presentation.title,
						state_text_contains_not_a_diagnosis: true,
						unusable_text_model_neutral: unusablePresentation?.text ?? null
					},
					monitoring_route_http_status: route.status
				},
				null,
				1
			)
		);
	}, 300_000);
});
