<script lang="ts">
	import WorkbenchPage from '$lib/components/dashboard/WorkbenchPage.svelte';
	import TelemetryPlot from '$lib/components/dashboard/TelemetryPlot.svelte';
	import MetricTile from '$lib/components/dashboard/MetricTile.svelte';
	let paused = false;
	let showRaw = true;
	let windowSeconds = 3;
</script>

<svelte:head><title>ECG Analysis | NHM</title></svelte:head>

<WorkbenchPage eyebrow="03 / SIGNAL ANALYSIS / ECG" title="Read the electrical rhythm." description="Explore the processed cardiac signal and the variability hidden between beats. Every metric remains paired with its quality context.">
	<div class="toolbar"><label><input type="checkbox" bind:checked={showRaw} /> RAW CHANNEL</label><button on:click={() => (windowSeconds = Math.max(1, windowSeconds - 1))}>−</button><span>{windowSeconds}S WINDOW</span><button on:click={() => (windowSeconds = Math.min(10, windowSeconds + 1))}>+</button><button class:active={paused} on:click={() => (paused = !paused)}>{paused ? 'RESUME' : 'PAUSE'} / {paused ? '▶' : 'Ⅱ'}</button></div>
	<TelemetryPlot label={showRaw ? 'Raw + filtered ECG / AD8232' : 'Filtered ECG / AD8232'} value="72" unit="BPM" zoom={windowSeconds / 3} paused={paused} detail={paused ? 'PAUSED / INSPECTING' : `${windowSeconds}S / LIVE SYNTHETIC SIGNAL`} />
	<div class="metrics"><MetricTile label="Mean RR" value="833" unit="ms" detail="30 DETECTED BEATS" /><MetricTile label="SDNN" value="42" unit="ms" detail="RR VARIABILITY" tone="cyan" /><MetricTile label="RMSSD" value="31" unit="ms" detail="PARASYMPATHETIC INDEX" tone="teal" /><MetricTile label="pNN50" value="18" unit="%" detail="SUCCESSIVE DIFFERENCES" tone="amber" /></div>
</WorkbenchPage>

<style>
	.toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 18px; color: #94a3b8; font: 10px 'JetBrains Mono', monospace; letter-spacing: .1em; }.toolbar label { margin-right: auto; }.toolbar input { accent-color: #2bb8b0; }.toolbar button { border: 1px solid rgba(148,163,184,.25); border-radius: 0; padding: 7px 10px; color: #94a3b8; background: #080e1d; cursor: pointer; }.toolbar button:hover, .toolbar button.active { border-color: #2bb8b0; color: #2bb8b0; }.metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-top: 8px; }
	@media (max-width: 700px) { .metrics { grid-template-columns: 1fr 1fr; }.toolbar { flex-wrap: wrap; }.toolbar label { width: 100%; } }
</style>