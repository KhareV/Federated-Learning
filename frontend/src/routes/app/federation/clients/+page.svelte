<script lang="ts">
	import { onMount } from 'svelte';
	import Panel from '$lib/components/dashboard/Panel.svelte';
	import FederationBanner from '$lib/components/product/federation/FederationBanner.svelte';
	import DigestText from '$lib/components/product/federation/DigestText.svelte';
	import { CLIENT_LABEL } from '$lib/product/federation/labels';
	import { useFederation } from '$lib/product/federation/state.svelte';
	const fed = useFederation();
	onMount(() => { void fed.loadClients(); });
</script>
<svelte:head><title>Federation clients | NHM</title></svelte:head>
<div class="head"><div class="eyebrow">NHM / FEDERATION / CLIENTS</div><h1>Logical local clients</h1></div>
<FederationBanner />
<p class="banner" role="note" data-testid="synthetic-banner">SYNTHETIC RESEARCH PARTITIONS — NOT HOSPITALS OR INSTITUTIONS.</p>
<Panel eyebrow="LOCALITY" title="What stays local">
	<p class="dim">Each client keeps its local training examples inside its logical client buffer. The federation coordinator receives model updates and metadata rather than those local training examples.</p>
	<p class="dim">All eight logical clients currently execute on one demonstration machine.</p>
</Panel>
<div class="gap"></div>
{#if fed.clientsPhase === 'PREPARING' || fed.clientsPhase === 'IDLE'}
	<p class="dim" role="status" data-testid="clients-preparing">PREPARING 8 SYNTHETIC LOCAL CLIENT DATASETS. This can take several seconds on first use.</p>
{:else if fed.clientsPhase === 'ERROR'}<p class="warn" role="alert">Clients could not be loaded: {fed.error}</p>
{:else}
	<ul class="cards" data-testid="client-cards">
		{#each fed.clients as c}
			<li data-client={c.client_id}><b>{c.client_id}</b>
				<dl><div><dt>Edge node</dt><dd>{c.edge_node_id}</dd></div><div><dt>Global round</dt><dd>{c.global_round}</dd></div><div><dt>Local examples</dt><dd>{c.local_example_count}</dd></div>
					<div><dt>Eligibility</dt><dd>{c.eligible ? 'ELIGIBLE' : `INELIGIBLE (${c.ineligible_reason})`}</dd></div><div><dt>State</dt><dd>{CLIENT_LABEL[c.client_state]}</dd></div><div><dt>Update digest</dt><dd><DigestText value={c.update_digest} label="update digest" /></dd></div></dl></li>
		{/each}
	</ul>
{/if}
<style>
	.eyebrow { color: #2bb8b0; font: 10px 'JetBrains Mono', monospace; letter-spacing: .14em; } h1 { margin: 10px 0 14px; font: 500 clamp(26px, 3.6vw, 38px) 'Space Grotesk', sans-serif; } .gap { height: 12px; }
	.banner { border: 1px solid rgba(251,191,36,.5); color: #fbbf24; padding: 8px 12px; font: 11px 'JetBrains Mono', monospace; letter-spacing: .08em; } .dim { color: #94a3b8; font-size: 13px; line-height: 1.6; } .warn { color: #fbbf24; font: 12px 'JetBrains Mono', monospace; }
	.cards { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 260px), 1fr)); gap: 8px; } li { border: 1px solid rgba(148,163,184,.16); padding: 10px 12px; min-width: 0; } b { font: 13px 'JetBrains Mono', monospace; }
	dl { display: grid; gap: 4px; margin: 8px 0 0; } dl div { display: flex; justify-content: space-between; gap: 8px; font-size: 12px; } dt { color: #71829a; } dd { margin: 0; font: 11px 'JetBrains Mono', monospace; text-align: right; overflow-wrap: anywhere; }
</style>
