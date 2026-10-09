<script lang="ts">
	// Descriptive comparison of any two EVALUATED rounds of this run (point differences from the stored records). Nominal paired intervals exist only for the predeclared pair (see FIG16 / TAB02).
	import { display } from '$lib/product/studio/metrics';
	import type { StudioStore } from '$lib/product/studio/store.svelte';
	let { studio }: { studio: StudioStore } = $props();
	const done = $derived(studio.records.filter((r) => r.evaluation_status === 'COMPLETED').map((r) => r.round_id));
	let a = $state<number | null>(null);
	let b = $state<number | null>(null);
	const metric = $derived(studio.selectedMetric);
	const pair = $derived(studio.summary?.comparison);
	const A = $derived(a ?? (pair && done.includes(pair.comparator_round) ? pair.comparator_round : (done[0] ?? 0)));
	const B = $derived(b ?? (pair && done.includes(pair.endpoint_round) ? pair.endpoint_round : (done.at(-1) ?? 0)));
	const KEYS = ['AUPRC', 'AUROC', 'F1', 'recall', 'specificity', 'balanced_accuracy', 'accuracy', 'precision', 'BCE', 'Brier', 'TP', 'FP', 'TN', 'FN'];
	const rec = (r: number) => studio.records.find((x) => x.round_id === r);
	const val = (r: number, k: string): number | null => { const v = rec(r)?.metric_result?.[k]; return typeof v === 'number' ? v : null; };
	const diff = (k: string) => { const x = val(A, k), y = val(B, k); return x !== null && y !== null ? y - x : null; };
	const fmt = (v: number | null) => (v === null ? 'UNDEFINED' : Number.isInteger(v) ? String(v) : v.toFixed(6));
</script>
<div class="rc" data-testid="round-comparison">
	<div class="sel"><label>Compare round <select value={A} onchange={(e) => { a = Number((e.currentTarget as HTMLSelectElement).value); }} data-testid="cmp-a">{#each done as r}<option value={r}>R{r}</option>{/each}</select></label>
		<label>with round <select value={B} onchange={(e) => { b = Number((e.currentTarget as HTMLSelectElement).value); }} data-testid="cmp-b">{#each done as r}<option value={r}>R{r}</option>{/each}</select></label>
		<label>metric across rounds <select value={metric} onchange={(e) => { studio.selectedMetric = (e.currentTarget as HTMLSelectElement).value; }} data-testid="cmp-metric">{#each KEYS as k}<option>{k}</option>{/each}</select></label></div>
	{#if done.length < 2}<p class="dim" role="status">Comparison needs at least two evaluated rounds; evaluated so far: {done.length}.</p>
	{:else}
		<div class="scroll" tabindex="-1"><table data-testid="cmp-table"><thead><tr><th scope="col">Metric</th><th scope="col">R{A}</th><th scope="col">R{B}</th><th scope="col">Difference (R{B} − R{A})</th></tr></thead>
			<tbody>{#each KEYS as k}<tr><th scope="row">{k}</th><td>{fmt(val(A, k))}</td><td>{fmt(val(B, k))}</td><td data-testid={`cmp-diff-${k}`}>{fmt(diff(k))}</td></tr>{/each}</tbody></table></div>
		<p class="warn">Ranking metrics (AUPRC/AUROC) and probability-quality metrics (BCE/Brier) can move in opposite directions. Read the confusion matrices: a model can rank well yet still predict one class for every window at the fixed 0.5 rule.</p>
		<h4>{metric} across evaluated rounds</h4>
		<div class="scroll" tabindex="-1"><table><thead><tr>{#each studio.rounds as r}<th scope="col">R{r}</th>{/each}</tr></thead><tbody><tr data-testid="metric-across">{#each studio.rounds as r}<td>{display(rec(r), metric, 'rate').tone === 'value' ? fmt(val(r, metric)) : display(rec(r), metric).text}</td>{/each}</tr></tbody></table></div>
		<p class="dim">Descriptive point differences only: nominal intervals exist solely for the predeclared pair R{pair?.comparator_round} → R{pair?.endpoint_round}.</p>
	{/if}
</div>
<style>
	.rc { display: grid; grid-template-columns: minmax(0, 1fr); gap: 8px; min-width: 0; } .sel { display: flex; flex-wrap: wrap; gap: 10px; align-items: end; } label { display: grid; gap: 4px; font: 10px 'JetBrains Mono', monospace; color: #71829a; } select { background: #0a0f1f; color: #e2e8f0; border: 1px solid rgba(148,163,184,.35); padding: 6px 10px; min-height: 32px; font: 12px 'JetBrains Mono', monospace; } select:focus-visible { outline: 2px solid #2bb8b0; }
	.scroll { overflow: auto; max-width: 100%; } table { border-collapse: collapse; font-size: 11.5px; } th, td { border-bottom: 1px solid rgba(148,163,184,.15); padding: 4px 10px; text-align: left; white-space: nowrap; color: #cbd5e1; } thead th { background: #0a0f1f; color: #71829a; font: 10px 'JetBrains Mono', monospace; } h4 { margin: 8px 0 2px; font: 11px 'JetBrains Mono', monospace; letter-spacing: .1em; color: #a78bfa; } .dim, .warn { margin: 0; font-size: 12px; line-height: 1.55; color: #94a3b8; } .warn { color: #fbbf24; }
	p, label, h4 { overflow-wrap: anywhere; }
</style>
