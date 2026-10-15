<script lang="ts">
	// Long explanatory text stays in the page (and in the DOM) but starts collapsed behind a short, plain label so the page scans quickly.
	import type { Snippet } from 'svelte';
	let { label = 'Show details', open = false, children }: { label?: string; open?: boolean; children?: Snippet } = $props();
</script>
<details class="more" {open}><summary>{label}</summary><div class="body">{@render children?.()}</div></details>
<style>
	.more { border-left: 2px solid rgba(43,184,176,.4); padding: 2px 0 2px 10px; margin: 2px 0 8px; min-width: 0; }
	summary { cursor: pointer; color: #9fe7e1; font: 12px 'JetBrains Mono', monospace; letter-spacing: .04em; min-height: 24px; display: list-item; }
	.body { padding-top: 6px; color: #cbd5e1; font-size: 13px; line-height: 1.6; overflow-wrap: anywhere; }
	.body :global(p) { margin: 0 0 8px; }
</style>
