<script lang="ts">
	// Final engineering candidate of a 10-round run (not registered, promoted or deployed). The 3-round candidate lifecycle keeps its original component.
	import DigestText from '$lib/components/product/federation/DigestText.svelte';
	import type { StudioRun } from '$lib/product/studio/types';
	let { run }: { run: StudioRun } = $props();
	const c = $derived(run.candidate);
</script>
<div class="cs" data-testid="candidate-summary">
	{#if c}
		<div class="id"><span>CANDIDATE</span><b data-testid="candidate-id">{c.candidate_id}</b></div>
		<p>Final global state R{run.planned_rounds}: {#if c.state_sha256}<DigestText value={c.state_sha256} label="candidate state digest" />{/if}</p>
		<p class="badge" data-testid="candidate-label">{c.label ?? 'ENGINEERING CANDIDATE - NOT PROMOTED - NOT CLINICAL'}</p>
		<ul><li>Promoted: <b>NO</b></li><li>Deployed: <b>NO</b></li><li>Registered in the product model registry: <b>NO</b></li><li>Calibration applied: <b>NONE</b></li><li>Released monitoring model changed: <b>NO</b></li></ul>
		<p class="dim">The candidate is the committed output of round {run.planned_rounds}. It was not chosen by any evaluation result; its scores are exploratory measurements on a reused synthetic cohort.</p>
	{:else}<p class="dim" role="status">{run.status === 'FAILED' ? 'The run failed: there is no candidate. An interrupted run never produces one.' : 'The final candidate is created only when the last round commits.'}</p>{/if}
</div>
<style>
	.cs { display: grid; grid-template-columns: minmax(0, 1fr); gap: 8px; } .id { display: grid; gap: 2px; } .id span { font: 10px 'JetBrains Mono', monospace; letter-spacing: .12em; color: #71829a; } .id b { font: 600 13px 'JetBrains Mono', monospace; color: #fde68a; overflow-wrap: anywhere; } p { margin: 0; font-size: 12.5px; color: #cbd5e1; line-height: 1.5; } .badge { border: 1px solid rgba(251,191,36,.6); background: rgba(251,191,36,.07); padding: 5px 9px; font: 600 11px 'JetBrains Mono', monospace; color: #fde68a; width: fit-content; max-width: 100%; } ul { margin: 0; padding-left: 18px; font-size: 12px; color: #cbd5e1; display: grid; gap: 2px; } .dim { color: #94a3b8; font-size: 12px; }
	p, li { overflow-wrap: anywhere; }
</style>
