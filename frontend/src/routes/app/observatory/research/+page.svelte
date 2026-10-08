<script lang="ts">
	import { onMount } from 'svelte';
	import { getProductStore } from '$lib/product/state.svelte';
	import SignalStageChart from '$lib/components/product/observatory/SignalStageChart.svelte';
	import type { DatasetPreprocessing } from '$lib/product/observatory/evidence';
	import type { ResearchRecord, ResearchWindow } from '$lib/product/observatory/research';
	const store = getProductStore();
	let records = $state<ResearchRecord[]>([]);
	let prep = $state<DatasetPreprocessing | null>(null);
	let prepError = $state<string | null>(null);
	let selected = $state('101');
	let windowIndex = $state(0);
	let window = $state<ResearchWindow | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let requestNumber = 0;
	const active = $derived(records.find((record) => record.record_id === selected));
	async function loadWindow() {
		const request = ++requestNumber;
		loading = true; error = null;
		try {
			const result = await store.api.observatoryResearchWindow(selected, windowIndex);
			if (request === requestNumber) window = result;
		} catch (cause) {
			if (request === requestNumber) {
				window = null;
				error = cause instanceof Error ? cause.message : String(cause);
			}
		} finally { if (request === requestNumber) loading = false; }
	}
	function chooseRecord(event: Event) {
		selected = (event.currentTarget as HTMLSelectElement).value;
		windowIndex = 0;
		void loadWindow();
	}
	function chooseWindow(event: Event) {
		windowIndex = Number((event.currentTarget as HTMLInputElement).value);
		void loadWindow();
	}
	onMount(() => {
		void store.api.observatoryDatasetPreprocessing().then((v) => { prep = v; }).catch((c) => { prepError = c instanceof Error ? c.message : String(c); }); void (async () => {
		try {
			records = await store.api.observatoryResearchRecords();
			if (!records.some((record) => record.record_id === selected)) selected = records[0]?.record_id ?? '';
			if (selected) await loadWindow();
			else { loading = false; error = 'No authorized processed TRAIN records are available.'; }
		} catch (cause) { loading = false; error = cause instanceof Error ? cause.message : String(cause); }
	})(); });
