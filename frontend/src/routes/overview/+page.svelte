<script lang="ts">
	import { onMount } from 'svelte';
	import WorkbenchPage from '$lib/components/dashboard/WorkbenchPage.svelte';
	import MetricTile from '$lib/components/dashboard/MetricTile.svelte';
	import { api, type Session } from '$lib/services/api';
	let sessions = $state<Session[]>([]); let model = $state<{ available: boolean; model_version: string | null; release_status: string } | null>(null); let error = $state('');
	onMount(async () => { try { [sessions, model] = await Promise.all([api.monitoring.getSessions(), api.model()]); } catch (cause) { error = cause instanceof Error ? cause.message : 'Central service is unavailable.'; } });
</script>
<svelte:head><title>Centralized ECG Monitor | NHM</title></svelte:head>
<WorkbenchPage eyebrow="CENTRALIZED / ECG" title="Research monitoring, honestly." description="A centralized ECG research prototype with explicit quality states, immutable evidence, and no diagnosis claim.">
	<div class="metrics"><MetricTile label="Active sessions" value={sessions.filter((session) => session.status === 'active').length} detail="PERSISTED BACKEND DATA" /><MetricTile label="Recent sessions" value={sessions.length} detail="PERSISTED BACKEND DATA" tone="cyan" /><MetricTile label="Model" value={model?.model_version || '--'} detail={model?.available ? 'LOADED' : 'UNAVAILABLE'} /><MetricTile label="Release gate" value={model?.release_status || '--'} detail="EXTERNAL MIT-BIH REQUIRED" tone="amber" /></div>
	{#if error}<p class="error">{error}</p>{/if}
	<section><h2>Current scope</h2><p>ECG-only central inference is active. Multimodal supervised classification is blocked until compatible labelled data is supplied. Federated learning, privacy mechanisms, edge optimization, and hardware operation are deferred.</p><a href="/monitoring">OPEN CENTRAL MONITOR →</a></section>
</WorkbenchPage>
<style>.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:24px}section{max-width:720px;padding:20px;border:1px solid rgba(148,163,184,.18)}h2{margin:0;font:500 18px 'Space Grotesk',sans-serif}p{color:#94a3b8;font-size:13px;line-height:1.7}a{color:#2bb8b0;font:10px 'JetBrains Mono',monospace;letter-spacing:.1em;text-decoration:none}.error{color:#fecdd3}@media(max-width:800px){.metrics{grid-template-columns:1fr 1fr}}</style>
