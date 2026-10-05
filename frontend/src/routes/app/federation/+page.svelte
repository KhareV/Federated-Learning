<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import Panel from '$lib/components/dashboard/Panel.svelte';
	import MetricTile from '$lib/components/dashboard/MetricTile.svelte';
	import FederationBanner from '$lib/components/product/federation/FederationBanner.svelte';
	import ArchitectureLanes from '$lib/components/product/federation/ArchitectureLanes.svelte';
	import RunConfigForm from '$lib/components/product/federation/RunConfigForm.svelte';
	import RunList from '$lib/components/product/federation/RunList.svelte';
	import { FederationStore, REPLAY_NO_SOURCE, useFederation } from '$lib/product/federation/state.svelte';
	import { getProductStore } from '$lib/product/state.svelte';
	import type { FederationRunChoice } from '$lib/product/api';

	const fed = useFederation();
	const product = getProductStore();
	const enabled = $derived(FederationStore.backendEnabled(product.authState.system?.federation_runtime));
	onMount(() => {
		if (!enabled) return;
		void fed.loadOverview(); void fed.loadRuns(); void fed.loadModels();
		void fed.loadClients(); // independent and slow on first use: never blocks the page
	});
	async function start(choice: FederationRunChoice) {
		const run = await fed.createAndStart(choice);
		if (run) await goto(`/app/federation/live?run=${encodeURIComponent(run.run_id)}`);
	}
</script>
<svelte:head><title>Federation | NHM</title></svelte:head>
<div class="head"><div class="eyebrow">NHM / FEDERATION</div><h1>Federated development</h1>
	<p>The federation run executes on the product backend; this dashboard is an observer. Every value below is read from the backend.</p></div>
<FederationBanner />
{#if !enabled}
	<p class="warn" role="alert" data-testid="backend-not-enabled">FEDERATION BACKEND NOT ENABLED</p>
{:else}
<div class="tiles">
	<MetricTile label="Federation runtime" value={fed.overview?.federation_runtime ?? '--'} detail="ENGINEERING ONLY" tone="cyan" />
	<MetricTile label="Logical clients" value={fed.overview ? String(fed.overview.client_count) : '--'} detail={fed.overview?.cohort_id ?? '--'} />
	<MetricTile label="Active LIVE run" value={fed.overview ? (fed.overview.active_live_run ? 'YES' : 'NO') : '--'} detail="ONE AT A TIME (ONE-LAPTOP DEMO)" tone="amber" />
	<MetricTile label="Engineering candidates" value={fed.overview ? String(fed.overview.candidate_count) : '--'} detail="SANDBOX REGISTRY ONLY" />
	<MetricTile label="Released monitoring model" value={fed.overview?.released_model_id ?? '--'} detail="UNCHANGED BY FEDERATION" tone="cyan" />
</div>
<div class="grid">
	<Panel eyebrow="01 / ARCHITECTURE" title="Two separate lanes"><ArchitectureLanes releasedModel={fed.overview?.released_model_id ?? 'MODEL_V2_FINAL'} /></Panel>
	<Panel eyebrow="02 / RUN" title="Configure a federation run" note="FL_SINGLE_RUN">
		<RunConfigForm disabled={fed.busy} liveBlocked={fed.overview?.active_live_run ?? false} backendEnabled={enabled} onSubmit={start} />
		{#if fed.replayNoSource}<p class="warn" role="alert" data-testid="replay-no-source">{REPLAY_NO_SOURCE}</p>{/if}
		{#if fed.error}<p class="warn" role="alert">{fed.error}</p>{/if}
	</Panel>
	<Panel eyebrow="03 / CLIENTS" title="Logical local clients" note="SYNTHETIC RESEARCH PARTITIONS">
		{#if fed.clientsPhase === 'PREPARING' || fed.clientsPhase === 'IDLE'}
			<p class="dim" role="status" data-testid="clients-preparing">PREPARING 8 SYNTHETIC LOCAL CLIENT DATASETS. This can take several seconds on first use.</p>
		{:else if fed.clientsPhase === 'ERROR'}<p class="warn" role="alert">Clients could not be loaded.</p>
		{:else}<p class="dim">{fed.clients.length} logical clients ready · <a href="/app/federation/clients">view clients →</a></p>{/if}
		<p class="dim">All eight logical clients currently execute on one demonstration machine.</p>
	</Panel>
	<Panel eyebrow="04 / RUNS" title="Your federation runs"><RunList runs={fed.runs} /></Panel>
</div>
{/if}
<style>
	.eyebrow { color: #2bb8b0; font: 10px 'JetBrains Mono', monospace; letter-spacing: .14em; } h1 { margin: 10px 0 8px; font: 500 clamp(28px, 4vw, 42px) 'Space Grotesk', sans-serif; } .head p { color: #94a3b8; margin: 0 0 16px; max-width: 680px; line-height: 1.6; }
	.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 190px), 1fr)); gap: 8px; margin-bottom: 14px; } .tiles :global(.metric-value) { font-size: clamp(16px, 1.6vw, 22px); overflow-wrap: anywhere; }
	.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 320px), 1fr)); gap: 10px; } .dim { color: #94a3b8; font-size: 13px; line-height: 1.6; } .warn { color: #fbbf24; font: 12px 'JetBrains Mono', monospace; } a { color: #2bb8b0; }
</style>
