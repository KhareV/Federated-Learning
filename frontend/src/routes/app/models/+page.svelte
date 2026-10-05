<script lang="ts">
	import { onMount } from 'svelte';
	import Panel from '$lib/components/dashboard/Panel.svelte';
	import FederationBanner from '$lib/components/product/federation/FederationBanner.svelte';
	import CandidateCard from '$lib/components/product/federation/CandidateCard.svelte';
	import { useFederation } from '$lib/product/federation/state.svelte';
	const fed = useFederation();
	onMount(() => { void fed.loadModels(); });
</script>
<svelte:head><title>Models | NHM</title></svelte:head>
<div class="head"><div class="eyebrow">NHM / MODELS</div><h1>Model registry</h1></div>
<FederationBanner />
{#if fed.error}<p class="warn" role="alert">{fed.error}</p>{/if}
<div class="two">
	<Panel eyebrow="NAMESPACE 1" title="RELEASED SCIENTIFIC" note="FROZEN">
		{#if fed.registry}
			<ul class="rel" data-testid="released-models">{#each fed.registry.released_scientific as m}<li data-model={m.model_id}><b>{m.model_id}</b><span>role: {m.role}</span></li>{/each}</ul>
			<p class="dim">The released default is <b>{fed.registry.released_default_model_id}</b>. Federation never changes it.</p>
		{:else}<p class="dim">Loading…</p>{/if}
	</Panel>
	<Panel eyebrow="NAMESPACE 2" title="ENGINEERING FEDERATED CANDIDATES" note="SANDBOX REGISTRY">
		{#if !fed.registry}<p class="dim">Loading…</p>
		{:else if fed.candidates.length === 0}<p class="dim" data-testid="no-candidates">No engineering candidates yet.</p>
		{:else}<div class="cands" data-testid="candidates">{#each fed.candidates as c}<CandidateCard candidate={c} />{/each}</div>{/if}
		<p class="dim">Candidates are engineering sandbox entries. They are never used for live monitoring and no candidate inference runtime is enabled.</p>
	</Panel>
</div>
<style>
	.eyebrow { color: #2bb8b0; font: 10px 'JetBrains Mono', monospace; letter-spacing: .14em; } h1 { margin: 10px 0 14px; font: 500 clamp(26px, 3.6vw, 38px) 'Space Grotesk', sans-serif; } .two { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 340px), 1fr)); gap: 12px; align-items: start; }
	.rel { list-style: none; margin: 0 0 10px; padding: 0; display: grid; gap: 6px; } .rel li { display: flex; justify-content: space-between; gap: 8px; border: 1px solid rgba(148,163,184,.16); padding: 8px 10px; font: 12px 'JetBrains Mono', monospace; } .cands { display: grid; gap: 10px; }
	.dim { color: #94a3b8; font-size: 13px; line-height: 1.6; } .warn { color: #fbbf24; font: 12px 'JetBrains Mono', monospace; }
</style>
