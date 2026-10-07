<script lang="ts">
	// Global-state evolution from the REPORTED state digests: BEFORE -> 8 model updates -> AFTER. A different digest means the state changed;
	// it is NOT a performance claim and is not presented as one.
	import DigestText from './DigestText.svelte';
	import TechnicalEvidence from './TechnicalEvidence.svelte';
	import { stateTransitions } from '$lib/product/federation/presentation';
	import type { FederationView } from '$lib/product/federation/live-model';
	let { view, baseDigest = null }: { view: FederationView; baseDigest?: string | null } = $props();
	const items = $derived(stateTransitions(view, baseDigest));
</script>
<div class="mst" data-testid="model-state-evolution">
	{#if items.length === 0}<p class="dim">The global state appears here as soon as the first aggregation is reported.</p>{/if}
	{#each items as t (t.roundId)}
		<div class="r">
			<span class="rn">ROUND {t.roundId}</span>
			<div class="box before"><small>BEFORE ROUND</small><DigestText value={t.before} label={`round ${t.roundId} starting global state digest`} /></div>
			<div class="mid"><span aria-hidden="true">↓</span><b>{t.accepted} / {t.expected} model updates</b><span aria-hidden="true">↓</span></div>
			<div class={`box after${t.after ? ' done' : ''}`}><small>AFTER AGGREGATION</small>{#if t.after}<DigestText value={t.after} label={`round ${t.roundId} resulting global state digest`} />{:else}<span class="dim">not reported yet</span>{/if}</div>
			{#if t.after}<p class="ok">GLOBAL MODEL STATE UPDATED</p>{/if}
		</div>
	{/each}
	<p class="dim">The global model state changed after aggregation. Performance is not being evaluated on this live engineering screen.</p>
	<TechnicalEvidence label="VIEW TECHNICAL EVIDENCE (full digests)"><ul class="full">{#each items as t}<li>Round {t.roundId}: <code>{t.before ?? '--'}</code> → <code>{t.after ?? '--'}</code></li>{/each}</ul></TechnicalEvidence>
</div>
<style>
	.mst { display: grid; gap: 10px; min-width: 0; } .r { display: grid; gap: 4px; border: 1px solid rgba(167,139,250,.3); padding: 8px 10px; justify-items: start; } .rn { font: 10px 'JetBrains Mono', monospace; letter-spacing: .12em; color: #c4b5fd; }
	.box { border: 1px solid rgba(148,163,184,.25); padding: 5px 8px; display: grid; gap: 3px; min-width: 0; max-width: 100%; } .box small { font: 9px 'JetBrains Mono', monospace; letter-spacing: .1em; color: #71829a; } .after.done { border-color: rgba(167,139,250,.7); background: rgba(167,139,250,.08); }
	.mid { display: flex; gap: 8px; align-items: center; color: #94a3b8; font-size: 12px; } .mid b { font: 11px 'JetBrains Mono', monospace; } .ok { margin: 0; color: #c4b5fd; font: 11px 'JetBrains Mono', monospace; letter-spacing: .08em; } .dim { margin: 0; color: #94a3b8; font-size: 12px; line-height: 1.5; }
	.full { margin: 0; padding-left: 16px; display: grid; gap: 4px; } code { font: 10.5px 'JetBrains Mono', monospace; overflow-wrap: anywhere; }
</style>
