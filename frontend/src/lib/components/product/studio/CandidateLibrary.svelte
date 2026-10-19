<script lang="ts">
	import { displayCopy } from '$lib/product/display-copy';
	// The Studio candidate library: durable engineering candidates of the owner's completed runs. Each can be the starting model of a later run. Read-only here; nothing is promoted or deployed.
	import { onMount } from 'svelte';
	import { getProductStore } from '$lib/product/state.svelte';
	import { candidateChipText } from '$lib/product/studio/cohort-text';
	import { groupByTrainingCohort } from '$lib/product/studio/candidate-text';
	import type { StudioCandidate } from '$lib/product/studio/types';
	const product = getProductStore();
	let candidates = $state<StudioCandidate[] | null>(null);
	let error = $state<string | null>(null);
	onMount(() => { void product.api.studioCandidates().then((c) => { candidates = c; }).catch((cause) => { error = cause instanceof Error ? cause.message : String(cause); }); });
	const SOURCE: Record<StudioCandidate['source_kind'], string> = { SYNTHETIC_COHORT: 'Research cohort run', LIVE_MONITORED_SITE: 'Live-monitored logical site run', RECORDED_HARDWARE: 'Recorded-hardware run (pretrained-V2 family)', RESEARCH_FEDERATED_CHECKPOINT: 'Imported federated research checkpoint (real MIT-BIH patients)' };
	const metric = (c: StudioCandidate, key: string) => (c.metrics && typeof c.metrics[key] === 'number' ? c.metrics[key].toFixed(3) : '—');
	const when = (iso: string) => new Date(iso).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });
	const parent = (c: StudioCandidate) => (c.base_model.kind === 'CANDIDATE' ? `candidate ${String(c.base_model.model_id)}` : String(c.base_model.model_id ?? '—'));
	// Segregated by the cohort each candidate was TRAINED on (newest first within a group). Scores are only comparable between candidates scored on the SAME evaluation cohort, so the cohorts scored on are counted separately.
	const groups = $derived(groupByTrainingCohort(candidates ?? []));
	const evaluationCohorts = $derived(new Set((candidates ?? []).map((c) => c.evaluation_cohort_id ?? 'an unrecorded evaluation cohort')));
	/** This candidate, then what it was started from, as far as the library knows: `a ← b ← MODEL_V2_FINAL`. A parent that is no longer in the library is said so, never guessed. */
	function lineage(c: StudioCandidate): string {
		const known = new Map((candidates ?? []).map((x) => [x.candidate_id, x]));
		const chain = [c.candidate_id];
		let current = c;
		const seen = new Set(chain);
		while (current.base_model.kind === 'CANDIDATE') {
			const parentId = String(current.base_model.model_id);
			if (seen.has(parentId)) break;
			chain.push(parentId);
			seen.add(parentId);
			const next = known.get(parentId);
			if (!next) { chain.push('(not in this library)'); return chain.join(' ← '); }
			current = next;
		}
		chain.push(String(current.base_model.model_id ?? '—'));
		return chain.join(' ← ');
	}
