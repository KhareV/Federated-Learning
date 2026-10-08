<script lang="ts">
	import { focusHeading } from '$lib/product/observatory/focus';
	import { onMount } from 'svelte';
	import { downloadExport } from '$lib/product/observatory/export';
	import { getProductStore } from '$lib/product/state.svelte';
	import type { ShowcaseBundle } from '$lib/product/observatory/showcase';
	const store = getProductStore();
	let bundle = $state<ShowcaseBundle | null>(null);
	let error = $state<string | null>(null);
	let dataset = $state('INTERNAL_TEST');
	let algorithm = $state('FedAvg');
	let condition = $state('iid');
	let metric = $state<'validation_AUPRC' | 'validation_AUROC' | 'training_weighted_mean_loss'>('validation_AUPRC');
	let exportDigest = $state<string | null>(null);
	const conditions = ['iid', 'label', 'feature', 'quantity', 'combined'];
	const SYN_LABEL = 'SYNTHETIC ENGINEERING-EVENT CLASSIFICATION — NOT AAMI-SVF OR CLINICAL VALIDATION';
	const log = $derived(bundle?.round_logs[`${algorithm}|${condition}`] ?? null);
	const rows = $derived((bundle?.models ?? []).filter((m) => m.dataset === dataset && m.generation === 'V2' && (m.algorithm === algorithm) && (condition === 'ALL' || m.condition === condition)));
	const v1v2 = $derived((bundle?.models ?? []).filter((m) => m.dataset === dataset && m.condition === condition));
	const points = $derived((log?.series ?? []).filter((p) => p[metric] !== null));
	const range = $derived.by(() => { const v = points.map((p) => p[metric] as number); return v.length ? { lo: Math.min(...v), hi: Math.max(...v) } : { lo: 0, hi: 1 }; });
	const path = $derived(points.map((p, i) => { const x = (p.round / Math.max(1, log?.rounds ?? 1)) * 100; const y = 100 - (((p[metric] as number) - range.lo) / Math.max(1e-12, range.hi - range.lo)) * 100; return `${i ? 'L' : 'M'}${x.toFixed(2)},${y.toFixed(2)}`; }).join(' '));
	const bestX = $derived(log?.best_round_by_selection != null ? (log.best_round_by_selection / Math.max(1, log.rounds)) * 100 : null);
	const fmt = (v: number | null | undefined, d = 4) => (v === null || v === undefined ? 'UNDEFINED' : v.toFixed(d));
	const syn = $derived(bundle?.synthetic ?? null);
	const synMetrics = ['AUPRC', 'AUROC', 'F1', 'accuracy', 'precision', 'recall', 'specificity', 'balanced_accuracy', 'BCE'];
	onMount(() => { void store.api.observatoryShowcase().then((v) => { bundle = v; }).catch((c) => { error = c instanceof Error ? c.message : String(c); }); });
	async function exportView() {
		if (!bundle) return;
		exportDigest = await downloadExport('scientific-outcomes', `${dataset}-${algorithm}-${condition}`, 'Frozen scientific evidence; descriptive only.', 'Displayed frozen values, comparability audit and (separately labelled) synthetic evaluation. No inference or statistics are computed in the browser.', { dataset, algorithm, condition, models: rows, round_log: log, comparability: bundle.comparability });
	}
