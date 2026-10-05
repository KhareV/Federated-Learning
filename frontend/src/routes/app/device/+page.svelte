<script lang="ts">
	import { onMount } from 'svelte';
	import Panel from '$lib/components/dashboard/Panel.svelte';
	import SimulationBanner from '$lib/components/product/SimulationBanner.svelte';
	import { getProductStore } from '$lib/product/state.svelte';
	import { MONITORING_SCENARIOS, RECOMMENDED_SCENARIO, type DeviceState, type ScenarioId } from '$lib/product/types';

	const store = getProductStore();
	let scenario = $state<ScenarioId>(RECOMMENDED_SCENARIO);
	const device = $derived(store.selectedDevice);
	const STEPS: DeviceState[] = ['DETACHED', 'SCANNING', 'FOUND', 'PAIRING', 'CONNECTED'];
	const stepIndex = $derived(device ? STEPS.indexOf(device.connection_state) : -1);
	const scenarioOf = $derived(device ? store.scenarioFor(device.device_id) : null);
	const dstate = $derived(device?.connection_state ?? null);
	onMount(() => { void store.loadDevices(); void store.loadSessions(); });
</script>

<svelte:head><title>Device | NHM</title></svelte:head>

<SimulationBanner />
<div class="eyebrow">NHM / DEVICE</div>
<h1>Virtual wearable</h1>

