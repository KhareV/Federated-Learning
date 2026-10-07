<script lang="ts">
	// CAPSTONE_MONITORING_UI_V1: renders ONLY validated PRODUCT_LIVE_EVENT_V1 events from the CAP-004
	// product backend. The browser never calls /v1/infer-window and never derives a monitoring state.
	import { onDestroy, onMount } from 'svelte';
	import Panel from '$lib/components/dashboard/Panel.svelte';
	import MetricTile from '$lib/components/dashboard/MetricTile.svelte';
	import WaveformPlot from '$lib/components/product/WaveformPlot.svelte';
	import FlowDiagram from '$lib/components/product/story/FlowDiagram.svelte';
	import ComparisonPanel from '$lib/components/product/story/ComparisonPanel.svelte';
	import TechnicalEvidence from '$lib/components/product/federation/TechnicalEvidence.svelte';
	import SimulationBanner from '$lib/components/product/SimulationBanner.svelte';
	import { STATE_PRESENTATION } from '$lib/dashboard/state-presentation';
	import { getProductStore } from '$lib/product/state.svelte';
	import { MONITORING_SCENARIOS, RECOMMENDED_SCENARIO, type ScenarioId } from '$lib/product/types';

	const store = getProductStore();
	const live = $derived(store.live);
	const session = $derived(store.activeSession);
	const device = $derived(store.selectedDevice);
	const connected = $derived(device?.connection_state === 'CONNECTED' || device?.connection_state === 'STREAMING');
	let pickedScenario = $state<ScenarioId | ''>('');
	const known = $derived(device ? store.scenarioFor(device.device_id) : null);
	const scenario = $derived((known ?? (pickedScenario || RECOMMENDED_SCENARIO)) as ScenarioId);
	const sessState = $derived(live.sessionState ?? session?.state ?? null);
	const active = $derived(sessState === 'MONITORING' || sessState === 'STOPPING');
	const finished = $derived(sessState === 'COMPLETED' || sessState === 'FAILED');
	const canCreate = $derived(connected && !active && (!session || finished));
	const canStart = $derived(session?.state === 'DEVICE_READY' && !finished && live.sessionState === null);
	const pct = (v: number | null | undefined, d = 4) => (v === null || v === undefined ? '--' : v.toFixed(d));
	const stateText = $derived(live.monitoringState ? STATE_PRESENTATION[live.monitoringState] : null);
	const ts = (us: number | null) => (us === null ? '--' : new Date(us / 1000).toLocaleString());
	const announce = $derived(`Session ${sessState ?? 'not started'}. Device ${live.deviceState ?? device?.connection_state ?? 'none'}. Monitoring state ${live.monitoringState ?? 'none yet'}.`);

	const sys = $derived(store.authState.system);
	const modelId = $derived(live.inference?.model_id ?? sys?.model_id ?? 'MODEL_V2_FINAL');
	const calId = $derived(live.inference?.calibration_id ?? sys?.calibration_id ?? 'CAL_V2');
	// Pipeline progress is derived ONLY from events already received (never from the browser running anything).
	const flow = $derived.by(() => {
		const done = [connected || !!session, live.segments.length > 0, !!live.quality, !!live.inference, !!live.monitoringState, finished];
		const firstOpen = done.indexOf(false);
		const names: [string, string][] = [['VIRTUAL WEARABLE', 'simulated source'], ['SIGNAL', 'source ECG'], ['QUALITY', 'signal quality'], [`${modelId}`, 'server-side inference'], ['MONITORING STATE', 'research state'], ['ALERT / HISTORY', 'persisted']];
		return names.map(([label, sub], i) => ({ label, sub, tone: (i === 3 ? 'released' : 'neutral') as 'released' | 'neutral', mark: done[i] ? '✓' : i === firstOpen && active ? '●' : '○', status: (done[i] ? 'done' : i === firstOpen && active ? 'active' : 'pending') as 'done' | 'active' | 'pending' }));
	});
	onMount(() => { void store.loadDevices(); void store.loadSessions(); });
	onDestroy(() => { if (!active) store.closeLive(); });
</script>

<svelte:head><title>Monitor | NHM</title></svelte:head>

