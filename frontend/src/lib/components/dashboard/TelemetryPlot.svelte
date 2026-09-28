<script lang="ts">
	import PhysiologicalWaveform from '$lib/components/landing/PhysiologicalWaveform.svelte';
	let { label, mode = 'ecg', color = '#2bb8b0', value = '--', unit = '', detail = '', paused = false, zoom = 1 }: { label: string; mode?: 'ecg' | 'ppg' | 'spo2'; color?: string; value?: string | number; unit?: string; detail?: string; paused?: boolean; zoom?: number } = $props();
</script>

<article class="plot-panel" style={`--plot-color:${color}`}>
	<header><span>{label}</span><strong>{value}<small>{unit}</small></strong></header>
	<div class="plot-grid"><PhysiologicalWaveform {mode} color={color} speed={paused ? 0 : 0.55} {zoom} amplitude={0.72} /></div>
	<footer><span>{detail || 'LOCAL / LIVE'}</span><span>QUALITY / TRACKING</span></footer>
</article>

<style>
	.plot-panel { overflow: hidden; border: 1px solid rgba(148,163,184,.18); background: #080e1d; }.plot-panel header { display: flex; align-items: end; justify-content: space-between; gap: 16px; padding: 22px 22px 0; }.plot-panel header span, .plot-panel footer { color: #64748b; font: 10px 'JetBrains Mono', monospace; letter-spacing: .1em; text-transform: uppercase; }.plot-panel strong { color: var(--plot-color); font: 500 26px 'Space Grotesk', sans-serif; }.plot-panel strong small { margin-left: 4px; color: #64748b; font: 10px 'JetBrains Mono', monospace; }.plot-grid { height: 170px; margin-top: 8px; padding: 24px 10px 0; background-image: linear-gradient(rgba(148,163,184,.07) 1px, transparent 1px), linear-gradient(90deg, rgba(148,163,184,.07) 1px, transparent 1px); background-size: 36px 36px; }.plot-panel :global(.waveform) { width: 100%; height: 100%; }.plot-panel footer { display: flex; justify-content: space-between; padding: 0 22px 18px; font-size: 8px; }
</style>