<script lang="ts">
	import type { Snippet } from 'svelte';
	let { eyebrow = '', title, note = '', children }: { eyebrow?: string; title: string; note?: string; children?: Snippet } = $props();
</script>
<section class="panel"><header><div>{#if eyebrow}<span>{eyebrow}</span>{/if}<h2>{title}</h2></div>{#if note}<small>{note}</small>{/if}</header><div class="panel-body">{@render children?.()}</div></section>
<style>
	.panel{min-width:0;border:1px solid rgba(148,163,184,.16);background:linear-gradient(145deg,rgba(10,18,34,.95),rgba(5,10,21,.95))}.panel>header{display:flex;justify-content:space-between;align-items:start;gap:14px;padding:17px 18px 13px;border-bottom:1px solid rgba(148,163,184,.1)}.panel header span,.panel header small{color:#2bb8b0;font:7px 'JetBrains Mono',monospace;letter-spacing:.12em}.panel header small{color:#53647b}.panel h2{margin:6px 0 0;color:#e5f1f0;font:500 16px 'Space Grotesk',sans-serif}.panel-body{padding:16px 18px}
</style>
