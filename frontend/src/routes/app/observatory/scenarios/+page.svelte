<script lang="ts">
	import { focusHeading } from '$lib/product/observatory/focus';
	import { onMount } from 'svelte';
	import { getProductStore } from '$lib/product/state.svelte';
	import SignalStageChart from '$lib/components/product/observatory/SignalStageChart.svelte';
	import type { ScenarioInfo, ScenarioTimeline, WindowTrace } from '$lib/product/observatory/types';
	const store = getProductStore();
	let scenarios = $state<ScenarioInfo[]>([]);
	let scenarioId = $state('MIXED_MONITORING_SESSION');
	let timeline = $state<ScenarioTimeline | null>(null);
	let windowIndex = $state(0);
	let trace = $state<WindowTrace | null>(null);
	let loading = $state(false);
	let error = $state<string | null>(null);
	let compareId = $state('');
	let compareIndex = $state(0);
	let compareTrace = $state<WindowTrace | null>(null);
	let compareError = $state<string | null>(null);
	let request = 0;
	const FAULT_TEXT: Record<string, string> = { ECG_FLATLINE: 'ECG flatline: the source sends a constant signal.', ECG_CLIPPING: 'ECG clipping: the source amplitude saturates.', TRANSPORT_DROPPED_CHUNK: 'Transport drop: source chunks are missing, so the source has a gap.' };
	const CONTEXT_TEXT: Record<string, string> = { MISSING_PPG: 'PPG context is missing; ECG is still the model signal.', INVALID_SPO2: 'SpO₂ context is invalid; ECG is still the model signal.' };
	const edge = $derived(timeline?.window_right_edges_s[windowIndex] ?? 0);
	const left = $derived(timeline ? Math.max(0, edge - timeline.window_length_s) : 0);
	async function loadTimeline() {
		timeline = null; trace = null; error = null; windowIndex = 0;
		try { timeline = await store.api.observatoryScenarioTimeline(scenarioId); await loadWindow(); } catch (c) { error = c instanceof Error ? c.message : String(c); }
	}
	async function loadWindow() {
		const mine = ++request; loading = true; error = null;
		try { const t = await store.api.observatoryScenarioWindow(scenarioId, windowIndex); if (mine === request) trace = t; }
		catch (c) { if (mine === request) { trace = null; error = c instanceof Error ? c.message : String(c); } }
		finally { if (mine === request) loading = false; }
	}
	async function loadCompare() {
		compareError = null; compareTrace = null;
		if (!compareId) return;
		try { compareTrace = await store.api.observatoryScenarioWindow(compareId, compareIndex); } catch (c) { compareError = c instanceof Error ? c.message : String(c); }
	}
	function step(delta: number) { if (!timeline) return; windowIndex = Math.min(timeline.window_right_edges_s.length - 1, Math.max(0, windowIndex + delta)); void loadWindow(); }
	const filtered = (t: WindowTrace | null) => t?.stages.find((s) => s.stage_id.includes('ECG_FILTER')) ?? t?.stages[0];
	const overlapping = $derived(timeline?.segments.filter((s) => s.start_s < edge && s.end_s > left) ?? []);
	onMount(() => { void store.api.observatoryScenarios().then((v) => { scenarios = v; return loadTimeline(); }).catch((c) => { error = c instanceof Error ? c.message : String(c); }); });
