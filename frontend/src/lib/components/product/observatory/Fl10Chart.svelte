<script lang="ts">
	import { cell, type Fl10Spec, type Fl10View } from '$lib/product/observatory/fl10';
	let { spec, initialView = null }: { spec: Fl10Spec; initialView?: string | null } = $props();
	const W = 640, H = 340, L = 60, R = 16, T = 14, B = 52;
	const COLORS = ['#4ea1ff', '#f59e0b', '#34d399', '#c084fc', '#f87171', '#2dd4bf', '#d6b36a', '#cbd5e1', '#f472b6', '#22d3ee', '#a3e635'];
	let viewId = $state<string | null>(initialView);
	let hidden = $state<Record<string, boolean>>({});
	let tip = $state('Focus or hover a point to read its exact value.');
	let normalize = $state(false);
	const view = $derived<Fl10View>(spec.views.find((v) => v.id === viewId) ?? spec.views[0]);
	const series = $derived<{ name: string; x?: number[]; y?: (number | null)[]; values?: (number | null)[]; dashed?: boolean; default?: boolean }[]>(view.series ?? []);
	const visible = $derived(series.filter((s) => (hidden[`${view.id}|${s.name}`] ?? s.default === false) === false));
	function toggle(name: string) { const key = `${view.id}|${name}`; const s = series.find((x) => x.name === name); hidden = { ...hidden, [key]: !(hidden[key] ?? s?.default === false) }; }
	const isHidden = (name: string) => { const s = series.find((x) => x.name === name); return hidden[`${view.id}|${name}`] ?? s?.default === false; };
	const nums = (a: (number | null | undefined)[]) => a.filter((v): v is number => typeof v === 'number' && Number.isFinite(v));
	function niceTicks(lo: number, hi: number, n = 5): number[] {
		if (!(hi > lo)) return [lo];
		const span = hi - lo; const step0 = span / n; const mag = Math.pow(10, Math.floor(Math.log10(step0)));
		const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= step0) ?? step0;
		const out: number[] = []; for (let t = Math.ceil(lo / step) * step; t <= hi + 1e-12; t += step) out.push(Math.round(t / step) * step);
		return out;
	}
	const fmt = (v: number) => (Math.abs(v) >= 1000 || (Math.abs(v) > 0 && Math.abs(v) < 0.01) ? v.toExponential(1) : String(Math.round(v * 1000) / 1000));
	const xs = $derived(nums(visible.flatMap((s) => s.x ?? [])));
	const ys = $derived(nums(visible.flatMap((s) => (s.y ?? s.values ?? []) as (number | null)[])));
	const xr = $derived<[number, number]>(xs.length ? [Math.min(...xs), Math.max(...xs)] : [0, 1]);
	const yr = $derived.by<[number, number]>(() => {
		const extra = view.kind === 'curves' ? [0, 1] : view.kind === 'bars' || view.kind === 'stacked' ? [0] : [];
		const all = [...ys, ...extra, ...(typeof view.hline === 'number' ? [view.hline] : [])];
		if (!all.length) return [0, 1];
		const lo = Math.min(...all), hi = Math.max(...all); const pad = (hi - lo || 1) * 0.06;
		return [view.kind === 'curves' || view.kind === 'bars' || view.kind === 'stacked' ? Math.min(lo, 0) : lo - pad, hi + pad];
	});
	const px = (x: number) => L + ((x - xr[0]) / (xr[1] - xr[0] || 1)) * (W - L - R);
	const py = (y: number) => H - B - ((y - yr[0]) / (yr[1] - yr[0] || 1)) * (H - B - T);
	function path(s: { x?: number[]; y?: (number | null)[] }): string {
		let d = ''; let pen = false;
		(s.x ?? []).forEach((x, i) => { const y = s.y?.[i]; if (y === null || y === undefined) { pen = false; return; } d += `${pen ? 'L' : 'M'}${px(x).toFixed(1)},${py(y).toFixed(1)}`; pen = true; });
		return d;
	}
	// bars / stacked -------------------------------------------------------------------------------------------------------------
	const cats = $derived<string[]>(view.categories ?? []);
	const bx = (i: number) => L + (i + 0.1) * ((W - L - R) / Math.max(1, cats.length));
	const bw = $derived(((W - L - R) / Math.max(1, cats.length)) * 0.8);
	const stackedTop = $derived.by(() => (view.kind === 'stacked' ? cats.map((_, i) => visible.reduce((a, s) => a + (s.values?.[i] ?? 0), 0)) : []));
	const byr = $derived.by<[number, number]>(() => {
		if (view.kind === 'stacked') return [0, Math.max(...stackedTop, 1e-9) * 1.05];
		const vals = nums(visible.flatMap((s) => (s.values ?? []) as (number | null)[]));
		return [Math.min(0, ...vals), Math.max(...vals, 1e-9) * 1.08];
	});
	const bpy = (y: number) => H - B - ((y - byr[0]) / (byr[1] - byr[0] || 1)) * (H - B - T);
	// heatmap -------------------------------------------------------------------------------------------------------------------
	const hv = $derived(view.kind === 'heatmap' ? nums((view.values as (number | null)[][]).flat()) : []);
	function heat(v: number): string { const lo = Math.min(...hv), hi = Math.max(...hv); const t = hi > lo ? (v - lo) / (hi - lo) : 0.5; const r = Math.round(30 + 200 * t), g = Math.round(60 + 150 * t), b = Math.round(140 - 90 * t); return `rgb(${r},${g},${b})`; }
	// intervals ----------------------------------------------------------------------------------------------------------------
	const iv = $derived<{ label: string; point: number | null; lo: number | null; hi: number | null; valid: number; invalid: number }[]>(view.kind === 'intervals' ? view.rows : []);
	const ir = $derived.by<[number, number]>(() => { const a = nums(iv.flatMap((r) => [r.point, r.lo, r.hi, 0])); return a.length ? [Math.min(...a), Math.max(...a)] : [-1, 1]; });
	const ix = (v: number) => L + 90 + ((v - ir[0]) / (ir[1] - ir[0] || 1)) * (W - L - R - 90);
	const rows = $derived.by<string[][]>(() => {
		if (view.kind === 'lines' || view.kind === 'curves') return visible.flatMap((s) => (s.x ?? []).slice(0, view.kind === 'curves' ? 400 : 200).map((x, i) => [s.name, cell(x, 6), cell(s.y?.[i] ?? null, 6)]));
		if (view.kind === 'bars' || view.kind === 'stacked') return series.flatMap((s) => cats.map((c, i) => [s.name, c, cell(s.values?.[i] ?? null, 6)]));
		if (view.kind === 'heatmap') return (view.rows as string[]).flatMap((r, i) => (view.cols as string[]).map((c, j) => [r, c, view.values[i][j] === null ? 'NOT CAPTURED' : cell(view.values[i][j], 6)]));
		if (view.kind === 'intervals') return iv.map((r) => [r.label, cell(r.point), cell(r.lo), cell(r.hi), `${r.valid} valid / ${r.invalid} invalid`]);
		if (view.kind === 'confusion') return view.matrices.map((m: Record<string, number | string>) => [String(m.label), `TP ${m.TP}`, `FP ${m.FP}`, `TN ${m.TN}`, `FN ${m.FN}`, `N ${m.n}`]);
		if (view.kind === 'hist') return view.panels.flatMap((p: { name: string; edges: number[]; positive: number[]; negative: number[] }) => p.positive.map((v, i) => [p.name, `${p.edges[i].toFixed(2)}-${p.edges[i + 1].toFixed(2)}`, `positive ${v}`, `negative ${p.negative[i]}`]));
		if (view.kind === 'lineage') return view.states.map((s: Record<string, unknown>) => [String(s.state), String(s.sha256), String(s.previous ?? 'FL_INIT_V2'), String(s.accepted_updates), String(s.status), s.equals_frozen_reference === null ? 'n/a' : String(s.equals_frozen_reference)]);
		if (view.kind === 'diagram') return view.nodes.map((n: { label: string }) => [n.label]);
		return [];
	});
	const say = (t: string) => { tip = t; };
