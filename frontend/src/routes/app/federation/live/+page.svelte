<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import Panel from '$lib/components/dashboard/Panel.svelte';
	import FederationBanner from '$lib/components/product/federation/FederationBanner.svelte';
	import RunSelector from '$lib/components/product/federation/RunSelector.svelte';
	import ClientGrid from '$lib/components/product/federation/ClientGrid.svelte';
	import ClientDetailPanel from '$lib/components/product/federation/ClientDetailPanel.svelte';
	import DigestText from '$lib/components/product/federation/DigestText.svelte';
	import ProcessStepper from '$lib/components/product/federation/ProcessStepper.svelte';
	import RoundProgress from '$lib/components/product/federation/RoundProgress.svelte';
	import ModelStateTransition from '$lib/components/product/federation/ModelStateTransition.svelte';
	import CandidateLifecycle from '$lib/components/product/federation/CandidateLifecycle.svelte';
	import FederationTimeline from '$lib/components/product/federation/FederationTimeline.svelte';
	import LiveVsReplay from '$lib/components/product/federation/LiveVsReplay.svelte';
	import TechnicalEvidence from '$lib/components/product/federation/TechnicalEvidence.svelte';
	import { bootRun, chooseRun } from '$lib/components/product/federation/useRunParam';
	import { useFederation } from '$lib/product/federation/state.svelte';
	import { getProductStore } from '$lib/product/state.svelte';
	import { ownerBoundClientId } from '$lib/product/federation/participation';
	import { algorithmName } from '$lib/product/federation/presentation';
	const fed = useFederation();
	const product = getProductStore();
	onMount(() => { void bootRun(fed, page.url.searchParams.get('run')); void fed.loadClients(); return () => fed.closeLive(); });
	const v = $derived(fed.view);
	const replay = $derived(v.runType === 'REPLAY');
	// UFL-LITE-002: owner binding is a pure presentation rule over the backend-decided auth provider and the run type.
	const ownerBound = $derived(ownerBoundClientId(product.authState.system?.auth_provider, v.runType ?? fed.run?.run_type));
	const plannedRounds = $derived(v.plannedRounds || fed.run?.planned_rounds || 0);
	const status = $derived(v.runStatus ?? fed.run?.status ?? '--');
	const shadow = $derived(v.secagg.filter((s) => s.mode === 'SECAGG_SHADOW'));
	const lastShadow = $derived(shadow.length ? shadow[shadow.length - 1].status : null);
	const shadowRequested = $derived((v.algorithm && fed.run?.secagg_mode === 'SECAGG_SHADOW') || shadow.length > 0);
	const shadowState = $derived(!shadowRequested ? 'NOT USED' : lastShadow === 'SHADOW_RUNNING' ? 'RUNNING' : lastShadow === 'SHADOW_VERIFIED' ? 'COMPLETE' : lastShadow === 'SHADOW_FAILED' ? 'FAILED' : 'NOT STARTED');
	let picked = $state<string | null>(null);
	const selectedId = $derived(picked ?? ownerBound ?? null);
	const selectedClient = $derived(selectedId ? v.clients.find((c) => c.clientId === selectedId) : undefined);
	const identity = $derived(selectedId ? fed.clients.find((c) => c.client_id === selectedId) : undefined);
	const mine = $derived(ownerBound ? (v.clients.find((c) => c.clientId === ownerBound) ?? null) : null);
	const runDone = $derived(v.runStatus === 'COMPLETED');
</script>
<svelte:head><title>Live federation | NHM</title></svelte:head>
<div class="head"><div class="eyebrow">NHM / FEDERATION / LIVE</div><h1>Live federation</h1>
	<p class="dim">The run executes on the product backend; closing this page does not stop it. Returning rebuilds this view from the event journal (sequence 0).</p></div>
