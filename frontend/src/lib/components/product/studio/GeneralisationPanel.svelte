<script lang="ts">
	// GENERALISATION: every committed global state of THIS run, and the unchanged frozen V2 checkpoint, scored on the same unseen synthetic cohort with the same windows,
	// the same fixed 0.5 threshold and no calibration. Everything shown is a measured stored record; a round that has not been scored shows its status, never a value.
	import GenLineChart from './GenLineChart.svelte';
	import GenCurveOverlay from './GenCurveOverlay.svelte';
	import { display } from '$lib/product/studio/metrics';
	import type { StudioStore } from '$lib/product/studio/store.svelte';
	import type { GenRecord } from '$lib/product/studio/types';
	let { studio }: { studio: StudioStore } = $props();
	const g = $derived(studio.generalisation);
	const roundsList = $derived(g ? g.rounds.map((r) => r.round_id) : []);
	const base = $derived(g?.baseline.record ?? null);
	const done = (r: { record: GenRecord | null }) => r.record?.evaluation_status === 'COMPLETED';
	const metric = $derived(g && g.metrics_order.includes(studio.selectedMetric) ? studio.selectedMetric : 'AUPRC');
	const lower = $derived(new Set(g?.lower_is_better ?? []));
	const latestDone = $derived(g ? [...g.rounds].reverse().find(done)?.round_id ?? null : null);
	const selected = $derived(studio.selectedRound);
	/** The round every card shows: the user's/live selection when scored, otherwise (while following live) the latest scored round, labelled as such. */
	const shown = $derived.by(() => {
		if (!g) return selected;
		const sel = g.rounds.find((r) => r.round_id === selected);
		if (sel && done(sel)) return selected;
		return studio.followLive && latestDone !== null ? latestDone : selected;
	});
	const shownRow = $derived(g?.rounds.find((r) => r.round_id === shown) ?? null);
	const shownRecord = $derived(shownRow?.record ?? null);
	const substituted = $derived(shown !== selected);
	$effect(() => { void studio.ensureGenDetail(shown); });
	const baseValue = (key: string) => (base?.evaluation_status === 'COMPLETED' ? ((base.metric_result?.[key] as number | null | undefined) ?? null) : null);
	const roundValue = (rec: GenRecord | null, key: string) => (rec?.evaluation_status === 'COMPLETED' ? ((rec.metric_result?.[key] as number | null | undefined) ?? null) : null);
	const flSeries = $derived(g ? g.rounds.map((r) => roundValue(r.record, metric)) : []);
	const v2Series = $derived(g ? g.rounds.map(() => baseValue(metric)) : []);
	const diffPoint = $derived(g ? g.rounds.map((r) => r.paired_vs_v2?.metrics[metric]?.difference_point ?? null) : []);
	const diffLo = $derived(g ? g.rounds.map((r) => r.paired_vs_v2?.metrics[metric]?.difference_interval.lower ?? null) : []);
	const diffHi = $derived(g ? g.rounds.map((r) => r.paired_vs_v2?.metrics[metric]?.difference_interval.upper ?? null) : []);
	const fixed = (v: number | null | undefined, d = 4) => (typeof v === 'number' ? v.toFixed(d) : '—');
	const signed = (v: number | null | undefined) => (typeof v === 'number' ? `${v >= 0 ? '+' : ''}${v.toFixed(4)}` : '—');
	const counts = (rec: GenRecord | null | undefined) => (rec?.evaluation_status === 'COMPLETED' ? rec.confusion_counts : null);
	const curves = $derived(studio.genCurves[shown]);
	const parts = $derived(studio.genParticipants[shown]);
	const partRows = $derived.by(() => {
		if (!parts?.available || !parts.round) return [];
		return Object.entries(parts.round).map(([id, m]) => ({ id, round: m, base: parts.baseline?.[id] ?? null }));
	});
	const baseWorking = $derived(!base || base.evaluation_status === 'QUEUED' || base.evaluation_status === 'EVALUATING');
	const evaluated = $derived(g ? g.rounds.filter(done).length : 0);
	const TABLE_KEYS = ['AUPRC', 'AUROC', 'F1', 'specificity', 'recall', 'precision', 'accuracy', 'balanced_accuracy', 'BCE', 'Brier'];
