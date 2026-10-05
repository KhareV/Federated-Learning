<script lang="ts">
	import Panel from '$lib/components/dashboard/Panel.svelte';
	import { getProductStore } from '$lib/product/state.svelte';
	const store = getProductStore();
	const s = $derived(store.authState.system);
</script>
<svelte:head><title>System | NHM</title></svelte:head>
<div class="eyebrow">NHM / SYSTEM</div><h1>System</h1>
<Panel eyebrow="01 / BACKEND" title="GET /product/v1/system" note="READ FROM THE PRODUCT API">
	{#if s}<dl>{#each Object.entries(s) as [k, v]}<dt>{k}</dt><dd>{String(v)}</dd>{/each}</dl>{:else}<p>Not loaded.</p>{/if}
</Panel>
<style>.eyebrow{color:#2bb8b0;font:10px 'JetBrains Mono',monospace;letter-spacing:.14em}h1{margin:10px 0 18px;font:500 clamp(26px,4vw,40px) 'Space Grotesk',sans-serif}dl{display:grid;grid-template-columns:max-content 1fr;gap:6px 20px;margin:0;font:12px/1.5 'JetBrains Mono',monospace}dt{color:#71829a}dd{margin:0;overflow-wrap:anywhere}@media(max-width:560px){dl{grid-template-columns:1fr;gap:1px}dd{margin-bottom:8px}}</style>
