<script lang="ts">
	import WorkbenchPage from './WorkbenchPage.svelte';
	let { title, description }: { title: string; description: string } = $props();
</script>

<WorkbenchPage eyebrow="DEFERRED / OUT OF SCOPE" {title} {description}>
	<div class="deferred"><span>STATUS / DEFERRED</span><p>Federated learning, hardware integration, edge optimization, and privacy protocols are not part of the centralized software release.</p><small>This route is retained as a documented placeholder. It exposes no fabricated metrics or operational controls.</small></div>
</WorkbenchPage>

<style>
	.deferred { max-width: 720px; margin-top: 28px; padding: 24px; border: 1px solid rgba(251,191,36,.32); background: rgba(120,80,10,.12); color: #cbd5e1; }.deferred span, .deferred small { color: #fbbf24; font: 9px 'JetBrains Mono', monospace; letter-spacing: .1em; }.deferred p { margin: 18px 0 10px; font: 16px/1.6 Inter, sans-serif; }.deferred small { color: #94a3b8; letter-spacing: .04em; }
</style>
