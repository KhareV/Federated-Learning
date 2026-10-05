<script lang="ts">
	// Rolling SIMULATED SOURCE ECG (360 Hz, ADC_COUNTS). null samples stay GAPS: segments are drawn
	// as separate polylines and the missing interval is shaded and labelled - never zero-filled,
	// interpolated, or flat-lined. y-scaling is a display transform only.
	import type { GapRun, WaveformSegment } from '$lib/product/waveform';
	let {
		segments, start, end, capacity, gaps = [], openGap = null, height = 190
	}: { segments: WaveformSegment[]; start: number; end: number; capacity: number; gaps?: GapRun[]; openGap?: GapRun | null; height?: number } = $props();

	const W = 900;
	const left = $derived(Math.max(0, end - capacity));
	const span = $derived(Math.max(1, capacity));
	const x = (index: number) => ((index - left) / span) * W;

	const range = $derived.by(() => {
		let lo = Infinity, hi = -Infinity;
		for (const seg of segments) for (const v of seg.values) { if (v < lo) lo = v; if (v > hi) hi = v; }
		if (!Number.isFinite(lo)) return { lo: -1, hi: 1 };
		if (hi - lo < 1) return { lo: lo - 1, hi: hi + 1 };
		const pad = (hi - lo) * 0.08;
		return { lo: lo - pad, hi: hi + pad };
	});
	const y = (v: number) => height - 6 - ((v - range.lo) / (range.hi - range.lo)) * (height - 12);
	const lines = $derived(segments.map((seg) => seg.values.map((v, i) => `${x(seg.start + i).toFixed(1)},${y(v).toFixed(1)}`).join(' ')));
	const visibleGaps = $derived([...gaps, ...(openGap ? [openGap] : [])].filter((g) => g.end >= left && g.start <= end));
</script>

<div class="plot" data-testid="waveform-plot" data-points={segments.reduce((n, s) => n + s.values.length, 0)} data-segments={segments.length} data-visible-gaps={visibleGaps.length}>
	<svg viewBox={`0 0 ${W} ${height}`} width="100%" height={height} preserveAspectRatio="none" role="img" aria-label="Simulated source ECG, rolling ten-second window, with gaps where the source delivered no data">
		<defs><pattern id="gap-hatch" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="8" stroke="#fb7185" stroke-width="2" opacity=".55" /></pattern></defs>
		{#each [0.25, 0.5, 0.75] as f}<line x1="0" x2={W} y1={height * f} y2={height * f} stroke="rgba(148,163,184,.1)" />{/each}
		{#each visibleGaps as gap}
			<rect class="gap" data-testid="waveform-gap" data-start={gap.start} data-end={gap.end} x={Math.max(0, x(gap.start))} y="0" width={Math.max(2, x(gap.end + 1) - Math.max(0, x(gap.start)))} height={height} fill="url(#gap-hatch)" />
		{/each}
		{#each lines as points}<polyline {points} fill="none" stroke="#2bb8b0" stroke-width="1.6" vector-effect="non-scaling-stroke" />{/each}
	</svg>
	{#if visibleGaps.length}<div class="gaplabel" role="status">SOURCE GAP - NO DATA DELIVERED (shown as a gap, not zero)</div>{/if}
</div>

<style>
	.plot { position: relative; border: 1px solid rgba(148,163,184,.16); background: #050a15; }
	svg { display: block; }
	.gaplabel { position: absolute; top: 8px; right: 10px; padding: 3px 8px; background: rgba(127,29,29,.7); color: #fecdd3; font: 10px 'JetBrains Mono', monospace; letter-spacing: .08em; }
</style>
