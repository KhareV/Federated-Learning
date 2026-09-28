<script lang="ts">
	// MultiLine — annotated multi-series line chart (pure SVG, no deps)
	let {
		series = [],
		xLabels = [],
		height = 180,
		yMin = 0,
		yMax = 1,
		yLabel = ''
	}: {
		series?: { name: string; color: string; values: number[] }[];
		xLabels?: string[];
		height?: number;
		yMin?: number;
		yMax?: number;
		yLabel?: string;
	} = $props();

	const W = 600, H = height;
	const PAD = { top: 14, right: 20, bottom: 28, left: 36 };
	const pw = W - PAD.left - PAD.right;
	const ph = H - PAD.top - PAD.bottom;

	function toX(i: number, len: number) {
		return PAD.left + (i / Math.max(1, len - 1)) * pw;
	}
	function toY(v: number) {
		return PAD.top + ph - ((v - yMin) / (yMax - yMin || 1)) * ph;
	}
	function pts(vals: number[]) {
		return vals.map((v, i) => `${toX(i, vals.length).toFixed(1)},${toY(v).toFixed(1)}`).join(' ');
	}

	const yTicks = $derived(() => {
		const steps = 4;
		return Array.from({length: steps + 1}, (_, i) => yMin + (i / steps) * (yMax - yMin));
	});
</script>

<svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} role="img" aria-label="line chart">
	<!-- Grid -->
	{#each yTicks() as tick}
		<line
			x1={PAD.left} y1={toY(tick)}
			x2={W - PAD.right} y2={toY(tick)}
			stroke="rgba(148,163,184,.1)" stroke-width="1"
		/>
		<text x={PAD.left - 4} y={toY(tick) + 4} text-anchor="end" fill="#64748b" font-size="9" font-family="JetBrains Mono, monospace">
			{tick.toFixed(2)}
		</text>
	{/each}

	<!-- X labels -->
	{#each xLabels as lbl, i}
		<text
			x={toX(i, xLabels.length)} y={H - 6}
			text-anchor="middle" fill="#64748b" font-size="9" font-family="JetBrains Mono, monospace"
		>{lbl}</text>
	{/each}

	<!-- Lines -->
	{#each series as s}
		{#if s.values.length > 1}
			<defs>
				<linearGradient id={`ml-fill-${s.name.replace(/\s/g,'')}`} x1="0" x2="0" y1="0" y2="1">
					<stop offset="0" stop-color={s.color} stop-opacity=".18" />
					<stop offset="1" stop-color={s.color} stop-opacity="0" />
				</linearGradient>
			</defs>
			<polygon
				points={`${PAD.left},${PAD.top+ph} ${pts(s.values)} ${toX(s.values.length-1, s.values.length)},${PAD.top+ph}`}
				fill={`url(#ml-fill-${s.name.replace(/\s/g,'')})`}
			/>
			<polyline
				points={pts(s.values)}
				fill="none" stroke={s.color} stroke-width="2"
				style={`filter:drop-shadow(0 0 4px ${s.color}60);vector-effect:non-scaling-stroke`}
			/>
			<!-- End dot -->
			<circle
				cx={toX(s.values.length-1, s.values.length)}
				cy={toY(s.values[s.values.length-1])}
				r="3" fill={s.color}
				style={`filter:drop-shadow(0 0 5px ${s.color})`}
			/>
		{/if}
	{/each}
</svg>

<!-- Legend -->
{#if series.length > 1}
	<div class="legend">
		{#each series as s}
			<span class="leg-item">
				<i style={`background:${s.color};box-shadow:0 0 5px ${s.color}`}></i>
				{s.name}
			</span>
		{/each}
	</div>
{/if}

<style>
	svg { display: block; }
	.legend { display: flex; gap: 16px; flex-wrap: wrap; margin-top: 6px; }
	.leg-item { display: flex; align-items: center; gap: 5px; color: #71829a; font: 9px 'JetBrains Mono', monospace; letter-spacing: .08em; }
	.leg-item i { display: inline-block; width: 20px; height: 2px; border-radius: 1px; }
</style>
