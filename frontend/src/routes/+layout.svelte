<script lang="ts">
	import '../app.css';
	import { SmoothCursor } from '$lib/components/magic/smooth-cursor';
	import { afterNavigate } from '$app/navigation';
	import { page } from '$app/state';
	import type { Snippet } from 'svelte';

	let { children }: { children?: Snippet } = $props();
	const path = $derived(page.url.pathname);
	// The landing page's smooth cursor is the site-wide pointer: it is mounted on every page, including the product workspace and sign-in.
	// /monitoring is the legacy research-runtime replay tool, NOT the product live monitor.
	const researchTool = $derived(path === '/monitoring' || path.startsWith('/monitoring/'));

	afterNavigate(({ to }) => {
		// Preserve native anchor navigation while making page-to-page transitions
		// settle into the same calm, editorial scroll used by the landing page.
		if (!to?.url.hash) window.scrollTo({ top: 0, left: 0, behavior: 'smooth' });
	});
</script>

<SmoothCursor />
{#if researchTool}
	<div class="research-tool" role="note" data-testid="research-tool-banner">
		<b>RESEARCH RUNTIME TOOL</b> - recorded-replay technical view of the frozen POST /v1/infer-window contract. It is not the product live monitor.
		<a href="/app/monitoring">Open the product monitor →</a>
	</div>
{/if}
{@render children?.()}

<style>
	.research-tool { padding: 9px 16px; background: #1e293b; color: #e2e8f0; font: 11px/1.5 'JetBrains Mono', monospace; letter-spacing: .06em; text-align: center; }
	.research-tool b { color: #fbbf24; } .research-tool a { margin-left: 10px; color: #2bb8b0; }
</style>