<FederationBanner runType={v.runType} />
<RunSelector runs={fed.runs} selected={fed.run?.run_id ?? null} onSelect={(id) => { picked = null; void chooseRun(fed, page.url.pathname, id); }} />
{#if v.streamError}<p class="err" role="alert" data-testid="stream-error">FEDERATION STREAM ERROR ({v.streamError.reason}) — derived progress below is no longer trustworthy. <button type="button" onclick={() => fed.reconnectLive()}>Reconnect</button></p>{/if}
{#if fed.error}<p class="err" role="alert">{fed.error}</p>{/if}
{#if replay}<p class="replay" role="status" data-testid="replay-note"><b>REPLAY — NO TRAINING IS EXECUTING.</b> The events below are a faithful re-emission of a previous LIVE_RUN.</p>{/if}
{#if fed.run}
<section class="run" aria-label="Run header">
	<div class="tag">{replay ? 'REPLAY OF A PREVIOUS RUN' : 'LIVE FEDERATED TRAINING'}</div>
	<p role="status" aria-live="polite" data-testid="run-status"><b>{status}</b> · {v.runType ?? fed.run.run_type} · {v.algorithm ?? fed.run.algorithm} · round {v.currentRound}/{v.plannedRounds || fed.run.planned_rounds} · {v.eventCount} events</p>
	<ul class="chips"><li>Round {v.currentRound || '--'} of {plannedRounds || '--'}</li><li>{algorithmName(v.algorithm ?? fed.run.algorithm)}</li><li>8 synthetic logical clients</li><li>one demonstration machine</li>{#if ownerBound}<li class="own">1 owner-bound client · 7 synthetic peers</li>{/if}<li class="muted">stream: {fed.socketStatus}</li></ul>
	<p class="dim counters">Update-ready events: <b data-testid="update-ready-count">{v.updateReadyCount}</b> · client SUBMITTED completions: <b data-testid="submitted-count">{v.submittedCount}</b></p>
	{#each v.errors as e}<p class="err" role="alert">ERROR {e.code}: {e.message}{e.roundId ? ` (round ${e.roundId})` : ''}</p>{/each}
</section>
<div class="gap"></div>
<Panel eyebrow="STAGES" title="Where is the federation right now?" note={replay ? 'HISTORICAL EVENTS' : 'DERIVED FROM BACKEND STATE'}><ProcessStepper view={v} {replay} /></Panel>
<div class="gap"></div>
{#if replay}<Panel eyebrow="REPLAY VS LIVE" title="What a replay does and does not do"><LiveVsReplay highlight="REPLAY" /></Panel><div class="gap"></div>{/if}
<Panel eyebrow="CLIENT NETWORK" title={ownerBound ? `Federated participants (round ${v.currentRound || '--'})` : `Eight logical clients (round ${v.currentRound || '--'})`} note="SYNTHETIC">
	{#if ownerBound}<p class="dim" data-testid="participants-note">1 authenticated owner-bound client · 7 synthetic peers · ALL TRAINING DATA IN THIS DEMO IS SYNTHETIC ENGINEERING DATA and does not represent the authenticated user's physiology.</p>{/if}
	<ClientGrid live={v.clients} round={v.currentRound} {replay} ownerBoundClientId={ownerBound} selected={selectedId} onSelect={(id) => (picked = id)} {runDone} />
	<p class="dim">Click a client to see what it is doing. Training milestones are shown exactly as reported (started / completed); nothing is interpolated.</p>
	{#if ownerBound}
		<div class="mine" data-testid="my-participation">
			<b>MY FEDERATED PARTICIPATION</b>
			<p>Client: <code>{ownerBound}</code> · data source: SYNTHETIC ENGINEERING FIXTURE (not the authenticated user's physiology)</p>
			<p>Local examples in buffer: <b data-testid="my-local-examples">{mine?.localExamples ?? '--'}</b></p>
			<p>Completed local-training rounds: <b data-testid="my-completed-rounds">{mine ? Object.values(mine.milestones).filter((m) => m === 1).length : 0} / {plannedRounds}</b></p>
			<p>Updates produced: <b data-testid="my-updates-produced">{mine ? Object.keys(mine.updateDigests).length : 0} / {plannedRounds}</b></p>
			<p>Raw training examples sent to the federation coordinator: <b data-testid="my-raw-examples-sent">0</b></p>
			<TechnicalEvidence label="WHY THIS IS SYNTHETIC (full qualification)"><p>Training examples remain in this client's logical local buffer; the federation coordinator receives model updates and metadata rather than those local training examples. All clients execute on one demonstration machine. The owner label is a presentation role only: your physiology and your monitoring sessions never feed federation.</p></TechnicalEvidence>
		</div>
	{/if}
	{#if selectedId}<ClientDetailPanel clientId={selectedId} client={selectedClient} ownerBound={selectedId === ownerBound} {plannedRounds} {replay} {identity} />{/if}
</Panel>
<div class="gap"></div>
<div class="grid">
	<Panel eyebrow="CURRENT ROUND" title="Round progress" note="REPORTED COUNTS ONLY"><RoundProgress view={v} {plannedRounds} />
		<TechnicalEvidence label="TECHNICAL EVIDENCE (round states)" testid="round-evidence"><ul class="rs" data-testid="round-states">{#each v.rounds as r}<li data-round={r.roundId}>Round {r.roundId}: <b>{r.state}</b> · accepted {r.accepted}/{r.expected} · authoritative aggregate: <b>{r.aggregationMode ?? '--'}</b> {#if r.stateDigest}· <DigestText value={r.stateDigest} label="round state digest" />{/if}</li>{/each}</ul></TechnicalEvidence>
	</Panel>
	<Panel eyebrow="PROTECTED AGGREGATION" title="Protected aggregation check" note="ROUND-1 SHADOW ONLY">
		<p class="big">Round 1 shadow: <b class={`ss ss-${shadowState.replace(' ', '-').toLowerCase()}`}>{shadowState}</b></p>
		<p class="dim">Engineering protected-aggregation interface only; no differential-privacy or anonymity claim.</p>
		<TechnicalEvidence label="TECHNICAL EVIDENCE (SECAGG_SHADOW)" testid="secagg-evidence">
			<p data-testid="authoritative-aggregate">AUTHORITATIVE AGGREGATE: <b>{v.rounds.find((r) => r.aggregationMode)?.aggregationMode ?? '--'}</b></p>
			{#if shadowRequested}<p data-testid="secagg-status">ROUND-1 SECAGG+ SHADOW: <b>{lastShadow ?? 'NOT YET REPORTED'}</b></p><p class="dim">{shadow.map((s) => s.status).join(' → ')}</p>{:else}<p data-testid="secagg-status">SECAGG SHADOW: <b>NOT USED</b></p>{/if}
		</TechnicalEvidence>
	</Panel>
</div>
<div class="gap"></div>
<div class="grid">
	<Panel eyebrow="MODEL STATE" title="Global model state evolution" note="REPORTED DIGESTS"><ModelStateTransition view={v} baseDigest={fed.rounds[0]?.base_state_digest ?? null} /></Panel>
	<Panel eyebrow="CANDIDATE" title="Candidate lifecycle" note={replay ? 'HISTORICAL EVENT REPLAY' : 'ENGINEERING SANDBOX'}><CandidateLifecycle view={v} {replay} /></Panel>
</div>
<div class="gap"></div>
<Panel eyebrow="TIMELINE" title="What happened, in order" note={`${v.timeline.length} events`}><FederationTimeline view={v} /></Panel>
{:else}
<Panel eyebrow="NO RUN SELECTED" title="Pick a run to watch"><p class="dim">Select a run, or start one from <a href="/app/federation">Federation</a>.</p><LiveVsReplay /></Panel>
{/if}
<style>
	.eyebrow { color: #2bb8b0; font: 10px 'JetBrains Mono', monospace; letter-spacing: .14em; } h1 { margin: 10px 0 8px; font: 500 clamp(26px, 3.6vw, 38px) 'Space Grotesk', sans-serif; } .gap { height: 12px; } .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 380px), 1fr)); gap: 12px; align-items: start; }
	.dim { color: #94a3b8; font-size: 13px; line-height: 1.6; margin: 0 0 8px; } p { margin: 0 0 8px; font-size: 13px; } .err { color: #f87171; font: 12px 'JetBrains Mono', monospace; } a { color: #2bb8b0; } .replay { border: 1px solid rgba(148,163,184,.6); color: #e5e7eb; background: rgba(148,163,184,.08); padding: 8px 12px; font: 12px 'JetBrains Mono', monospace; }
	.run { border: 1px solid rgba(167,139,250,.4); background: rgba(167,139,250,.05); padding: 12px 14px; display: grid; gap: 6px; } .tag { font: 600 12px 'JetBrains Mono', monospace; letter-spacing: .16em; color: #c4b5fd; } .chips { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: 6px; } .chips li { border: 1px solid rgba(148,163,184,.3); padding: 3px 9px; font-size: 12px; color: #cbd5e1; } .chips .own { border-color: rgba(43,184,176,.6); color: #9fe8e3; } .chips .muted { color: #71829a; } .counters { margin: 0; }
	.mine { margin: 10px 0; border: 1px solid rgba(43,184,176,.5); padding: 10px 12px; display: grid; gap: 4px; } .mine > b { font: 11px 'JetBrains Mono', monospace; letter-spacing: .1em; color: #2bb8b0; } .mine p { margin: 0; font-size: 12.5px; color: #cbd5e1; line-height: 1.5; }
	.big { font-size: 14px; } .ss { font: 600 13px 'JetBrains Mono', monospace; letter-spacing: .06em; } .ss-complete { color: #c4b5fd; } .ss-running { color: #fbbf24; } .ss-failed { color: #f87171; } .ss-not-started, .ss-not-used { color: #94a3b8; }
	.rs { list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; font-size: 12px; } button { background: none; border: 1px solid #f87171; color: #f87171; padding: 3px 8px; min-height: 24px; cursor: pointer; } button:focus-visible { outline: 2px solid #2bb8b0; }
</style>
