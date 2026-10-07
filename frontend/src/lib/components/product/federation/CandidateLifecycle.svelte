<script lang="ts">
	// Candidate lifecycle from the REPORTED candidate/run state. Scientific validation and deployment are shown as NOT done - they never happen here.
	import TechnicalEvidence from './TechnicalEvidence.svelte';
	import DigestText from './DigestText.svelte';
	import type { FederationView } from '$lib/product/federation/live-model';
	let { view, replay = false }: { view: FederationView; replay?: boolean } = $props();
	const cand = $derived(view.candidate);
	const trained = $derived(view.runStatus === 'COMPLETED' || cand !== null);
	const checks = $derived(cand?.validation === 'PASSED');
	const sandbox = $derived(cand?.governance === 'ACCEPTED_TO_SANDBOX' && cand?.sandbox === 'IN_SANDBOX');
	const steps = $derived([
		{ id: 'train', label: 'Training complete', done: trained, note: '' },
		{ id: 'cand', label: replay ? 'Candidate event replayed' : 'Candidate created', done: cand !== null, note: '' },
		{ id: 'checks', label: 'Structural checks', done: checks, note: '' },
		{ id: 'sandbox', label: 'Engineering sandbox', done: sandbox, note: '' },
		{ id: 'sci', label: 'Scientific validation', done: false, note: 'not performed here' },
		{ id: 'dep', label: 'Deployment', done: false, note: 'never automatic' }
	]);
</script>
<div class="cl" data-testid="candidate-lifecycle">
	<ol class="steps">{#each steps as s (s.id)}<li class={s.done ? 'on' : s.id === 'sci' || s.id === 'dep' ? 'na' : ''} data-step={s.id}><span class="m" aria-hidden="true">{s.done ? '✓' : '—'}</span><span class="l">{s.label}</span>{#if s.note}<small>{s.note}</small>{/if}</li>{/each}</ol>
	<p class="big" data-testid="not-deployed">NOT DEPLOYED</p>
	{#if replay && cand}<p class="rp" data-testid="historical-candidate">HISTORICAL EVENT REPLAY — NO NEW CANDIDATE CREATED.</p>{/if}
	{#if cand}
		{#if cand.governance === 'ACCEPTED_TO_SANDBOX'}<p class="ok">ACCEPTED TO ENGINEERING SANDBOX REGISTRY · NOT A SCIENTIFIC RELEASE · NOT DEPLOYED</p>{:else if cand.governance === 'REJECTED'}<p class="err">REJECTED BY ENGINEERING GOVERNANCE · NOT IN SANDBOX · NOT DEPLOYED</p>{/if}
		<TechnicalEvidence label="TECHNICAL EVIDENCE (candidate metadata)" testid="candidate-evidence">
			<dl data-testid="candidate-live"><div><dt>Candidate</dt><dd>{cand.candidateId}</dd></div><div><dt>Parent</dt><dd>{cand.parentModelId}</dd></div><div><dt>State digest</dt><dd><DigestText value={cand.stateDigest} label="candidate digest" /></dd></div>
				<div><dt>Validation</dt><dd>{cand.validation ?? 'PENDING'}</dd></div><div><dt>Checks reported passed</dt><dd>{cand.checksPassed.length ? cand.checksPassed.join(', ') : '--'}</dd></div>
				<div><dt>Governance</dt><dd>{cand.governance ?? '--'}</dd></div><div><dt>Sandbox</dt><dd>{cand.sandbox ?? '--'}</dd></div><div><dt>production_deployed</dt><dd>FALSE</dd></div></dl>
		</TechnicalEvidence>
	{:else}<p class="dim">No candidate event yet. A candidate appears only after the final round.</p>{/if}
</div>
<style>
	.cl { display: grid; gap: 10px; min-width: 0; } .steps { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 118px), 1fr)); gap: 6px; } li { border: 1px solid rgba(148,163,184,.2); padding: 7px 8px; display: grid; gap: 2px; color: #71829a; min-width: 0; } li.on { border-color: rgba(251,191,36,.55); color: #fcd34d; background: rgba(251,191,36,.06); } li.na { border-style: dashed; }
	.m { font: 13px 'JetBrains Mono', monospace; } .l { font-size: 12px; line-height: 1.35; } small { font-size: 10px; color: #71829a; } .big { margin: 0; align-self: start; display: inline-block; width: fit-content; border: 1px solid rgba(251,191,36,.7); color: #fbbf24; padding: 5px 12px; font: 600 14px 'JetBrains Mono', monospace; letter-spacing: .14em; }
	.ok { margin: 0; color: #fcd34d; font: 11px 'JetBrains Mono', monospace; line-height: 1.5; } .err { margin: 0; color: #f87171; font: 11px 'JetBrains Mono', monospace; } .rp { margin: 0; border: 1px solid rgba(148,163,184,.5); color: #cbd5e1; padding: 6px 10px; font: 11px 'JetBrains Mono', monospace; } .dim { margin: 0; color: #94a3b8; font-size: 12.5px; line-height: 1.5; }
	dl { display: grid; gap: 4px; margin: 0; } dl div { display: flex; justify-content: space-between; gap: 8px; font-size: 12px; } dt { color: #71829a; } dd { margin: 0; font: 11px 'JetBrains Mono', monospace; text-align: right; overflow-wrap: anywhere; }
</style>