</script>
<svelte:head><title>Scenario and fault lab | NHM</title></svelte:head>
<div class="eyebrow">NHM / RESEARCH OBSERVATORY / SCENARIO AND FAULT LAB</div>
<h1 tabindex="-1" use:focusHeading>Scenario and fault lab</h1>
<p class="lead">Existing deterministic simulated-wearable scenarios, shown in <b>simulated source time</b> (not wall-clock). Fault schedules come from the frozen scenario definitions; each selected window is reconstructed with the canonical operators. This does not show real-world hardware robustness.</p>
<label class="pick">Scenario <select bind:value={scenarioId} onchange={loadTimeline}>{#each scenarios as s (s.scenario_id)}<option value={s.scenario_id}>{s.scenario_id} · {s.duration_s} s</option>{/each}</select></label>
{#if error}<p role="alert" class="err">{error}</p>{/if}
{#if timeline}
<section aria-label="Source timeline" data-testid="fault-timeline"><h2>Source timeline · {timeline.duration_s} s of simulated time</h2>
	<div class="bar" role="list">{#each timeline.segments as seg (seg.name + seg.start_s)}<div role="listitem" class:fault={!!seg.ecg_fault} class:ctx={seg.context_mode !== 'VALID'} style={`flex:${seg.end_s - seg.start_s}`} title={`${seg.name} ${seg.start_s}–${seg.end_s} s`}><b>{seg.name}</b><small>{seg.start_s}–{seg.end_s} s</small>{#if seg.ecg_fault}<small>⚠ {seg.ecg_fault}</small>{/if}{#if seg.context_mode !== 'VALID'}<small>◇ {seg.context_mode}</small>{/if}</div>{/each}</div>
	<div class="track" aria-hidden="true"><i style={`left:${(left / timeline.duration_s) * 100}%;width:${((edge - left) / timeline.duration_s) * 100}%`}></i></div>
	<div class="scrub"><button onclick={() => step(-1)} disabled={windowIndex === 0}>← Previous window</button><label>Window {windowIndex + 1} of {timeline.window_right_edges_s.length} <input type="range" min="0" max={timeline.window_right_edges_s.length - 1} bind:value={windowIndex} onchange={loadWindow} /></label><button onclick={() => step(1)} disabled={windowIndex === timeline.window_right_edges_s.length - 1}>Next window →</button></div>
	<p class="dim">Selected window covers source seconds [{left}, {edge}) and advances in {timeline.window_cadence_s}-second steps. <span>Connection events defined for this scenario: {timeline.connection_events.join(' → ')}.</span></p>
	<ul class="ctx-list">{#each overlapping as seg (seg.name + seg.start_s)}<li>{seg.name}: {seg.ecg_fault ? FAULT_TEXT[seg.ecg_fault] ?? seg.ecg_fault : 'no ECG fault'} {CONTEXT_TEXT[seg.context_mode] ?? ''}</li>{/each}</ul>
</section>
{/if}
{#if loading}<p class="dim" role="status">Reconstructing the selected window with the canonical operators…</p>{/if}
{#if trace}
<section aria-label="Selected window" data-testid="lab-window"><h2>{trace.window_id} · quality <span class={`q q-${trace.quality_state.toLowerCase()}`}>{trace.quality_state}</span></h2>
	<p>Reasons: {trace.quality_reasons.length ? trace.quality_reasons.join(', ') : 'none emitted'} · missing source slots: {trace.missing_slots} · context {trace.context_available ? 'available' : 'not available for this window'}.</p>
	{#if trace.gaps.some((g) => g.kind === 'LONG')}<p class="teach">A long gap is not filled. The preprocessing state resets at the new segment, and windows spanning the missing interval are unusable.</p>{/if}
	{#if trace.gaps.some((g) => g.kind === 'SHORT')}<p class="teach">A short gap (≤ 100 ms) is filled causally with the last previously observed valid value; the window is DEGRADED rather than VALID.</p>{/if}
	<div class="charts">{#each trace.stages.slice(0, 3) as stage (stage.stage_id)}<SignalStageChart {stage} startUs={trace.left_timestamp_us} endUs={trace.right_timestamp_us} />{/each}</div>
	<p class="dim">{trace.classification === 'DETERMINISTIC_LOCAL_RECONSTRUCTION' ? 'DETERMINISTIC RECONSTRUCTION from the frozen scenario (not a captured historical trace).' : trace.classification} Quality is an engineering gate, not a diagnosis. <a href="/app/observatory">Full signal journey →</a></p></section>
{/if}
<section aria-label="Side by side" data-testid="lab-compare"><h2>Side-by-side window comparison</h2>
	<p class="warn">Different scenarios use different seeds, so this is a side-by-side view and <b>not</b> a controlled before/after experiment.</p>
	<div class="cmp-controls"><label>Compare with <select bind:value={compareId} onchange={loadCompare}><option value="">— choose a scenario —</option>{#each scenarios as s (s.scenario_id)}<option value={s.scenario_id}>{s.scenario_id}</option>{/each}</select></label><label>Window index <input type="number" min="0" max="200" bind:value={compareIndex} onchange={loadCompare} /></label></div>
	{#if compareError}<p role="alert" class="err">{compareError}</p>{/if}
	{#if trace && compareTrace}<div class="cmp"><article><h3>{trace.scenario_id} · window {trace.window_index}</h3><p>Quality {trace.quality_state}; reasons {trace.quality_reasons.join(', ') || 'none'}; gaps {trace.gaps.length}; context {trace.context_available ? 'available' : 'not available'}</p>{#if filtered(trace)}<SignalStageChart stage={filtered(trace)!} startUs={trace.left_timestamp_us} endUs={trace.right_timestamp_us} />{/if}</article>
		<article><h3>{compareTrace.scenario_id} · window {compareTrace.window_index}</h3><p>Quality {compareTrace.quality_state}; reasons {compareTrace.quality_reasons.join(', ') || 'none'}; gaps {compareTrace.gaps.length}; context {compareTrace.context_available ? 'available' : 'not available'}</p>{#if filtered(compareTrace)}<SignalStageChart stage={filtered(compareTrace)!} startUs={compareTrace.left_timestamp_us} endUs={compareTrace.right_timestamp_us} />{/if}</article></div>{/if}
</section>
<p class="dim"><a href="/app/observatory">← Observatory</a> · <a href="/app/observatory/federation">Federation participants (each has its own fault profile)</a></p>
<style>
	.eyebrow{color:#2bb8b0;font:10px 'JetBrains Mono',monospace;letter-spacing:.14em}h1{font:500 clamp(26px,4vw,40px) 'Space Grotesk',sans-serif;margin:8px 0}h2{font:500 18px 'Space Grotesk',sans-serif;margin:22px 0 8px}h3{font:500 14px 'JetBrains Mono',monospace;margin:0 0 6px}.lead{max-width:860px;color:#a7b8c9;line-height:1.6}.dim,small,li,p{color:#94a3b8;font-size:13px;line-height:1.6;overflow-wrap:anywhere}.err{color:#fecdd3}a{color:#2bb8b0}.warn{border-left:3px solid #fbbf24;padding:6px 12px;background:rgba(251,191,36,.06);color:#fde68a}.teach{border-left:3px solid #a78bfa;padding:6px 12px;color:#e9e3ff}
	.pick,.cmp-controls label,.scrub label{display:grid;gap:4px;font:10px 'JetBrains Mono',monospace;color:#71829a}select,input[type=number],button{background:#0a0f1f;color:#e2e8f0;border:1px solid rgba(148,163,184,.35);padding:6px 10px;min-height:32px;font:12px 'JetBrains Mono',monospace}button:disabled{opacity:.4}
	.bar{display:flex;gap:2px;min-height:64px}.bar div{border:1px solid rgba(148,163,184,.3);padding:6px 8px;display:grid;gap:2px;min-width:0;align-content:start;background:#0a0f1f}.bar b{font:600 11px 'JetBrains Mono',monospace;overflow-wrap:anywhere}.bar .fault{border-color:#f87171}.bar .ctx{border-color:#fbbf24}.track{position:relative;height:10px;background:rgba(148,163,184,.15);margin:6px 0}.track i{position:absolute;top:0;height:100%;background:rgba(167,139,250,.7)}
	.scrub{display:flex;flex-wrap:wrap;gap:10px;align-items:end}.scrub input{width:min(60vw,360px)}.ctx-list{padding-left:18px}.q{font:600 13px 'JetBrains Mono',monospace;padding:2px 8px;border:1px solid}.q-valid{color:#2bb8b0}.q-degraded{color:#fbbf24}.q-unusable{color:#f87171}.charts,.cmp{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,380px),1fr));gap:12px}.cmp article{border:1px solid rgba(148,163,184,.2);padding:10px 12px;min-width:0}.cmp-controls{display:flex;gap:12px;flex-wrap:wrap;margin:8px 0}
	@media (max-width: 760px) { .bar { flex-direction: column; } .bar div { flex: none !important; } }
	a{display:inline-block;min-height:24px;line-height:24px}
	h1:focus{outline:none}
</style>