</script>
<svelte:head><title>Scientific outcomes | NHM</title></svelte:head>
<div class="eyebrow">NHM / RESEARCH OBSERVATORY / SCIENTIFIC OUTCOMES</div>
<h1 tabindex="-1" use:focusHeading>Federated learning research outcomes</h1>
<p class="lead">Frozen evidence from V2-FL-001 to 004, V2-FL-EVAL-001 and V2-010, shown with selectors. Nothing is trained, tuned or re-evaluated here, and no new statistic is computed.</p>
<p class="tag" data-testid="frozen-label">FROZEN RESEARCH EVIDENCE · SCIENTIFIC LANE B</p>
{#if error}<p role="alert" class="err">Outcomes unavailable: {error}</p>{:else if !bundle}<p class="dim" role="status">Loading frozen evidence…</p>{:else}
<section class="controls" aria-label="Selectors">
	<fieldset><legend>Evaluation dataset</legend>{#each Object.keys(bundle.datasets) as d}<button class:on={dataset===d} aria-pressed={dataset===d} onclick={() => (dataset = d)}>{d}</button>{/each}</fieldset>
	<label>Algorithm <select bind:value={algorithm}><option>FedAvg</option><option>FedProx</option></select></label>
	<label>Condition <select bind:value={condition}>{#each conditions as c}<option>{c}</option>{/each}</select></label>
	<label>Training-evolution metric <select bind:value={metric}><option value="validation_AUPRC">Validation AUPRC</option><option value="validation_AUROC">Validation AUROC</option><option value="training_weighted_mean_loss">Training mean loss</option></select></label>
</section>
<p class="warn" data-testid="population-note"><b>{bundle.datasets[dataset].claim_label}</b> · {bundle.datasets[dataset].windows.toLocaleString()} windows · {bundle.datasets[dataset].clusters} patient clusters.</p>
<section aria-label="Training evolution" data-testid="training-evolution"><h2>Training evolution · V2 {algorithm}, {condition}</h2>
	{#if log}
	<svg viewBox="-8 -4 116 116" role="img" aria-label={`Round-by-round ${metric} across ${log.rounds} rounds`}><rect x="0" y="0" width="100" height="100" class="frame" /><path d={path} class="line" />{#if bestX !== null}<path d={`M${bestX},0 L${bestX},100`} class="best" />{/if}</svg>
	<p class="dim">{log.rounds} rounds from the frozen <code>round_log.csv</code>. Range {fmt(range.lo)} to {fmt(range.hi)}{#if log.best_round_by_selection !== null}; dashed line marks the round selected on validation ({log.best_round_by_selection}){/if}. <b>{log.metric_scope}.</b> Source <code>{log.source}</code> · SHA256 <code>{log.sha256.slice(0, 16)}…</code></p>
	{:else}<p class="dim">No frozen round log for this selection.</p>{/if}
</section>
<section aria-label="Model metrics"><h2>Frozen evaluation on {dataset} · V2 {algorithm}</h2>
	<div class="scroll"><table data-testid="outcome-models"><thead><tr><th>Model</th><th>AUPRC [95% interval]</th><th>AUROC</th><th>Patient-macro F1</th><th>Sensitivity</th><th>Specificity</th></tr></thead><tbody>
	{#each rows as m (m.model_id)}<tr><th scope="row">{m.model_id}</th><td>{fmt(m.point.AUPRC)} <small>[{fmt(m.ci_95.AUPRC?.lower, 3)}, {fmt(m.ci_95.AUPRC?.upper, 3)}]</small></td><td>{fmt(m.point.AUROC)}</td><td>{fmt(m.point.patient_macro_F1)}</td><td>{fmt(m.point.sensitivity)}</td><td>{fmt(m.point.specificity)}</td></tr>{/each}</tbody></table></div>
	<h3>V1 against V2, same condition ({condition})</h3>
	<div class="scroll"><table><thead><tr><th>Model</th><th>AUPRC</th><th>AUROC</th></tr></thead><tbody>{#each v1v2 as m (m.model_id)}<tr><th scope="row">{m.model_id}</th><td>{fmt(m.point.AUPRC)}</td><td>{fmt(m.point.AUROC)}</td></tr>{/each}</tbody></table></div>
</section>
<section aria-label="Centralized versus federated" data-testid="comparability"><h2>Centralized V2 against federated V2 (FedAvg, IID)</h2>
	<p class="warn">{bundle.comparability.verdict}</p>
	<div class="scroll"><table data-testid="comparability-matrix"><thead><tr><th>Dataset</th><th>Centralized AUPRC</th><th>Federated AUPRC</th><th>Difference</th><th>Centralized AUROC</th><th>Federated AUROC</th><th>Difference</th></tr></thead><tbody>
	{#each bundle.comparability.rows as r (r.dataset)}<tr><th scope="row">{r.dataset}</th><td>{fmt(r.centralized_V2_AUPRC, 6)}</td><td>{fmt(r.federated_V2_FedAvg_IID_AUPRC, 6)}</td><td>{fmt(r.AUPRC_difference_federated_minus_centralized, 6)}</td><td>{fmt(r.centralized_V2_AUROC, 6)}</td><td>{fmt(r.federated_V2_FedAvg_IID_AUROC, 6)}</td><td>{fmt(r.AUROC_difference_federated_minus_centralized, 6)}</td></tr>{/each}</tbody></table></div>
	<h3>Comparability audit (read-only)</h3>
	<ul>{#each bundle.comparability.checks as c}<li><b>{c.item}</b> — <span class={`st ${c.status.toLowerCase()}`}>{c.status}</span>: {c.detail}</li>{/each}</ul>
	<h3>Four defensible readings</h3>
	<ol data-testid="interpretations">{#each bundle.comparability.interpretations as i (i.id)}<li><b>{i.reading}.</b> {i.support} <em>Limit:</em> {i.limit}</li>{/each}</ol>
</section>
{#if syn}
<section aria-label="Synthetic sandbox evaluation" data-testid="synthetic-eval"><h2>Live sandbox candidate · independent synthetic holdout</h2>
	<p class="syn" data-testid="synthetic-label">{syn.boundary_label || SYN_LABEL}</p>
	<p class="dim">Frozen protocol <code>{syn.protocol_sha256.slice(0, 16)}…</code> (method-freeze commit <code>{syn.method_freeze_commit.slice(0, 10)}</code>) · {syn.holdout_windows} holdout windows from 8 unseen participants · raw sigmoid 0.5, no CAL_V2, no tuning · candidate <code>{syn.candidate_digest.slice(0, 16)}…</code>.</p>
	<div class="scroll"><table><thead><tr><th>State</th>{#each synMetrics as m}<th>{m}</th>{/each}<th>TP/FP/TN/FN</th></tr></thead><tbody>
	{#each Object.entries(syn.states) as [k, s] (k)}<tr><th scope="row">{k.replace('_', ' ')}</th>{#each synMetrics as m}<td>{fmt(s.pooled[m])}</td>{/each}<td>{s.pooled.TP}/{s.pooled.FP}/{s.pooled.TN}/{s.pooled.FN}</td></tr>{/each}</tbody></table></div>
	<p class="warn">Reported as measured, including operating-point failures. Metric undefined ⇒ shown as UNDEFINED, never as zero. These are not AAMI-SVF, clinical or deployment claims.</p>
</section>
{/if}
<section aria-label="Limitations"><h2>Preserved limitations</h2><ul>{#each bundle.limitations as l}<li>{l}</li>{/each}</ul></section>
<p class="exp"><button onclick={() => void exportView()}>Export this view as evidence JSON</button>{#if exportDigest} <small>Exported · SHA256 <code>{exportDigest.slice(0, 16)}…</code></small>{/if}</p>
<p class="dim">Publication figures and tables (SVG, PNG, CSV, JSON provenance and hashes) are produced by the export command listed in the demo runbook. <a href="/app/observatory/evidence">Evidence explorer</a> · <a href="/app/observatory/storyboard">FL storyboard</a> · <a href="/app/observatory">Observatory</a></p>
{/if}
<style>
	.eyebrow{color:#2bb8b0;font:10px 'JetBrains Mono',monospace;letter-spacing:.14em}h1{font:500 clamp(28px,4vw,42px) 'Space Grotesk',sans-serif;margin:8px 0}h2{font:500 18px 'Space Grotesk',sans-serif;margin:22px 0 8px}h3{font:500 14px 'Space Grotesk',sans-serif;margin:14px 0 6px}.lead{max-width:860px;color:#a7b8c9;line-height:1.6}.tag{display:inline-block;margin:0 0 10px;border:1px solid rgba(43,184,176,.5);padding:5px 10px;color:#9fe8e3;font:11px 'JetBrains Mono',monospace;letter-spacing:.1em}
	.dim,small,li{color:#94a3b8;font-size:13px;line-height:1.6;overflow-wrap:anywhere}p{overflow-wrap:anywhere}.err{color:#fecdd3}.warn{border-left:3px solid #fbbf24;background:rgba(251,191,36,.06);padding:8px 12px;color:#fde68a;font-size:13px}.syn{display:inline-block;border:1px solid rgba(167,139,250,.6);padding:5px 10px;color:#d8ccff;font:11px 'JetBrains Mono',monospace}a{color:#2bb8b0;display:inline-block;min-height:24px;line-height:24px}code{font:11px 'JetBrains Mono',monospace;color:#9fe7e1}
	.controls{display:flex;flex-wrap:wrap;gap:12px;align-items:end;margin:12px 0}.controls fieldset{border:1px solid rgba(148,163,184,.25);padding:6px 10px;display:flex;gap:6px}.controls legend{font:10px 'JetBrains Mono',monospace;color:#71829a}.controls label{display:grid;gap:4px;font:10px 'JetBrains Mono',monospace;color:#71829a}select,button{background:#0a0f1f;color:#e2e8f0;border:1px solid rgba(148,163,184,.35);padding:6px 10px;min-height:32px;font:12px 'JetBrains Mono',monospace}button.on{border-color:#2bb8b0;color:#9fe8e3}
	.scroll{overflow-x:auto;max-width:100%}table{border-collapse:collapse;width:100%;font-size:12px}th,td{border-bottom:1px solid rgba(148,163,184,.16);padding:7px 9px;text-align:left}thead th{color:#71829a;font:10px 'JetBrains Mono',monospace;letter-spacing:.08em}svg{width:100%;max-width:420px;height:auto;background:#050a15}.frame{fill:none;stroke:rgba(148,163,184,.35)}.line{fill:none;stroke:#a78bfa;stroke-width:1.6;vector-effect:non-scaling-stroke}.best{stroke:#fbbf24;stroke-dasharray:3 3}.st{font:10px 'JetBrains Mono',monospace;border:1px solid rgba(148,163,184,.4);padding:1px 5px}h1:focus{outline:none}
</style>
