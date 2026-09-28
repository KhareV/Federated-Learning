<script lang="ts">
	import { page } from '$app/state';
	import DashboardShell from '$lib/components/dashboard/DashboardShell.svelte';
	import { error as httpError } from '@sveltejs/kit';

	const route = $derived(page.url.pathname);
	if (route) throw httpError(404, `No NHM route exists at ${route}`);
</script>

<svelte:head>
	<title>{page.url.pathname.slice(1).replaceAll('/', ' / ').toUpperCase()} | NHM</title>
</svelte:head>

<DashboardShell>
<main class="compatibility-shell">
	<div class="technical-line"><span>NHM / ROUTE NOT FOUND</span><span>STATUS / 404</span></div>
	<section><div class="eyebrow">NO SUCH WORKBENCH SURFACE</div><h2>{page.url.pathname}</h2><p>This route is not part of the active NHM system. Return to the monitor or use the navigation to choose a supported workspace.</p><a href="/monitor">Return to monitor ↗</a></section>
</main>
</DashboardShell>

<style>
	.compatibility-shell { min-height: 60vh; box-sizing: border-box; padding: clamp(28px, 7vw, 100px); background-image: linear-gradient(rgba(43,184,176,.08) 1px, transparent 1px), linear-gradient(90deg, rgba(43,184,176,.08) 1px, transparent 1px); background-size: 52px 52px; }
	.technical-line { display: flex; justify-content: space-between; gap: 20px; color: #64748b; font: 10px 'JetBrains Mono', monospace; letter-spacing: .12em; }
	section { max-width: 900px; margin-top: clamp(70px, 12vh, 150px); }.eyebrow { color: #2bb8b0; font: 11px 'JetBrains Mono', monospace; letter-spacing: .18em; } h2 { margin: 22px 0; font: 500 clamp(44px, 7vw, 96px)/.94 'Space Grotesk', sans-serif; } p { max-width: 540px; color: #94a3b8; font-size: 17px; line-height: 1.7; } a { display: inline-block; margin-top: 28px; color: #2bb8b0; font: 12px 'JetBrains Mono', monospace; letter-spacing: .1em; text-decoration: none; text-transform: uppercase; } pre { max-width: 100%; overflow: auto; margin-top: 32px; padding: 18px; border: 1px solid rgba(43,184,176,.25); color: #9fe7e1; background: rgba(15,23,42,.65); font: 12px/1.6 'JetBrains Mono', monospace; }.data-state { margin-top: 32px; color: #64748b; font: 11px 'JetBrains Mono', monospace; letter-spacing: .1em; }.data-state--error { color: #fecdd3; }
	@media (max-width: 640px) { .technical-line { display: block; }.technical-line span { display: block; margin-bottom: 8px; } }
</style>