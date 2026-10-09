<script lang="ts">
	// ROC or precision-recall of the selected round overlaid on frozen V2, from the stored curves of both. Nothing is smoothed or resampled.
	let { kind, round, baseline, roundLabel, testid }: { kind: 'roc' | 'pr'; round: number[][] | null; baseline: number[][] | null; roundLabel: string; testid: string } = $props();
	const S = 220, P = 34;
	const path = (pts: number[][] | null) => (pts && pts.length ? pts.map((p, i) => `${i ? 'L' : 'M'}${(P + p[0] * (S - P - 10)).toFixed(1)},${(S - P - p[1] * (S - P - 10)).toFixed(1)}`).join('') : '');
	const xLabel = $derived(kind === 'roc' ? 'false-positive rate' : 'recall'), yLabel = $derived(kind === 'roc' ? 'true-positive rate' : 'precision');
</script>
<figure class="co" data-testid={testid}>
	<figcaption><b>{kind === 'roc' ? 'ROC' : 'PRECISION–RECALL'}</b><span>{roundLabel} vs frozen V2</span></figcaption>
	{#if !round}
		<p class="empty" role="status">Curves appear when this round has been scored.</p>
	{:else}
		<svg viewBox={`0 0 ${S} ${S}`} role="img" aria-label={`${kind === 'roc' ? 'ROC' : 'Precision-recall'} curves for ${roundLabel} and frozen V2`}>
			<rect x={P} y="10" width={S - P - 10} height={S - P - 10} class="frame" />
			{#if kind === 'roc'}<line x1={P} y1={S - P} x2={S - 10} y2="10" class="diag" />{/if}
			{#if baseline}<path d={path(baseline)} fill="none" stroke="#f59e0b" stroke-width="1.8" stroke-dasharray="5 4" data-testid={`${testid}-baseline`} />{/if}
			<path d={path(round)} fill="none" stroke="#2bb8b0" stroke-width="2" data-testid={`${testid}-round`} />
			<text x={(S + P) / 2} y={S - 8} class="t" text-anchor="middle">{xLabel}</text>
			<text x="10" y={(S - P) / 2} class="t" text-anchor="middle" transform={`rotate(-90 10 ${(S - P) / 2})`}>{yLabel}</text>
		</svg>
		<ul class="key"><li><i style="background:#2bb8b0"></i>{roundLabel}</li><li><i class="dash"></i>frozen V2</li></ul>
	{/if}
</figure>
<style>
	.co { margin: 0; display: grid; gap: 6px; min-width: 0; border: 1px solid rgba(148,163,184,.2); padding: 10px 12px; background: rgba(7,16,30,.55); } figcaption { display: grid; gap: 2px; }
	figcaption b { font: 600 12px 'JetBrains Mono', monospace; letter-spacing: .06em; color: #e5f1f0; } figcaption span { color: #94a3b8; font-size: 12px; }
	svg { width: 100%; max-width: 300px; height: auto; } .frame { fill: none; stroke: rgba(148,163,184,.3); } .diag { stroke: rgba(148,163,184,.3); stroke-dasharray: 3 3; } .t { fill: #71829a; font: 9px 'JetBrains Mono', monospace; }
	.key { display: flex; flex-wrap: wrap; gap: 4px 12px; list-style: none; margin: 0; padding: 0; color: #cbd5e1; font-size: 12px; } .key li { display: flex; align-items: center; gap: 6px; } .key i { width: 18px; height: 3px; display: inline-block; }
	.key i.dash { background: repeating-linear-gradient(90deg, #f59e0b 0 6px, transparent 6px 11px); height: 2px; } .empty { margin: 0; color: #94a3b8; font-size: 12px; }
</style>