{#if store.error}<p class="err" role="alert">{store.error}</p>{/if}

{#if !device}
	<Panel eyebrow="01 / ATTACH" title="No device">
		<p class="dim">No device is attached. Attach the NHM Virtual Wearable - a software source (WEARABLE_SIM_V1). It is not a physical device.</p>
		<label for="scenario">Monitoring scenario</label>
		<select id="scenario" bind:value={scenario}>
			{#each MONITORING_SCENARIOS as s}<option value={s.id}>{s.label} - {s.id}</option>{/each}
		</select>
		<p class="hint">Recommended for the faculty demo: <code>MIXED_MONITORING_SESSION</code> (streaming, context loss, quality degradation, disconnect, reconnect).</p>
		<button class="primary" onclick={() => store.attachVirtualWearable(scenario)} disabled={store.busy}>ATTACH NHM VIRTUAL WEARABLE</button>
	</Panel>
{:else}
	<Panel eyebrow="01 / DEVICE" title={device.display_name} note={device.adapter_type}>
		<div class="badges"><span class="sim">SIMULATED</span><span>{device.simulation_version}</span><span>{device.source_mode}</span></div>
		<dl>
			<dt>DEVICE ID</dt><dd data-testid="device-id">{device.device_id}</dd>
			<dt>PROVENANCE</dt><dd>{device.source_dataset_id} (software simulation)</dd>
			<dt>SCENARIO</dt><dd data-testid="device-scenario">{scenarioOf ?? 'select when creating a session'}</dd>
			<dt>CONNECTION STATE</dt><dd><strong data-testid="device-state">{device.connection_state}</strong></dd>
			<dt>CAPABILITIES</dt><dd>ECG {device.capabilities.supports_ecg ? 'yes' : 'no'} / PPG waveform {device.capabilities.supports_ppg ? 'yes' : 'unavailable'} / SpO2 context {device.capabilities.supports_spo2_context ? 'where emitted' : 'no'} / source {Object.values(device.capabilities.nominal_source_rates_hz).join(', ')} Hz</dd>
			<dt>PHYSICAL HARDWARE</dt><dd>NOT CONNECTED / NOT IMPLEMENTED</dd>
		</dl>
		<ol class="steps" aria-label="Device lifecycle">
			{#each STEPS as step, i}<li class:done={stepIndex >= 0 && i < stepIndex} class:now={i === stepIndex} aria-current={i === stepIndex ? 'step' : undefined}>{step}</li>{/each}
		</ol>
		{#if dstate === 'DISCONNECTED' || dstate === 'RECONNECTING' || dstate === 'ERROR' || dstate === 'STREAMING' || dstate === 'STOPPED'}<p class="dim">Current state: <b>{dstate}</b></p>{/if}
		<div class="actions">
			<button class="primary" onclick={() => store.scan(device.device_id)} disabled={store.busy || !(dstate === 'DETACHED' || dstate === 'STOPPED' || dstate === 'DISCONNECTED')}>SCAN</button>
			<button class="primary" onclick={() => store.connect(device.device_id)} disabled={store.busy || dstate !== 'FOUND'}>PAIR / CONNECT</button>
			<button onclick={() => store.disconnect(device.device_id)} disabled={store.busy || !(dstate === 'CONNECTED' || dstate === 'STREAMING')}>DISCONNECT</button>
			{#if dstate === 'CONNECTED'}<a class="next" href="/app/monitoring">Continue to monitoring →</a>{/if}
		</div>
		<div class="live" role="status" aria-live="polite">Device state: {device.connection_state}</div>
	</Panel>
	{#if store.devices.length > 1}
		<Panel eyebrow="02 / DEVICES" title="Attached devices"><ul>{#each store.devices as d}<li><button class="link" onclick={() => (store.selectedDeviceId = d.device_id)}>{d.device_id}</button> {d.connection_state}</li>{/each}</ul></Panel>
	{/if}
{/if}

<style>
	.eyebrow { color: #2bb8b0; font: 10px 'JetBrains Mono', monospace; letter-spacing: .14em; } h1 { margin: 10px 0 18px; font: 500 clamp(26px, 4vw, 40px) 'Space Grotesk', sans-serif; }
	label { display: block; margin: 12px 0 6px; color: #94a3b8; font: 11px 'JetBrains Mono', monospace; letter-spacing: .1em; } select { width: 100%; max-width: 560px; padding: 11px 12px; border: 1px solid var(--nhm-border); background: #050a15; color: #eef7f6; }
	.dim, .hint { color: #94a3b8; font-size: 13px; line-height: 1.6; } code { font: 12px 'JetBrains Mono', monospace; color: #9fe7e1; } .err { color: #fecdd3; padding: 10px 12px; border: 1px solid rgba(251,113,133,.4); background: rgba(127,29,29,.2); }
	button { padding: 11px 16px; border: 1px solid var(--nhm-border); background: transparent; color: #e2e8f0; font: 600 12px 'JetBrains Mono', monospace; letter-spacing: .1em; cursor: pointer; } button.primary { background: #2bb8b0; color: #03110f; border-color: #2bb8b0; } button:disabled { opacity: .4; cursor: not-allowed; } button:hover:not(:disabled) { filter: brightness(1.12); } button.link { padding: 0; border: 0; color: #2bb8b0; text-decoration: underline; }
	.badges { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px; } .badges span { padding: 3px 9px; border: 1px solid var(--nhm-border); color: #cbd5e1; font: 10px 'JetBrains Mono', monospace; letter-spacing: .08em; } .badges .sim { border-color: #fbbf24; color: #fbbf24; }
	dl { display: grid; grid-template-columns: max-content 1fr; gap: 8px 20px; margin: 0 0 18px; font: 12px/1.5 'JetBrains Mono', monospace; } dt { color: #71829a; letter-spacing: .08em; } dd { margin: 0; overflow-wrap: anywhere; color: #e2e8f0; }
	.steps { display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 18px; padding: 0; list-style: none; } .steps li { padding: 6px 10px; border: 1px solid var(--nhm-border); color: #71829a; font: 10px 'JetBrains Mono', monospace; letter-spacing: .08em; } .steps li.done { color: #2bb8b0; border-color: rgba(43,184,176,.4); } .steps li.now { color: #03110f; background: #2bb8b0; border-color: #2bb8b0; font-weight: 700; }
	.actions { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; } .next { color: #2bb8b0; font: 12px 'JetBrains Mono', monospace; text-decoration: none; } ul { margin: 0; padding: 0; list-style: none; display: grid; gap: 6px; font-size: 12px; } .live { position: absolute; left: -9999px; }
	@media (max-width: 560px) { dl { grid-template-columns: 1fr; gap: 2px; } dd { margin-bottom: 10px; } .actions button { flex: 1 1 140px; } }
</style>
