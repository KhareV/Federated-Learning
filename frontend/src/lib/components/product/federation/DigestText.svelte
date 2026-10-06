<script lang="ts">
	import { shortDigest } from '$lib/product/federation/labels';
	let { value, label = 'digest' }: { value: string | null | undefined; label?: string } = $props();
	let copied = $state(false);
	async function copy() {
		if (!value) return;
		try { await navigator.clipboard.writeText(value); copied = true; setTimeout(() => (copied = false), 1200); } catch { /* clipboard unavailable: the full value is in the title */ }
	}
</script>
{#if value}
	<span class="d"><code title={value}>{shortDigest(value)}</code><button type="button" aria-label={`Copy full ${label}`} onclick={copy}>{copied ? 'copied' : 'copy'}</button></span>
{:else}<span class="none">--</span>{/if}
<style>
	.d { display: inline-flex; gap: 6px; align-items: center; max-width: 100%; } code { font: 11px 'JetBrains Mono', monospace; overflow-wrap: anywhere; }
	button { background: none; border: 1px solid rgba(148,163,184,.3); color: #94a3b8; font: 9px 'JetBrains Mono', monospace; padding: 1px 5px; min-width: 24px; min-height: 24px; cursor: pointer; } button:focus-visible { outline: 2px solid #2bb8b0; } .none { color: #71829a; }
</style>
