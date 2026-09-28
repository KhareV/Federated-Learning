<script lang="ts">
	import { onMount } from 'svelte';
	import WorkbenchPage from '$lib/components/dashboard/WorkbenchPage.svelte';
	import MetricTile from '$lib/components/dashboard/MetricTile.svelte';
	import { api, type InferenceMessage, type Prediction } from '$lib/services/api';
	import { connectLive } from '$lib/services/websocket';

	let sessionId = $state(''); let channel = $state('CONNECTING'); let error = $state(''); let latest = $state<InferenceMessage | null>(null); let history = $state<Prediction[]>([]);
	onMount(() => {
		void loadActiveSession();
		const socket = connectLive('central-monitor', { onopen: () => channel = 'LIVE', onclose: () => channel = 'CLOSED', onerror: () => channel = 'UNAVAILABLE', onmessage: (event) => { try { const message = JSON.parse(event.data) as InferenceMessage | { type: string }; if (message.type === 'inference') { const inference = message as InferenceMessage; if (inference.session_id === sessionId) { latest = inference; history = [{ id: inference.timestamp, prediction: inference.prediction, confidence: inference.confidence, probability_abnormal: inference.probability_abnormal, signal_quality: inference.signal_quality, timestamp: inference.timestamp }, ...history]; } } } catch { error = 'Received malformed stream data.'; } } });
		return () => socket.close();
	});
	async function loadActiveSession() { try { const sessions = await api.monitoring.getSessions(); const active = sessions.find((session) => session.status === 'active'); if (active) { sessionId = active.session_id; history = await api.monitoring.getPredictions(sessionId); } } catch (cause) { error = cause instanceof Error ? cause.message : 'Unable to load monitoring sessions.'; } }
	async function startSession() { error = ''; try { const session = await api.monitoring.startSession('replay-subject', 'software-replay'); sessionId = session.session_id; history = []; latest = null; } catch (cause) { error = cause instanceof Error ? cause.message : 'Unable to start session.'; } }
	async function stopSession() { if (!sessionId) return; error = ''; try { await api.monitoring.stopSession(sessionId); sessionId = ''; latest = null; } catch (cause) { error = cause instanceof Error ? cause.message : 'Unable to stop session.'; } }
</script>
<svelte:head><title>Central Monitoring | NHM</title></svelte:head>
<WorkbenchPage eyebrow="CENTRALIZED / MONITORING" title="Observe verified inference." description="This dashboard displays only persisted central-service data. Start a replay session, then send signal chunks through the documented replay command or API.">
	<div class="control"><span>CHANNEL / {channel}</span><span>SESSION / {sessionId || 'NONE'}</span><span>SOURCE / {latest?.source || 'UNAVAILABLE'}</span>{#if sessionId}<button onclick={stopSession}>STOP SESSION</button>{:else}<button onclick={startSession}>START REPLAY SESSION</button>{/if}</div>
	{#if error}<p class="error">{error}</p>{/if}
	<div class="metrics"><MetricTile label="Prediction" value={latest?.prediction || '--'} detail="CENTRALIZED MODEL OUTPUT" /><MetricTile label="Confidence" value={latest ? latest.confidence.toFixed(4) : '--'} detail="CALIBRATED WHEN AVAILABLE" tone="cyan" /><MetricTile label="Signal quality" value={latest?.signal_quality || '--'} detail="QUALITY GATE" tone="amber" /><MetricTile label="Model version" value={latest?.model_version || '--'} detail="RELEASE STATUS BLOCKED" tone="rose" /></div>
	<section class="history"><h2>Prediction history</h2>{#if !sessionId}<p>Start a session to receive replay or live chunks.</p>{:else if !history.length}<p>Awaiting a valid 10-second signal window.</p>{:else}<ul>{#each history as item}<li><span>{item.timestamp || '--'}</span><b>{item.prediction}</b><span>{item.signal_quality}</span><span>{item.confidence.toFixed(4)}</span></li>{/each}</ul>{/if}</section>
</WorkbenchPage>
<style>
	.control{display:flex;flex-wrap:wrap;gap:18px;align-items:center;padding:14px 0;border-block:1px solid rgba(148,163,184,.18);color:#64748b;font:9px 'JetBrains Mono',monospace;letter-spacing:.1em}.control button{margin-left:auto;padding:10px 12px;border:1px solid #2bb8b0;background:#2bb8b0;color:#03100f;font:9px 'JetBrains Mono',monospace;cursor:pointer}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:20px 0}.error{color:#fecdd3;font:11px 'JetBrains Mono',monospace}.history{border:1px solid rgba(148,163,184,.18);padding:18px}.history h2{margin:0 0 14px;font:500 16px 'Space Grotesk',sans-serif}.history p,.history li{color:#94a3b8;font:10px 'JetBrains Mono',monospace}.history ul{list-style:none;padding:0;margin:0}.history li{display:grid;grid-template-columns:1.4fr 1fr 1fr .7fr;gap:12px;padding:10px 0;border-top:1px solid rgba(148,163,184,.12)}.history b{color:#dce9e8}@media(max-width:800px){.metrics{grid-template-columns:1fr 1fr}.history li{grid-template-columns:1fr 1fr}.control button{margin-left:0}}
</style>
