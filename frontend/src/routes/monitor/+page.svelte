<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '$lib/services/api';
	import { connectLive } from '$lib/services/websocket';
	import TelemetryPlot from '$lib/components/dashboard/TelemetryPlot.svelte';

	let systemStatus = 'CHECKING';
	let statusError = '';
	let liveStatus = 'CONNECTING';
	let liveData = $state<Record<string, number>>({ hr: 0, spo2: 0, ecg_sqi: 0, ppg_sqi: 0 });

	onMount(() => {
		const connection = connectLive('client_01', {
			onopen: () => (liveStatus = 'LIVE CHANNEL READY'),
			onclose: () => (liveStatus = 'CHANNEL CLOSED'),
			onerror: () => (liveStatus = 'CHANNEL UNAVAILABLE'),
			onmessage: (event) => { try { liveData = { ...liveData, ...JSON.parse(event.data) }; } catch { /* Keep the last valid reading. */ } }
		});

		void (async () => {
			try {
				const health = await api.health();
				systemStatus = health.status.toUpperCase();
			} catch (cause) {
				systemStatus = 'OFFLINE';
				statusError = cause instanceof Error ? cause.message : 'Backend unavailable';
			}
		})();

		return () => connection.close();
	});

</script>

<svelte:head>
	<title>Monitor | NHM</title>
	<meta name="description" content="NHM continuous health monitoring environment." />
</svelte:head>

