<script lang="ts">
	import { onMount } from 'svelte';
	import Panel from '$lib/components/dashboard/Panel.svelte';
	import FlowDiagram from '$lib/components/product/story/FlowDiagram.svelte';
	import TechnicalEvidence from '$lib/components/product/federation/TechnicalEvidence.svelte';
	import MetricTile from '$lib/components/dashboard/MetricTile.svelte';
	import { getProductStore } from '$lib/product/state.svelte';
	import { FederationStore, useFederation } from '$lib/product/federation/state.svelte';

	const store = getProductStore();
	const system = $derived(store.authState.system);
	const identity = $derived(store.authState.identity);
	const latest = $derived(store.sessions[0] ?? null);
	const connected = $derived(store.devices.filter((d) => d.connection_state === 'CONNECTED' || d.connection_state === 'STREAMING'));
	const fed = useFederation();
	const fedEnabled = $derived(FederationStore.backendEnabled(system?.federation_runtime));
	onMount(() => { void store.loadDevices(); void store.loadSessions(); void (async () => { if (FederationStore.backendEnabled(store.authState.system?.federation_runtime)) await fed.loadOverview(); })(); });
</script>

<svelte:head><title>Overview | NHM</title></svelte:head>

<div class="head"><div class="eyebrow">NHM / OVERVIEW</div><h1>NHM research system</h1><p>A simulated-wearable monitoring system and a separate federated-learning development lane. Research prototype: not diagnostic, not clinical. Status and session values are read from the local product backend; the system map is explanatory.</p></div>

