<script lang="ts">
	import { onMount } from 'svelte';
	import Panel from '$lib/components/dashboard/Panel.svelte';
	import FederationBanner from '$lib/components/product/federation/FederationBanner.svelte';
	import CandidateCard from '$lib/components/product/federation/CandidateCard.svelte';
	import TechnicalEvidence from '$lib/components/product/federation/TechnicalEvidence.svelte';
	import ComparisonPanel from '$lib/components/product/story/ComparisonPanel.svelte';
	import FlowDiagram from '$lib/components/product/story/FlowDiagram.svelte';
	import { useFederation } from '$lib/product/federation/state.svelte';
	const fed = useFederation();
	onMount(() => { void fed.loadModels(); });
	const released = $derived(fed.registry?.released_default_model_id ?? 'MODEL_V2_FINAL');
	const cand = $derived(fed.candidates[0] ?? null);
	const rows = $derived([
		{ label: 'Model role', left: 'Live research monitoring', right: 'Engineering development' },
		{ label: 'Training', left: 'Centrally trained', right: 'Federated local training' },
		{ label: 'Current runtime', left: 'Enabled (server-side)', right: 'No inference runtime' },
		{ label: 'Calibration', left: 'CAL_V2', right: 'Not established' },
		{ label: 'Validation', left: 'Frozen research evidence', right: 'Structural engineering checks only' },
		{ label: 'Monitoring use', left: 'YES', right: 'NO' },
		{ label: 'Deployment', left: 'Research default', right: 'Sandbox only / NOT DEPLOYED' }
	]);
</script>
<svelte:head><title>Models | NHM</title></svelte:head>
<div class="head"><div class="eyebrow">NHM / MODELS</div><h1>Model governance &amp; comparison</h1><p class="lead">One model runs the live research monitoring. A separate federated engineering candidate exists only in a sandbox. They are compared here by role and status, not by performance: no candidate performance is claimed.</p></div>
<FederationBanner />
{#if fed.error}<p class="warn" role="alert">{fed.error}</p>{/if}
<Panel eyebrow="COMPARISON" title="Released monitoring model vs federated engineering candidate" note="ROLE AND STATUS ONLY">
	<ComparisonPanel testid="released-vs-candidate" leftTitle={released} leftSub="Released monitoring model" leftStatus="RELEASED" leftTone="released" rightTitle={cand?.candidate_id ?? 'CAPSTONE_FL_CANDIDATE_####'} rightSub={cand ? 'Federated engineering candidate' : 'No candidate yet'} rightStatus="NOT DEPLOYED" rightTone="candidate" {rows} />
	<p class="dim">This comparison does not say that the candidate is better or worse. No candidate performance has been established.</p>
</Panel>
<div class="gap"></div>
<Panel eyebrow="LIFECYCLE" title="Two lifecycles, one blocked boundary">
	<div class="lc"><p class="ln r">RELEASED MONITORING</p><FlowDiagram tone="released" label="Released model lifecycle" steps={[{ label: released }, { label: 'RELEASED MONITORING' }, { label: 'LIVE RESEARCH SYSTEM' }]} /></div>
	<div class="lc"><p class="ln f">FEDERATED DEVELOPMENT</p><FlowDiagram tone="federated" label="Candidate lifecycle" steps={[{ label: 'FL_INIT_V2' }, { label: 'FEDERATED TRAINING' }, { label: 'CANDIDATE CREATED', tone: 'candidate' }, { label: 'STRUCTURAL GOVERNANCE', tone: 'candidate' }, { label: 'ENGINEERING SANDBOX', tone: 'candidate' }]} /></div>
	<div class="wall" role="note"><span>SCIENTIFIC EVALUATION REQUIRED BEFORE ANY FUTURE PROMOTION</span><small>No promotion exists today; nothing moves a candidate into monitoring automatically.</small></div>
</Panel>
<div class="gap"></div>
<Panel eyebrow="CANDIDATES" title="Engineering federated candidates" note="SANDBOX REGISTRY">
	{#if !fed.registry}<p class="dim" role="status">Loading registry…</p>
	{:else if fed.candidates.length === 0}<p class="dim" data-testid="no-candidates">No engineering candidates yet. Run federated training in the <a href="/app/federation">Federation Studio</a> to create one.</p>
	{:else}<div class="cands" data-testid="candidates">{#each fed.candidates as c}<CandidateCard candidate={c} />{/each}</div>{/if}
	<p class="dim">Candidates are engineering sandbox entries. They are never used for live monitoring and no candidate inference runtime is enabled.</p>
</Panel>
<div class="gap"></div>
<TechnicalEvidence label="TECHNICAL EVIDENCE (released scientific registry)" testid="models-evidence">
	{#if fed.registry}
		<ul class="rel" data-testid="released-models">{#each fed.registry.released_scientific as m}<li data-model={m.model_id}><b>{m.model_id}</b><span>role: {m.role}</span></li>{/each}</ul>
		<p class="dim">The released default is <b>{fed.registry.released_default_model_id}</b>. Federation never changes it.</p>
	{:else}<p class="dim">Loading…</p>{/if}
</TechnicalEvidence>
<style>
	.eyebrow { color: #2bb8b0; font: 10px 'JetBrains Mono', monospace; letter-spacing: .14em; } h1 { margin: 10px 0 10px; font: 500 clamp(26px, 3.6vw, 38px) 'Space Grotesk', sans-serif; } .lead { color: #94a3b8; max-width: 720px; line-height: 1.6; margin: 0 0 14px; font-size: 14px; } .gap { height: 12px; }
	.rel { list-style: none; margin: 0 0 10px; padding: 0; display: grid; gap: 6px; } .rel li { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px; border: 1px solid rgba(148,163,184,.16); padding: 8px 10px; font: 12px 'JetBrains Mono', monospace; overflow-wrap: anywhere; } .cands { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 360px), 1fr)); gap: 10px; }
	.dim { color: #94a3b8; font-size: 13px; line-height: 1.6; } .dim a { display: inline-block; min-height: 24px; line-height: 24px; color: #2bb8b0; } .warn { color: #fbbf24; font: 12px 'JetBrains Mono', monospace; }
	.lc { display: grid; gap: 6px; margin-bottom: 14px; } .ln { margin: 0; font: 600 11px 'JetBrains Mono', monospace; letter-spacing: .14em; } .ln.r { color: #2bb8b0; } .ln.f { color: #c4b5fd; }
	.wall { border: 1px dashed rgba(248,113,113,.6); padding: 10px 12px; text-align: center; display: grid; gap: 3px; } .wall span { font: 600 12px 'JetBrains Mono', monospace; letter-spacing: .1em; color: #fca5a5; } .wall small { color: #94a3b8; font-size: 12px; }
</style>
