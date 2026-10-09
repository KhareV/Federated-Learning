<script lang="ts">
	// The 10-round experiment lives in the Federation Studio now (the same 20 figures and 12 tables, run-specific exports, live start for both source modes, recorded runs).
	// This route is kept as a redirect so bookmarks, documentation links and ?run= deep links keep working.
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { focusHeading } from '$lib/product/observatory/focus';
	const run = $derived(page.url.searchParams.get('run') ?? 'recorded-A');
	onMount(() => { void goto(`/app/federation/live?run=${encodeURIComponent(run)}`, { replaceState: true }); });
</script>
<svelte:head><title>10-Round Federated Experiment | NHM</title></svelte:head>
<div class="eyebrow">NHM / RESEARCH OBSERVATORY / 10-ROUND FEDERATED EXPERIMENT</div>
<h1 tabindex="-1" use:focusHeading>Moved into the Federation Studio</h1>
<p class="lead" data-testid="fl10-moved">The 10-round federated experiment has moved into the Federation Studio, which now runs both the 3-round and the 10-round experiment with per-round evaluation, all 20 figures, all 12 tables and run-specific exports. The recorded NHM_FL10_001 runs open there as read-only historical evidence.</p>
<p class="lead"><a href={`/app/federation/live?run=${encodeURIComponent(run)}`}>Open it in the Federation Studio →</a></p>
<p class="dim"><a href="/app/observatory">← Observatory</a> · <a href="/app/observatory/outcomes">Scientific outcomes</a> · <a href="/app/federation">Federation Studio</a></p>
<style>
	.eyebrow{color:#2bb8b0;font:10px 'JetBrains Mono',monospace;letter-spacing:.14em}h1{font:500 clamp(28px,4vw,42px) 'Space Grotesk',sans-serif;margin:8px 0}.lead{max-width:880px;color:#cbd5e1;line-height:1.7;font-size:15px}.dim{color:#94a3b8;font-size:13px}a{color:#2bb8b0}
</style>
