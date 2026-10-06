<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import Panel from '$lib/components/dashboard/Panel.svelte';
	import FederationBanner from '$lib/components/product/federation/FederationBanner.svelte';
	import RunSelector from '$lib/components/product/federation/RunSelector.svelte';
	import ClientGrid from '$lib/components/product/federation/ClientGrid.svelte';
	import DigestText from '$lib/components/product/federation/DigestText.svelte';
	import { bootRun, chooseRun } from '$lib/components/product/federation/useRunParam';
	import { useFederation } from '$lib/product/federation/state.svelte';
	import { getProductStore } from '$lib/product/state.svelte';
	import { ownerBoundClientId } from '$lib/product/federation/participation';
	const fed = useFederation();
	const product = getProductStore();
	onMount(() => { void bootRun(fed, page.url.searchParams.get('run')); return () => fed.closeLive(); });
	const v = $derived(fed.view);
	const replay = $derived(v.runType === 'REPLAY');
	// UFL-LITE-002: owner binding is a pure presentation rule over the backend-decided auth provider and the run type.
	const ownerBound = $derived(ownerBoundClientId(product.authState.system?.auth_provider, v.runType ?? fed.run?.run_type));
	const mine = $derived(ownerBound ? v.clients.find((c) => c.clientId === ownerBound) ?? null : null);
	const plannedRounds = $derived(v.plannedRounds || fed.run?.planned_rounds || 0);
	const status = $derived(v.runStatus ?? fed.run?.status ?? '--');
	const shadow = $derived(v.secagg.filter((s) => s.mode === 'SECAGG_SHADOW'));
	const lastShadow = $derived(shadow.length ? shadow[shadow.length - 1].status : null);
</script>
<svelte:head><title>Live federation | NHM</title></svelte:head>
<div class="head"><div class="eyebrow">NHM / FEDERATION / LIVE</div><h1>Live federation</h1>
	<p class="dim">The run executes on the product backend; closing this page does not stop it. Returning rebuilds this view from the event journal (sequence 0).</p></div>