<main class="monitor-shell">
	<header class="topbar">
		<a class="brand" href="/" aria-label="Return to NHM home"><span>N</span> NHM</a>
		<div class="topbar-meta"><span class:offline={systemStatus === 'OFFLINE'} class="status-dot"></span>{systemStatus} / LOCAL SYSTEM</div>
		<a class="logout" href="/">Exit monitor</a>
	</header>

	<section class="monitor-content">
		<div class="technical-line"><span>NHM / MONITORING ENVIRONMENT</span><span>{liveStatus} / RESEARCH PROTOTYPE / 01</span></div>
		<div class="heading-row">
			<div>
				<div class="eyebrow">CONTINUOUS PHYSIOLOGICAL INTELLIGENCE</div>
				<h1>Understand the pattern.</h1>
				<p class="lede">The dashboard migration is now anchored to the NHM visual system. Live signal, anomaly, federated learning, and research surfaces will land here without losing their existing backend contracts.</p>
			</div>
			<div class="identity-panel"><span>ACCESS MODE</span><strong>Authentication disabled</strong><small>Session and device IDs are data provenance only</small></div>
		</div>

		{#if statusError}<div class="notice">SYSTEM HEALTH / {statusError}</div>{/if}

		<div class="signal-grid">
			<TelemetryPlot label="ECG / ELECTRICAL CARDIAC SIGNAL" value={liveData.hr || '--'} unit="BPM" detail={liveStatus} />
			<TelemetryPlot label="PPG / OPTICAL PULSE WAVEFORM" mode="ppg" color="#0ea5e9" value={liveData.spo2 || '--'} unit="%" detail="MAX30102 / SENSOR ARRAY" />
			<article class="signal-card"><span>SpO₂ / BLOOD OXYGEN ESTIMATION</span><strong>{liveData.spo2 || '--'}<em>%</em></strong><small>EDGE FEATURE PROCESSING</small><div class="metric">{liveData.spo2 || '--'}<em>%</em></div></article>
		</div>

		<nav class="workbench" aria-label="Monitoring workbench">
			<a href="/overview">Overview <span>01</span></a>
			<a href="/monitoring">Live signals <span>02</span></a>
			<a href="/ai/insights">AI insights <span>03</span></a>
			<a href="/fl/overview">Federated learning <span>04</span></a>
			<a href="/research/results">Research results <span>05</span></a>
		</nav>
	</section>
</main>

<style>
	:global(body) { margin: 0; background: #030712; }
	.monitor-shell { min-height: 100vh; background: #030712; color: #eef7f6; font-family: Inter, sans-serif; }
	.topbar { display: flex; align-items: center; justify-content: space-between; min-height: 72px; padding: 0 clamp(20px, 5vw, 80px); border-bottom: 1px solid rgba(148,163,184,.18); }
	.brand { color: #eef7f6; font: 600 15px 'Space Grotesk', sans-serif; letter-spacing: .12em; text-decoration: none; }
	.brand span { display: inline-grid; place-items: center; width: 28px; height: 28px; margin-right: 8px; border: 1px solid #2bb8b0; color: #2bb8b0; }
	.topbar-meta, .technical-line, .eyebrow, .identity-panel span, .identity-panel small, .signal-card span, .signal-card small, .workbench span { font: 10px/1.4 'JetBrains Mono', monospace; letter-spacing: .12em; }
	.topbar-meta { color: #94a3b8; }.status-dot { display: inline-block; width: 7px; height: 7px; margin-right: 8px; border-radius: 50%; background: #2bb8b0; box-shadow: 0 0 14px #2bb8b0; }.status-dot.offline { background: #fb7185; box-shadow: 0 0 14px #fb7185; }
	.logout { border: 0; background: transparent; color: #94a3b8; font: 10px 'JetBrains Mono', monospace; letter-spacing: .12em; text-transform: uppercase; cursor: pointer; }.logout:hover { color: #2bb8b0; }
	.monitor-content { max-width: 1400px; margin: 0 auto; padding: clamp(32px, 6vw, 90px) clamp(20px, 5vw, 80px); }.technical-line { display: flex; justify-content: space-between; color: #64748b; }.heading-row { display: flex; justify-content: space-between; gap: 40px; margin: 70px 0 54px; }.eyebrow { color: #2bb8b0; }.heading-row h1 { max-width: 700px; margin: 18px 0; font: 500 clamp(48px, 8vw, 112px)/.9 'Space Grotesk', sans-serif; letter-spacing: 0; }.lede { max-width: 620px; color: #94a3b8; font-size: 17px; line-height: 1.7; }.identity-panel { align-self: end; min-width: 180px; padding: 20px; border-left: 1px solid #2bb8b0; background: rgba(15,23,42,.5); }.identity-panel span, .identity-panel small { display: block; color: #64748b; }.identity-panel strong { display: block; margin: 10px 0; font: 18px 'Space Grotesk', sans-serif; }.notice { margin-bottom: 24px; border: 1px solid rgba(251,113,133,.35); padding: 14px; color: #fecdd3; background: rgba(127,29,29,.18); font: 11px 'JetBrains Mono', monospace; }.signal-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px; background: rgba(148,163,184,.2); }.signal-card { min-height: 240px; padding: clamp(22px, 3vw, 38px); background: #080e1d; }.signal-card--teal { background: linear-gradient(135deg, rgba(43,184,176,.14), #080e1d 60%); }.signal-card span, .signal-card small { display: block; color: #64748b; }.signal-card strong { display: block; margin: 32px 0 10px; font: 500 24px 'Space Grotesk', sans-serif; }.wave { height: 52px; margin-top: 24px; opacity: .8; background-size: 30px 100%; background-repeat: repeat-x; }.wave--ecg { background-image: linear-gradient(135deg, transparent 47%, #2bb8b0 48%, #2bb8b0 52%, transparent 53%), linear-gradient(35deg, transparent 46%, #2bb8b0 47%, #2bb8b0 53%, transparent 54%); }.wave--ppg { background-image: radial-gradient(ellipse at 50% 100%, transparent 40%, #0ea5e9 42%, #0ea5e9 48%, transparent 50%); }.metric { margin-top: 40px; color: #2bb8b0; font: 500 54px 'Space Grotesk', sans-serif; }.metric em { color: #64748b; font: 14px 'JetBrains Mono', monospace; font-style: normal; }.workbench { display: grid; grid-template-columns: repeat(5, 1fr); margin-top: 54px; border-top: 1px solid rgba(148,163,184,.2); border-bottom: 1px solid rgba(148,163,184,.2); }.workbench a { display: flex; justify-content: space-between; gap: 12px; padding: 20px 14px; color: #eef7f6; border-right: 1px solid rgba(148,163,184,.2); font-family: 'Space Grotesk', sans-serif; text-decoration: none; }.workbench a:hover { color: #2bb8b0; background: rgba(43,184,176,.06); }.workbench span { color: #64748b; }
	@media (max-width: 800px) { .topbar-meta { display: none; }.heading-row { display: block; margin-top: 54px; }.identity-panel { margin-top: 32px; }.signal-grid, .workbench { grid-template-columns: 1fr; }.workbench a { border-right: 0; border-bottom: 1px solid rgba(148,163,184,.2); }.technical-line { gap: 12px; }.technical-line span:last-child { text-align: right; } }
</style>
