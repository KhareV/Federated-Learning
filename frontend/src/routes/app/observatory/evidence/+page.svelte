<script lang="ts">
	import { onMount } from 'svelte';
	import { getProductStore } from '$lib/product/state.svelte';
	import type { EvalModel, FlCurves, FlEval } from '$lib/product/observatory/evidence';
	const store = getProductStore();
	let evalData = $state<FlEval | null>(null);
	let error = $state<string | null>(null);
	let dataset = $state('INTERNAL_TEST');
	let generation = $state('ALL');
	let algorithm = $state('ALL');
	let condition = $state('ALL');
	let modelId = $state('V2_FEDAVG_IID');
	let curves = $state<FlCurves | null>(null);
	let curveError = $state<string | null>(null);
	let curveRequest = 0;
	const data = $derived(evalData?.datasets[dataset] ?? null);
	const rows = $derived((data?.models ?? []).filter((m) => (generation === 'ALL' || m.generation === generation) && (algorithm === 'ALL' || m.algorithm === algorithm) && (condition === 'ALL' || m.condition === condition)));
	const selected = $derived(data?.models.find((m) => m.model_id === modelId) ?? null);
	const pairs = $derived((data?.comparisons ?? []).filter((c) => c.family === 'fedprox_effect'));
	const conditions = ['iid', 'label', 'quantity', 'feature', 'combined'];
	const MEANING: Record<string, string> = { iid: 'balanced reference partition', label: 'label-distribution skew', quantity: 'client-size imbalance', feature: 'feature-distribution shift', combined: 'multiple non-IID effects' };
	const fmt = (v: number | undefined, d = 4) => (v === undefined ? '—' : v.toFixed(d));
	const path = (pts: [number, number][]) => pts.map(([x, y], i) => `${i ? 'L' : 'M'}${(x * 100).toFixed(2)},${((1 - y) * 100).toFixed(2)}`).join(' ');
	onMount(() => { void store.api.observatoryFlEval().then((v) => { evalData = v; }).catch((c) => { error = c instanceof Error ? c.message : String(c); }); });
	$effect(() => {
		const id = modelId; const ds = dataset;
		if (!evalData) return;
		const request = ++curveRequest; curveError = null;
		void store.api.observatoryFlCurves(ds, id).then((v) => { if (request === curveRequest) curves = v; }).catch((c) => { if (request === curveRequest) { curves = null; curveError = c instanceof Error ? c.message : String(c); } });
	});
	function pick(m: EvalModel) { modelId = m.model_id; }
	function changeDataset(next: string) { dataset = next; }