</script>
<svelte:head><title>Research-record inspection | NHM</title></svelte:head>
<div class="eyebrow">NHM / RESEARCH OBSERVATORY / SCIENTIFIC RECORD</div>
<h1>Inspect an authorized research window</h1>
<p class="lead">This is an actual frozen, processed MIT-BIH <b>TRAIN</b> ECG window, not the signed-in user's signal. It is a different data source and target from the eight synthetic federation clients. No held-out inference or new scientific metric runs when you inspect it.</p>
<p><a href="/app/observatory">← Synthetic signal journey</a> · <a href="/app/research/ml">Frozen ML evidence →</a></p>
<div class="boundary"><b>Access boundary</b><p>Only hash-verified MIT-BIH TRAIN caches are served. INTERNAL_TEST, calibration, validation, and INCART waveforms are not exposed by this inspector. The raw WFDB recordings and beat-position files are not present locally; exact annotation symbols and positions cannot be plotted here.</p></div>
<div class="controls"><label>MIT-BIH TRAIN RECORD<select value={selected} onchange={chooseRecord} disabled={!records.length}>{#each records as item}<option value={item.record_id}>Record {item.record_id} · {item.eligible_window_count} eligible windows</option>{/each}</select></label>
	{#if active}<label>ELIGIBLE WINDOW {windowIndex + 1} / {active.eligible_window_count}<input type="range" min="0" max={active.eligible_window_count - 1} value={windowIndex} oninput={chooseWindow} /></label>{/if}</div>
{#if loading}<p role="status">Loading hash-verified processed TRAIN window…</p>{/if}
{#if error}<p class="error" role="alert">{error}</p>{/if}
{#if window}<section><div class="facts"><div><span>DATASET / SPLIT</span><strong>MIT-BIH · TRAIN</strong><small>{window.record.participant_group_id}</small></div><div><span>SCIENTIFIC TARGET</span><strong>{window.label_contract}</strong><small>{window.label_status} · label {window.label}</small></div><div><span>PREPROCESSING</span><strong>{window.stage.stage_id}</strong><small>250 Hz · 2,500 samples · 10 s</small></div></div>
	<SignalStageChart stage={window.stage} startUs={window.left_timestamp_us} endUs={window.right_timestamp_us} />
	<p class="notice">The ECG signal occupies [{window.left_timestamp_us / 1_000_000}s, {window.right_timestamp_us / 1_000_000}s). The separately frozen beat-annotation decision includes the right endpoint. Overlapping windows are not independent patient observations.</p>
	<section class="counts"><h2>Frozen label decision evidence</h2><p>The committed manifest records mapped-beat counts, not the raw symbol positions. N: {window.mapped_n_count}; S: {window.mapped_s_count}; V: {window.mapped_v_count}; F: {window.mapped_f_count}; Q: {window.q_count}; unmappable: {window.unmappable_count}.</p><p>Exact raw annotation symbols and locations: <b>UNAVAILABLE — RAW WFDB FILES NOT PRESENT</b>.</p></section>
	<details><summary>TECHNICAL PROVENANCE</summary><p>Example ID <code>{window.example_id}</code></p><p>Cache SHA256 <code>{window.cache_file_sha256}</code></p><p>Example IDs SHA256 <code>{window.example_ids_file_sha256}</code></p><p>Window manifest SHA256 <code>{window.window_manifest_sha256}</code></p><p>Split manifest SHA256 <code>{window.split_manifest_sha256}</code></p><p>{window.claim_boundary}</p></details>
</section>{/if}

<section class="prep" aria-label="Dataset preprocessing paths" data-testid="dataset-preprocessing"><h2>Two datasets, two locked resampling paths</h2>
	{#if prepError}<p role="alert">{prepError}</p>{:else if !prep}<p role="status">Loading…</p>{:else}
	<div class="prepgrid">{#each prep.datasets as d (d.dataset)}<article><h3>{d.dataset}</h3><p>Native {d.native_rate_hz} Hz → {d.target_rate_hz} Hz with <code>{d.resampler_id}</code> (up {d.up} / down {d.down}, {d.taps} taps, group delay {d.group_delay_seconds} s). INCART does not use the MIT-BIH conversion path.</p>
		<p>Locked role: {d.role}. Training allowed: {d.allowed_for_training}. {d.access_rule}</p>
		<p class="demo">Causality check on the real resampler (synthetic test signal, not research data): after altering source samples from index {d.causality.altered_from_source_sample}, the first changed output was #{d.causality.first_output_index_that_changed}; all earlier outputs identical: {d.causality.outputs_before_alteration_identical ? 'yes' : 'NO'}.</p></article>{/each}</div>
	<p>Windows: signal samples occupy [t−10 s, t); scientific annotations use the separately frozen closed interval [t−10 s, t]. Annotation time mapping: {prep.annotation_time_mapping}.</p>
	<ul>{#each prep.label_contracts as l (l.id)}<li><b>{l.id}</b> ({l.kind}): {l.rule}</li>{/each}</ul>
	<p class="note">{prep.raw_recordings}</p>{/if}</section>
<style>
	.eyebrow,.facts span{color:#2bb8b0;font:10px 'JetBrains Mono',monospace;letter-spacing:.13em}h1{font:500 clamp(28px,4vw,42px) 'Space Grotesk',sans-serif;margin:8px 0}.lead,.notice,.boundary p,.counts p{color:#a7b8c9;line-height:1.6;max-width:920px}.lead b{color:#fbbf24}a{color:#2bb8b0}.boundary{border:1px solid #805e2b;background:#1b1711;padding:16px;margin:20px 0}.boundary b{color:#fbbf24}.boundary p{margin:7px 0 0}.controls{display:flex;gap:20px;flex-wrap:wrap;margin:20px 0}.controls label{display:grid;gap:8px;color:#94a3b8;font:11px 'JetBrains Mono',monospace;min-width:min(100%,280px)}select,input{min-height:38px;max-width:100%;background:#071421;color:#e5f1f0;border:1px solid #475569;padding:7px}input{accent-color:#2bb8b0}.facts{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:18px 0}.facts div{display:grid;gap:7px;padding:14px;border:1px solid #334155;background:#071421;min-width:0}.facts strong{font-size:15px;overflow-wrap:anywhere}.facts small{color:#94a3b8}.counts{border:1px solid #334155;padding:16px;margin:15px 0}.counts h2{font:500 18px 'Space Grotesk',sans-serif;margin:0}details{border:1px solid #334155;padding:12px;color:#a7b8c9}summary{color:#2bb8b0;cursor:pointer}code{overflow-wrap:anywhere}.error{color:#f87171}a:focus-visible,summary:focus-visible,select:focus-visible,input:focus-visible{outline:2px solid #fbbf24;outline-offset:2px}@media(max-width:700px){.facts{grid-template-columns:1fr}.controls{display:grid}}
.prepgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr));gap:10px}.prep article{border:1px solid rgba(148,163,184,.25);padding:10px 12px;min-width:0}.prep p,.prep li{color:#a7b8c9;font-size:13px;line-height:1.6;overflow-wrap:anywhere}.prep .demo{color:#e9e3ff;border-left:3px solid #a78bfa;padding-left:8px}.prep .note{border-left:3px solid #fbbf24;padding-left:8px;color:#fde68a}
	a{display:inline-block;min-height:24px;line-height:24px}summary{min-height:24px}
</style>
