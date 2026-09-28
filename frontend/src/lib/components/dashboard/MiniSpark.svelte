<script lang="ts">
	// MiniSpark — tiny inline animated sparkline
	let { values = [], color = '#2bb8b0', height = 40, width = 120, animated = true }:
		{ values?: number[]; color?: string; height?: number; width?: number; animated?: boolean } = $props();

	const pts = $derived(() => {
		if (!values.length) return '';
		const mn = Math.min(...values), mx = Math.max(...values);
		const range = mx - mn || 1;
		return values.map((v, i) => {
			const x = (i / (values.length - 1)) * width;
			const y = height - ((v - mn) / range) * (height - 4) - 2;
			return `${x.toFixed(1)},${y.toFixed(1)}`;
		}).join(' ');
	});

	// Animated demo data if no values provided
	import { onMount } from 'svelte';
	let demoVals = $state<number[]>(Array.from({length: 24}, (_, i) => 50 + Math.sin(i * 0.5) * 20 + Math.random() * 8));
	let timer: ReturnType<typeof setInterval>;
	onMount(() => {
		if (!values.length && animated) {
			timer = setInterval(() => {
				demoVals = [...demoVals.slice(1), 50 + Math.sin(Date.now() * 0.001) * 20 + Math.random() * 8];
			}, 300);
		}
		return () => clearInterval(timer);
	});

	const activeVals = $derived(values.length ? values : demoVals);
	const sparkPts = $derived(() => {
		if (!activeVals.length) return '';
		const mn = Math.min(...activeVals), mx = Math.max(...activeVals);
		const range = mx - mn || 1;
		return activeVals.map((v, i) => {
			const x = (i / (activeVals.length - 1)) * width;
			const y = height - ((v - mn) / range) * (height - 4) - 2;
			return `${x.toFixed(1)},${y.toFixed(1)}`;
		}).join(' ');
	});
</script>

<svg viewBox={`0 0 ${width} ${height}`} width={width} height={height} style="overflow:visible" role="img" aria-label="sparkline">
	<defs>
		<linearGradient id={`sg-${color.replace('#','')}`} x1="0" x2="0" y1="0" y2="1">
			<stop offset="0" stop-color={color} stop-opacity=".3" />
			<stop offset="1" stop-color={color} stop-opacity="0" />
		</linearGradient>
	</defs>
	{#if sparkPts()}
		<polygon points={`0,${height} ${sparkPts()} ${width},${height}`} fill={`url(#sg-${color.replace('#','')})`} />
		<polyline points={sparkPts()} fill="none" stroke={color} stroke-width="1.5" style={`filter:drop-shadow(0 0 3px ${color}80);vector-effect:non-scaling-stroke`} />
	{/if}
</svg>

<style>
	svg { display: block; }
</style>
