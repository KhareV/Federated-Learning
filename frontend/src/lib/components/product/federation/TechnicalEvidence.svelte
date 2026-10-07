<script lang="ts">
	// Consistent disclosure for exact IDs, digests, raw events and claim-boundary text. Warnings that must stay visible never go in here.
	import type { Snippet } from 'svelte';
	let { label = 'TECHNICAL EVIDENCE', open = false, testid = undefined, children }: { label?: string; open?: boolean; testid?: string; children?: Snippet } = $props();
</script>
<details class="te" {open} data-testid={testid}>
	<summary><span class="chev" aria-hidden="true">▾</span> {label}</summary>
	<div class="body">{@render children?.()}</div>
</details>
<style>
	.te { border: 1px solid rgba(148,163,184,.18); background: rgba(7,16,30,.5); min-width: 0; } summary { cursor: pointer; padding: 8px 12px; min-height: 24px; box-sizing: border-box; font: 10px 'JetBrains Mono', monospace; letter-spacing: .12em; color: #94a3b8; list-style: none; display: flex; align-items: center; gap: 6px; }
	summary::-webkit-details-marker { display: none; } summary:focus-visible { outline: 2px solid #2bb8b0; outline-offset: 2px; } .chev { display: inline-block; transition: transform .15s; } .te:not([open]) .chev { transform: rotate(-90deg); }
	.body { padding: 4px 12px 12px; display: grid; gap: 8px; min-width: 0; overflow-wrap: anywhere; font-size: 12px; color: #cbd5e1; }
	@media (prefers-reduced-motion: reduce) { .chev { transition: none; } }
</style>
