<script lang="ts">
	// One client across all committed rounds (from the run's client-round table) and the diagnostic-holdout participants that share its site condition, for the selected round.
	import type { StudioStore } from '$lib/product/studio/store.svelte';
	let { studio }: { studio: StudioStore } = $props();
	const CLIENTS = Array.from({ length: 8 }, (_, i) => `SIM_FL_SITE_0${i}`);
	const client = $derived(studio.selectedClientId ?? 'SIM_FL_SITE_00');
	const t3 = $derived(studio.tables?.tables['FL10_TAB03'] ?? null);
	const t5 = $derived(studio.tables?.tables['FL10_TAB05'] ?? null);
	const t6 = $derived(studio.tables?.tables['FL10_TAB06'] ?? null);
	const idx = (t: { columns: string[] } | null, c: string) => (t ? t.columns.indexOf(c) : -1);
	const rows = $derived(t3 ? t3.rows.filter((r) => r[idx(t3, 'client_id')] === client) : []);
	const holdout = $derived(t6 ? t6.rows.filter((r) => r[idx(t6, 'site_condition')] === client).map((r) => String(r[idx(t6, 'participant_id')])) : []);
	const state = $derived(`R${String(studio.metricRound).padStart(2, '0')}`);
	const part = $derived(t5 ? t5.rows.filter((r) => r[0] === state && holdout.includes(String(r[1]))) : []);
	const n = (v: unknown, d = 4) => (typeof v === 'number' ? (Number.isInteger(v) ? String(v) : v.toFixed(d)) : v === null || v === undefined ? 'NOT CAPTURED' : String(v));
</script>
<div class="ch" data-testid="client-history">
	<label>Client <select value={client} onchange={(e) => studio.selectClient((e.currentTarget as HTMLSelectElement).value)} data-testid="client-select">{#each CLIENTS as c}<option value={c}>{c}</option>{/each}</select></label>
	{#if !t3}<p class="dim" role="status">Loading client history…</p>
	{:else}
		<h4>{client}: per-round training statistics ({rows.length} committed rounds)</h4>
		{#if rows.length === 0}<p class="dim">No committed round yet for this client.</p>{:else}
		<div class="scroll" tabindex="-1"><table data-testid="client-history-table"><thead><tr><th scope="col">round</th><th scope="col">examples</th><th scope="col">mean loss</th><th scope="col">update norm</th><th scope="col">grad norm</th><th scope="col">weight</th><th scope="col">acceptance</th></tr></thead>
			<tbody>{#each rows as r}<tr class:sel={r[idx(t3, 'round')] === studio.selectedRound}><td>{r[idx(t3, 'round')]}</td><td>{n(r[idx(t3, 'examples_processed')])}</td><td>{n(r[idx(t3, 'mean_training_loss')])}</td><td>{n(r[idx(t3, 'local_update_norm')])}</td><td>{n(r[idx(t3, 'gradient_norm_mean')])}</td><td>{n(r[idx(t3, 'aggregation_weight')], 8)}</td><td>{n(r[idx(t3, 'acceptance_status')])}</td></tr>{/each}</tbody></table></div>{/if}
		<h4>Evaluation-holdout participants with this site's condition, state {state}</h4>
		{#if part.length === 0}<p class="dim" data-testid="client-holdout-none">No evaluated record for {state} yet.</p>
		{:else}<div class="scroll" tabindex="-1"><table data-testid="client-holdout-table"><thead><tr><th scope="col">participant</th>{#each ['AUPRC', 'AUROC', 'F1', 'recall', 'specificity'] as k}<th scope="col">{k}</th>{/each}</tr></thead>
			<tbody>{#each part as r}<tr><th scope="row">{r[1]}</th>{#each ['AUPRC', 'AUROC', 'F1', 'recall', 'specificity'] as k}<td>{n(r[idx(t5, k)])}</td>{/each}</tr>{/each}</tbody></table></div>{/if}
		<p class="dim">Two holdout participants share each site's synthetic condition; the holdout never enters training.</p>
	{/if}
</div>
<style>
	.ch { display: grid; grid-template-columns: minmax(0, 1fr); gap: 8px; min-width: 0; } label { display: grid; gap: 4px; font: 10px 'JetBrains Mono', monospace; color: #71829a; width: fit-content; } select { background: #0a0f1f; color: #e2e8f0; border: 1px solid rgba(148,163,184,.35); padding: 6px 10px; min-height: 32px; font: 12px 'JetBrains Mono', monospace; } select:focus-visible { outline: 2px solid #2bb8b0; } h4 { margin: 6px 0 0; font: 500 14px 'Space Grotesk', sans-serif; color: #e5f1f0; }
	.scroll { overflow: auto; max-width: 100%; max-height: 300px; } table { border-collapse: collapse; font-size: 11.5px; } th, td { border-bottom: 1px solid rgba(148,163,184,.15); padding: 4px 10px; text-align: left; white-space: nowrap; color: #cbd5e1; } thead th { position: sticky; top: 0; background: #0a0f1f; color: #71829a; font: 10px 'JetBrains Mono', monospace; } tr.sel { background: rgba(43,184,176,.1); } .dim { margin: 0; color: #94a3b8; font-size: 12px; line-height: 1.55; }
	p, label, h4 { overflow-wrap: anywhere; }
</style>
