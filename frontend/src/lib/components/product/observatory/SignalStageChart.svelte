<script lang="ts">
	import type { SignalStage } from '$lib/product/observatory/types';
	let { stage, startUs, endUs }: { stage: SignalStage; startUs: number; endUs: number } = $props();
	const left = 45, right = 910, top = 15, bottom = 170;
	function chartPaths(data: SignalStage, start: number, end: number): string[] {
		const points = data.points;
		const finite = points.filter((p) => p.value !== null).map((p) => p.value as number);
		if (!points.length || !finite.length) return [];
		const span = Math.max(1, end - start);
		const minimum = Math.min(...finite), maximum = Math.max(...finite);
		const spread = Math.max(1e-9, maximum - minimum);
		const paths: string[] = [];
		let current = '';
		for (const point of points) {
			if (point.value === null) {
				if (current) paths.push(current);
				current = '';
				continue;
			}
			const x = left + (point.timestamp_us - start) / span * (right - left);
			const y = bottom - (point.value - minimum) / spread * (bottom - top);
			current += `${current ? ' L' : 'M'}${x.toFixed(2)} ${y.toFixed(2)}`;
		}
		if (current) paths.push(current);
		return paths;
	}
	let paths = $derived(chartPaths(stage, startUs, endUs));
	let cursorIndex = $state(0);
	let selectedPoint = $derived(stage.points[Math.min(cursorIndex, Math.max(0, stage.points.length - 1))]);
</script>

<figure class="signal" data-testid={`signal-${stage.stage_id}`}>
	<figcaption><strong>{stage.stage_id}</strong><span>{stage.sample_rate_hz} Hz · {stage.unit}</span></figcaption>
	<svg viewBox="0 0 930 190" role="img" aria-label={`${stage.stage_id}: ${stage.displayed_point_count} actual sampled display points from ${stage.actual_point_count} selected positions; null gaps are not joined`} preserveAspectRatio="none">
		<title>{stage.stage_id}: bounded signal view with gaps preserved</title>
		<line x1={left} y1={bottom} x2={right} y2={bottom} class="axis" />
		<line x1={left} y1={top} x2={left} y2={bottom} class="axis" />
		{#each paths as path}<path d={path} class="wave" />{/each}
		<text x={left} y="185" class="axis-label">{startUs / 1_000_000}s source time</text>
		<text x={right} y="185" text-anchor="end" class="axis-label">{endUs / 1_000_000}s</text>
	</svg>
	<p class="caption">{stage.displayed_point_count} rendered actual points / {stage.actual_point_count} selected positions. {stage.display_is_decimated ? 'Display decimated; processing used the full canonical array.' : 'All selected positions shown.'} Missing points remain gaps.</p>
	{#if stage.points.length}
		<div class="cursor"><label for={`cursor-${stage.stage_id}`}>Inspect a rendered point</label><input id={`cursor-${stage.stage_id}`} type="range" min="0" max={stage.points.length - 1} value={cursorIndex} oninput={(event) => cursorIndex = Number(event.currentTarget.value)} /><output for={`cursor-${stage.stage_id}`}>Point {Math.min(cursorIndex, stage.points.length - 1) + 1}/{stage.points.length} · {selectedPoint.timestamp_us / 1_000_000}s source time · {selectedPoint.value === null ? 'MISSING / GAP' : `${selectedPoint.value.toPrecision(6)} ${stage.unit}`}{selectedPoint.source_index === null ? '' : ` · source index ${selectedPoint.source_index}`}</output></div>
	{/if}
</figure>

<style>
	.signal{min-width:0;margin:0;padding:14px;border:1px solid rgba(148,163,184,.22);background:rgba(9,18,32,.7)}
	figcaption{display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;margin-bottom:8px}
	figcaption strong{color:#e5f1f0;font:600 11px 'JetBrains Mono',monospace;overflow-wrap:anywhere}
	figcaption span,.caption{color:#94a3b8;font-size:11px;line-height:1.5}
	svg{display:block;width:100%;height:155px;background:#050b15;border:1px solid rgba(148,163,184,.14)}
	.axis{stroke:#526176;stroke-width:1}.wave{fill:none;stroke:#2bb8b0;stroke-width:1.7;vector-effect:non-scaling-stroke}
	.axis-label{fill:#94a3b8;font:10px 'JetBrains Mono',monospace}
	.caption{margin:8px 0 0}
	.cursor{display:grid;gap:7px;margin-top:11px;padding-top:11px;border-top:1px solid rgba(148,163,184,.14);color:#a7b8c9;font:11px 'JetBrains Mono',monospace}.cursor input{width:100%;accent-color:#2bb8b0;min-height:24px}.cursor output{overflow-wrap:anywhere}.cursor input:focus-visible{outline:2px solid #2bb8b0;outline-offset:2px}
</style>
