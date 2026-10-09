<script lang="ts">
	// Metric across rounds as a plain SVG line chart: federated rounds as measured points, the frozen V2 reference as a dashed horizontal line, an optional nominal-interval band.
	// A round without a measured value (pending / failed / undefined) draws NOTHING: no interpolation, no zero-fill. The same values are always available as a table.
	interface Series { id: string; label: string; color: string; dashed?: boolean; values: (number | null)[] }
	let { title, caption, rounds, series, band = null, zeroLine = false, selected = null, onSelect, testid, metric }: {
		title: string; caption: string; rounds: number[]; series: Series[]; band?: { lower: (number | null)[]; upper: (number | null)[] } | null; zeroLine?: boolean;
		selected?: number | null; onSelect?: (round: number) => void; testid: string; metric: string } = $props();
	const W = 640, H = 250, L = 58, R = 16, T = 18, B = 40;
	const finite = (v: number | null): v is number => typeof v === 'number' && Number.isFinite(v);
	const all = $derived([...series.flatMap((s) => s.values), ...(band ? [...band.lower, ...band.upper] : []), ...(zeroLine ? [0] : [])].filter(finite));
	const lo = $derived(all.length ? Math.min(...all) : 0);
	const hi = $derived(all.length ? Math.max(...all) : 1);
	const pad = $derived((hi - lo || Math.abs(hi) || 1) * 0.1);
	const y0 = $derived(lo - pad), y1 = $derived(hi + pad);
	const x = (i: number) => L + (rounds.length <= 1 ? 0 : (i * (W - L - R)) / (rounds.length - 1));
	const y = (v: number) => T + ((y1 - v) / (y1 - y0)) * (H - T - B);
	const ticks = $derived(Array.from({ length: 5 }, (_, i) => y0 + ((y1 - y0) * i) / 4));
	const fmt = (v: number) => (Math.abs(v) >= 100 ? v.toFixed(0) : Math.abs(v) >= 1 ? v.toFixed(2) : v.toFixed(3));
	function path(values: (number | null)[]): string {
		let d = '', open = false;
		values.forEach((v, i) => { if (finite(v)) { d += `${open ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`; open = true; } else open = false; });
		return d;
	}
	const bandPath = $derived.by(() => {
		if (!band) return '';
		const idx = rounds.map((_, i) => i).filter((i) => finite(band.lower[i]) && finite(band.upper[i]));
		if (idx.length < 1) return '';
		const up = idx.map((i) => `${x(i).toFixed(1)},${y(band.upper[i] as number).toFixed(1)}`);
		const down = [...idx].reverse().map((i) => `${x(i).toFixed(1)},${y(band.lower[i] as number).toFixed(1)}`);
		return `M${up.join('L')}L${down.join('L')}Z`;
	});
	const description = $derived(`${title}. ${series.map((s) => `${s.label}: ${s.values.map((v, i) => `R${i} ${finite(v) ? fmt(v) : 'not available'}`).join(', ')}`).join('. ')}`);
</script>
<figure class="gc" data-testid={testid} data-metric={metric}>
	<figcaption><b>{title}</b><span>{caption}</span></figcaption>
	{#if !all.length}
		<p class="empty" role="status" data-testid={`${testid}-empty`}>No measured value yet. Points appear here as each round finishes scoring; nothing is drawn for a pending round.</p>
	{:else}
		<svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={description} preserveAspectRatio="xMidYMid meet">
			{#each ticks as t (t)}<line x1={L} x2={W - R} y1={y(t)} y2={y(t)} class="grid" /><text x={L - 8} y={y(t) + 4} class="tick" text-anchor="end">{fmt(t)}</text>{/each}
			{#if zeroLine && y0 < 0 && y1 > 0}<line x1={L} x2={W - R} y1={y(0)} y2={y(0)} class="zero" data-testid={`${testid}-zero`} /><text x={W - R} y={y(0) - 4} class="tick" text-anchor="end">0 = same as frozen V2</text>{/if}
			{#if bandPath}<path d={bandPath} class="band" data-testid={`${testid}-band`} />{/if}
			{#each rounds as r, i (r)}
				<line x1={x(i)} x2={x(i)} y1={T} y2={H - B} class={selected === r ? 'sel' : 'col'} />
				<text x={x(i)} y={H - B + 16} class="tick" text-anchor="middle">R{r}</text>
				<rect x={x(i) - 14} y={T} width="28" height={H - T - B} class="hit" role="button" tabindex="-1" aria-label={`Select round ${r}`} onclick={() => onSelect?.(r)} onkeydown={() => {}} />
			{/each}
			{#each series as s (s.id)}
				<path d={path(s.values)} fill="none" stroke={s.color} stroke-width="2" stroke-dasharray={s.dashed ? '6 5' : undefined} data-testid={`${testid}-line-${s.id}`} />
				{#each s.values as v, i (i)}{#if finite(v) && !s.dashed}<circle cx={x(i)} cy={y(v)} r={selected === rounds[i] ? 5 : 3.2} fill={s.color} data-testid={`${testid}-point-${s.id}-${rounds[i]}`}><title>{`${s.label} R${rounds[i]}: ${v}`}</title></circle>{/if}{/each}
			{/each}
			<text x={L} y={H - 6} class="tick">round</text>
		</svg>
		<ul class="key">{#each series as s (s.id)}<li><i style={`background:${s.color}`} class:dash={s.dashed}></i>{s.label}</li>{/each}{#if band}<li><i class="bandkey"></i>nominal 95% interval (participant-cluster bootstrap, no significance claim)</li>{/if}</ul>
	{/if}
</figure>
<style>
	.gc { margin: 0; display: grid; gap: 6px; min-width: 0; border: 1px solid rgba(148,163,184,.2); padding: 10px 12px; background: rgba(7,16,30,.55); }
	figcaption { display: grid; gap: 2px; } figcaption b { font: 600 12px 'JetBrains Mono', monospace; letter-spacing: .06em; color: #e5f1f0; } figcaption span { color: #94a3b8; font-size: 12px; line-height: 1.45; }
	svg { width: 100%; height: auto; max-height: 300px; display: block; } .grid { stroke: rgba(148,163,184,.14); } .tick { fill: #71829a; font: 10px 'JetBrains Mono', monospace; }
	.col { stroke: rgba(148,163,184,.08); } .sel { stroke: rgba(43,184,176,.55); stroke-width: 1.5; } .zero { stroke: #e5f1f0; stroke-width: 1; stroke-dasharray: 3 3; opacity: .7; }
	.band { fill: rgba(43,184,176,.16); stroke: none; } .hit { fill: transparent; cursor: pointer; }
	.key { display: flex; flex-wrap: wrap; gap: 4px 14px; list-style: none; margin: 0; padding: 0; color: #cbd5e1; font-size: 12px; } .key li { display: flex; align-items: center; gap: 6px; }
	.key i { width: 18px; height: 3px; display: inline-block; } .key i.dash { background: repeating-linear-gradient(90deg, currentColor 0 6px, transparent 6px 11px) !important; height: 2px; color: #f59e0b; } .bandkey { background: rgba(43,184,176,.4); height: 8px !important; }
	.empty { margin: 0; color: #94a3b8; font-size: 12px; } figure, p, li { overflow-wrap: anywhere; }
</style>