</script>
<svelte:head><title>Scientific evidence explorer | NHM</title></svelte:head>
<div class="eyebrow">NHM / RESEARCH OBSERVATORY / SCIENTIFIC EVIDENCE</div>
<h1>Frozen scientific FL evidence</h1>
<p class="lead">Every value here is read from the committed V2-FL-EVAL-001 evidence after a SHA-256 check. Nothing is trained, tuned or re-evaluated. These are the scientific FL experiments (AAMI_SVF_WINDOW_V1), <b>not</b> the product's three-round engineering candidate, which has no established efficacy.</p>
<p class="tag" data-testid="frozen-label">FROZEN RESEARCH EVIDENCE</p>
{#if error}<p role="alert" class="err">Evidence unavailable: {error}</p>{:else if !data}<p class="dim" role="status">Loading frozen evidence…</p>{:else}
<section class="controls" aria-label="Experiment filters">
	<fieldset><legend>Evaluation population</legend>
		{#each Object.keys(evalData?.datasets ?? {}) as name}<button class:on={dataset===name} aria-pressed={dataset===name} onclick={() => changeDataset(name)}>{name}</button>{/each}</fieldset>
	<label>Generation <select bind:value={generation}><option>ALL</option><option>V1</option><option>V2</option></select></label>
	<label>Algorithm <select bind:value={algorithm}><option>ALL</option><option>FedAvg</option><option>FedProx</option></select></label>
	<label>Condition <select bind:value={condition}><option>ALL</option>{#each conditions as c}<option>{c}</option>{/each}</select></label>
</section>
<p class="warn" data-testid="population-note"><b>{data.claim_label}</b> · {data.windows.toLocaleString()} eligible windows · {data.clusters} patient clusters. {dataset === 'INTERNAL_TEST' ? 'Six contributing clusters: intervals are wide and unstable.' : 'Post-freeze second look on a project-exposed dataset, not untouched validation.'}</p>
<section aria-label="Experiment matrix">
	<h2>Experiment matrix · AUPRC with nominal 95% patient-cluster interval</h2>
	<div class="scroll"><table data-testid="experiment-matrix"><thead><tr><th>Model</th><th>Algorithm</th><th>Condition</th><th>Dev. round</th><th>AUPRC</th><th>Interval (0 to 1 scale)</th><th>AUROC</th><th>Pooled F1</th><th>Patient-macro F1</th></tr></thead>
		<tbody>{#each rows as m (m.model_id)}{@const ci = m.ci_95.AUPRC}<tr class:sel={m.model_id===modelId}><th scope="row"><button class="link" onclick={() => pick(m)}>{m.model_id}</button></th><td>{m.algorithm}{m.mu !== null ? ` (μ=${m.mu})` : ''}</td><td>{m.condition}</td><td>{m.development_round}</td><td>{fmt(m.point.AUPRC)}</td>
			<td>{#if ci}<span class="range" role="img" aria-label={`AUPRC interval ${fmt(ci.lower, 3)} to ${fmt(ci.upper, 3)}`}><i style={`left:${ci.lower * 100}%;width:${Math.max(0.6, (ci.upper - ci.lower) * 100)}%`}></i><b style={`left:${m.point.AUPRC * 100}%`}></b></span> <small>[{fmt(ci.lower, 3)}, {fmt(ci.upper, 3)}]</small>{:else}—{/if}</td><td>{fmt(m.point.AUROC)}</td><td>{fmt(m.point.pooled_F1)}</td><td>{fmt(m.point.patient_macro_F1)}</td></tr>{/each}</tbody></table></div>
	{#if rows.length === 0}<p class="dim">No frozen model matches this filter.</p>{/if}
</section>
{#if selected}
<section aria-label="Selected model" class="detail" data-testid="selected-model">
	<h2>{selected.model_id} on {dataset}</h2>
	<p class="dim">Checkpoint <code>{selected.checkpoint_sha256.slice(0, 16)}…</code> · selected at development round {selected.development_round} using VALIDATION only · decision rule: raw sigmoid ≥ 0.5, no calibration.</p>
	{#if curveError}<p role="alert" class="err">Curves unavailable: {curveError}</p>{:else if !curves}<p class="dim" role="status">Loading curves…</p>{:else}
	<div class="charts">
		<figure><figcaption>Precision–recall (recall →, precision ↑)</figcaption><svg viewBox="-8 -4 116 116" role="img" aria-label={`Precision recall curve, AUPRC ${fmt(curves.frozen.AUPRC)}`}><rect x="0" y="0" width="100" height="100" class="frame" /><path d={path(curves.pr)} class="line" /></svg></figure>
		<figure><figcaption>ROC (false-positive rate →, sensitivity ↑)</figcaption><svg viewBox="-8 -4 116 116" role="img" aria-label={`ROC curve, AUROC ${fmt(curves.frozen.AUROC)}`}><rect x="0" y="0" width="100" height="100" class="frame" /><path d="M0,100 L100,0" class="diag" /><path d={path(curves.roc)} class="line" /></svg></figure>
		<figure><figcaption>Confusion matrix at the frozen 0.5 rule</figcaption><div class="cm" data-testid="confusion"><span></span><b>Pred. positive</b><b>Pred. negative</b><b>Actual positive</b><span class="tp">TP {curves.confusion.TP}</span><span class="fn">FN {curves.confusion.FN}</span><b>Actual negative</b><span class="fp">FP {curves.confusion.FP}</span><span class="tn">TN {curves.confusion.TN}</span></div></figure>
	</div>
	<p class="dim" data-testid="curve-provenance">Descriptive recomputation from the frozen prediction table ({curves.windows.toLocaleString()} windows), {curves.matches ? 'matching' : 'NOT matching'} the frozen point metrics (AUPRC {fmt(curves.recomputed.AUPRC, 6)} / {fmt(curves.frozen.AUPRC, 6)}). Display curves are thinned; metrics use every window. Source <code>{curves.source.path}</code> · SHA256 <code>{curves.source.sha256.slice(0, 16)}…</code>.</p>
	{/if}
</section>
{/if}
<section aria-label="FedAvg versus FedProx" data-testid="fedprox-pairs">
	<h2>FedProx − FedAvg, same architecture and condition (paired, shared bootstrap draws)</h2>
	<p class="dim">No winner is declared. A paired interval that excludes zero is not a formal significance test, and no p-values were computed.</p>
	<div class="scroll"><table><thead><tr><th>Comparison</th><th>AUPRC Δ</th><th>Interval</th><th>AUROC Δ</th><th>Interval</th></tr></thead><tbody>{#each pairs as c (c.comparison_id)}<tr><th scope="row">{c.a} − {c.b}</th><td>{fmt(c.delta.AUPRC?.point, 5)}</td><td><small>[{fmt(c.delta.AUPRC?.lower, 5)}, {fmt(c.delta.AUPRC?.upper, 5)}]</small></td><td>{fmt(c.delta.AUROC?.point, 5)}</td><td><small>[{fmt(c.delta.AUROC?.lower, 5)}, {fmt(c.delta.AUROC?.upper, 5)}]</small></td></tr>{/each}</tbody></table></div>
</section>
<section aria-label="Non-IID conditions"><h2>What the five conditions mean</h2><ul class="cond">{#each conditions as c}<li><b>{c.toUpperCase()}</b> {MEANING[c]}</li>{/each}</ul><p class="dim">Synthetic research partitions of real research ECG, not institutions or a geographic map.</p></section>
<section aria-label="Uncertainty method" data-testid="uncertainty"><h2>How the uncertainty was computed</h2>
	<p>Patient-cluster bootstrap: {data.bootstrap.replicates.toLocaleString()} replicates (seed {data.bootstrap.seed}, {data.bootstrap.rng}), resampling the {data.clusters} patient clusters rather than windows, with shared draws for paired comparisons. Intervals are {data.bootstrap.multiplicity_adjustment}. p-values: {data.bootstrap.p_values}. Windows from one patient are never treated as independent.</p>
	<ul>{#each evalData?.limitations ?? [] as limit}<li>{limit}</li>{/each}</ul>
	<p class="dim">Source <code>{data.source.path}</code> · SHA256 <code>{data.source.sha256.slice(0, 16)}…</code> · bootstrap draws <code>{data.bootstrap.draws_sha256.slice(0, 16)}…</code></p></section>
{/if}
<section aria-label="Model comparison workbench" data-testid="model-workbench"><h2>Model comparison workbench · what can and cannot be compared</h2>
	<div class="scroll"><table><thead><tr><th></th><th>Released MODEL_V2_FINAL</th><th>Scientific FL checkpoints (this page)</th><th>Product sandbox candidate</th></tr></thead><tbody>
		<tr><th scope="row">Role</th><td>Live research monitoring</td><td>Frozen research experiments</td><td>Engineering development</td></tr>
		<tr><th scope="row">Initialization / training</th><td>Centrally trained</td><td>Federated, real eligible ECG TRAIN partitions</td><td>Federated from FL_INIT_V2, synthetic logical clients</td></tr>
		<tr><th scope="row">Training target</th><td>AAMI_SVF_WINDOW_V1</td><td>AAMI_SVF_WINDOW_V1</td><td>WEARABLE_SIM_EVENT_WINDOW_V1 (synthetic engineering events)</td></tr>
		<tr><th scope="row">Calibration</th><td>CAL_V2 (MIT-BIH source domain)</td><td>None: raw sigmoid at 0.5</td><td>Not established</td></tr>
		<tr><th scope="row">Evaluation population</th><td>Frozen research evidence (see Research ML)</td><td>INTERNAL_TEST (held out from FL development), INCART (post-freeze second look)</td><td>None</td></tr>
		<tr><th scope="row">Metrics available</th><td>Frozen metrics and calibration</td><td>AUPRC, AUROC, F1, precision, sensitivity, specificity, with intervals</td><td>None: efficacy not established under this engineering contract</td></tr>
		<tr><th scope="row">Runtime status</th><td>Enabled, server-side</td><td>Not in the product runtime</td><td>No inference runtime; NOT DEPLOYED</td></tr></tbody></table></div>
	<p class="warn">Metrics from the middle column must never be attributed to the right column: both share the V2 architecture, but the training target, data and evaluation differ.</p></section>
<p class="dim"><a href="/app/observatory">← Observatory</a> · <a href="/app/research/fl">Research FL summary</a> · <a href="/app/observatory/provenance">Provenance and boundaries</a></p>
<style>
	.eyebrow{color:#2bb8b0;font:10px 'JetBrains Mono',monospace;letter-spacing:.14em}h1{font:500 clamp(28px,4vw,42px) 'Space Grotesk',sans-serif;margin:8px 0}h2{font:500 18px 'Space Grotesk',sans-serif;margin:22px 0 8px}.lead{max-width:860px;color:#a7b8c9;line-height:1.6}.tag{display:inline-block;margin:0 0 10px;border:1px solid rgba(43,184,176,.5);padding:5px 10px;color:#9fe8e3;font:11px 'JetBrains Mono',monospace;letter-spacing:.1em}
	.dim,small,li{color:#94a3b8;font-size:13px;line-height:1.6;overflow-wrap:anywhere}p{overflow-wrap:anywhere}.err{color:#fecdd3}.warn{border-left:3px solid #fbbf24;background:rgba(251,191,36,.06);padding:8px 12px;color:#fde68a;font-size:13px}a{color:#2bb8b0}code{font:11px 'JetBrains Mono',monospace;color:#9fe7e1}
	.controls{display:flex;flex-wrap:wrap;gap:12px;align-items:end;margin:12px 0}.controls fieldset{border:1px solid rgba(148,163,184,.25);padding:6px 10px;display:flex;gap:6px}.controls legend{font:10px 'JetBrains Mono',monospace;color:#71829a}.controls label{display:grid;gap:4px;font:10px 'JetBrains Mono',monospace;color:#71829a}select,button{background:#0a0f1f;color:#e2e8f0;border:1px solid rgba(148,163,184,.35);padding:6px 10px;min-height:32px;font:12px 'JetBrains Mono',monospace}button.on{border-color:#2bb8b0;color:#9fe8e3}button.link{border:0;background:none;padding:2px 0;color:#2bb8b0;text-align:left;text-decoration:underline;cursor:pointer;min-height:24px}
	.scroll{overflow-x:auto;max-width:100%}table{border-collapse:collapse;width:100%;font-size:12px}th,td{border-bottom:1px solid rgba(148,163,184,.16);padding:7px 9px;text-align:left;vertical-align:middle}thead th{color:#71829a;font:10px 'JetBrains Mono',monospace;letter-spacing:.08em}tr.sel{background:rgba(167,139,250,.08)}
	.range{position:relative;display:inline-block;width:140px;height:8px;background:rgba(148,163,184,.18);vertical-align:middle}.range i{position:absolute;top:0;height:100%;background:rgba(167,139,250,.6)}.range b{position:absolute;top:-3px;width:2px;height:14px;background:#e9e3ff}
	.detail{border:1px solid rgba(148,163,184,.2);padding:14px 16px;margin-top:18px}.detail h2{margin-top:0}.charts{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr));gap:14px}figure{margin:0;display:grid;gap:6px}figcaption{font:10px 'JetBrains Mono',monospace;color:#71829a}svg{width:100%;max-width:320px;height:auto;background:#050a15}.frame{fill:none;stroke:rgba(148,163,184,.35)}.line{fill:none;stroke:#a78bfa;stroke-width:1.6;vector-effect:non-scaling-stroke}.diag{stroke:rgba(148,163,184,.4);stroke-dasharray:3 3;fill:none}
	.cm{display:grid;grid-template-columns:auto 1fr 1fr;gap:4px;font:12px 'JetBrains Mono',monospace}.cm b{font-size:10px;color:#71829a;align-self:center}.cm span{border:1px solid rgba(148,163,184,.3);padding:12px 8px;text-align:center}.tp,.tn{border-color:rgba(167,139,250,.6)!important}.fp,.fn{border-color:rgba(251,191,36,.6)!important}.cond{display:grid;gap:4px;padding-left:18px}
</style>
