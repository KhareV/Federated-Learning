<script lang="ts">
	import { onMount } from 'svelte';
	import Panel from '$lib/components/dashboard/Panel.svelte';
	import SimulationBanner from '$lib/components/product/SimulationBanner.svelte';
	import { getProductStore } from '$lib/product/state.svelte';
	import { MONITORING_SCENARIOS, RECOMMENDED_SCENARIO, type DeviceState, type ScenarioId } from '$lib/product/types';

	const store = getProductStore();
	let scenario = $state<ScenarioId>(RECOMMENDED_SCENARIO);
	let loaded = $state(false);
	const device = $derived(store.selectedDevice);
	const STEPS: DeviceState[] = ['DETACHED', 'SCANNING', 'FOUND', 'PAIRING', 'CONNECTED'];
	const LABELS = ['ATTACH', 'SCAN', 'FOUND', 'PAIR / CONNECT', 'READY FOR MONITORING'];
	const stepIndex = $derived(device ? (device.connection_state === 'STREAMING' ? 4 : STEPS.indexOf(device.connection_state)) : -1);
	const scenarioOf = $derived(device ? store.scenarioFor(device.device_id) : null);
	const dstate = $derived(device?.connection_state ?? null);
	onMount(() => { void Promise.all([store.loadDevices(), store.loadSessions()]).finally(() => (loaded = true)); });
</script>

<svelte:head><title>Device | NHM</title></svelte:head>

<SimulationBanner />
<div class="eyebrow">NHM / DEVICE</div>
<h1>Virtual wearable</h1>
<p class="lead">A simulated ECG source for research monitoring. This lifecycle is software-only; no Bluetooth or physical sensor is connected.</p>
<div class="boundary"><strong>SIMULATED ONLY</strong><span>PHYSICAL HARDWARE: NOT CONNECTED / NOT IMPLEMENTED</span></div>

