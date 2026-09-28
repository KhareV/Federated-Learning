<script lang="ts">
	import { onMount } from 'svelte';
	import WorkbenchPage from './WorkbenchPage.svelte';
	import MetricTile from './MetricTile.svelte';
	import TelemetryPlot from './TelemetryPlot.svelte';
	import { api } from '$lib/services/api';

	let { eyebrow, title, description, endpoint = '', signal = '' }: { eyebrow: string; title: string; description: string; endpoint?: string; signal?: 'ecg' | 'ppg' | 'spo2' | '' } = $props();
	let data = $state<unknown>(null);
	let loading = $state(true);
	let error = $state('');
	let requestStatus = $state<'idle' | 'loading' | 'received' | 'unavailable'>('idle');
	const verifiedEndpoints = new Set(['/system/health', '/monitoring/sessions']);

	onMount(async () => {
		if (!endpoint) { loading = false; return; }
		if (!verifiedEndpoints.has(endpoint)) { loading = false; requestStatus = 'unavailable'; error = 'This service surface is not implemented by the current backend.'; return; }
		requestStatus = 'loading';
		try { data = await api.request(endpoint); requestStatus = 'received'; } catch (cause) { requestStatus = 'unavailable'; error = cause instanceof Error ? cause.message : 'Backend request failed'; } finally { loading = false; }
	});
</script>

<WorkbenchPage {eyebrow} {title} {description}>
	<div class="route-meta"><span>DATA CHANNEL / {requestStatus === 'received' ? 'LIVE API' : requestStatus === 'unavailable' ? 'UNAVAILABLE' : endpoint ? 'REQUESTING' : 'LOCAL VIEW'}</span><span>AUTH / DISABLED BY SCOPE</span><span>STATUS / RESEARCH</span></div>
	{#if signal}<div class="signal-layout"><TelemetryPlot label={`${signal.toUpperCase()} / analysis stream`} mode={signal} value="--" unit={signal === 'spo2' ? '%' : 'BPM'} detail="AWAITING LIVE OR REPLAY DATA" /><div class="metrics"><MetricTile label="Signal quality" value="--" unit="%" detail="AWAITING API DATA" /><MetricTile label="Confidence" value="--" detail="MODEL OUTPUT UNAVAILABLE" tone="cyan" /></div></div>
	{:else}<div class="metrics"><MetricTile label="Pipeline status" value={loading ? 'SYNC' : error ? 'WARN' : 'READY'} detail="BACKEND CONTRACT" tone={error ? 'amber' : 'teal'} /><MetricTile label="Records returned" value={data && Array.isArray(data) ? data.length : '--'} detail="LIVE API RESPONSE" tone="cyan" /><MetricTile label="Model status" value="--" detail="NO SYNTHETIC METRICS" /></div>{/if}
	{#if error}<div class="error">{error}</div>{:else if data !== null}<details><summary>Inspect service response</summary><pre>{JSON.stringify(data, null, 2)}</pre></details>{:else if loading}<div class="loading">REQUESTING SERVICE DATA...</div>{/if}
</WorkbenchPage>

<style>
	.route-meta { display: flex; flex-wrap: wrap; gap: 22px; padding: 14px 0; border-block: 1px solid rgba(148,163,184,.18); color: #64748b; font: 9px 'JetBrains Mono', monospace; letter-spacing: .1em; }.signal-layout { display: grid; grid-template-columns: minmax(0, 1fr) 260px; gap: 8px; margin-top: 28px; }.metrics { display: grid; grid-template-columns: 1fr; gap: 8px; align-content: start; }details { margin-top: 8px; border: 1px solid rgba(148,163,184,.18); background: #080e1d; }summary { padding: 16px 20px; color: #2bb8b0; cursor: pointer; font: 10px 'JetBrains Mono', monospace; letter-spacing: .1em; }pre { max-height: 300px; overflow: auto; margin: 0; padding: 20px; border-top: 1px solid rgba(148,163,184,.15); color: #9fe7e1; font: 11px/1.6 'JetBrains Mono', monospace; }.loading, .error { margin-top: 24px; color: #64748b; font: 10px 'JetBrains Mono', monospace; letter-spacing: .1em; }.error { color: #fecdd3; }
	@media (max-width: 700px) { .signal-layout { grid-template-columns: 1fr; }.metrics { grid-template-columns: 1fr 1fr; } }
</style>
