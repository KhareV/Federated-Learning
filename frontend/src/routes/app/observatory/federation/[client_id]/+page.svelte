<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { getProductStore } from '$lib/product/state.svelte';
	import type { FlClientWindowTrace, FrozenClient } from '$lib/product/observatory/federation';
	import SignalStageChart from '$lib/components/product/observatory/SignalStageChart.svelte';
	const store = getProductStore();
	const id = page.params.client_id ?? '';
	let client = $state<FrozenClient | null>(null);
	let index = $state(0);
	let evidence = $state<FlClientWindowTrace | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let request = 0;
	const maximum = $derived(Math.max(0, (client?.windows_emitted ?? 1)-1));
	async function load() {
		const active = ++request; loading = true; error = null;
		try { const result = await store.api.observatoryFlClientWindow(id, index);
			if (active === request) evidence = result;
		} catch (cause) { if (active === request) { evidence = null; error = cause instanceof Error ? cause.message : String(cause); } }
		finally { if (active === request) loading = false; }
	}
	function move(delta: number) { index = Math.max(0, Math.min(maximum, index+delta)); void load(); }
	onMount(() => { void (async () => { try {
		const cohort = await store.api.observatoryCohort();
		client = cohort.clients.find((c) => c.client_id === id) ?? null;
		if (!client) throw new Error('Unknown frozen synthetic client');
		await load();
	} catch (cause) { error = cause instanceof Error ? cause.message : String(cause); loading = false; } })(); });
</script>
<svelte:head><title>{id} signal inspection | NHM</title></svelte:head>
<div class="eyebrow">NHM / OBSERVATORY / SYNTHETIC CLIENT SOURCE</div>
<h1>{id}: inspect one local window</h1>
<p class="lead">This is a deterministic read-only reconstruction of a synthetic FL client's <em>observed source</em> through the canonical streaming operators. The label is calculated by the existing client-local scheduled-event label adapter. No FL training or model inference occurs when you move the window.</p>
<a href="/app/observatory/federation">← All clients and round contributions</a>
{#if client}<div class="profile"><b>{client.participant_id}</b> · {client.scenario} · {client.windows_emitted} emitted windows · {client.trainable} trainable · {client.degraded} degraded · {client.unusable} unusable</div>
	<div class="stepper"><button aria-label="Previous client window" onclick={()=>move(-1)} disabled={loading||index===0}>←</button><input aria-label="Selected synthetic client window" type="range" min="0" max={maximum} step="1" bind:value={index} oninput={()=>void load()} disabled={loading} /><button aria-label="Next client window" onclick={()=>move(1)} disabled={loading||index===maximum}>→</button><output>W{String(index).padStart(4,'0')} / {maximum}</output></div>{/if}
{#if loading}<p role="status">Reconstructing this synthetic participant's selected window…</p>{/if}
{#if error}<p role="alert" class="error">{error}</p>{/if}
{#if evidence && !loading}
	<div class="summary"><article><span>ECG QUALITY</span><strong>{evidence.signal.quality_state}</strong><small>{evidence.signal.quality_reasons.join(', ') || 'No quality reason emitted'}</small></article><article><span>LOCAL TRAINING ELIGIBILITY</span><strong>{evidence.training_eligible ? 'ELIGIBLE' : 'EXCLUDED'}</strong><small>{evidence.signal.missing_slots} missing target slots</small></article><article><span>SYNTHETIC ENGINEERING LABEL</span><strong>{evidence.engineering_label === null ? 'NOT ASSIGNED' : evidence.engineering_label === 1 ? 'SCHEDULED EVENT POSITIVE' : 'NEGATIVE'}</strong><small>WEARABLE_SIM_EVENT_WINDOW_V1 · not AAMI-SVF</small></article></div>
	<div class="time">Window {evidence.signal.left_timestamp_us/1_000_000}–{evidence.signal.right_timestamp_us/1_000_000} s source time · 10 s signal interval [left,right) · 5 s cadence.</div>
	<div class="plots">{#each evidence.signal.stages as stage}<SignalStageChart {stage} startUs={evidence.signal.left_timestamp_us} endUs={evidence.signal.right_timestamp_us} />{/each}</div>
	<section class="explain"><h2>Why this window has this status</h2><p>Quality: {evidence.signal.quality_state}. {evidence.signal.quality_reasons.length ? evidence.signal.quality_reasons.join(', ') : 'No quality reason emitted.'} A training example requires a VALID, complete, finite ECG window. A degraded or unusable source window cannot silently enter the local training buffer.</p><p>{#if evidence.training_eligible}The existing synthetic event-label adapter assigns {evidence.engineering_label} because of its scheduled-event rule on [t−10 s,t].{:else}No synthetic training label is assigned to this excluded window.{/if} These labels are not patient annotations or diagnoses.</p></section>
	<details><summary>TECHNICAL EVIDENCE & SOURCE BOUNDARY</summary><p>Client {evidence.client_id}; participant {evidence.participant_id}; source session {evidence.signal.session_id}; cohort manifest SHA256 <code>{evidence.cohort_manifest_sha256}</code>.</p><p>Trace: {evidence.signal.trace_version} · {evidence.signal.classification}. Label: {evidence.label_contract}. Claim: {evidence.claim_boundary}.</p><p>Displayed points are decimated, but the reconstruction used the canonical source and processing arrays. This separate authenticated inspection response transfers bounded synthetic signal values; normal FL update envelopes do not transfer raw ECG training examples.</p></details>
{/if}
<style>
	.eyebrow,.summary span{color:#2bb8b0;font:10px 'JetBrains Mono',monospace;letter-spacing:.13em}h1{font:500 clamp(27px,4vw,40px) 'Space Grotesk',sans-serif;margin:8px 0}.lead{max-width:850px;color:#a7b8c9;line-height:1.6}a{color:#2bb8b0}.profile,.time{border:1px solid #334155;background:#071421;padding:12px;color:#b9cad7;font-size:13px;margin:16px 0}.stepper{display:flex;gap:10px;align-items:center;border:1px solid #334155;padding:12px}.stepper input{flex:1;min-width:30px}.stepper button{background:#0b262b;border:1px solid #2bb8b0;color:#e5f1f0;min-width:34px;min-height:34px;cursor:pointer}.stepper button:disabled{opacity:.4}.stepper output{font:11px 'JetBrains Mono',monospace;color:#b9cad7;white-space:nowrap}.summary{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px;margin:15px 0}.summary article{display:grid;gap:7px;border:1px solid #334155;padding:14px;min-width:0}.summary strong{font:500 17px 'Space Grotesk',sans-serif;overflow-wrap:anywhere}.summary small{color:#94a3b8;line-height:1.5}.plots{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.explain,details{border:1px solid #334155;padding:15px;margin:17px 0;background:#071421;color:#b9cad7;line-height:1.6}.explain h2{margin:0 0 7px;font:500 20px 'Space Grotesk',sans-serif}.explain p,details p{font-size:13px}summary{color:#2bb8b0;cursor:pointer;font:11px 'JetBrains Mono',monospace}code{overflow-wrap:anywhere}.error{color:#f87171}button:focus-visible,input:focus-visible,a:focus-visible,summary:focus-visible{outline:2px solid #fbbf24;outline-offset:2px}@media(max-width:750px){.summary,.plots{grid-template-columns:1fr}}@media(max-width:450px){.stepper{flex-wrap:wrap}.stepper input{order:2;flex-basis:100%}.stepper output{order:3}}
</style>
