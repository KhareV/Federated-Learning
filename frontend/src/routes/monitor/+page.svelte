<script lang="ts">
	// LEGACY ROUTE (retired as the product monitor in CAP-005): /monitor used to be a placeholder
	// shell with a fake "Authentication disabled" identity. The product monitor is /app/monitoring.
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	onMount(() => { void goto('/app/monitoring', { replaceState: true }); });
</script>

<svelte:head>
	<title>Monitor moved | NHM</title>
	<meta name="robots" content="noindex" />
</svelte:head>

<main class="moved">
	<p class="tag">NHM / LEGACY ROUTE</p>
	<h1>The product monitor moved.</h1>
	<p>This legacy address is no longer the product monitor. The live monitoring page for the virtual wearable is now:</p>
	<p><a class="go" href="/app/monitoring">Open /app/monitoring →</a></p>
	<p class="dim">Looking for the recorded-replay technical research tool? It is available as the <a href="/monitoring">research runtime tool</a>.</p>
</main>

<style>
	:global(body) { background: #030712; }
	.moved { min-height: 100vh; box-sizing: border-box; padding: clamp(24px, 8vw, 120px); color: #eef7f6; font-family: Inter, sans-serif; }
	.tag { color: #2bb8b0; font: 11px 'JetBrains Mono', monospace; letter-spacing: .16em; }
	h1 { margin: 14px 0 18px; font: 500 clamp(32px, 6vw, 64px)/1 'Space Grotesk', sans-serif; }
	p { max-width: 560px; color: #94a3b8; line-height: 1.7; }
	.go { display: inline-block; padding: 12px 18px; background: #2bb8b0; color: #03110f; font: 700 12px 'JetBrains Mono', monospace; letter-spacing: .1em; text-decoration: none; }
	.dim a { color: #2bb8b0; }
</style>