<section class="cards" aria-label="System status" data-testid="system-cards">
	<article class="sc released"><p class="k">MONITORING</p><h2>{system?.model_id ?? 'MODEL_V2_FINAL'}</h2><p class="st"><span aria-hidden="true">●</span> {system ? 'RESEARCH DEFAULT' : 'CHECKING'}</p><p class="d">Server-side inference in {system?.software_system ?? 'SOFTWARE_SYSTEM_V2'} with {system?.calibration_id ?? 'CAL_V2'}. This is what the Monitor page uses.</p></article>
	<article class="sc fed"><p class="k">FEDERATED DEVELOPMENT</p><h2>8 synthetic logical clients</h2>{#if fedEnabled}<p class="st"><span aria-hidden="true">●</span> <span class="badge">ENGINEERING RUNTIME ENABLED</span></p><p class="d">Engineering candidates: <b data-testid="overview-candidate-count">{fed.overview ? fed.overview.candidate_count : '--'}</b> · never automatically deployed.</p>{:else}<p class="st"><span aria-hidden="true">○</span> <span class="badge warn">FEDERATION BACKEND NOT ENABLED</span></p><p class="d">The federation runtime is not enabled on this backend.</p>{/if}</article>
	<article class="sc auth"><p class="k">AUTHENTICATION</p><h2>{identity ? identity.auth_provider : (system?.auth_provider ?? '--')}</h2><p class="st"><span aria-hidden="true">●</span> {identity ? (identity.demo_mode ? 'OFFLINE DEMO WORKSPACE' : 'SIGNED IN') : 'NOT SIGNED IN'}</p><p class="d">Identity is decided by the backend; the browser never decides access.</p></article>
</section>

<Panel eyebrow="SYSTEM MAP" title="Two separate lanes" note="NO AUTOMATIC PROMOTION">
	<div class="lane" data-testid="lane-monitoring"><p class="ln released">LANE A · RELEASED MONITORING</p>
		<FlowDiagram tone="released" label="Released monitoring lane" steps={[{ label: 'VIRTUAL WEARABLE', sub: 'simulated source' }, { label: 'PRODUCT API', sub: 'authenticated backend' }, { label: `${system?.model_id ?? 'MODEL_V2_FINAL'} + ${system?.calibration_id ?? 'CAL_V2'}`, sub: 'server-side inference' }, { label: 'RESEARCH MONITORING STATE', sub: 'not a diagnosis' }, { label: 'PERSISTED HISTORY', sub: 'local database' }]} /></div>
	<div class="wall" role="separator" aria-label="No automatic promotion between the lanes"><span>NO AUTOMATIC PROMOTION</span><small>candidate → monitoring: not enabled</small></div>
	<div class="lane" data-testid="lane-federated"><p class="ln fed">LANE B · FEDERATED DEVELOPMENT</p>
		<FlowDiagram tone="federated" label="Federated development lane" steps={[{ label: 'FL_INIT_V2', sub: 'initial federated state' }, { label: '8 SYNTHETIC CLIENTS', sub: 'one demonstration machine' }, { label: 'FEDERATED TRAINING', sub: 'local training + aggregation' }, { label: 'CANDIDATE', sub: 'engineering artifact', tone: 'candidate' }, { label: 'ENGINEERING SANDBOX', sub: 'NOT DEPLOYED', tone: 'candidate' }]} /></div>
</Panel>
<div class="gap"></div>
<Panel eyebrow="START HERE" title="What do you want to demonstrate?">
	<div class="actions" data-testid="evaluator-actions">
		<a class="act released" href="/app/monitoring"><b>MONITOR A SIMULATED WEARABLE</b><span>Attach a virtual wearable, run a session, watch MODEL_V2_FINAL monitoring.</span><i>Open Monitor →</i></a>
		<a class="act fed" href="/app/federation"><b>RUN FEDERATED TRAINING</b><span>Watch 8 synthetic clients train locally and produce an engineering candidate.</span><i>Open Federation Studio →</i></a>
		<div class="act ev"><b>REVIEW RESEARCH EVIDENCE</b><span>How the released model and the scientific FL experiments were evaluated.</span><span class="links"><a href="/app/research/ml">ML evidence →</a><a href="/app/research/fl">FL evidence →</a></span></div>
	</div>
</Panel>
<div class="gap"></div>
<div class="grid">
	<Panel eyebrow="DEVICE" title="Virtual wearable" note="SIMULATED">
		{#if store.devices.length === 0}<p class="dim">No device attached yet.</p>{:else}
			<p class="big">{connected.length} connected / {store.devices.length} attached</p>
			<ul>{#each store.devices as d}<li><code>{d.device_id}</code> <span class="badge">{d.connection_state}</span></li>{/each}</ul>
		{/if}
		<a class="go" href="/app/device">Open device page →</a>
	</Panel>
	<Panel eyebrow="SESSIONS" title="Latest monitoring session" note="PERSISTED">
		{#if !latest}<p class="dim">No session yet.</p>{:else}
			<p class="big"><code>{latest.session_id}</code></p><p class="dim">State <span class="badge">{latest.state}</span> / scenario {latest.simulation_provenance?.scenario_id ?? '--'}</p>
		{/if}
		<a class="go" href="/app/monitoring">Open monitor →</a>
	</Panel>
</div>
<div class="gap"></div>
<TechnicalEvidence label="SYSTEM DETAILS" testid="overview-system-details">
	<div class="tiles">
		<MetricTile label="Identity" value={identity?.user_id ?? '--'} detail={identity ? `AUTH ${identity.auth_provider}${identity.demo_mode ? ' / OFFLINE DEMO' : ''}` : 'NOT SIGNED IN'} />
		<MetricTile label="Released model" value={system?.model_id ?? '--'} detail={`${system?.software_system ?? '--'} / SERVER-SIDE / ${system?.calibration_id ?? '--'}`} tone="cyan" />
		<MetricTile label="Persistence" value={system?.persistence_mode ?? '--'} detail="LOCAL DATABASE" />
		<MetricTile label="Hardware mode" value={system?.hardware_mode ?? '--'} detail={system?.physical_hardware_available === false ? 'PHYSICAL HARDWARE: NOT CONNECTED' : 'CHECKING'} tone="amber" />
	</div>
</TechnicalEvidence>
<p class="claim">{system?.claim ?? ''}</p>

<style>
	.eyebrow { color: #2bb8b0; font: 10px 'JetBrains Mono', monospace; letter-spacing: .14em; } h1 { margin: 10px 0 8px; font: 500 clamp(28px, 4vw, 42px) 'Space Grotesk', sans-serif; } .head p { color: #94a3b8; margin: 0 0 22px; max-width: 640px; line-height: 1.6; }
	.tiles :global(.metric-tile) { min-width: 0; } .tiles :global(.metric-value) { font-size: clamp(18px, 1.9vw, 26px); overflow-wrap: anywhere; } .tiles :global(.metric-detail) { overflow-wrap: anywhere; }
	.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 8px; margin-bottom: 14px; } .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 10px; }
	.big { margin: 0 0 6px; font: 500 18px 'Space Grotesk', sans-serif; overflow-wrap: anywhere; } .dim { color: #94a3b8; font-size: 13px; line-height: 1.6; } ul { margin: 8px 0; padding: 0; list-style: none; display: grid; gap: 6px; font-size: 12px; } code { font: 12px 'JetBrains Mono', monospace; overflow-wrap: anywhere; }
	.badge { padding: 2px 7px; border: 1px solid rgba(43,184,176,.5); color: #2bb8b0; font: 10px 'JetBrains Mono', monospace; letter-spacing: .08em; } .badge.warn { border-color: rgba(251,191,36,.6); color: #fbbf24; }
	.go { display: inline-flex; align-items: center; min-height: 24px; margin-top: 10px; color: #2bb8b0; font: 12px 'JetBrains Mono', monospace; text-decoration: none; letter-spacing: .06em; } .go:hover { text-decoration: underline; }
	.claim { margin-top: 18px; color: #71829a; font: 11px 'JetBrains Mono', monospace; letter-spacing: .06em; }
	.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 260px), 1fr)); gap: 10px; margin-bottom: 14px; } .sc { border: 1px solid rgba(148,163,184,.25); padding: 14px 16px; display: grid; gap: 6px; min-width: 0; align-content: start; } .sc .k { margin: 0; font: 10px 'JetBrains Mono', monospace; letter-spacing: .14em; color: #71829a; } .sc h2 { margin: 0; font: 500 20px 'Space Grotesk', sans-serif; overflow-wrap: anywhere; } .sc .st { margin: 0; font: 12px 'JetBrains Mono', monospace; display: flex; gap: 6px; align-items: center; flex-wrap: wrap; } .sc .d { margin: 0; color: #94a3b8; font-size: 12.5px; line-height: 1.55; }
	.sc.released { border-color: rgba(43,184,176,.55); } .sc.released .st { color: #2bb8b0; } .sc.fed { border-color: rgba(167,139,250,.55); } .sc.fed .st { color: #c4b5fd; } .sc.auth .st { color: #cbd5e1; }
	.lane { display: grid; gap: 8px; } .ln { margin: 0; font: 600 11px 'JetBrains Mono', monospace; letter-spacing: .14em; } .ln.released { color: #2bb8b0; } .ln.fed { color: #c4b5fd; }
	.wall { margin: 14px 0; border-block: 1px dashed rgba(248,113,113,.5); padding: 8px; text-align: center; display: grid; gap: 2px; } .wall span { font: 600 12px 'JetBrains Mono', monospace; letter-spacing: .16em; color: #fca5a5; } .wall small { color: #94a3b8; font-size: 11px; }
	.actions { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 250px), 1fr)); gap: 10px; } .act { display: grid; gap: 8px; padding: 14px 16px; border: 1px solid rgba(148,163,184,.3); text-decoration: none; color: #e2e8f0; min-height: 24px; align-content: start; } .act b { font: 600 12.5px 'JetBrains Mono', monospace; letter-spacing: .06em; } .act span { color: #a7b8c9; font-size: 13px; line-height: 1.5; } .act i { font: normal 12px 'JetBrains Mono', monospace; color: #2bb8b0; }
	.links { display: flex; flex-wrap: wrap; gap: 14px; } .links a { display: inline-flex; align-items: center; min-height: 24px; color: #2bb8b0; font: 12px 'JetBrains Mono', monospace; } .act.released { border-color: rgba(43,184,176,.6); } .act.fed { border-color: rgba(167,139,250,.6); } .act.fed i { color: #c4b5fd; } .act.ev { border-color: rgba(148,163,184,.5); } .act:hover, .act:focus-visible { background: rgba(148,163,184,.07); outline: none; } .act:focus-visible { box-shadow: 0 0 0 2px #fbbf24; } .gap { height: 12px; }
</style>