</script>
<figure class="chart" data-testid={`chart-${spec.id}`}>
	<figcaption><b>{spec.id.replace('FL10_', '')} · {spec.title}</b></figcaption>
	{#if spec.views.length > 1}
		<div class="views" role="group" aria-label="Select view">{#each spec.views as v (v.id)}<button class:on={v.id === view.id} aria-pressed={v.id === view.id} onclick={() => { viewId = v.id; }}>{v.label}</button>{/each}</div>
	{/if}
	{#if view.kind === 'lines' || view.kind === 'curves'}
		<div class="legend">{#each series as s, i (s.name)}<button class:off={isHidden(s.name)} aria-pressed={!isHidden(s.name)} onclick={() => toggle(s.name)}><i style={`background:${COLORS[i % COLORS.length]}`}></i>{s.name}</button>{/each}</div>
		<svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${spec.title}: ${view.label}. ${visible.length} visible series.`}>
			{#each niceTicks(yr[0], yr[1]) as t}<line x1={L} x2={W - R} y1={py(t)} y2={py(t)} class="grid" /><text x={L - 6} y={py(t) + 3} class="tick" text-anchor="end">{fmt(t)}</text>{/each}
			{#each niceTicks(xr[0], xr[1], 6) as t}<text x={px(t)} y={H - B + 14} class="tick" text-anchor="middle">{fmt(t)}</text>{/each}
			<line x1={L} x2={L} y1={T} y2={H - B} class="axis" /><line x1={L} x2={W - R} y1={H - B} y2={H - B} class="axis" />
			<text x={(L + W - R) / 2} y={H - 8} class="label" text-anchor="middle">{view.x_label}</text>
			<text transform={`translate(14 ${(T + H - B) / 2}) rotate(-90)`} class="label" text-anchor="middle">{view.y_label}</text>
			{#if view.diagonal}<line x1={px(0)} y1={py(0)} x2={px(1)} y2={py(1)} class="diag" />{/if}
			{#if typeof view.hline === 'number'}<line x1={L} x2={W - R} y1={py(view.hline)} y2={py(view.hline)} class="diag" /><text x={W - R} y={py(view.hline) - 3} class="tick" text-anchor="end">{view.hline_label}</text>{/if}
			{#each series as s, i (s.name)}{#if !isHidden(s.name)}
				<path d={path(s)} fill="none" stroke={COLORS[i % COLORS.length]} stroke-width="1.6" stroke-dasharray={s.dashed ? '5 4' : undefined} />
				{#if view.kind === 'lines'}{#each s.x ?? [] as x, k}{#if s.y?.[k] !== null && s.y?.[k] !== undefined}
					<circle cx={px(x)} cy={py(s.y[k] as number)} r="3.2" fill={COLORS[i % COLORS.length]} tabindex="0" role="img" aria-label={`${s.name}, x ${x}, value ${cell(s.y[k])}`}
						onfocus={() => say(`${s.name} · x ${x} · ${cell(s.y?.[k])}`)} onmouseenter={() => say(`${s.name} · x ${x} · ${cell(s.y?.[k])}`)}><title>{`${s.name}: x ${x}, ${cell(s.y[k])}`}</title></circle>
				{:else}<text x={px(x)} y={H - B - 4} class="undef" text-anchor="middle">U</text>{/if}{/each}{/if}
			{/if}{/each}
		</svg>
	{:else if view.kind === 'bars' || view.kind === 'stacked'}
		<div class="legend">{#each series as s, i (s.name)}<button class:off={isHidden(s.name)} aria-pressed={!isHidden(s.name)} onclick={() => toggle(s.name)}><i style={`background:${COLORS[i % COLORS.length]}`}></i>{s.name}</button>{/each}</div>
		<svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${spec.title}: ${view.label}`}>
			{#each niceTicks(byr[0], byr[1]) as t}<line x1={L} x2={W - R} y1={bpy(t)} y2={bpy(t)} class="grid" /><text x={L - 6} y={bpy(t) + 3} class="tick" text-anchor="end">{fmt(t)}</text>{/each}
			<line x1={L} x2={L} y1={T} y2={H - B} class="axis" /><line x1={L} x2={W - R} y1={H - B} y2={H - B} class="axis" />
			{#each cats as c, i}<text transform={`translate(${bx(i) + bw / 2} ${H - B + 10}) rotate(${cats.length > 8 ? -55 : 0})`} class="tick" text-anchor={cats.length > 8 ? 'end' : 'middle'}>{c}</text>{/each}
			<text x={(L + W - R) / 2} y={H - 4} class="label" text-anchor="middle">{view.x_label}</text>
			<text transform={`translate(14 ${(T + H - B) / 2}) rotate(-90)`} class="label" text-anchor="middle">{view.y_label}</text>
			{#each cats as c, i}
				{#if view.kind === 'stacked'}
					{#each visible as s, k}{@const below = visible.slice(0, k).reduce((a, q) => a + (q.values?.[i] ?? 0), 0)}{@const v = s.values?.[i] ?? 0}{@const colorIndex = series.findIndex((q) => q.name === s.name)}
						<rect x={bx(i)} width={bw} y={bpy(below + v)} height={Math.max(0, bpy(below) - bpy(below + v))} fill={COLORS[colorIndex % COLORS.length]} tabindex="0" role="img" aria-label={`${s.name} ${c} ${cell(v)}`} onfocus={() => say(`${s.name} · ${c} · ${cell(v)}`)} onmouseenter={() => say(`${s.name} · ${c} · ${cell(v)}`)}><title>{`${s.name} ${c}: ${cell(v)}`}</title></rect>{/each}
				{:else}
					{@const vs = series.filter((s) => !isHidden(s.name))}
					{#each vs as s, k}{@const v = s.values?.[i] ?? null}{@const w = bw / Math.max(1, vs.length)}{@const idx = series.findIndex((q) => q.name === s.name)}
						{#if v === null}<text x={bx(i) + k * w + w / 2} y={H - B - 3} class="undef" text-anchor="middle">U</text>
						{:else}<rect x={bx(i) + k * w} width={w * 0.94} y={Math.min(bpy(v), bpy(0))} height={Math.abs(bpy(0) - bpy(v))} fill={COLORS[idx % COLORS.length]} tabindex="0" role="img" aria-label={`${s.name} ${c} ${cell(v)}`}
							onfocus={() => say(`${s.name} · ${c} · ${cell(v)}`)} onmouseenter={() => say(`${s.name} · ${c} · ${cell(v)}`)}><title>{`${s.name} ${c}: ${cell(v)}`}</title></rect>{/if}
					{/each}
				{/if}
			{/each}
		</svg>
		{#if view.kind === 'stacked'}<p class="dim">Weights per round sum to {view.total_check.map((t: number) => t.toFixed(6)).join(', ')}.</p>{/if}
	{:else if view.kind === 'heatmap'}
		{@const rl = view.rows as string[]}{@const cl = view.cols as string[]}
		<svg viewBox={`0 0 ${W} ${40 + rl.length * 30}`} role="img" aria-label={`${spec.title}: ${view.label}`}>
			{#each cl as c, j}<text x={80 + j * ((W - 90) / cl.length) + (W - 90) / cl.length / 2} y="14" class="tick" text-anchor="middle">{c}</text>{/each}
			{#each rl as r, i}<text x="74" y={44 + i * 30} class="tick" text-anchor="end">{r}</text>
				{#each cl as c, j}{@const v = view.values[i][j]}{@const cw = (W - 90) / cl.length}
					<rect x={80 + j * cw} y={26 + i * 30} width={cw - 2} height="27" fill={v === null ? '#1f2937' : heat(v)} tabindex="0" role="img" aria-label={`${r} ${c} ${v === null ? 'NOT CAPTURED' : cell(v)}`} onfocus={() => say(`${r} · ${c} · ${v === null ? 'NOT CAPTURED' : cell(v)}`)} onmouseenter={() => say(`${r} · ${c} · ${v === null ? 'NOT CAPTURED' : cell(v)}`)}><title>{`${r} ${c}: ${v === null ? 'NOT CAPTURED' : cell(v)}`}</title></rect>
					<text x={80 + j * cw + cw / 2} y={44 + i * 30} class="cellv" text-anchor="middle">{v === null ? 'NC' : Math.abs(v) >= 100 ? Math.round(v) : v.toPrecision(3)}</text>{/each}{/each}
		</svg>
		<p class="dim">Colour scale: {view.value_label}; min {fmt(Math.min(...hv))}, max {fmt(Math.max(...hv))}. NC = NOT CAPTURED.</p>
	{:else if view.kind === 'hist'}
		<div class="panels">{#each view.panels as p (p.name)}
			{@const hmax = Math.max(1, ...p.positive, ...p.negative)}{@const hw = (W - L - R) / p.positive.length}
			<svg viewBox={`0 0 ${W} ${H - 60}`} role="img" aria-label={`Predicted probability histogram for ${p.name}`}>
				<text x={W / 2} y="12" class="label" text-anchor="middle">{p.name}</text>
				{#each p.positive as v, i}<rect x={L + i * hw} width={hw * 0.46} y={H - 60 - 36 - (p.negative[i] / hmax) * (H - 120)} height={(p.negative[i] / hmax) * (H - 120)} fill="#4ea1ff" tabindex="0" role="img" aria-label={`${p.name} bin ${i} negative ${p.negative[i]}`} onfocus={() => say(`${p.name} · bin ${p.edges[i].toFixed(2)}-${p.edges[i + 1].toFixed(2)} · negative ${p.negative[i]} · positive ${v}`)} onmouseenter={() => say(`${p.name} · bin ${p.edges[i].toFixed(2)}-${p.edges[i + 1].toFixed(2)} · negative ${p.negative[i]} · positive ${v}`)}><title>{`negative ${p.negative[i]}`}</title></rect>
					<rect x={L + i * hw + hw * 0.5} width={hw * 0.46} y={H - 60 - 36 - (v / hmax) * (H - 120)} height={(v / hmax) * (H - 120)} fill="#f59e0b" tabindex="0" role="img" aria-label={`${p.name} bin ${i} positive ${v}`} onfocus={() => say(`${p.name} · bin ${p.edges[i].toFixed(2)}-${p.edges[i + 1].toFixed(2)} · positive ${v} · negative ${p.negative[i]}`)} onmouseenter={() => say(`${p.name} · positive ${v}`)}><title>{`positive ${v}`}</title></rect>{/each}
				<line x1={L + view.threshold * (W - L - R)} x2={L + view.threshold * (W - L - R)} y1="18" y2={H - 96} class="thr" /><text x={L + view.threshold * (W - L - R) + 4} y="30" class="tick">threshold 0.5</text>
				<line x1={L} x2={W - R} y1={H - 96} y2={H - 96} class="axis" />{#each [0, 0.25, 0.5, 0.75, 1] as t}<text x={L + t * (W - L - R)} y={H - 80} class="tick" text-anchor="middle">{t}</text>{/each}
				<text x={W / 2} y={H - 66} class="label" text-anchor="middle">Predicted probability (20 fixed bins); blue = actual negative, orange = actual positive; peak count {hmax}</text>
			</svg>{/each}</div>
	{:else if view.kind === 'confusion'}
		<label class="norm"><input type="checkbox" bind:checked={normalize} /> Row-normalise (raw counts always shown)</label>
		<div class="panels">{#each view.matrices as m (m.label)}
			<div class="cm" role="group" aria-label={`Confusion matrix ${m.label}`} data-testid={`cm-${m.label}`}><b>{m.label}</b> <small>N = {m.n} · actual + {m.positives} · actual − {m.negatives}</small>
				<div class="grid2"><span></span><b>pred +</b><b>pred −</b>
					<b>actual +</b><span class="tp">TP {m.TP}{#if normalize}<br /><small>{m.positives ? ((m.TP / m.positives) * 100).toFixed(1) : 'UNDEFINED'}%</small>{/if}</span><span class="fn">FN {m.FN}{#if normalize}<br /><small>{m.positives ? ((m.FN / m.positives) * 100).toFixed(1) : 'UNDEFINED'}%</small>{/if}</span>
					<b>actual −</b><span class="fp">FP {m.FP}{#if normalize}<br /><small>{m.negatives ? ((m.FP / m.negatives) * 100).toFixed(1) : 'UNDEFINED'}%</small>{/if}</span><span class="tn">TN {m.TN}{#if normalize}<br /><small>{m.negatives ? ((m.TN / m.negatives) * 100).toFixed(1) : 'UNDEFINED'}%</small>{/if}</span></div></div>{/each}</div>
	{:else if view.kind === 'intervals'}
		<svg viewBox={`0 0 ${W} ${40 + iv.length * 28}`} role="img" aria-label={`${spec.title}: paired differences with nominal intervals`}>
			<line x1={ix(0)} x2={ix(0)} y1="8" y2={30 + iv.length * 28} class="thr" /><text x={ix(0)} y="6" class="tick" text-anchor="middle">0</text>
			{#each iv as r, i}<text x="12" y={34 + i * 28} class="tick">{r.label}</text>
				{#if r.lo !== null && r.hi !== null}<line x1={ix(r.lo)} x2={ix(r.hi)} y1={30 + i * 28} y2={30 + i * 28} stroke="#4ea1ff" stroke-width="2" />{/if}
				{#if r.point !== null}<circle cx={ix(r.point)} cy={30 + i * 28} r="4" fill="#f59e0b" tabindex="0" role="img" aria-label={`${r.label} difference ${cell(r.point)} interval ${cell(r.lo)} to ${cell(r.hi)}`} onfocus={() => say(`${r.label} · ${cell(r.point)} [${cell(r.lo)}, ${cell(r.hi)}] · ${r.valid} valid / ${r.invalid} invalid replicates`)} onmouseenter={() => say(`${r.label} · ${cell(r.point)} [${cell(r.lo)}, ${cell(r.hi)}]`)}><title>{`${r.label}: ${cell(r.point)}`}</title></circle>
				{:else}<text x={ix(0) + 6} y={34 + i * 28} class="undef">UNDEFINED</text>{/if}{/each}
			<text x={W / 2} y={38 + iv.length * 28} class="label" text-anchor="middle">{view.x_label} · nominal 95% paired participant-cluster interval · axis range {fmt(ir[0])} to {fmt(ir[1])}</text>
		</svg>
	{:else if view.kind === 'diagram'}
		<div class="diagram"><div class="col">{#each view.nodes as n}<span class="node">{n.label}</span>{/each}</div><div class="arrow" aria-hidden="true">→</div><div class="col">{#each view.stages as st}<span class="stage">{st}</span>{/each}</div></div>
		<p class="dim">{view.monitoring}</p>
	{:else if view.kind === 'lineage'}
		<ol class="lineage">{#each view.states as s (s.state)}<li><b>{s.state}</b> <code>{s.sha256.slice(0, 20)}…</code> ← <code>{(s.previous ?? 'FL_INIT_V2').slice(0, 12)}…</code> · accepted {s.accepted_updates} · {s.status}{#if s.equals_frozen_reference === true} · <span class="ok">= frozen reference</span>{:else if s.equals_frozen_reference === false} · <span class="bad">DIFFERS</span>{/if}</li>{/each}</ol>
	{/if}
	<div class="tip" aria-live="polite" data-testid="chart-tip">{tip}</div>
	<p class="cap">{spec.caption}</p>
	<p class="syn">{spec.synthetic_label}</p>
	<details class="datatable"><summary>Data table for this view ({rows.length} rows) · sources {spec.sources.join(', ')}</summary>
		<div class="scroll"><table><tbody>{#each rows.slice(0, 700) as r}<tr>{#each r as c}<td>{c}</td>{/each}</tr>{/each}</tbody></table></div>
		{#if rows.length > 700}<p class="dim">First 700 rows shown; the complete data is in the CSV export.</p>{/if}</details>
</figure>
<style>
	.chart{margin:0;display:grid;gap:8px;padding:12px;border:1px solid rgba(148,163,184,.22);background:rgba(10,15,31,.5);min-width:0}figcaption{font:13px 'Space Grotesk',sans-serif;color:#e2e8f0}svg{width:100%;height:auto;background:#050a15;max-width:100%}
	.grid{stroke:rgba(148,163,184,.14)}.axis{stroke:rgba(148,163,184,.55)}.diag{stroke:rgba(148,163,184,.5);stroke-dasharray:4 4}.thr{stroke:#e2e8f0;stroke-dasharray:5 4}.tick{fill:#94a3b8;font:10px 'JetBrains Mono',monospace}.label{fill:#a7b8c9;font:11px 'Space Grotesk',sans-serif}.undef{fill:#f87171;font:9px 'JetBrains Mono',monospace}.cellv{fill:#fff;font:10px 'JetBrains Mono',monospace}
	.views,.legend{display:flex;flex-wrap:wrap;gap:6px}button{background:#0a0f1f;color:#e2e8f0;border:1px solid rgba(148,163,184,.35);padding:4px 9px;min-height:28px;font:11px 'JetBrains Mono',monospace;cursor:pointer}button.on{border-color:#2bb8b0;color:#9fe8e3}button.off{opacity:.45;text-decoration:line-through}.legend i{display:inline-block;width:10px;height:10px;margin-right:6px}
	.tip{font:11px 'JetBrains Mono',monospace;color:#9fe8e3;min-height:16px;overflow-wrap:anywhere}.cap{color:#a7b8c9;font-size:12px;line-height:1.5;margin:0}.syn{display:inline-block;width:fit-content;border:1px solid rgba(167,139,250,.55);padding:3px 8px;color:#d8ccff;font:10px 'JetBrains Mono',monospace;margin:0}.dim{color:#94a3b8;font-size:12px;margin:0}
	.panels{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,290px),1fr));gap:10px}.cm{border:1px solid rgba(148,163,184,.25);padding:8px}.grid2{display:grid;grid-template-columns:auto 1fr 1fr;gap:4px;margin-top:6px;font:12px 'JetBrains Mono',monospace}.grid2 b{font-size:10px;color:#71829a;align-self:center}.grid2 span{border:1px solid rgba(148,163,184,.3);padding:10px 6px;text-align:center}.tp,.tn{border-color:rgba(167,139,250,.6)!important}.fp,.fn{border-color:rgba(251,191,36,.6)!important}.norm{font-size:12px;color:#a7b8c9}
	.diagram{display:flex;gap:12px;align-items:center;flex-wrap:wrap}.col{display:grid;gap:4px}.node{border:1px solid #4ea1ff;background:rgba(78,161,255,.08);padding:4px 8px;font:11px 'JetBrains Mono',monospace}.stage{border:1px solid #f59e0b;background:rgba(245,158,11,.07);padding:8px 10px;font-size:12px}.arrow{font-size:26px;color:#94a3b8}
	.lineage{padding-left:18px;display:grid;gap:4px;font-size:12px;color:#cbd5e1}.lineage code{color:#9fe7e1}.ok{color:#86efac}.bad{color:#fca5a5}.scroll{overflow:auto;max-height:260px}table{border-collapse:collapse;font-size:11px;width:100%}td{border-bottom:1px solid rgba(148,163,184,.15);padding:4px 8px;color:#cbd5e1;overflow-wrap:anywhere}summary{cursor:pointer;color:#94a3b8;font-size:12px}
</style>
