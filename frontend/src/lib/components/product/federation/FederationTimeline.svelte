<script lang="ts">
	// Human-readable timeline first (derived from the reported state, no invented timestamps), then the raw event journal as evidence.
	import TechnicalEvidence from './TechnicalEvidence.svelte';
	import { humanTimeline } from '$lib/product/federation/presentation';
	import type { FederationView } from '$lib/product/federation/live-model';
	let { view }: { view: FederationView } = $props();
	const lines = $derived(humanTimeline(view));
</script>
<div class="tl" data-testid="human-timeline">
	{#if lines.length === 0}<p class="dim">Nothing has been reported yet.</p>{/if}
	<ol class="h">{#each lines.slice(-14) as l (l.key)}<li>{l.text}</li>{/each}</ol>
	<TechnicalEvidence label="RAW EVENT JOURNAL" testid="raw-journal">
		<p class="dim">{view.timeline.length} events kept · exactly as reported (sequence number, event kind).</p>
		<ol class="raw" data-testid="timeline">{#each view.timeline.slice(-40) as t}<li><code>{t.sequence}</code> {t.summary}</li>{/each}</ol>
	</TechnicalEvidence>
</div>
<style>
	.tl { display: grid; gap: 10px; min-width: 0; } .h { margin: 0; padding: 0; list-style: none; display: grid; gap: 4px; border-left: 2px solid rgba(167,139,250,.5); padding-left: 12px; font-size: 13px; color: #cbd5e1; } .h li { position: relative; line-height: 1.45; } .h li::before { content: ''; position: absolute; left: -17px; top: .55em; width: 7px; height: 7px; border-radius: 50%; background: #a78bfa; }
	.raw { list-style: none; margin: 0; padding: 0; max-height: 280px; overflow: auto; display: grid; gap: 3px; font: 11px 'JetBrains Mono', monospace; } .dim { margin: 0; color: #94a3b8; font-size: 12.5px; }
</style>
