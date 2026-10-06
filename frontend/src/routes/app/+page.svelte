<script lang="ts">
	import { onMount } from 'svelte';
	import Panel from '$lib/components/dashboard/Panel.svelte';
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

<div class="head"><div class="eyebrow">NHM / OVERVIEW</div><h1>Product workspace</h1><p>Every value on this page is read from the local product backend. Nothing is simulated by the browser.</p></div>

<div class="tiles">
	<MetricTile label="Identity" value={identity?.user_id ?? '--'} detail={identity ? `AUTH ${identity.auth_provider}${identity.demo_mode ? ' / OFFLINE DEMO' : ''}` : 'NOT SIGNED IN'} />
	<MetricTile label="Released model" value={system?.model_id ?? '--'} detail={`${system?.software_system ?? '--'} / SERVER-SIDE / ${system?.calibration_id ?? '--'}`} tone="cyan" />
	<MetricTile label="Persistence" value={system?.persistence_mode ?? '--'} detail="LOCAL DATABASE" />
	<MetricTile label="Hardware mode" value={system?.hardware_mode ?? '--'} detail={system?.physical_hardware_available === false ? 'PHYSICAL HARDWARE: NOT CONNECTED' : 'CHECKING'} tone="amber" />
</div>

<div class="grid">
	<Panel eyebrow="01 / DEVICE" title="Virtual wearable" note="SIMULATED">
		{#if store.devices.length === 0}<p class="dim">No device attached yet.</p>{:else}
			<p class="big">{connected.length} connected / {store.devices.length} attached</p>
			<ul>{#each store.devices as d}<li><code>{d.device_id}</code> <span class="badge">{d.connection_state}</span></li>{/each}</ul>
		{/if}
		<a class="go" href="/app/device">Open device page →</a>
	</Panel>
	<Panel eyebrow="02 / SESSIONS" title="Latest monitoring session" note="PERSISTED">
		{#if !latest}<p class="dim">No session yet.</p>{:else}
			<p class="big"><code>{latest.session_id}</code></p><p class="dim">State <span class="badge">{latest.state}</span> / scenario {latest.simulation_provenance?.scenario_id ?? '--'}</p>
		{/if}
		<a class="go" href="/app/monitoring">Open monitor →</a>
	</Panel>
	<Panel eyebrow="03 / PRODUCT STORY" title="Released monitoring ≠ federated development">
		<div class="two">
			<div><b>Released monitoring</b><p class="dim">{system?.model_id ?? 'MODEL_V2_FINAL'} runs server-side in {system?.software_system ?? 'SOFTWARE_SYSTEM_V2'}. This is what the Monitor page uses.</p></div>
			<div><b>Federated development</b>{#if fedEnabled}<p class="dim">Federated development: <span class="badge">ENGINEERING RUNTIME ENABLED</span> · engineering candidates: <b data-testid="overview-candidate-count">{fed.overview ? fed.overview.candidate_count : '--'}</b> · never automatically deployed.</p>{:else}<p class="dim">Federated development: <span class="badge warn">FEDERATION BACKEND NOT ENABLED</span></p>{/if}<a class="go" href="/app/federation">Federation →</a></div>
		</div>
	</Panel>
</div>
<p class="claim">{system?.claim ?? ''}</p>

<style>
	.eyebrow { color: #2bb8b0; font: 10px 'JetBrains Mono', monospace; letter-spacing: .14em; } h1 { margin: 10px 0 8px; font: 500 clamp(28px, 4vw, 42px) 'Space Grotesk', sans-serif; } .head p { color: #94a3b8; margin: 0 0 22px; max-width: 640px; line-height: 1.6; }
	.tiles :global(.metric-tile) { min-width: 0; } .tiles :global(.metric-value) { font-size: clamp(18px, 1.9vw, 26px); overflow-wrap: anywhere; } .tiles :global(.metric-detail) { overflow-wrap: anywhere; }
	.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 8px; margin-bottom: 14px; } .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 10px; }
	.big { margin: 0 0 6px; font: 500 18px 'Space Grotesk', sans-serif; overflow-wrap: anywhere; } .dim { color: #94a3b8; font-size: 13px; line-height: 1.6; } ul { margin: 8px 0; padding: 0; list-style: none; display: grid; gap: 6px; font-size: 12px; } code { font: 12px 'JetBrains Mono', monospace; overflow-wrap: anywhere; }
	.badge { padding: 2px 7px; border: 1px solid rgba(43,184,176,.5); color: #2bb8b0; font: 10px 'JetBrains Mono', monospace; letter-spacing: .08em; } .badge.warn { border-color: rgba(251,191,36,.6); color: #fbbf24; }
	.go { display: inline-flex; align-items: center; min-height: 24px; margin-top: 10px; color: #2bb8b0; font: 12px 'JetBrains Mono', monospace; text-decoration: none; letter-spacing: .06em; } .go:hover { text-decoration: underline; }
	.two { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; } .claim { margin-top: 18px; color: #71829a; font: 11px 'JetBrains Mono', monospace; letter-spacing: .06em; }
</style>
