<script lang="ts">
	import { focusHeading } from '$lib/product/observatory/focus';
	import { onMount } from 'svelte';
	import { getProductStore } from '$lib/product/state.svelte';
	import type { ShowcaseBundle } from '$lib/product/observatory/showcase';
	const store = getProductStore();
	let bundle = $state<ShowcaseBundle | null>(null);
	let error = $state<string | null>(null);
	let step = $state(0);
	const fmt = (v: number | null | undefined, d = 4) => (v === null || v === undefined ? 'UNDEFINED' : v.toFixed(d));
	const syn = $derived(bundle?.synthetic ?? null);
	const final = $derived(syn?.states['round_3_candidate'] ?? null);
	const sci = $derived(bundle?.comparability.rows.find((r) => r.dataset === 'INCART') ?? null);
	// lane: A monitoring, B scientific FL, C synthetic engineering FL, H historical reference
	const STEPS = $derived([
		{ lane: 'A', title: 'Monitoring', body: 'A simulated wearable session streams ECG records through the monitoring runtime. MODEL_V2_FINAL with CAL_V2 classifies windows server-side. This is lane A and is never used as FL evidence.' },
		{ lane: 'C', title: 'SITE_00 eligible windows', body: 'In the product federation the eight logical clients each hold windows that pass the trainable rule (VALID, 2500 samples, no missing slots). SITE_00 is one of the eight. Its labels are synthetic engineering events (WEARABLE_SIM_EVENT_WINDOW_V1).' },
		{ lane: 'C', title: 'Local batches', body: 'Each client runs one local epoch of AdamW (learning rate 0.001, batch 64) on its own windows. Raw windows never leave the client.' },
		{ lane: 'C', title: 'Eight updates', body: 'Eight model updates (digests, example counts) cross the boundary per round; stale, duplicate, wrong-base and unknown-client submissions are rejected by the coordinator.' },
		{ lane: 'C', title: 'Weighted FedAvg', body: 'The coordinator averages the accepted updates weighted by example counts and commits a new global state, in canonical order so arrival order does not matter.' },
		{ lane: 'C', title: 'Global state', body: syn ? `Three rounds yield the sandbox candidate ${syn.candidate_digest.slice(0, 16)}…, not deployed and not promoted.` : 'Three rounds yield the sandbox candidate.' },
		{ lane: 'C', title: 'Measured synthetic metrics', body: final ? `On an independent synthetic holdout (${syn?.holdout_windows} windows, 8 unseen participants) the round-3 candidate has AUPRC ${fmt(final.pooled.AUPRC)} and AUROC ${fmt(final.pooled.AUROC)}; at the fixed 0.5 threshold specificity is ${fmt(final.pooled.specificity)} and recall ${fmt(final.pooled.recall)}. Reported as measured.` : 'Synthetic evaluation not available.' },
		{ lane: 'B', title: 'Frozen scientific outcomes', body: sci ? `Separately, the frozen scientific FL experiments (real ECG partitions) give federated V2 FedAvg IID AUPRC ${fmt(sci.federated_V2_FedAvg_IID_AUPRC, 6)} on INCART against a historical centralized reference of ${fmt(sci.centralized_V2_AUPRC, 6)}. Descriptive only; no paired interval.` : 'Frozen scientific outcomes unavailable.' }
	]);
	const LANE: Record<string, string> = { A: 'A · MODEL_V2_FINAL + CAL_V2 monitoring', B: 'B · Scientific FL (AAMI_SVF_WINDOW_V1)', C: 'C · Synthetic engineering FL (WEARABLE_SIM_EVENT_WINDOW_V1)', H: 'H · Historical centralized reference' };
	onMount(() => { void store.api.observatoryShowcase().then((v) => { bundle = v; }).catch((c) => { error = c instanceof Error ? c.message : String(c); }); });
</script>
<svelte:head><title>FL storyboard | NHM</title></svelte:head>
<div class="eyebrow">NHM / RESEARCH OBSERVATORY / STORYBOARD</div>
<h1 tabindex="-1" use:focusHeading>Federated learning storyboard</h1>
<p class="lead">One path from monitoring to measured outcomes. Every number comes from committed evidence through the backend; the four lanes are never mixed.</p>
{#if error}<p role="alert" class="err">Storyboard unavailable: {error}</p>{:else if !bundle}<p class="dim" role="status">Loading…</p>{:else}
<ol class="rail" aria-label="Storyboard steps">{#each STEPS as s, i (s.title)}<li><button class:on={step===i} aria-current={step===i ? 'step' : undefined} onclick={() => (step = i)}><span>{i + 1}</span>{s.title}</button></li>{/each}</ol>
<article class="card" data-testid="storyboard-step" aria-live="polite">
	<span class={`lane l${STEPS[step].lane}`} data-testid="lane-label">{LANE[STEPS[step].lane]}</span>
	<h2>{step + 1}. {STEPS[step].title}</h2><p>{STEPS[step].body}</p>
	{#if STEPS[step].lane === 'C' && step >= 6}<p class="syn">{syn?.boundary_label}</p>{/if}
	<div class="nav"><button disabled={step===0} onclick={() => (step -= 1)}>← Previous</button><button disabled={step===STEPS.length - 1} onclick={() => (step += 1)}>Next →</button></div>
</article>
<ul class="lanes">{#each Object.entries(LANE) as [k, v]}<li><b>{k}</b> {v}</li>{/each}</ul>
<p class="dim"><a href="/app/observatory/outcomes">Scientific outcomes</a> · <a href="/app/observatory/federation">Federation contributions</a> · <a href="/app/observatory">Observatory</a></p>
{/if}
<style>
	.eyebrow{color:#2bb8b0;font:10px 'JetBrains Mono',monospace;letter-spacing:.14em}h1{font:500 clamp(28px,4vw,42px) 'Space Grotesk',sans-serif;margin:8px 0}h2{font:500 20px 'Space Grotesk',sans-serif;margin:10px 0}.lead,.card p{max-width:820px;color:#a7b8c9;line-height:1.6;overflow-wrap:anywhere}.dim,li{color:#94a3b8;font-size:13px}.err{color:#fecdd3}a{color:#2bb8b0;display:inline-block;min-height:24px;line-height:24px}
	.rail{display:flex;flex-wrap:wrap;gap:6px;list-style:none;padding:0}.rail button,.nav button{background:#0a0f1f;color:#e2e8f0;border:1px solid rgba(148,163,184,.35);padding:6px 10px;min-height:32px;font:12px 'JetBrains Mono',monospace}.rail button.on{border-color:#2bb8b0;color:#9fe8e3}.rail span{color:#71829a;margin-right:6px}
	.card{border:1px solid rgba(148,163,184,.25);padding:16px 18px;margin:12px 0}.lane{font:10px 'JetBrains Mono',monospace;border:1px solid;padding:3px 8px}.lA{color:#7dd3fc}.lB{color:#86efac}.lC{color:#d8ccff}.lH{color:#fde68a}.syn{display:inline-block;border:1px solid rgba(167,139,250,.6);padding:5px 10px;color:#d8ccff;font:11px 'JetBrains Mono',monospace}.nav{display:flex;gap:8px;margin-top:10px}.lanes{padding-left:18px;font-size:12px}h1:focus{outline:none}
</style>