</script>
<section class="gp" data-testid="generalisation-panel" aria-label="Generalisation: frozen V2 versus the federated global model on an unseen cohort">
	{#if !g}
		<p class="dim" role="status" data-testid="generalisation-unavailable">{studio.genNote ?? 'Loading the generalisation evaluation…'}</p>
	{:else}
		<header class="hd">
			<h3>GENERALISATION · frozen V2 vs federated global model, unseen cohort</h3>
			<p class="label" data-testid="generalisation-cohort-label">{g.cohort.label}</p>
			<dl class="facts">
				<div><dt>Starting model</dt><dd data-testid="generalisation-base-model">{g.base_model.label}</dd></div>
				<div><dt>Cohort</dt><dd>{g.cohort.participants} participants · {g.cohort.windows} windows · {g.cohort.positive_windows} positive</dd></div>
				<div><dt>Decision rule</dt><dd>fixed threshold {g.threshold}, calibration {g.calibration}</dd></div>
				<div><dt>Progress</dt><dd data-testid="generalisation-progress">{evaluated}/{g.rounds.length} rounds scored · frozen V2 {base ? base.evaluation_status : 'NOT YET QUEUED'}</dd></div>
			</dl>
			<p class="dim" data-testid="generalisation-target">Target: the synthetic engineering-event task (not AAMI-SVF). {g.baseline.detail}</p>
			{#if g.integrity.r0_predictions_equal_frozen_v2}<p class="ok" data-testid="generalisation-r0-identical">R0 is identical to frozen V2 (same state digest, identical predictions on every window): this run started from the pretrained weights.</p>{/if}
			{#if g.integrity.r0_digest_equals_frozen_v2 === false}<p class="dim" data-testid="generalisation-r0-different">R0 is an untrained model; frozen V2 is shown as an external reference line, not as this run's starting point.</p>{/if}
			{#if g.run_length === 10}<p class="dim">Rounds R0–R3 of this run are its 3-round view; the same deterministic coordinator produced them.</p>{/if}
		</header>

		{#if baseWorking}<p class="warn" role="status" data-testid="generalisation-baseline-working">Frozen V2 is {base ? base.evaluation_status.toLowerCase() : 'about to be scored'} on the unseen cohort. Comparisons appear when it has finished; nothing is estimated in the meantime.</p>{/if}
		{#if base?.evaluation_status === 'FAILED'}<p class="warn" role="alert">Frozen V2 scoring failed: {base.failure?.code}. No comparison is shown.</p>{/if}

		<div class="pick"><label>Metric <select value={metric} onchange={(e) => { studio.selectedMetric = (e.currentTarget as HTMLSelectElement).value; }} data-testid="generalisation-metric">{#each g.metrics_order as m (m)}<option value={m}>{m}{lower.has(m) ? ' (lower is better)' : ''}</option>{/each}</select></label>
			<span class="dim">Showing R{shown}{substituted ? ` (latest scored round; R${selected} is not scored yet)` : ''}. Click a round on a chart to inspect it.</span></div>

		<div class="charts">
			<GenLineChart testid="gen-chart-metric" metric={metric} title={`${metric} across rounds`} caption="Federated global model per round (solid) against the unchanged frozen V2 (dashed)." rounds={roundsList} selected={shown}
				onSelect={(r) => studio.selectRound(r)} series={[{ id: 'fl', label: 'Federated global model', color: '#2bb8b0', values: flSeries }, { id: 'v2', label: 'Frozen V2', color: '#f59e0b', dashed: true, values: v2Series }]} />
			<GenLineChart testid="gen-chart-diff" metric={metric} title={`${metric}: round minus frozen V2`} caption="Paired difference with a nominal participant-cluster interval (replicates and seed predeclared by the protocol); no significance claim." rounds={roundsList}
				selected={shown} onSelect={(r) => studio.selectRound(r)} zeroLine band={{ lower: diffLo, upper: diffHi }} series={[{ id: 'diff', label: 'Difference (round − V2)', color: '#2bb8b0', values: diffPoint }]} />
		</div>

		<div class="cmp">
			<table data-testid="generalisation-table">
				<caption>Round R{shown} against frozen V2, same {g.cohort.windows} windows, same fixed 0.5 rule{shownRecord ? ` · state ${shownRecord.global_state_digest.slice(0, 10)}…` : ''}</caption>
				<thead><tr><th scope="col">Metric</th><th scope="col">Frozen V2</th><th scope="col">R{shown}</th><th scope="col">Difference</th><th scope="col">Nominal interval (95 percent)</th></tr></thead>
				<tbody>{#each TABLE_KEYS as key (key)}{@const m = shownRow?.paired_vs_v2?.metrics[key]}
					<tr data-testid={`generalisation-row-${key}`}><th scope="row">{key}{lower.has(key) ? ' ↓' : ''}</th>
						<td>{base ? display(base, key).text : '—'}</td><td>{display(shownRecord ?? undefined, key).text}</td>
						<td>{signed(m?.difference_point)}</td><td>{m && m.difference_interval.lower !== null ? `[${fixed(m.difference_interval.lower)}, ${fixed(m.difference_interval.upper)}]` : '—'}</td></tr>{/each}</tbody>
			</table>
			<div class="cms">
				{#each [{ id: 'v2', title: 'Frozen V2', rec: base }, { id: 'fl', title: `R${shown}`, rec: shownRecord }] as m (m.id)}{@const c = counts(m.rec)}
					<figure class="cm" data-testid={`generalisation-cm-${m.id}`}>
						<figcaption>{m.title} · confusion counts</figcaption>
						{#if c}<div class="mx" role="table" aria-label={`${m.title} confusion matrix`}><span class="h"></span><span class="h">pred +</span><span class="h">pred −</span><span class="h">actual +</span><b class="tp">{c.TP}</b><b class="fn">{c.FN}</b><span class="h">actual −</span><b class="fp">{c.FP}</b><b class="tn">{c.TN}</b></div>
						{:else}<p class="dim" role="status">{m.rec ? m.rec.evaluation_status : 'NOT YET AVAILABLE'}</p>{/if}
					</figure>{/each}
			</div>
		</div>

		<div class="curves">
			<GenCurveOverlay testid="gen-roc" kind="roc" roundLabel={`R${shown}`} round={curves?.available ? (curves.round?.roc ?? null) : null} baseline={curves?.available ? (curves.baseline?.roc ?? null) : null} />
			<GenCurveOverlay testid="gen-pr" kind="pr" roundLabel={`R${shown}`} round={curves?.available ? (curves.round?.pr ?? null) : null} baseline={curves?.available ? (curves.baseline?.pr ?? null) : null} />
		</div>

		{#if partRows.length}
			<table class="pt" data-testid="generalisation-participants"><caption>Per-participant AUPRC and AUROC, R{shown} vs frozen V2 (undefined where a participant has a single class)</caption>
				<thead><tr><th scope="col">Participant</th><th scope="col">V2 AUPRC</th><th scope="col">R{shown} AUPRC</th><th scope="col">V2 AUROC</th><th scope="col">R{shown} AUROC</th></tr></thead>
				<tbody>{#each partRows as p (p.id)}<tr><th scope="row">{p.id}</th><td>{fixed(p.base?.AUPRC as number | null | undefined)}</td><td>{fixed(p.round.AUPRC as number | null | undefined)}</td><td>{fixed(p.base?.AUROC as number | null | undefined)}</td><td>{fixed(p.round.AUROC as number | null | undefined)}</td></tr>{/each}</tbody></table>
		{/if}

		<section class="read" data-testid="generalisation-interpretation" aria-label="Measured statements"><h4>What the numbers say</h4><ul>{#each g.interpretation as line, i (i)}<li>{line}</li>{/each}</ul></section>

		<section class="lim" aria-label="Limits of this evaluation"><h4>Limits</h4><ul>
			<li>{g.cohort.detail}</li>
			<li>Frozen V2 was trained on the real-ECG AAMI-SVF task; here it is a zero-shot transfer reference on a different, synthetic target. A lower federated score would be a finding, not an error.</li>
			<li>Real-ECG (AAMI-SVF) retention of the adapted model was <b>not executed</b>: it needs the governed external-data path, and synthetic-event scores must never be plotted as if they measured it.</li>
			<li>Nothing here selects a round, tunes a threshold, calibrates, or promotes a model. {g.claim_boundary.replaceAll('_', ' ').toLowerCase()}.</li></ul></section>
	{/if}
</section>
<style>
	.gp { display: grid; grid-template-columns: minmax(0, 1fr); gap: 12px; min-width: 0; } .hd { display: grid; gap: 6px; } h3 { margin: 0; font: 600 13px 'JetBrains Mono', monospace; letter-spacing: .06em; color: #e5f1f0; }
	h4 { margin: 0 0 4px; font: 600 11px 'JetBrains Mono', monospace; letter-spacing: .08em; color: #94a3b8; } .label { margin: 0; display: inline-block; justify-self: start; padding: 4px 10px; border: 1px solid rgba(43,184,176,.5); color: #2bb8b0; font: 600 11px 'JetBrains Mono', monospace; letter-spacing: .06em; }
	.facts { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 6px; margin: 0; } .facts div { border: 1px solid rgba(148,163,184,.16); padding: 6px 8px; min-width: 0; } dt { color: #71829a; font: 9px 'JetBrains Mono', monospace; letter-spacing: .08em; text-transform: uppercase; } dd { margin: 2px 0 0; color: #e5f1f0; font-size: 12px; }
	.dim { margin: 0; color: #94a3b8; font-size: 12px; line-height: 1.5; } .ok { margin: 0; color: #2bb8b0; font-size: 12px; } .warn { margin: 0; padding: 8px 10px; border: 1px solid rgba(245,158,11,.5); color: #fbbf24; font-size: 12px; }
	.pick { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 14px; } .pick label { display: flex; align-items: center; gap: 8px; color: #94a3b8; font: 11px 'JetBrains Mono', monospace; } select { background: #07101e; color: #e5f1f0; border: 1px solid rgba(148,163,184,.3); padding: 6px 8px; }
	.charts { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 420px), 1fr)); gap: 10px; min-width: 0; } .cmp { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 340px), 1fr)); gap: 10px; align-items: start; min-width: 0; }
	table { border-collapse: collapse; width: 100%; font-size: 12px; } caption { text-align: left; color: #94a3b8; padding-bottom: 6px; line-height: 1.45; } th, td { border: 1px solid rgba(148,163,184,.18); padding: 5px 8px; text-align: left; color: #cbd5e1; font-variant-numeric: tabular-nums; } thead th { color: #71829a; font: 10px 'JetBrains Mono', monospace; letter-spacing: .06em; } tbody th { color: #e5f1f0; font-weight: 500; }
	.cms { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; } .cm { margin: 0; border: 1px solid rgba(148,163,184,.2); padding: 8px 10px; display: grid; gap: 6px; } .cm figcaption { color: #94a3b8; font: 11px 'JetBrains Mono', monospace; }
	.mx { display: grid; grid-template-columns: auto 1fr 1fr; gap: 4px; align-items: center; text-align: center; } .mx .h { color: #71829a; font: 9px 'JetBrains Mono', monospace; } .mx b { padding: 10px 4px; border: 1px solid rgba(148,163,184,.2); font: 600 14px 'JetBrains Mono', monospace; color: #e5f1f0; }
	.mx .tp, .mx .tn { background: rgba(43,184,176,.14); } .mx .fp, .mx .fn { background: rgba(245,158,11,.12); } .curves { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 260px), 1fr)); gap: 10px; }
	.read, .lim { border: 1px solid rgba(148,163,184,.16); padding: 10px 12px; } ul { margin: 0; padding-left: 18px; color: #cbd5e1; font-size: 12px; line-height: 1.6; } .pt { max-width: 640px; }
	p, li, dd, td, th, caption { overflow-wrap: anywhere; }
</style>
