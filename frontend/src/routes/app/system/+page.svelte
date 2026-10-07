<script lang="ts">
	import Panel from '$lib/components/dashboard/Panel.svelte';
	import { getProductStore } from '$lib/product/state.svelte';
	const store = getProductStore();
	const s = $derived(store.authState.system);
</script>
<svelte:head><title>System | NHM</title></svelte:head>
<div class="eyebrow">NHM / SYSTEM</div><h1>System</h1>
<p class="lead">Current research product identity from the authenticated product API. This is configuration evidence, not a health score.</p>
{#if s}
	<div class="cards">
		<Panel eyebrow="AUTHENTICATION" title={s.auth_provider}><p>{s.demo_mode ? 'Offline DEMO workspace' : s.auth_status}</p></Panel>
		<Panel eyebrow="MONITORING RUNTIME" title={s.software_system}><p>{s.api_contract_version} · {s.product_api_version}</p></Panel>
		<Panel eyebrow="MODEL / CALIBRATION" title={s.model_id}><p>{s.calibration_id}</p></Panel>
		<Panel eyebrow="PERSISTENCE" title={s.persistence_mode}><p>Product session and evidence storage.</p></Panel>
		<Panel eyebrow="FEDERATION RUNTIME" title={s.federation_runtime}><p>Engineering development lane; no automatic candidate promotion.</p></Panel>
		<Panel eyebrow="HARDWARE MODE" title={s.hardware_mode}><p>Physical hardware available: {s.physical_hardware_available ? 'YES' : 'NO'}</p></Panel>
	</div>
	<details class="raw"><summary>RAW SYSTEM RESPONSE · TECHNICAL EVIDENCE</summary><dl>{#each Object.entries(s) as [k, v]}<dt>{k}</dt><dd>{String(v)}</dd>{/each}</dl></details>
{:else}<p role="status">System response is not available. Return to sign-in if the product backend is unavailable.</p>{/if}
<style>.eyebrow{color:#2bb8b0;font:10px 'JetBrains Mono',monospace;letter-spacing:.14em}h1{margin:10px 0 12px;font:500 clamp(26px,4vw,40px) 'Space Grotesk',sans-serif}.lead{max-width:680px;color:#94a3b8;font-size:14px;line-height:1.6}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,250px),1fr));gap:12px}.cards p{font-size:12px;color:#a7b8c9;overflow-wrap:anywhere}.raw{margin-top:16px;padding:12px;border:1px solid var(--nhm-border)}summary{cursor:pointer;color:#2bb8b0;font:11px 'JetBrains Mono',monospace;letter-spacing:.08em}summary:focus-visible{outline:2px solid #fbbf24;outline-offset:3px}dl{display:grid;grid-template-columns:max-content 1fr;gap:6px 20px;margin:16px 0 0;font:12px/1.5 'JetBrains Mono',monospace}dt{color:#71829a}dd{margin:0;overflow-wrap:anywhere}@media(max-width:560px){dl{grid-template-columns:1fr;gap:1px}dd{margin-bottom:8px}}</style>