</script>
<div class="lib" data-testid="candidate-library">
	{#if error}<p class="warn" role="alert">{error}</p>
	{:else if candidates === null}<p class="dim" role="status">Loading your candidate library…</p>
	{:else if candidates.length === 0}<p class="dim" data-testid="no-library-candidates">No stored candidates yet. Every completed Studio run (research cohort, monitored-site or recorded-hardware pretrained V2) keeps its final engineering candidate here.</p>
	{:else}
		{#if evaluationCohorts.size > 1}<p class="dim" role="note" data-testid="library-not-comparable"><b>Different evaluation cohorts.</b> These candidates were scored on {evaluationCohorts.size} different cohorts; their scores are not comparable with each other. Each card names the cohort it was scored on.</p>{/if}
		{#each groups as g (g.cohort)}
		<h3 class="group" data-testid="library-group" data-training-cohort={g.cohort}>{g.label}</h3>
		<ul class="cards" data-testid="library-candidates">
			{#each g.items as c (c.candidate_id)}
				<li data-candidate={c.candidate_id} data-cohort={c.cohort}>
					<div class="top"><b class="id">{c.candidate_id}</b><span class="chip" class:real={c.cohort === 'REALISTIC' || c.cohort === 'REALISTIC_NSTDB'} class:ecg={c.cohort === 'REAL_ECG'} data-testid="library-cohort">{candidateChipText(c.cohort)}</span></div>
					<p class="dim">{SOURCE[c.source_kind]} · {c.run_length} rounds · {c.algorithm}{c.secagg_mode === 'SECAGG_SHADOW' ? ' · SecAgg+ shadow' : ''} · {when(c.created_at)}</p>
					<dl>
						<div><dt>AUPRC</dt><dd>{metric(c, 'AUPRC')}</dd></div><div><dt>AUROC</dt><dd>{metric(c, 'AUROC')}</dd></div><div><dt>F1 @ 0.5</dt><dd>{metric(c, 'F1')}</dd></div>
						<div><dt>Started from</dt><dd>{parent(c)}</dd></div>
					</dl>
					<p class="dim">Scores are exploratory measurements on {c.evaluation_cohort_id ?? 'its evaluation cohort'} at round {c.round_id}; they are not a basis for choosing it. State <code>{c.state_sha256.slice(0, 16)}…</code> · source run <code>{c.source_run_id}</code></p>
					<p class="dim" data-testid="library-lineage">Lineage: {lineage(c)}</p>
					<p class="badge">{displayCopy(c.label)} · NOT DEPLOYED · NEVER USED FOR MONITORING</p>
				</li>
			{/each}
		</ul>
		{/each}
	{/if}
	<p class="dim">Stored candidates survive restarts and belong to the account that ran them. Choose one as the <b>starting model</b> of a research cohort, monitored-site or recorded-hardware run in the <a href="/app/federation">Federation Studio</a>. A candidate trained on one research cohort may start a run on the other; the run says so.</p>
	<p class="dim" data-testid="library-real-ecg-caution">Caution: in five repeated 10-round runs, adapting to the realistic research cohort lowered performance on real MIT-BIH validation ECG (mean AUROC −0.06, AUPRC −0.13 against the released model); on unseen real PTB-XL ECG the drop was larger (AUROC −0.04 to −0.05, AUPRC −0.17 to −0.23). A candidate is an engineering artefact, not a better ECG model.</p>
</div>
<style>
	.lib { display: grid; gap: 10px; min-width: 0; } .cards { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 10px; }
	.cards li { border: 1px solid rgba(148,163,184,.25); background: rgba(8,13,22,.5); padding: 12px; display: grid; gap: 8px; min-width: 0; } .top { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; justify-content: space-between; }
	.id { font: 600 12px 'JetBrains Mono', monospace; color: #9fe7e1; overflow-wrap: anywhere; } .chip { font: 10.5px 'JetBrains Mono', monospace; letter-spacing: .08em; border: 1px solid rgba(148,163,184,.4); padding: 2px 7px; color: #cbd5e1; } .chip.real { border-color: #a78bfa; color: #c4b5fd; } .chip.ecg { border-color: #fbbf24; color: #fcd34d; }
	dl { display: grid; grid-template-columns: repeat(auto-fit, minmax(90px, 1fr)); gap: 6px; margin: 0; } dl div { border: 1px solid rgba(148,163,184,.16); padding: 6px 8px; min-width: 0; } dt { color: #71829a; font: 10.5px 'JetBrains Mono', monospace; letter-spacing: .08em; } dd { margin: 3px 0 0; font-size: 13px; color: #e5f1f0; overflow-wrap: anywhere; }
	.group { margin: 4px 0 0; font: 600 12px 'JetBrains Mono', monospace; letter-spacing: .06em; color: #cbd5e1; overflow-wrap: anywhere; }
	.dim { margin: 0; color: #94a3b8; font-size: 12px; line-height: 1.5; overflow-wrap: anywhere; } .warn { margin: 0; color: #fbbf24; font: 11px 'JetBrains Mono', monospace; } .badge { margin: 0; color: #fbbf24; font: 10.5px/1.4 'JetBrains Mono', monospace; } code { color: #9fe7e1; overflow-wrap: anywhere; }
</style>
