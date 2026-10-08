<script lang="ts">
	import { onMount } from 'svelte';
	import { getProductStore } from '$lib/product/state.svelte';
	import { ProductApiError } from '$lib/product/api';
	import type { ScenarioInfo, WindowTrace } from '$lib/product/observatory/types';
	import SignalStageChart from '$lib/components/product/observatory/SignalStageChart.svelte';

	const store = getProductStore();
	let scenarios = $state<ScenarioInfo[]>([]);
	let scenarioId = $state('MIXED_MONITORING_SESSION');
	let sessionId = $state('');
	let windowIndex = $state(0);
	let trace = $state<WindowTrace | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let requestNumber = 0;
	let captureRequested = $state(false);
	const scenario = $derived(scenarios.find((s) => s.scenario_id === scenarioId) ?? null);
	const selectedSession = $derived(store.sessions.find((s) => s.session_id === sessionId));
	const maximum = $derived(Math.max(0, (scenario?.window_count ?? 1) - 1));
	const sourceCommit = 'dff28f6a7b7bd527def21cb9fd95d682aa60a667';
	const codeLinks = [
		{ label: 'Gap policy', path: 'preprocessing/gaps.py' },
		{ label: 'Causal resampling', path: 'preprocessing/resample.py' },
		{ label: 'ECG filtering', path: 'preprocessing/filters.py' },
		{ label: 'Window normalization', path: 'preprocessing/windowing.py' },
		{ label: 'Streaming assembly', path: 'simulation/stream_runtime_v2013.py' }
	];

	async function load() {
		const current = ++requestNumber;
		loading = true;
		error = null;
		try {
			const value = sessionId
				? await store.api.observatorySessionWindow(sessionId, windowIndex)
				: await store.api.observatoryScenarioWindow(scenarioId, windowIndex);
			if (current === requestNumber) trace = value;
		} catch (cause) {
			if (current === requestNumber) {
				trace = null;
				error = cause instanceof Error ? cause.message : String(cause);
			}
		} finally {
			if (current === requestNumber) loading = false;
		}
	}
	function chooseScenario(event: Event) {
		scenarioId = (event.currentTarget as HTMLSelectElement).value;
		sessionId = '';
		captureRequested = false;
		windowIndex = 0;
		void load();
	}
	function chooseSession(event: Event) {
		sessionId = (event.currentTarget as HTMLSelectElement).value;
		captureRequested = false;
		const selected = store.sessions.find((s) => s.session_id === sessionId);
		if (selected?.simulation_provenance) scenarioId = selected.simulation_provenance.scenario_id;
		windowIndex = 0;
		if (selected?.state === 'DEVICE_READY') {
			requestNumber += 1;
			trace = null; loading = false; error = null;
			return;
		}
		void load();
	}
	function move(delta: number) {
		windowIndex = Math.min(maximum, Math.max(0, windowIndex + delta));
		captureRequested = false;
		if (selectedSession?.state !== 'DEVICE_READY') void load();
	}
	async function startWithCapture() {
		if (!sessionId || selectedSession?.state !== 'DEVICE_READY') return;
		const current = ++requestNumber;
		loading = true; error = null; trace = null;
		try {
			await store.api.observatoryArmSessionCapture(sessionId, windowIndex);
			await store.api.startSession(sessionId);
			captureRequested = true;
			await store.loadSessions();
			for (let attempt = 0; attempt < 60; attempt++) {
				if (current !== requestNumber) return;
				try {
					const value = await store.api.observatoryCapturedSessionWindow(sessionId);
					if (current === requestNumber) trace = value;
					return;
				} catch (cause) {
					if (!(cause instanceof ProductApiError && cause.status === 409)) throw cause;
					await new Promise((resolve) => setTimeout(resolve, 500));
				}
			}
			throw new Error('The selected live window was not emitted within 30 seconds. The monitoring session may still be running; retry loading its captured trace.');
		} catch (cause) {
			if (current === requestNumber) error = cause instanceof Error ? cause.message : String(cause);
		} finally { if (current === requestNumber) loading = false; }
	}
	async function reloadCapture() {
		if (!sessionId) return;
		const current = ++requestNumber;
		captureRequested = true;
		loading = true; error = null;
		try {
			const value = await store.api.observatoryCapturedSessionWindow(sessionId);
			if (current === requestNumber) trace = value;
		} catch (cause) {
			if (current === requestNumber) error = cause instanceof Error ? cause.message : String(cause);
		} finally { if (current === requestNumber) loading = false; }
	}
	onMount(() => {
		void (async () => {
			try {
				const loaded = await store.api.observatoryScenarios();
				scenarios = loaded;
				if (!loaded.some((s) => s.scenario_id === scenarioId)) scenarioId = loaded[0]?.scenario_id ?? '';
				await store.loadSessions();
				if (scenarioId) await load();
				else { loading = false; error = 'No frozen synthetic scenarios are available.'; }
			} catch (cause) {
				loading = false;
				error = cause instanceof Error ? cause.message : String(cause);
			}
		})();
	});