<FederationBanner runType={v.runType} />
<RunSelector runs={fed.runs} selected={fed.run?.run_id ?? null} onSelect={(id) => chooseRun(fed, page.url.pathname, id)} />
{#if v.streamError}<p class="err" role="alert" data-testid="stream-error">FEDERATION STREAM ERROR ({v.streamError.reason}) — derived progress below is no longer trustworthy. <button type="button" onclick={() => fed.reconnectLive()}>Reconnect</button></p>{/if}
{#if fed.error}<p class="err" role="alert">{fed.error}</p>{/if}
{#if replay}<p class="replay" role="status" data-testid="replay-note"><b>REPLAY — NO TRAINING IS EXECUTING.</b> The events below are a faithful re-emission of a previous LIVE_RUN.</p>{/if}
{#if fed.run}
<div class="grid">
	<Panel eyebrow="RUN" title="Status" note={fed.socketStatus}>
		<p role="status" aria-live="polite" data-testid="run-status"><b>{status}</b> · {v.runType ?? fed.run.run_type} · {v.algorithm ?? fed.run.algorithm} · round {v.currentRound}/{v.plannedRounds || fed.run.planned_rounds} · {v.eventCount} events</p>
		<p class="dim">Update-ready events: <b data-testid="update-ready-count">{v.updateReadyCount}</b> · client SUBMITTED completions: <b data-testid="submitted-count">{v.submittedCount}</b></p>
		<ul class="rs" data-testid="round-states">{#each v.rounds as r}<li data-round={r.roundId}>Round {r.roundId}: <b>{r.state}</b> · accepted {r.accepted}/{r.expected} · authoritative aggregate: <b>{r.aggregationMode ?? '--'}</b> {#if r.stateDigest}· <DigestText value={r.stateDigest} label="round state digest" />{/if}</li>{/each}</ul>
		{#each v.errors as e}<p class="err" role="alert">ERROR {e.code}: {e.message}{e.roundId ? ` (round ${e.roundId})` : ''}</p>{/each}
	</Panel>
	<Panel eyebrow="SECAGG+" title="Protection" note="ROUND-1 SHADOW ONLY">
		<p data-testid="authoritative-aggregate">AUTHORITATIVE AGGREGATE: <b>{v.rounds.find((r) => r.aggregationMode)?.aggregationMode ?? '--'}</b></p>
		{#if (v.algorithm && fed.run.secagg_mode === 'SECAGG_SHADOW') || shadow.length}
			<p data-testid="secagg-status">ROUND-1 SECAGG+ SHADOW: <b>{lastShadow ?? 'NOT YET REPORTED'}</b></p>
			<p class="dim">{shadow.map((s) => s.status).join(' → ')}</p>
		{:else}<p data-testid="secagg-status">SECAGG SHADOW: <b>NOT USED</b></p>{/if}
		<p class="dim">Protected-aggregation interface only; no differential-privacy or anonymity claim.</p>
	</Panel>
	<Panel eyebrow="CLIENTS" title={ownerBound ? `Federated participants (round ${v.currentRound || '--'})` : `Eight logical clients (round ${v.currentRound || '--'})`} note="SYNTHETIC">
		{#if ownerBound}<p class="dim" data-testid="participants-note">1 authenticated owner-bound client · 7 synthetic peers · ALL TRAINING DATA IN THIS DEMO IS SYNTHETIC ENGINEERING DATA and does not represent the authenticated user's physiology.</p>{/if}
		<ClientGrid live={v.clients} round={v.currentRound} {replay} ownerBoundClientId={ownerBound} />
		{#if ownerBound}
			<div class="mine" data-testid="my-participation">
				<b>MY FEDERATED PARTICIPATION</b>
				<p>Client: <code>{ownerBound}</code> · authenticated owner-bound participation · data source: SYNTHETIC ENGINEERING FIXTURE (not the authenticated user's physiology)</p>
				<p>Local examples in buffer: <b data-testid="my-local-examples">{mine?.localExamples ?? '--'}</b></p>
				<p>Completed local-training rounds: <b data-testid="my-completed-rounds">{mine ? Object.values(mine.milestones).filter((m) => m === 1).length : 0} / {plannedRounds}</b></p>
				<p>Updates produced: <b data-testid="my-updates-produced">{mine ? Object.keys(mine.updateDigests).length : 0} / {plannedRounds}</b></p>
				<p>Raw training examples sent to the federation coordinator: <b data-testid="my-raw-examples-sent">0</b></p>
				<p class="dim">Training examples remain in this client's logical local buffer; the federation coordinator receives model updates and metadata rather than those local training examples. All clients execute on one demonstration machine.</p>
			</div>
		{/if}
		<p class="dim">Training milestones are shown exactly as reported (started / completed); nothing is interpolated.</p>
	</Panel>
	<Panel eyebrow="CANDIDATE" title="Candidate, validation, governance" note={replay ? 'HISTORICAL EVENT REPLAY' : 'ENGINEERING SANDBOX'}>
		{#if replay && v.candidate}<p class="replay" data-testid="historical-candidate">HISTORICAL EVENT REPLAY — NO NEW CANDIDATE CREATED.</p>{/if}
		{#if v.candidate}
			<dl data-testid="candidate-live"><div><dt>Candidate</dt><dd>{v.candidate.candidateId}</dd></div><div><dt>Parent</dt><dd>{v.candidate.parentModelId}</dd></div><div><dt>State digest</dt><dd><DigestText value={v.candidate.stateDigest} label="candidate digest" /></dd></div>
				<div><dt>Validation</dt><dd>{v.candidate.validation ?? 'PENDING'}</dd></div><div><dt>Checks reported passed</dt><dd>{v.candidate.checksPassed.length ? v.candidate.checksPassed.join(', ') : '--'}</dd></div>
				<div><dt>Governance</dt><dd>{v.candidate.governance ?? '--'}</dd></div><div><dt>Sandbox</dt><dd>{v.candidate.sandbox ?? '--'}</dd></div><div><dt>production_deployed</dt><dd>FALSE</dd></div></dl>
			{#if v.candidate.governance === 'ACCEPTED_TO_SANDBOX'}<p class="ok">ACCEPTED TO ENGINEERING SANDBOX REGISTRY · NOT A SCIENTIFIC RELEASE · NOT DEPLOYED</p>{:else if v.candidate.governance === 'REJECTED'}<p class="err">REJECTED BY ENGINEERING GOVERNANCE · NOT IN SANDBOX · NOT DEPLOYED</p>{/if}
		{:else}<p class="dim">No candidate event yet. A candidate appears only after the final round.</p>{/if}
	</Panel>
	<Panel eyebrow="JOURNAL" title="Recent events" note={`${v.timeline.length} kept`}>
		<ol class="tl" data-testid="timeline">{#each v.timeline.slice(-40) as t}<li><code>{t.sequence}</code> {t.summary}</li>{/each}</ol>
	</Panel>
</div>
{:else}<p class="dim">Select a run, or start one from <a href="/app/federation">Federation</a>.</p>{/if}
<style>
	.mine { margin-top: 10px; border: 1px solid rgba(43,184,176,.5); padding: 10px 12px; display: grid; gap: 4px; } .mine b:first-child { font: 11px 'JetBrains Mono', monospace; letter-spacing: .1em; color: #2bb8b0; } .mine p { margin: 0; }
	.eyebrow { color: #2bb8b0; font: 10px 'JetBrains Mono', monospace; letter-spacing: .14em; } h1 { margin: 10px 0 8px; font: 500 clamp(26px, 3.6vw, 38px) 'Space Grotesk', sans-serif; } .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 340px), 1fr)); gap: 10px; }
	.dim { color: #94a3b8; font-size: 13px; line-height: 1.6; } p { margin: 0 0 8px; font-size: 13px; } .err { color: #f87171; font: 12px 'JetBrains Mono', monospace; } .ok { color: #2bb8b0; font: 12px 'JetBrains Mono', monospace; } .replay { border: 1px solid rgba(251,191,36,.6); color: #fbbf24; padding: 8px 12px; font: 12px 'JetBrains Mono', monospace; } a { color: #2bb8b0; }
	.rs, .tl { list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; font-size: 12px; } .tl { max-height: 320px; overflow: auto; font: 11px 'JetBrains Mono', monospace; } dl { display: grid; gap: 4px; margin: 0 0 8px; } dl div { display: flex; justify-content: space-between; gap: 8px; font-size: 12px; } dt { color: #71829a; } dd { margin: 0; font: 11px 'JetBrains Mono', monospace; text-align: right; overflow-wrap: anywhere; }
	button { background: none; border: 1px solid #f87171; color: #f87171; padding: 3px 8px; cursor: pointer; } button:focus-visible { outline: 2px solid #2bb8b0; }
</style>