{#if store.error}<p class="err" role="alert">{store.error}</p>{/if}

{#if !loaded}<p role="status" class="dim">Loading virtual wearable and persisted sessions…</p>{/if}
{#if !device}
	<Panel eyebrow="01 / ATTACH" title="No virtual wearable attached">
		<p class="dim">No device is attached. Attach the NHM Virtual Wearable - a software source (WEARABLE_SIM_V1). It is not a physical device.</p>
		<label for="scenario">Monitoring scenario</label>
		<select id="scenario" bind:value={scenario}>
			{#each MONITORING_SCENARIOS as s}<option value={s.id}>{s.label} - {s.id}</option>{/each}
		</select>
		<p class="hint">Recommended for the faculty demo: <code>MIXED_MONITORING_SESSION</code> (streaming, context loss, quality degradation, disconnect, reconnect).</p>
		<button class="primary" onclick={() => store.attachVirtualWearable(scenario)} disabled={store.busy}>ATTACH NHM VIRTUAL WEARABLE</button>
		{#if store.busy}<p role="status" class="dim">Attaching simulated source…</p>{/if}
	</Panel>
{:else}
	<Panel eyebrow="01 / CONNECTION" title={device.display_name} note="SIMULATED SOURCE">
		<div class="current"><span>CURRENT SOFTWARE STATE</span><strong data-testid="device-state">{device.connection_state}</strong><small>{dstate === 'CONNECTED' ? 'Ready for a research monitoring session.' : dstate === 'FOUND' ? 'Select Pair / Connect to continue.' : dstate === 'DETACHED' ? 'Scan for the attached virtual source.' : 'This is a simulated source lifecycle, not a physical connection.'}</small></div>
		<ol class="steps" aria-label="Device lifecycle">
			{#each STEPS as step, i}<li class:done={stepIndex >= 0 && i < stepIndex} class:now={i === stepIndex} aria-current={i === stepIndex ? 'step' : undefined}><span>{i + 1}</span>{LABELS[i]}</li>{/each}
		</ol>
		{#if dstate === 'DISCONNECTED' || dstate === 'RECONNECTING' || dstate === 'ERROR' || dstate === 'STREAMING' || dstate === 'STOPPED'}<p class="dim">Current state: <b>{dstate}</b></p>{/if}
		<div class="actions">
			<button class="primary" onclick={() => store.scan(device.device_id)} disabled={store.busy || !(dstate === 'DETACHED' || dstate === 'STOPPED' || dstate === 'DISCONNECTED')}>SCAN</button>
			<button class="primary" onclick={() => store.connect(device.device_id)} disabled={store.busy || dstate !== 'FOUND'}>PAIR / CONNECT</button>
			<button onclick={() => store.disconnect(device.device_id)} disabled={store.busy || !(dstate === 'CONNECTED' || dstate === 'STREAMING')}>DISCONNECT</button>
			{#if dstate === 'CONNECTED'}<a class="next" href="/app/monitoring">CONTINUE TO MONITORING →</a>{/if}
		</div>
		{#if store.busy}<p role="status" class="dim">Updating virtual wearable connection…</p>{/if}
		<details class="technical"><summary>TECHNICAL DEVICE EVIDENCE</summary><dl>
			<dt>DEVICE ID</dt><dd data-testid="device-id">{device.device_id}</dd>
			<dt>ADAPTER</dt><dd>{device.adapter_type}</dd>
			<dt>PROVENANCE</dt><dd>{device.source_dataset_id} (software simulation)</dd>
			<dt>SCENARIO</dt><dd data-testid="device-scenario">{scenarioOf ?? 'select when creating a session'}</dd>
			<dt>VERSION / MODE</dt><dd>{device.simulation_version} / {device.source_mode}</dd>
			<dt>CAPABILITIES</dt><dd>ECG {device.capabilities.supports_ecg ? 'yes' : 'no'} / PPG waveform {device.capabilities.supports_ppg ? 'yes' : 'unavailable'} / SpO2 context {device.capabilities.supports_spo2_context ? 'where emitted' : 'no'} / source {Object.values(device.capabilities.nominal_source_rates_hz).join(', ')} Hz</dd>
			<dt>PHYSICAL HARDWARE</dt><dd>NOT CONNECTED / NOT IMPLEMENTED</dd>
		</dl></details>
		<div class="live" role="status" aria-live="polite">Device state: {device.connection_state}</div>
	</Panel>
	{#if store.devices.length > 1}
		<Panel eyebrow="02 / DEVICES" title="Attached virtual sources"><ul>{#each store.devices as d}<li><button class="link" onclick={() => (store.selectedDeviceId = d.device_id)} aria-current={d.device_id === device.device_id ? 'true' : undefined}>{d.display_name} · {d.device_id}</button> <span>{d.connection_state}</span></li>{/each}</ul></Panel>
	{/if}
{/if}

<style>
	.eyebrow { color: #2bb8b0; font: 10px 'JetBrains Mono', monospace; letter-spacing: .14em; } h1 { margin: 10px 0 18px; font: 500 clamp(26px, 4vw, 40px) 'Space Grotesk', sans-serif; }
	label { display: block; margin: 12px 0 6px; color: #94a3b8; font: 11px 'JetBrains Mono', monospace; letter-spacing: .1em; } select { width: 100%; max-width: 560px; padding: 11px 12px; border: 1px solid var(--nhm-border); background: #050a15; color: #eef7f6; }
	.dim, .hint { color: #94a3b8; font-size: 13px; line-height: 1.6; } code { font: 12px 'JetBrains Mono', monospace; color: #9fe7e1; } .err { color: #fecdd3; padding: 10px 12px; border: 1px solid rgba(251,113,133,.4); background: rgba(127,29,29,.2); }
	button { padding: 11px 16px; border: 1px solid var(--nhm-border); background: transparent; color: #e2e8f0; font: 600 12px 'JetBrains Mono', monospace; letter-spacing: .1em; cursor: pointer; } button.primary { background: #2bb8b0; color: #03110f; border-color: #2bb8b0; } button:disabled { opacity: .4; cursor: not-allowed; } button:hover:not(:disabled) { filter: brightness(1.12); } button.link { padding: 0; border: 0; color: #2bb8b0; text-decoration: underline; }
	dl { display: grid; grid-template-columns: max-content 1fr; gap: 8px 20px; margin: 0 0 18px; font: 12px/1.5 'JetBrains Mono', monospace; } dt { color: #71829a; letter-spacing: .08em; } dd { margin: 0; overflow-wrap: anywhere; color: #e2e8f0; }
	.steps { display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 18px; padding: 0; list-style: none; } .steps li { padding: 6px 10px; border: 1px solid var(--nhm-border); color: #71829a; font: 10px 'JetBrains Mono', monospace; letter-spacing: .08em; } .steps li.done { color: #2bb8b0; border-color: rgba(43,184,176,.4); } .steps li.now { color: #03110f; background: #2bb8b0; border-color: #2bb8b0; font-weight: 700; }
	.actions { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; } .next { color: #2bb8b0; font: 12px 'JetBrains Mono', monospace; text-decoration: none; } ul { margin: 0; padding: 0; list-style: none; display: grid; gap: 6px; font-size: 12px; } .live { position: absolute; left: -9999px; }
	@media (max-width: 560px) { dl { grid-template-columns: 1fr; gap: 2px; } dd { margin-bottom: 10px; } .actions button { flex: 1 1 140px; } }
	.lead{max-width:720px;margin:-6px 0 14px;color:#a7b8c9;font-size:14px;line-height:1.6}.boundary{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:16px;padding:10px 13px;border:1px solid rgba(251,191,36,.5);color:#fbbf24;font:11px 'JetBrains Mono',monospace}.boundary span{overflow-wrap:anywhere}
	.current{display:grid;gap:5px;margin-bottom:16px;padding:14px;border:1px solid rgba(43,184,176,.48);background:rgba(43,184,176,.05)}.current span{font:10px 'JetBrains Mono',monospace;color:#71829a;letter-spacing:.1em}.current strong{font:500 23px 'Space Grotesk',sans-serif;color:#9fe8e3}.current small{font-size:12px;color:#a7b8c9}.technical{margin-top:16px;border:1px solid var(--nhm-border);padding:10px 12px}.technical summary{cursor:pointer;color:#94a3b8;font:11px 'JetBrains Mono',monospace;letter-spacing:.1em}.technical dl{margin:16px 0 0}
	.steps{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:6px}.steps li{display:grid;gap:6px;padding:8px;overflow-wrap:anywhere}.steps li span{font-size:11px}.next{display:inline-flex;align-items:center;min-height:36px;padding:8px 14px;border:1px solid #2bb8b0;color:#03110f;background:#2bb8b0;font:700 11px 'JetBrains Mono',monospace;letter-spacing:.06em;text-decoration:none}.next:focus-visible,button:focus-visible,select:focus-visible,summary:focus-visible{outline:2px solid #fbbf24;outline-offset:3px}
	@media(max-width:760px){.steps{grid-template-columns:repeat(auto-fit,minmax(min(100%,125px),1fr))}.actions{align-items:stretch}.actions button,.actions .next{justify-content:center;flex:1 1 170px}}
</style>