</script>

<svelte:head><title>Research Observatory | NHM</title></svelte:head>

<div class="eyebrow">NHM / RESEARCH OBSERVATORY</div>
<h1>Follow one signal through the system</h1>
<p class="lead">Inspect a deterministic synthetic window through the unchanged gap controller, causal resampler, ECG filter and normalization. Existing sessions default to bounded reconstruction; a new session can explicitly capture one window from its actual live preprocessing runtime.</p>
<p><a href="/app/observatory/federation">Inspect all eight synthetic federation participants and their recorded contributions →</a></p>
<p><a href="/app/observatory/research">Inspect an authorized MIT-BIH TRAIN research window →</a></p>
<p><a href="/app/observatory/tour">Start the guided evidence journey →</a></p>

<section class="controls" aria-label="Trace selection">
	<label>SCENARIO
		<select value={scenarioId} onchange={chooseScenario} disabled={!scenarios.length}>
			{#each scenarios as item}<option value={item.scenario_id}>{item.scenario_id}</option>{/each}
		</select>
	</label>
	<label>OWNED PERSISTED SESSION (OPTIONAL)
		<select value={sessionId} onchange={chooseSession}>
			<option value="">Scenario reconstruction only</option>
			{#each store.sessions.filter((s) => !!s.simulation_provenance) as item}<option value={item.session_id}>{item.session_id} · {item.state}</option>{/each}
		</select>
	</label>
	<div class="window-control">
		<span>SELECTED 10-SECOND WINDOW</span>
		<div class="stepper"><button onclick={() => move(-1)} disabled={loading || windowIndex === 0} aria-label="Previous window">←</button>
			<input aria-label="Selected window index" type="range" min="0" max={maximum} step="1" bind:value={windowIndex} oninput={() => { captureRequested = false; if (selectedSession?.state !== 'DEVICE_READY') void load(); }} disabled={loading || !scenario} />
			<button onclick={() => move(1)} disabled={loading || windowIndex >= maximum} aria-label="Next window">→</button>
			<output>W{String(windowIndex).padStart(4, '0')} / {maximum}</output></div>
	</div>
</section>
{#if selectedSession?.state === 'DEVICE_READY'}<div class="capture-control"><p><b>CAPTURE ONE ACTUAL LIVE WINDOW</b> — arming is opt-in and memory-only. Starting this owned session runs the normal released monitoring model; capture observes the selected source/gap/resampler/filter stages without changing its processing. The normalized input shown is reconstructed from the emitted filtered window, not recorded inside the gateway.</p><button onclick={() => void startWithCapture()} disabled={loading}>Arm window {windowIndex} and start monitoring</button></div>{/if}
{#if sessionId && selectedSession?.state !== 'DEVICE_READY' && !captureRequested}<div class="capture-control"><p>A previously armed capture may still be available in this backend process. Historical sessions without one remain reconstruction-only.</p><button onclick={() => void reloadCapture()} disabled={loading}>Open captured live window if available</button></div>{/if}
{#if captureRequested}<p class="capture-control">Live capture was requested for this session. {#if loading}Waiting for the selected source window…{:else}<button onclick={() => void reloadCapture()}>Reload captured evidence</button>{/if}</p>{/if}

{#if loading}<p role="status" class="status">{captureRequested ? 'Waiting for the actual live captured window…' : 'Reconstructing the selected canonical window…'}</p>{/if}
{#if error}<div role="alert" class="error"><strong>Trace unavailable</strong><p>{error}</p><p>Historical sessions only expose windows with persisted inference evidence. For an excluded/unusable window, inspect the scenario reconstruction instead.</p></div>{/if}

{#if trace && !loading}
	<section class="summary" aria-label="Selected window evidence">
		<div><span>WINDOW</span><strong>{trace.window_id}</strong><small>{trace.left_timestamp_us / 1_000_000}s–{trace.right_timestamp_us / 1_000_000}s source time · [left, right)</small></div>
		<div><span>QUALITY GATE</span><strong class:warn={trace.quality_state !== 'VALID'}>{trace.quality_state}</strong><small>{trace.quality_reasons.join(', ') || 'No emitted quality reasons'}</small></div>
		<div><span>MODEL INPUT</span><strong>{trace.normalization.status === 'RECONSTRUCTED_MODEL_INPUT' ? 'float32 [1, 2500]' : 'NOT APPLIED'}</strong><small>Per-window z-score, only for usable inference windows</small></div>
		<div><span>INFERENCE EVIDENCE</span><strong>{trace.persisted_inference ? trace.persisted_inference.monitoring_state : 'NOT ATTACHED'}</strong><small>{trace.inference_evidence_status}</small></div>
	</section>
	<div class="classification">{trace.classification === 'CAPTURED_LIVE_PREPROCESSING' ? 'CAPTURED FROM THIS LIVE PREPROCESSING RUNTIME · GATEWAY INPUT RECONSTRUCTED' : 'DETERMINISTIC LOCAL RECONSTRUCTION · SYNTHETIC VIRTUAL WEARABLE · NO NEW INFERENCE'}</div>
	<section aria-labelledby="pipeline-title">
		<div class="section-head"><div><span>01 / SIGNAL PATH</span><h2 id="pipeline-title">Same window, five representations</h2></div><p>Plots use actual values returned by the canonical operators. Null gaps are never joined or filled by the chart.</p></div>
		<div class="signal-grid">{#each trace.stages as stage}<SignalStageChart {stage} startUs={trace.left_timestamp_us} endUs={trace.right_timestamp_us} />{/each}</div>
	</section>
	<section class="facts" aria-label="Window and gap evidence">
		<article><span>02 / WINDOWING</span><h2>10 seconds, 5-second cadence</h2><p>The selected window contains {trace.window_sample_count} target-rate positions at {trace.target_rate_hz} Hz. Moving one step advances the right edge by {trace.cadence_us / 1_000_000} seconds; adjacent windows overlap. Signal samples occupy [t−10 s, t).</p><p>Source ECG uses {trace.source_rate_hz} Hz synthetic transport; processing and inference are server-side, not performed in this browser.</p></article>
		<article><span>03 / GAP POLICY</span><h2>{trace.gaps.length ? `${trace.gaps.length} intersecting source gap(s)` : 'No source gap intersects this window'}</h2>
			{#each trace.gaps as gap}<div class="gap"><b>{gap.kind} · {gap.duration_ms} ms</b><p>Missing source indices {gap.first_missing_index}–{gap.last_missing_index}; {gap.fill_count} causal hold fills; segment {gap.previous_segment_id} → {gap.next_segment_id}. Quality requirement: {gap.quality_requirement}.</p></div>{/each}
			{#if !trace.gaps.length}<p>No gap is invented for this selected interval. Select a faulted scenario/window to inspect actual emitted gap events.</p>{/if}
		</article>
		<article><span>04 / CONTEXT</span><h2>{trace.context_available ? 'Context available' : 'Context unavailable'}</h2><p>ECG is the supervised model signal. Device-reported PPG/SpO₂/pulse values are context and quality evidence, not a jointly supervised classification input. {trace.classification === 'CAPTURED_LIVE_PREPROCESSING' ? 'Availability comes from the live emitted window.' : trace.session_id ? 'For this owned session, availability comes from the projected public context snapshot.' : 'Availability comes from deterministic scenario reconstruction.'}</p></article>
		<article><span>05 / NORMALIZATION</span><h2>{trace.normalization.identity}</h2><p>Status: {trace.normalization.status}. {#if trace.normalization.mean !== null}Mean {trace.normalization.mean.toPrecision(7)}, population standard deviation {trace.normalization.std?.toPrecision(7)}, epsilon {trace.normalization.epsilon}.{:else}An unusable window is rejected before model input normalization.{/if}</p></article>
	</section>
	{#if trace.persisted_inference}<section class="inference"><span>06 / PERSISTED MODEL RESULT</span><h2>{trace.persisted_inference.monitoring_state}</h2><p>MODEL_V2_FINAL · CAL_V2 · {trace.persisted_inference.calibration_domain}. Raw sigmoid probability {trace.persisted_inference.raw_probability ?? 'unavailable'}; source-domain calibrated probability {trace.persisted_inference.source_domain_calibrated_probability ?? 'unavailable'}; fixed threshold {trace.persisted_inference.threshold ?? 'unavailable'}.</p><p><strong>RESEARCH TECHNICAL METADATA</strong> — not disease probability, diagnosis, or personal risk. The Observatory did not rerun inference.</p></section>{:else}<p class="not-available">No persisted model result is attached to this scenario-only reconstruction. Select an owned inferred session window to inspect its recorded result.</p>{/if}
	<details class="evidence"><summary>TECHNICAL EVIDENCE & LIMITATIONS</summary><dl><div><dt>Trace classification</dt><dd>{trace.classification}</dd></div><div><dt>Source</dt><dd>{trace.source_kind} / {trace.scenario_id}</dd></div><div><dt>Normalization tensor digest</dt><dd>{trace.normalization.tensor_sha256 ?? 'NOT APPLIED'}</dd></div><div><dt>Context/inference basis</dt><dd>{trace.inference_evidence_status}</dd></div><div><dt>Claim boundary</dt><dd>{trace.claim_boundary}</dd></div></dl><p>Canonical source-code references at accepted entry commit <code>{sourceCommit}</code> (offline path references; no external link):</p><ul>{#each codeLinks as item}<li>{item.label} · <code>{item.path}</code></li>{/each}</ul><ul>{#each trace.limitations as item}<li>{item}</li>{/each}</ul></details>
{/if}

<style>
	.eyebrow,.section-head span,.facts article>span,.inference>span{color:#2bb8b0;font:10px 'JetBrains Mono',monospace;letter-spacing:.14em}
	h1{margin:9px 0;font:500 clamp(28px,4vw,42px) 'Space Grotesk',sans-serif}.lead{max-width:850px;color:#a7b8c9;line-height:1.6;margin:0 0 20px}
	.controls{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-bottom:14px}.controls label,.window-control{display:grid;gap:8px;padding:13px;border:1px solid rgba(148,163,184,.25);color:#94a3b8;font:10px 'JetBrains Mono',monospace;letter-spacing:.09em;min-width:0}.window-control{grid-column:1/-1}
	select,input,button{min-height:32px;background:#07101e;color:#e5f1f0;border:1px solid rgba(148,163,184,.35);font:12px 'JetBrains Mono',monospace}select{width:100%;min-width:0;padding:7px}.stepper{display:flex;align-items:center;gap:10px}.stepper input{flex:1;min-width:40px}.stepper button{min-width:36px;cursor:pointer}.stepper button:disabled{opacity:.45;cursor:not-allowed}.stepper output{white-space:nowrap;color:#e5f1f0}
	.status,.error,.not-available{padding:14px;border:1px solid rgba(148,163,184,.3);color:#a7b8c9}.error{border-color:#fb7185;color:#fecdd3}.error p{margin:6px 0 0}
	.summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-bottom:10px}.summary>div{display:grid;gap:7px;padding:13px;border:1px solid rgba(148,163,184,.24);min-width:0}.summary span{color:#71829a;font:10px 'JetBrains Mono',monospace;letter-spacing:.1em}.summary strong{overflow-wrap:anywhere;font:500 15px 'Space Grotesk',sans-serif}.summary strong.warn{color:#fbbf24}.summary small{color:#94a3b8;line-height:1.5;overflow-wrap:anywhere;min-width:0}
	.classification{padding:8px 11px;margin-bottom:18px;border-left:3px solid #fbbf24;background:rgba(251,191,36,.08);color:#fbbf24;font:10px 'JetBrains Mono',monospace;letter-spacing:.08em}
	.capture-control{border:1px solid rgba(43,184,176,.45);background:rgba(43,184,176,.07);padding:12px;margin:12px 0;color:#b9cad7;font-size:12px;line-height:1.6}.capture-control p{margin:0 0 10px}.capture-control button{padding:9px 13px;cursor:pointer}.capture-control button:disabled{opacity:.5;cursor:not-allowed}
	.section-head{display:flex;justify-content:space-between;gap:16px;align-items:end;margin-bottom:10px}.section-head h2,.facts h2,.inference h2{font:500 21px 'Space Grotesk',sans-serif;margin:5px 0}.section-head p{max-width:360px;color:#94a3b8;font-size:12px;line-height:1.5;margin:0}
	.signal-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.facts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:14px 0}.facts article,.inference{padding:16px;border:1px solid rgba(148,163,184,.24)}.facts p,.inference p{color:#a7b8c9;font-size:13px;line-height:1.6}.gap{border-left:2px solid #fbbf24;padding-left:10px}.gap b{color:#fbbf24;font:11px 'JetBrains Mono',monospace}
	.inference{border-color:rgba(43,184,176,.45)}.inference strong{color:#fbbf24}.evidence{padding:12px;border:1px solid rgba(148,163,184,.24);margin:14px 0}.evidence summary{cursor:pointer;color:#2bb8b0;font:11px 'JetBrains Mono',monospace;min-height:24px}.evidence dl{display:grid;gap:7px}.evidence dl div{display:grid;grid-template-columns:180px minmax(0,1fr);gap:10px}.evidence dt{color:#71829a}.evidence dd{margin:0;overflow-wrap:anywhere}.evidence li{margin-bottom:6px;color:#94a3b8}.evidence code{overflow-wrap:anywhere}
	select:focus-visible,input:focus-visible,button:focus-visible,summary:focus-visible{outline:2px solid #fbbf24;outline-offset:2px}
	@media(max-width:900px){.summary{grid-template-columns:repeat(2,minmax(0,1fr))}.signal-grid{grid-template-columns:1fr}}
	@media(max-width:620px){.controls,.facts,.summary{grid-template-columns:1fr}.window-control{grid-column:auto}.section-head{display:block}.stepper{flex-wrap:wrap}.stepper output{width:100%}.evidence dl div{grid-template-columns:1fr;gap:2px}}
</style>
