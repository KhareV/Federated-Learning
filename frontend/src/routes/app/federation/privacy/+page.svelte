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
<p class="lead">A narrow engineering claim about what the aggregation interface receives. It is not a general privacy or security guarantee.</p>
<div class="grid">
	<Panel eyebrow="01 / LOGICAL CLIENT" title="What stays local">
		<p>Local synthetic training examples stay inside each logical client buffer. All eight logical clients execute on one demonstration machine, not separate hospitals or institutions.</p>
	</Panel>
	<Panel eyebrow="02 / COORDINATOR" title="What the coordinator receives">
		<p>Model updates and metadata — not the clients' local synthetic training examples. This is an application-level data-flow boundary, not host or network isolation.</p>
	</Panel>
	<Panel eyebrow="03 / SHADOW" title="What SecAgg+ demonstrates" note="ROUND 1 ONLY">
		<p>ROUND-1 PROTECTED-AGGREGATION SHADOW: a Flower SecAgg+ shadow is executed for round 1 only and compared with the plain aggregate under the frozen tolerance. <b>Authoritative aggregation remains PLAIN</b> in every product run.</p>
		<details><summary>TECHNICAL CLAIM BOUNDARY</summary><code>PROTECTED_AGGREGATION_INTERFACE_ONLY</code></details>
	</Panel>
</div>
<section class="not-claimed" aria-labelledby="not-claimed-heading"><h2 id="not-claimed-heading">What is not claimed</h2><ul><li>No differential privacy.</li><li>No anonymity guarantee.</li><li>No hospital deployment.</li><li>No network or host isolation claim.</li><li>No production security certification.</li></ul></section>
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
	.eyebrow { color: #2bb8b0; font: 10px 'JetBrains Mono', monospace; letter-spacing: .14em; } h1 { margin: 10px 0 14px; font: 500 clamp(26px, 3.6vw, 38px) 'Space Grotesk', sans-serif; } .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr)); gap: 10px; } .gap { height: 14px; }.lead{max-width:780px;color:#a7b8c9;font-size:14px;line-height:1.6}.not-claimed{margin-top:12px;padding:15px 18px;border:1px solid rgba(251,113,133,.55);background:rgba(127,29,29,.07)}.not-claimed h2{margin:0 0 10px;color:#fecdd3;font:500 18px 'Space Grotesk',sans-serif}.not-claimed ul{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,210px),1fr));gap:8px;list-style:none;padding:0}.not-claimed li{border-left:2px solid #fb7185;padding:5px 9px;color:#fecdd3;font:11px 'JetBrains Mono',monospace}details{margin-top:10px}summary{cursor:pointer;color:#2bb8b0;font:11px 'JetBrains Mono',monospace}summary:focus-visible{outline:2px solid #fbbf24;outline-offset:3px}
	p, li { font-size: 13px; line-height: 1.6; } ul { margin: 0; padding-left: 18px; } code { font: 12px 'JetBrains Mono', monospace; overflow-wrap: anywhere; }
</style>
