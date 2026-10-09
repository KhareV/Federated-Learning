<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import Panel from '$lib/components/dashboard/Panel.svelte';
	import FederationBanner from '$lib/components/product/federation/FederationBanner.svelte';
	import RunSelector from '$lib/components/product/federation/RunSelector.svelte';
	import TechnicalEvidence from '$lib/components/product/federation/TechnicalEvidence.svelte';
	import DigestText from '$lib/components/product/federation/DigestText.svelte';
	import { bootRun, chooseRun } from '$lib/components/product/federation/useRunParam';
	import { isStudioRunId, useFederation } from '$lib/product/federation/state.svelte';
	import { getProductStore } from '$lib/product/state.svelte';
	import { ownerBoundClientId } from '$lib/product/federation/participation';
	const fed = useFederation();
	const product = getProductStore();
	const ownerBound = $derived(ownerBoundClientId(product.authState.system?.auth_provider, fed.run?.run_type));
	onMount(() => { void bootRun(fed, page.url.searchParams.get('run')); return () => fed.closeLive(); });
	const studioRun = $derived(fed.run ? isStudioRunId(fed.run.run_id) : false);
	const finalCandidate = $derived(fed.run?.candidate_ids[0] ?? null);
</script>
<svelte:head><title>Federation rounds | NHM</title></svelte:head>
<div class="head"><div class="eyebrow">NHM / FEDERATION / ROUNDS</div><h1>Rounds</h1></div>
<FederationBanner runType={fed.run?.run_type ?? null} />
<RunSelector runs={fed.runs} selected={fed.run?.run_id ?? null} onSelect={(id) => chooseRun(fed, page.url.pathname, id)} />
{#if fed.error}<p class="warn" role="alert">{fed.error}</p>{/if}
{#if fed.run && studioRun}
	<Panel eyebrow="10-ROUND / RECORDED RUN" title="Round-by-round state lives in the Federation Studio" note="SAME EVIDENCE, RUN-SCOPED">
		<p class="dim" data-testid="rounds-studio-note">Round state, lineage digests, per-round client contributions and evaluation of {fed.run.run_id} are shown, synchronized and exportable, in the <a href={`/app/federation/live?run=${encodeURIComponent(fed.run.run_id)}`}>Federation Studio</a>. This page lists the persisted rounds of 3-round product runs.</p>
	</Panel>
{:else if fed.run}
	{#if ownerBound}<p class="dim" data-testid="rounds-owner-note">MY EDGE CLIENT: {ownerBound}. Presentation-bound to the authenticated run owner; training data remains synthetic engineering data.</p>{/if}
	<Panel eyebrow="MODEL STATE TIMELINE" title="How the global model state moved" note="NO PERFORMANCE CLAIM">
		<ol class="tl" data-testid="state-timeline">
			<li class="n0"><span class="dot" aria-hidden="true">●</span><b>FL_INIT_V2</b><span class="dim">Initial federated state</span></li>
			{#each fed.rounds as r}<li class="n1" data-round={r.round_id}><span class="dot" aria-hidden="true">●</span><b>Round {r.round_id}</b><span class="dim">{r.accepted_update_count} of {r.participating_client_ids.length} client updates accepted · {r.state}</span></li>{/each}
			<li class="n2"><span class="dot" aria-hidden="true">◆</span><b>{finalCandidate ?? 'NO CANDIDATE'}</b><span class="dim">{finalCandidate ? 'Engineering candidate' : 'No candidate for this run'}</span></li>
			<li class="n3"><span class="dot" aria-hidden="true">■</span><b>ENGINEERING SANDBOX</b><span class="dim">NOT DEPLOYED · NO AUTOMATIC PROMOTION</span></li>
		</ol>
		<p class="dim">Digests are the technical evidence of each state and sit below. Released monitoring is a separate lane and is not part of this timeline.</p>
	</Panel>
	<div class="gap"></div>
	<TechnicalEvidence label="TECHNICAL EVIDENCE (digests and round records)" testid="rounds-evidence" open>
	<Panel eyebrow="LINEAGE" title="Global-state lineage" note="DIGESTS FROM THE BACKEND">
		<ol class="lin" data-testid="lineage">
			<li>FL_INIT_V2 <DigestText value={fed.rounds[0]?.base_state_digest} label="FL_INIT_V2 digest" /></li>
			{#each fed.rounds as r, i}
				<li>{i + 1 < fed.rounds.length ? `ROUND ${i + 1} GLOBAL STATE` : `ROUND ${r.round_id} FINAL STATE`} {#if fed.rounds[i + 1]}<DigestText value={fed.rounds[i + 1].base_state_digest} label="round global state digest" />{:else}<span class="dim">(digest shown on the candidate)</span>{/if}</li>
			{/each}
			<li>{finalCandidate ?? 'NO CANDIDATE'}</li>
		</ol>
		<p class="dim">Released monitoring (MODEL_V2_FINAL) is a separate lane and is not part of this lineage. Intermediate aggregates are round states, not candidates.</p>
	</Panel>
	<div class="gap"></div>
	<ul class="rounds" data-testid="round-cards">
		{#each fed.rounds as r}
			<li data-round={r.round_id}><h3>Round {r.round_id}</h3>
				<dl><div><dt>State</dt><dd>{r.state}</dd></div><div><dt>Base state digest</dt><dd><DigestText value={r.base_state_digest} label="base state digest" /></dd></div><div><dt>Algorithm</dt><dd>{r.algorithm}</dd></div>
					<div><dt>Accepted updates</dt><dd>{r.accepted_update_count} / {r.participating_client_ids.length}</dd></div><div><dt>Candidate</dt><dd>{r.candidate_id ?? 'NONE'}</dd></div></dl></li>
		{/each}
	</ul>
	</TechnicalEvidence>
{:else}<p class="dim">Select a run to see its persisted rounds.</p>{/if}
<style>
	.eyebrow { color: #2bb8b0; font: 10px 'JetBrains Mono', monospace; letter-spacing: .14em; } h1 { margin: 10px 0 14px; font: 500 clamp(26px, 3.6vw, 38px) 'Space Grotesk', sans-serif; } .gap { height: 12px; } .dim { color: #94a3b8; font-size: 13px; line-height: 1.6; } .warn { color: #fbbf24; font: 12px 'JetBrains Mono', monospace; }
	.tl { list-style: none; margin: 0 0 8px; padding: 0; display: grid; gap: 0; } .tl li { display: grid; grid-template-columns: 22px auto 1fr; gap: 8px; align-items: baseline; padding: 8px 0 8px 4px; border-left: 2px solid rgba(148,163,184,.3); margin-left: 8px; } .tl b { font: 500 14px 'Space Grotesk', sans-serif; } .tl .dim { margin: 0; font-size: 12px; } .n0 .dot, .n1 .dot { color: #a78bfa; } .n2 .dot, .n3 .dot { color: #fbbf24; } .dot { margin-left: -14px; background: #0b1220; }
	.lin { list-style: none; margin: 0 0 8px; padding: 0; display: grid; gap: 4px; font: 11px 'JetBrains Mono', monospace; } .lin li { padding: 5px 9px; border-left: 2px solid rgba(43,184,176,.5); background: rgba(43,184,176,.06); overflow-wrap: anywhere; }
	.rounds { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 280px), 1fr)); gap: 8px; } .rounds li { border: 1px solid rgba(148,163,184,.16); padding: 10px 12px; min-width: 0; } h3 { margin: 0 0 6px; font: 500 15px 'Space Grotesk', sans-serif; }
	dl { display: grid; gap: 4px; margin: 0; } dl div { display: flex; justify-content: space-between; gap: 8px; font-size: 12px; } dt { color: #71829a; } dd { margin: 0; font: 11px 'JetBrains Mono', monospace; text-align: right; overflow-wrap: anywhere; }
</style>