<SimulationBanner />
<div class="eyebrow">NHM / MONITOR</div>
<h1>Live monitoring</h1>
<div class="sr" role="status" aria-live="polite">{announce}</div>
<p class="lead">A simulated wearable streams ECG to the backend. The server checks signal quality, runs {modelId} with {calId}, and reports a research monitoring state. The browser only displays what the backend sends.</p>
<div class="flowbox" data-testid="monitoring-flow"><FlowDiagram label="Monitoring pipeline" steps={flow} /></div>

{#if store.error}<p class="err" role="alert">{store.error}</p>{/if}

<Panel eyebrow="01 / SESSION" title="Monitoring session" note="PERSISTED IN SQLITE">
	{#if !device}
		<p class="dim">No virtual wearable is attached. <a href="/app/device">Attach one on the Device page →</a></p>
	{:else if !connected && !session}
		<p class="dim">Device <code>{device.device_id}</code> is <b>{device.connection_state}</b>. Scan and connect it first. <a href="/app/device">Device page →</a></p>
	{:else}
		<dl>
			<dt>DEVICE</dt><dd>{device.device_id} <span class="badge">{live.deviceState ?? device.connection_state}</span></dd>
			<dt>SCENARIO</dt><dd>{#if known}{known}{:else}<select aria-label="Scenario (must match the device)" bind:value={pickedScenario}><option value="">{RECOMMENDED_SCENARIO} (default)</option>{#each MONITORING_SCENARIOS as s}<option value={s.id}>{s.id}</option>{/each}</select>{/if}</dd>
			<dt>SESSION</dt><dd data-testid="session-id">{session?.session_id ?? 'not created'}</dd>
			<dt>SESSION STATE</dt><dd><strong data-testid="session-state">{sessState ?? '--'}</strong>{#if live.sessionElapsedMs !== null} <span class="dim">elapsed {(live.sessionElapsedMs / 1000).toFixed(1)} s (source time)</span>{/if}</dd>
		</dl>
		<div class="actions">
			<button class="primary" onclick={() => store.createSession(device.device_id, scenario)} disabled={store.busy || !canCreate} data-testid="create-session">CREATE MONITORING SESSION</button>
			<button class="primary" onclick={() => store.startSession()} disabled={store.busy || !canStart} data-testid="start-session">START MONITORING</button>
			<button onclick={() => store.stopSession()} disabled={store.busy || !active} data-testid="stop-session">STOP MONITORING</button>
		</div>
	{/if}
	{#if finished && !connected}<p class="dim" data-testid="rerun-hint">To run another session, scan and connect the virtual wearable again on the <a href="/app/device">Device page</a> (it ends each session {device?.connection_state === 'STOPPED' ? 'STOPPED' : 'in its own link state'}).</p>{/if}
	{#if finished && session}
		<div class="done" role="status" data-testid="session-complete">
			<b>{sessState === 'COMPLETED' ? 'Session completed' : 'Session failed (technical)'}</b>
			<span>Persistent session ID <code>{session.session_id}</code>{#if session.ended_at_us} / ended {ts(session.ended_at_us)}{/if}</span>
			<span><a href="/app/history">View sessions</a> · <button class="link" onclick={() => { store.resetLive(); }}>Start another session</button></span>
		</div>
	{/if}
	<dl class="facts" data-testid="session-facts"><div><dt>DEVICE</dt><dd>{device?.device_id ?? '--'}</dd></div><div><dt>SCENARIO</dt><dd>{known ?? (pickedScenario || RECOMMENDED_SCENARIO)}</dd></div><div><dt>MODEL</dt><dd>{modelId} · server-side</dd></div><div><dt>CALIBRATION</dt><dd>{calId}</dd></div></dl>
</Panel>

{#if store.socketStatus !== 'IDLE' || live.eventCount > 0}
	<div class="stream" data-testid="stream-status">
		<span>LIVE STREAM</span><b>{store.socketStatus}</b><span>EVENTS {live.eventCount}</span>
		{#if store.socketStatus === 'DISCONNECTED' || live.streamError}<button onclick={() => store.reconnectLive()}>RECONNECT</button>{/if}
	</div>
	{#if store.socketStatus === 'DISCONNECTED' && !live.streamError}<p class="err" role="alert">LIVE STREAM DISCONNECTED - use Reconnect to rebuild from the start of the session journal.</p>{/if}
{/if}
{#if live.streamError}<p class="err" role="alert" data-testid="stream-error">{live.streamError.message}</p>{/if}

<div class="wave">
	<Panel eyebrow="02 / SIMULATED SOURCE ECG" title="Virtual wearable ECG · MODEL SIGNAL" note="360 Hz / ADC_COUNTS / rolling 10 s">
		<WaveformPlot segments={live.segments} start={live.waveformStart} end={live.waveformEnd} capacity={live.waveformCapacity || 3600} gaps={live.gaps} openGap={live.openGap} />
		<p class="foot">Simulated device-source ECG transport (not the 250 Hz model-input window, not a physical sensor). PPG waveform is unavailable in the current simulator; SpO2/PPG-derived context appears only where emitted.</p>
		{#if live.gaps.length || live.openGap}
			<p class="warn" role="status">Source gaps were observed in this stream.</p>
			<TechnicalEvidence label="TECHNICAL EVIDENCE (gap ranges)" testid="gap-evidence"><p class="foot" data-testid="gap-list">Source gaps observed (sample indices): {#each [...live.gaps, ...(live.openGap ? [live.openGap] : [])] as g}<code>[{g.start}, {g.end}]</code> {/each}</p></TechnicalEvidence>
		{/if}
	</Panel>
</div>
<div class="wave">
	<Panel eyebrow="SOURCE VS MODEL INPUT" title="What is drawn is not what the model reads" note="SERVER-SIDE INFERENCE">
		<ComparisonPanel testid="source-vs-model" leftTitle="SIMULATED SOURCE ECG" leftSub="what the waveform shows" leftTone="neutral" rightTitle="MODEL INPUT" rightSub={modelId} rightTone="released" rows={[
			{ label: 'Form', left: '360 Hz transport', right: 'Causally prepared 10 s ECG window' },
			{ label: 'Prepared where', left: 'Streamed by the virtual wearable', right: 'On the server, from the source stream' },
			{ label: 'Browser role', left: 'Draws it', right: 'None: the browser never runs preprocessing or inference' }
		]} />
	</Panel>
</div>

<p class="sep" data-testid="quality-vs-state">SIGNAL QUALITY (is the signal usable?) is not the same thing as MONITORING STATE (the model-derived research state).</p>
<div class="pair">
	<Panel eyebrow="03 / SIGNAL QUALITY" title="Signal quality · is the signal usable?" note="quality.status">
		{#if live.quality}
			<p class="big" data-testid="quality-state">{live.quality.ecg_quality}</p>
			<p class="label" data-testid="quality-label">{live.quality.ui_label}</p>
			<p class="foot">A signal-quality message. It is NOT a monitoring state. ECG windows so far: {live.qualityCounts.VALID} valid / {live.qualityCounts.DEGRADED} degraded / {live.qualityCounts.UNUSABLE} unusable.</p>
		{:else}<p class="dim">No quality.status event yet.</p>{/if}
	</Panel>
	<Panel eyebrow="04 / MONITORING STATE" title="Research monitoring state · model-derived" note="monitoring.state">
		{#if live.monitoringState && stateText}
			<p class="big" data-testid="monitoring-state">{live.monitoringState}</p>
			<p class="label">{stateText.title}</p><p class="foot">{stateText.text}</p>
		{:else}<p class="dim" data-testid="monitoring-state-none">No monitoring.state event received yet. The state changes only when the backend sends one.</p>{/if}
		{#if live.monitoringChanges.length}<TechnicalEvidence label="TECHNICAL EVIDENCE (state-change log)" testid="state-changes-evidence"><ol class="changes" data-testid="state-changes">{#each live.monitoringChanges as c}<li><code>#{c.sequence_index}</code> {c.previous ?? 'start'} → <b>{c.state}</b></li>{/each}</ol></TechnicalEvidence>{/if}
	</Panel>
</div>
<div class="grid">
	<Panel eyebrow="05 / CONTEXT" title="PPG / SpO2 · context and quality" note="CONTEXT, NOT A MODEL SIGNAL">
		{#if (live.contextState === 'CURRENT' || live.contextState === 'PENDING') && live.context}
			{#if live.contextState === 'PENDING'}<p class="dim" data-testid="context-pending">Updating… (values below are from the previous window)</p>{/if}
			<div class="kv" class:fade={live.contextState === 'PENDING'}><MetricTile label="ECG HR" value={pct(live.context.hr_ecg_bpm, 1)} unit="bpm" /><MetricTile label="PPG pulse rate" value={pct(live.context.pr_ppg_bpm, 1)} unit="bpm" tone="cyan" /><MetricTile label="SpO2" value={live.context.spo2_valid ? pct(live.context.spo2_pct, 1) : '--'} unit="%" tone="cyan" detail={live.context.spo2_valid ? 'VALID' : 'NOT VALID'} /></div>
			<p class="foot">PPG quality: {live.context.ppg_quality ?? 'n/a'}</p>
		{:else if live.contextState === 'PENDING'}<p class="dim" data-testid="context-pending">Waiting for the first context for this window…</p>
		{:else}<p class="big" data-testid="context-unavailable">CONTEXT NOT AVAILABLE FOR THIS WINDOW</p><p class="foot">No current context for the latest window{live.context && !live.context.context_available ? ' (the backend reported context_available = false)' : ''}. Earlier values are not shown as current.</p>{/if}
	</Panel>
	<Panel eyebrow="06 / INFERENCE" title="MODEL_V2_FINAL result" note="inference.result">
		{#if live.inference}
			{#if live.inferenceState === 'NONE_FOR_WINDOW'}<p class="warn" data-testid="inference-stale">No inference for the latest window (it was not usable). Showing the previous result.</p>{:else if live.inferenceState === 'PENDING'}<p class="dim" data-testid="inference-pending">Updating… (previous window's result shown)</p>{/if}
			<dl class="tech">
				<dt>model</dt><dd data-testid="inf-model">{live.inference.model_id}</dd><dt>calibration</dt><dd data-testid="inf-cal">{live.inference.calibration_id} ({live.inference.calibration_domain})</dd>
				<dt>preprocess</dt><dd>{live.inference.preprocess_version}</dd><dt>alert policy</dt><dd>{live.inference.alert_policy_id}</dd>
				<dt>ECG quality</dt><dd>{live.inference.ecg_quality}</dd><dt>monitoring state</dt><dd>{live.inference.monitoring_state}</dd><dt>latency</dt><dd>{pct(live.inference.latency_ms, 1)} ms</dd>
			</dl>
			<details class="research"><summary>RESEARCH / TECHNICAL - not a risk score</summary>
				<dl class="tech"><dt>raw probability</dt><dd>{pct(live.inference.raw_probability)}</dd><dt>source-domain calibrated</dt><dd>{pct(live.inference.source_domain_calibrated_probability)}</dd><dt>threshold</dt><dd>{pct(live.inference.threshold)}</dd></dl>
				<p class="foot">Technical research metadata. Not a diagnosis, disease probability or clinical confidence.</p></details>
		{:else}<p class="dim">No inference.result event yet.</p>{/if}
	</Panel>
	<Panel eyebrow="07 / DEVICE LINK" title="Device connection" note="device.status">
		<p class="big" data-testid="live-device-state">{live.deviceState ?? device?.connection_state ?? '--'}</p>
		{#if live.deviceChanges.length}<ol class="changes">{#each live.deviceChanges as c}<li><code>#{c.sequence_index}</code> {c.state}{c.reason ? ` (${c.reason})` : ''}</li>{/each}</ol>{/if}
		<p class="foot">A device disconnect does not end the session; the backend session stays authoritative.</p>
	</Panel>
	{#if live.systemErrors.length}
		<Panel eyebrow="08 / TECHNICAL" title="System error" note="system.error">
			{#each live.systemErrors as e}<p class="warn" data-testid="system-error">{e.origin} / {e.error_code}: {e.message} {e.recoverable ? '(recoverable)' : ''}</p>{/each}
			<p class="foot">A technical/runtime failure - not a physiological state.</p>
		</Panel>
	{/if}
</div>

<style>
	.eyebrow { color: #2bb8b0; font: 10px 'JetBrains Mono', monospace; letter-spacing: .14em; } h1 { margin: 10px 0 18px; font: 500 clamp(26px, 4vw, 40px) 'Space Grotesk', sans-serif; }
	.sr { position: absolute; left: -9999px; } .dim, .foot { color: #94a3b8; font-size: 12px; line-height: 1.6; } .foot { margin: 10px 0 0; } code { font: 11px 'JetBrains Mono', monospace; color: #9fe7e1; overflow-wrap: anywhere; }
	.err { color: #fecdd3; padding: 10px 12px; border: 1px solid rgba(251,113,133,.4); background: rgba(127,29,29,.2); overflow-wrap: anywhere; } .warn { color: #fde68a; padding: 8px 10px; border: 1px solid rgba(251,191,36,.4); background: rgba(251,191,36,.06); font-size: 12px; }
	dl { display: grid; grid-template-columns: max-content 1fr; gap: 6px 18px; margin: 0 0 14px; font: 12px/1.5 'JetBrains Mono', monospace; } dt { color: #71829a; } dd { margin: 0; overflow-wrap: anywhere; } dl.tech { margin: 8px 0; }
	.actions { display: flex; flex-wrap: wrap; gap: 10px; } button { padding: 11px 16px; border: 1px solid var(--nhm-border); background: transparent; color: #e2e8f0; font: 600 12px 'JetBrains Mono', monospace; letter-spacing: .1em; cursor: pointer; } button.primary { background: #2bb8b0; color: #03110f; border-color: #2bb8b0; } button:disabled { opacity: .4; cursor: not-allowed; } button.link { padding: 0; border: 0; color: #2bb8b0; text-decoration: underline; }
	select { padding: 6px 8px; background: #050a15; color: #eef7f6; border: 1px solid var(--nhm-border); }
	.badge { padding: 2px 7px; border: 1px solid rgba(43,184,176,.5); color: #2bb8b0; font: 10px 'JetBrains Mono', monospace; }
	.done { display: grid; gap: 6px; margin-top: 14px; padding: 12px 14px; border: 1px solid rgba(43,184,176,.5); background: rgba(43,184,176,.08); font-size: 13px; } .done a, .done button { color: #2bb8b0; }
	.stream { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin: 14px 0; font: 11px 'JetBrains Mono', monospace; letter-spacing: .08em; color: #71829a; } .stream b { color: #2bb8b0; } .stream button { padding: 6px 12px; }
	.wave { margin: 14px 0; } .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 10px; }
	.big { margin: 0 0 4px; font: 500 20px 'Space Grotesk', sans-serif; overflow-wrap: anywhere; } .label { margin: 0; color: #e2e8f0; font-size: 14px; }
	.kv.fade { opacity: .5; }
	.kv { display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: 6px; } .changes { margin: 10px 0 0; padding-left: 18px; font-size: 12px; color: #cbd5e1; display: grid; gap: 3px; }
	.research { margin-top: 8px; padding: 8px 10px; border: 1px solid var(--nhm-border); background: rgba(5,10,21,.7); } summary { cursor: pointer; color: #fbbf24; font: 11px 'JetBrains Mono', monospace; letter-spacing: .08em; }
	@media (max-width: 560px) { dl { grid-template-columns: 1fr; gap: 1px; } dd { margin-bottom: 8px; } .actions button { flex: 1 1 100%; } }
.lead { color: #94a3b8; font-size: 14px; line-height: 1.6; max-width: 760px; margin: -8px 0 14px; } .flowbox { margin: 0 0 16px; } .facts { grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 6px; margin: 14px 0 0; } .facts div { border: 1px solid rgba(148,163,184,.16); padding: 6px 9px; min-width: 0; } .facts dd { font-size: 12px; }
	.pair { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 330px), 1fr)); gap: 10px; margin-bottom: 10px; } .sep { margin: 14px 0 8px; padding: 8px 12px; border-left: 3px solid #fbbf24; color: #fde68a; font: 12px/1.5 'JetBrains Mono', monospace; background: rgba(251,191,36,.05); }
</style>
