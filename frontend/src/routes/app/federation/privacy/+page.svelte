<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import Panel from '$lib/components/dashboard/Panel.svelte';
	import FederationBanner from '$lib/components/product/federation/FederationBanner.svelte';
	import RunSelector from '$lib/components/product/federation/RunSelector.svelte';
	import { bootRun, chooseRun } from '$lib/components/product/federation/useRunParam';
	import { useFederation } from '$lib/product/federation/state.svelte';
	const fed = useFederation();
	onMount(() => { void bootRun(fed, page.url.searchParams.get('run')); return () => fed.closeLive(); });
	const shadow = $derived(fed.view.secagg.filter((s) => s.mode === 'SECAGG_SHADOW'));
	const agg = $derived(fed.view.rounds.find((r) => r.aggregationMode)?.aggregationMode ?? null);
</script>
<svelte:head><title>Federation privacy boundary | NHM</title></svelte:head>
<div class="head"><div class="eyebrow">NHM / FEDERATION / PRIVACY</div><h1>The implemented privacy boundary</h1></div>
<FederationBanner runType={fed.run?.run_type ?? null} />
<div class="grid">
	<Panel eyebrow="01" title="Local-data boundary">
		<p>Each client keeps its local training examples inside its logical client buffer. The federation coordinator receives model updates and metadata rather than those local training examples.</p>
		<p class="dim">All eight logical clients currently execute on one demonstration machine.</p>
	</Panel>
	<Panel eyebrow="02" title="SecAgg+ shadow" note="ROUND 1 ONLY">
		<p>ROUND-1 PROTECTED-AGGREGATION SHADOW: a Flower SecAgg+ shadow is executed for round 1 only and compared with the plain aggregate under the frozen tolerance.</p>
		<p><b>Authoritative aggregation remains PLAIN</b> in every run, including SECAGG_SHADOW runs. Scope: <code>PROTECTED_AGGREGATION_INTERFACE_ONLY</code>.</p>
	</Panel>
	<Panel eyebrow="03" title="Limitations">
		<ul><li>Logical locality on one laptop (not separate machines or institutions).</li><li>No differential privacy.</li><li>No anonymity guarantee.</li><li>No hospital deployment.</li><li>No network or host isolation claim.</li></ul>
	</Panel>
</div>
<div class="gap"></div>
<RunSelector runs={fed.runs} selected={fed.run?.run_id ?? null} onSelect={(id) => chooseRun(fed, page.url.pathname, id)} />
{#if fed.run}
	<Panel eyebrow="SELECTED RUN" title={fed.run.run_id} note={fed.run.secagg_mode}>
		<p data-testid="privacy-agg">AUTHORITATIVE AGGREGATE: <b>{agg ?? '--'}</b></p>
		{#if fed.run.secagg_mode === 'SECAGG_SHADOW'}
			<p data-testid="privacy-secagg">ROUND-1 SECAGG+ SHADOW (from the event stream): <b>{shadow.length ? shadow[shadow.length - 1].status : 'NOT YET REPORTED'}</b> {shadow.length ? `(${shadow.map((s) => s.status).join(' → ')})` : ''}</p>
		{:else}<p data-testid="privacy-secagg">SECAGG SHADOW: <b>NOT USED</b></p>{/if}
	</Panel>
{/if}
<style>
	.eyebrow { color: #2bb8b0; font: 10px 'JetBrains Mono', monospace; letter-spacing: .14em; } h1 { margin: 10px 0 14px; font: 500 clamp(26px, 3.6vw, 38px) 'Space Grotesk', sans-serif; } .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr)); gap: 10px; } .gap { height: 14px; }
	p, li { font-size: 13px; line-height: 1.6; } .dim { color: #94a3b8; } ul { margin: 0; padding-left: 18px; } code { font: 12px 'JetBrains Mono', monospace; overflow-wrap: anywhere; }
</style>
