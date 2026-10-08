<script lang="ts">
	import { focusHeading } from '$lib/product/observatory/focus';
	import { onDestroy, onMount } from 'svelte';
	import { getProductStore } from '$lib/product/state.svelte';
	import Fl10Chart from '$lib/components/product/observatory/Fl10Chart.svelte';
	import Fl10Table from '$lib/components/product/observatory/Fl10Table.svelte';
	import { cell, sha256Hex, type Fl10Job, type Fl10Payload, type Fl10Recorded } from '$lib/product/observatory/fl10';
	const store = getProductStore();
	const STATES = Array.from({ length: 11 }, (_, i) => `R${String(i).padStart(2, '0')}`);
	const TABS = [
		{ id: 'overview', label: 'Overview', figs: ['FL10_FIG20', 'FL10_FIG04', 'FL10_FIG09'] },
		{ id: 'training', label: 'Training', figs: ['FL10_FIG02', 'FL10_FIG03', 'FL10_FIG12', 'FL10_FIG13', 'FL10_FIG19'] },
		{ id: 'classification', label: 'Classification', figs: ['FL10_FIG04', 'FL10_FIG05', 'FL10_FIG06', 'FL10_FIG07', 'FL10_FIG08', 'FL10_FIG09', 'FL10_FIG10'] },
		{ id: 'clients', label: 'Clients', figs: ['FL10_FIG11', 'FL10_FIG12', 'FL10_FIG14', 'FL10_FIG15'] },
		{ id: 'comparisons', label: 'R3 vs R10', figs: ['FL10_FIG16', 'FL10_FIG15', 'FL10_FIG20'] },
		{ id: 'internals', label: 'Optimizer & federation', figs: ['FL10_FIG01', 'FL10_FIG17', 'FL10_FIG18', 'FL10_FIG19'] },
		{ id: 'bridge', label: 'Research bridge', figs: [] },
		{ id: 'exports', label: 'Exports', figs: [] }
	] as const;
	let recorded = $state<Fl10Recorded[]>([]);
	let source = $state('recorded-A');
	let payload = $state<Fl10Payload | null>(null);
	let error = $state<string | null>(null);
	let loading = $state(true);
	let tab = $state<(typeof TABS)[number]['id']>('overview');
	let round = $state('R10');
	let client = $state('SIM_FL_SITE_00');
	let cmpA = $state('R03');
	let cmpB = $state('R10');
	let metric = $state('AUPRC');
	let baseline = $state(false);
	let job = $state<Fl10Job | null>(null);
	let timer: ReturnType<typeof setInterval> | null = null;
	let figureIndexOpen = $state(false);
	let manifestDigest = $state<string | null>(null);
	let exportNote = $state<string | null>(null);
	const running = $derived(job !== null && !['COMPLETED', 'FAILED_NOT_A_CANDIDATE'].includes(job.phase));
	const ov = $derived(payload?.overview ?? null);
	const t1 = $derived(payload?.tables['FL10_TAB01'] ?? null);
	const metricCols = $derived((t1?.columns ?? []).filter((c, i) => i > 0 && t1?.rows.some((r) => typeof r[i] === 'number' || r[i] === null) && !['undefined_reasons'].includes(c)));
	const metricIdx = $derived(t1 ? t1.columns.indexOf(metric) : -1);
	const rowOf = (state: string) => t1?.rows.find((r) => r[0] === state) ?? null;
	const colOf = (name: string, state: string) => { const r = rowOf(state); const i = t1?.columns.indexOf(name) ?? -1; return r && i >= 0 ? r[i] : null; };
	const roundNumber = $derived(Number(round.slice(1)));
	const roundRow = $derived(ov?.rounds?.find((r: { round: number }) => r.round === roundNumber) ?? null);
	const clientRows = $derived((payload?.tables['FL10_TAB03']?.rows ?? []).filter((r) => r[payload?.tables['FL10_TAB03'].columns.indexOf('client_id') ?? 0] === client));
	const siteIndex = $derived(Number(client.slice(-2)));
	const clientHoldout = $derived((ov?.evaluation?.holdout_participants ?? []).filter((h: { site_condition: string }) => h.site_condition === client).map((h: { participant_id: string }) => h.participant_id));
	const t5 = $derived(payload?.tables['FL10_TAB05'] ?? null);
	const bridgeRows = $derived<Record<string, number | string>[]>(ov?.scientific_bridge?.comparability_rows ?? []);
	async function load(key: string) {
		loading = true; error = null;
		try { payload = await store.api.fl10RecordedBundle(key); } catch (c) { payload = null; error = c instanceof Error ? c.message : String(c); }
		loading = false;
	}
	onMount(async () => {
		try { recorded = await store.api.fl10Recorded(); } catch (c) { error = c instanceof Error ? c.message : String(c); loading = false; return; }
		await load(source);
	});
	onDestroy(() => { if (timer) clearInterval(timer); });
	async function start(mode: 'A' | 'B') {
		error = null;
		try {
			job = await store.api.fl10Start(mode);
			timer = setInterval(async () => {
				if (!job) return;
				try {
					job = await store.api.fl10Status(job.job_id);
					if (job.phase === 'COMPLETED') { if (timer) clearInterval(timer); timer = null; payload = await store.api.fl10JobBundle(job.job_id); source = job.job_id; }
					else if (job.phase === 'FAILED_NOT_A_CANDIDATE' && timer) { clearInterval(timer); timer = null; }
				} catch (c) { error = c instanceof Error ? c.message : String(c); }
			}, 1500);
		} catch (c) { error = c instanceof Error ? c.message : String(c); }
	}
	function save(name: string, data: Blob | string, mime = 'application/json') {
		const blob = typeof data === 'string' ? new Blob([data], { type: mime }) : data;
		const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
	}
	async function exportFigure(fid: string, fmt: string) {
		exportNote = null;
		try { const { blob, sha256 } = await store.api.fl10ExportFile(source, fid, fmt); save(`${fid}.${fmt === 'provenance' ? 'provenance.json' : fmt}`, blob); exportNote = `${fid}.${fmt} saved · server SHA256 ${sha256 ?? 'n/a'}`; }
		catch (c) { exportNote = c instanceof Error ? c.message : String(c); }
	}
	async function exportManifest() {
		if (!ov) return;
		const text = JSON.stringify({ run_id: ov.run_id, mode: ov.mode, source_label: ov.source_label, protocol_sha256: ov.protocol.sha256, holdout_manifest_sha256: ov.protocol.holdout_manifest_sha256, state_digests: ov.evaluation.state_digests,
			candidate_sha256: ov.run.candidate.state_sha256, evaluation_files: ov.evaluation_files, run_files: ov.run_files, method_freeze_commit: ov.evaluation.method_freeze_commit, git_commit: ov.run.git_commit }, null, 1) + '\n';
		manifestDigest = await sha256Hex(text); save(`fl10-verification-manifest-${ov.run_id}.json`, text);
	}
	const specsOf = (ids: readonly string[]) => ids.map((id) => payload!.specs[id]);
	const diff = (a: unknown, b: unknown) => (typeof a === 'number' && typeof b === 'number' ? b - a : null);
	const current = $derived(TABS.find((t) => t.id === tab)!);
</script>
<svelte:head><title>10-Round Federated Experiment | NHM</title></svelte:head>
<div class="eyebrow">NHM / RESEARCH OBSERVATORY / 10-ROUND FEDERATED EXPERIMENT</div>
<h1 tabindex="-1" use:focusHeading>10-Round Federated Experiment</h1>
{#if ov}<p class="syn" data-testid="synthetic-label">{ov.synthetic_label}</p>{#if ov.live_label}<p class="syn live" data-testid="live-label">{ov.live_label}</p>{/if}{/if}
<p class="lead">An opt-in, separate ten-round extension of the three-round engineering federation. The default three-round run, the released model and the frozen scientific results are unchanged. All values below are measured from the executed run and the fresh independent holdout, with exports.</p>
<section class="controls" aria-label="Experiment controls">
	<button class:on={baseline} aria-pressed={baseline} onclick={() => { baseline = !baseline; }}>3-Round Baseline (read-only)</button>
	<button disabled={running} onclick={() => void start('A')} data-testid="start-a">10-Round FedAvg (run)</button>
	<button disabled={running} onclick={() => void start('B')} data-testid="start-b">10-Round Live-Monitored SITE_00 (run)</button>
	<label>Recorded Verified Run <select bind:value={source} onchange={() => void load(source)} disabled={running}>{#each recorded as r (r.key)}<option value={r.key}>{r.label}</option>{/each}{#if job?.phase === 'COMPLETED'}<option value={job.job_id}>LIVE RUN (this session)</option>{/if}</select></label>
	<label>Round <select bind:value={round}>{#each STATES as s}<option>{s}</option>{/each}</select></label>
	<label>Client <select bind:value={client}>{#each Array.from({ length: 8 }, (_, i) => `SIM_FL_SITE_0${i}`) as c}<option>{c}</option>{/each}</select></label>
	<label>Compare <select bind:value={cmpA}>{#each STATES as s}<option>{s}</option>{/each}</select> vs <select bind:value={cmpB}>{#each STATES as s}<option>{s}</option>{/each}</select></label>
	<label>Metric <select bind:value={metric}>{#each metricCols as m}<option>{m}</option>{/each}</select></label>
</section>
{#if job}
	<section class="job" aria-label="Run progress" data-testid="job-status"><b>{job.job_id}</b> · phase <b data-testid="job-phase">{job.phase}</b> · rounds committed {job.rounds_committed ?? 0} / 10 · {job.source_label}
		<progress max="10" value={job.rounds_committed ?? 0}></progress>
		{#if job.failure}<p class="err" role="alert">FAILED — not a candidate: {job.failure.type}: {job.failure.message}. Restart from R0.</p>{/if}
		<small>{job.note}</small></section>
{/if}
{#if error}<p role="alert" class="err">{error}</p>{/if}
{#if baseline && payload}
	<section class="panel" data-testid="baseline-panel"><h2>3-Round baseline (read-only)</h2>
		<p>The default product federation stays a three-round run. In this experiment R01–R03 are re-derived from the same cohort and compared with the frozen canonical digests:</p>
		<ul>{#each payload.specs['FL10_FIG18'].views[0].states.slice(0, 4) as s}<li><b>{s.state}</b> <code>{s.sha256.slice(0, 24)}…</code>{#if s.equals_frozen_reference === true} equals the frozen canonical state{:else if s.equals_frozen_reference === null} initial state{/if}</li>{/each}</ul>
		<p><a href="/app/federation">Open the original 3-round federation page →</a></p></section>
{/if}
{#if loading}<p class="dim" role="status">Loading evidence…</p>{:else if payload && ov}
<section class="cards" aria-label="Experiment overview" data-testid="overview-cards">
	<div><span>SOURCE</span><strong data-testid="source-label">{ov.source_label}</strong><small>mode {ov.mode} · {ov.run_id}</small></div>
	<div><span>STATUS</span><strong>{ov.run.status}</strong><small>weighted FedAvg · eight logical clients · {ov.run.rounds_committed} rounds</small></div>
	<div><span>ACCEPTED UPDATES</span><strong data-testid="accepted-updates">{ov.run.accepted_updates_total}</strong><small>8 per round expected</small></div>
	<div><span>EXAMPLE EXPOSURES</span><strong>{ov.run.example_exposures_total}</strong><small>{ov.run.unique_training_windows} unique windows × 10 rounds (repeated, not independent)</small></div>
	<div><span>FINAL CANDIDATE (R10)</span><strong class="mono">{ov.run.candidate.state_sha256.slice(0, 16)}…</strong><small>{ov.run.candidate.candidate_id} · not promoted · not deployed</small></div>
	<div><span>SELECTED STATE {round}</span><strong class="mono">{(ov.state_progression[String(roundNumber)].sha256 as string).slice(0, 16)}…</strong><small>{roundRow ? `accepted ${roundRow.accepted_updates} · loss ${cell(roundRow.weighted_mean_training_loss, 4)} · ${cell(roundRow.round_duration_seconds, 2)} s` : 'initial FL_INIT_V2 state'}</small></div>
	<div><span>HOLDOUT</span><strong>{ov.evaluation.windows} windows</strong><small>16 participants · threshold {ov.evaluation.threshold} · no CAL_V2 · no round selection</small></div>
	<div><span>TIMING</span><strong>{cell(ov.run.total_seconds, 1)} s</strong><small>measured wall clock, single machine</small></div>
</section>
<section class="headline" aria-label="R3 versus R10 headline" data-testid="headline">
	<h2>R3 versus R10 on the same fresh holdout</h2>
	<div class="scroll"><table><thead><tr><th>Metric</th><th>R03</th><th>R10</th><th>Difference</th></tr></thead><tbody>
		{#each ['AUPRC', 'AUROC', 'F1', 'recall', 'specificity', 'balanced_accuracy', 'BCE', 'Brier', 'TP', 'FP', 'TN', 'FN'] as m}<tr><th scope="row">{m}</th><td>{cell(colOf(m, 'R03'), 4)}</td><td>{cell(colOf(m, 'R10'), 4)}</td><td>{cell(diff(colOf(m, 'R03'), colOf(m, 'R10')), 4)}</td></tr>{/each}</tbody></table></div>
	<p class="warn">Ranking metrics (AUPRC/AUROC) and probability-quality metrics (BCE/Brier) can move in opposite directions. Read the confusion matrices: a model can rank well yet still predict one class for every window at the fixed 0.5 rule. Intervals are nominal (16 participants).</p>
</section>
<nav class="tabs" role="tablist" aria-label="Experiment sections">{#each TABS as t (t.id)}<button role="tab" aria-selected={tab === t.id} class:on={tab === t.id} onclick={() => { tab = t.id; }}>{t.label}</button>{/each}</nav>
<section class="tabpanel" role="tabpanel" aria-label={current.label} data-testid={`tab-${tab}`}>
	{#if tab === 'overview'}
		<div class="sel"><h3>Selected round {round}</h3><div class="scroll"><table><tbody>
			<tr><th>AUPRC / AUROC</th><td>{cell(colOf('AUPRC', round), 4)} / {cell(colOf('AUROC', round), 4)}</td></tr><tr><th>F1 · sensitivity · specificity</th><td>{cell(colOf('F1', round), 4)} · {cell(colOf('recall', round), 4)} · {cell(colOf('specificity', round), 4)}</td></tr>
			<tr><th>TP / FP / TN / FN</th><td>{colOf('TP', round)} / {colOf('FP', round)} / {colOf('TN', round)} / {colOf('FN', round)}</td></tr><tr><th>BCE / Brier</th><td>{cell(colOf('BCE', round), 4)} / {cell(colOf('Brier', round), 4)}</td></tr></tbody></table></div></div>
		<div class="sel"><h3>{metric} across rounds; {cmpA} vs {cmpB}</h3><div class="scroll"><table><thead><tr>{#each STATES as s}<th>{s}</th>{/each}</tr></thead><tbody><tr>{#each STATES as s}<td>{cell(metricIdx >= 0 ? rowOf(s)?.[metricIdx] : null, 4)}</td>{/each}</tr></tbody></table></div>
			<p>{cmpB} − {cmpA} for <b>{metric}</b>: {cell(diff(colOf(metric, cmpA), colOf(metric, cmpB)), 6)} <small>(descriptive point difference; nominal intervals exist only for the predeclared R03→R10 comparison)</small></p></div>
		<button class="link" onclick={() => { figureIndexOpen = !figureIndexOpen; }} aria-expanded={figureIndexOpen}>Figure index (all 20)</button>
		{#if figureIndexOpen}<ol class="index" data-testid="figure-index">{#each Object.values(payload.specs) as s (s.id)}<li><button class="link" onclick={() => { tab = s.group === 'evaluation' ? 'classification' : s.group === 'data' ? 'clients' : s.group === 'federation' ? 'internals' : 'training'; }}>{s.id.replace('FL10_', '')}</button> {s.title}</li>{/each}</ol>{/if}
	{:else if tab === 'clients'}
		<div class="sel"><h3>{client}: per-round training statistics</h3><div class="scroll"><table><thead><tr><th>round</th><th>examples</th><th>mean loss</th><th>update norm</th><th>grad norm</th><th>weight</th><th>update digest</th></tr></thead><tbody>
			{#each clientRows as r}{@const cols = payload.tables['FL10_TAB03'].columns}<tr><td>{r[cols.indexOf('round')]}</td><td>{r[cols.indexOf('examples_processed')]}</td><td>{cell(r[cols.indexOf('mean_training_loss')], 4)}</td><td>{cell(r[cols.indexOf('local_update_norm')], 4)}</td><td>{cell(r[cols.indexOf('gradient_norm_mean')], 4)}</td><td>{cell(r[cols.indexOf('aggregation_weight')], 4)}</td><td class="mono">{String(r[cols.indexOf('update_sha256')]).slice(0, 12)}…</td></tr>{/each}</tbody></table></div></div>
		<div class="sel"><h3>Independent evaluation of the matching site condition, state {round}</h3><div class="scroll"><table><thead><tr><th>participant</th><th>AUPRC</th><th>AUROC</th><th>F1</th><th>recall</th><th>specificity</th><th>TP/FP/TN/FN</th></tr></thead><tbody>
			{#each (t5?.rows ?? []).filter((r) => r[0] === round && clientHoldout.includes(r[1])) as r}{@const c = t5!.columns}<tr><th scope="row">{r[1]}</th><td>{cell(r[c.indexOf('AUPRC')], 4)}</td><td>{cell(r[c.indexOf('AUROC')], 4)}</td><td>{cell(r[c.indexOf('F1')], 4)}</td><td>{cell(r[c.indexOf('recall')], 4)}</td><td>{cell(r[c.indexOf('specificity')], 4)}</td><td>{r[c.indexOf('TP')]}/{r[c.indexOf('FP')]}/{r[c.indexOf('TN')]}/{r[c.indexOf('FN')]}</td></tr>{/each}</tbody></table></div>
			<small>Site {siteIndex}: the two holdout participants with this site's synthetic condition.</small></div>
	{:else if tab === 'bridge'}
		<div class="panel"><h2>Scientific research bridge (separate evidence lane)</h2><p class="warn">{ov.scientific_bridge.note}</p>
			<div class="scroll"><table data-testid="bridge-table"><thead><tr><th>Dataset</th><th>Centralized V2 AUPRC</th><th>Federated V2 FedAvg IID AUPRC</th><th>Difference</th></tr></thead><tbody>{#each bridgeRows as r}<tr><th scope="row">{r.dataset}</th><td>{cell(r.centralized_V2_AUPRC as number, 6)}</td><td>{cell(r.federated_V2_FedAvg_IID_AUPRC as number, 6)}</td><td>{cell(r.AUPRC_difference_federated_minus_centralized as number, 6)}</td></tr>{/each}</tbody></table></div>
			<p class="dim">{ov.scientific_bridge.verdict}. <a href="/app/observatory/outcomes">Open the frozen scientific outcomes →</a> · <a href="/app/observatory/evidence">Evidence explorer →</a></p></div>
		<Fl10Table table={payload.tables['FL10_TAB10']} open /><Fl10Table table={payload.tables['FL10_TAB11']} />
	{:else if tab === 'exports'}
		<div class="panel"><h2>Exports and provenance</h2>
			<p>Protocol <code>{ov.protocol.sha256.slice(0, 16)}…</code> · holdout manifest <code>{ov.protocol.holdout_manifest_sha256.slice(0, 16)}…</code> · method freeze <code>{ov.evaluation.method_freeze_commit.slice(0, 10)}</code> · git <code>{ov.run.git_commit.slice(0, 10)}</code></p>
			<button onclick={() => void exportManifest()}>Download verification manifest (JSON)</button>{#if manifestDigest}<small> SHA256 <code>{manifestDigest.slice(0, 16)}…</code></small>{/if}
			{#if exportNote}<p class="dim" role="status">{exportNote}</p>{/if}
			<h3>Figures (SVG, PNG 300 dpi, source CSV, provenance JSON)</h3>
			<ul class="exp">{#each Object.values(payload.specs) as s (s.id)}<li><b>{s.id.replace('FL10_', '')}</b> {s.title} {#each ['svg', 'png', 'csv', 'provenance'] as f}<button onclick={() => void exportFigure(s.id, f)}>{f}</button>{/each}</li>{/each}</ul></div>
		<h3>Tables (CSV / JSON)</h3><div class="tables">{#each Object.values(payload.tables) as t (t.id)}<Fl10Table table={t} />{/each}</div>
	{/if}
	{#if current.figs.length}<div class="charts">{#each specsOf(current.figs) as s (tab + s.id)}<Fl10Chart spec={s} />{/each}</div>
		<div class="tables">{#if tab === 'training'}<Fl10Table table={payload.tables['FL10_TAB03']} /><Fl10Table table={payload.tables['FL10_TAB04']} />{:else if tab === 'classification'}<Fl10Table table={payload.tables['FL10_TAB01']} open /><Fl10Table table={payload.tables['FL10_TAB09']} />
			{:else if tab === 'clients'}<Fl10Table table={payload.tables['FL10_TAB05']} /><Fl10Table table={payload.tables['FL10_TAB06']} />{:else if tab === 'comparisons'}<Fl10Table table={payload.tables['FL10_TAB02']} open />
			{:else if tab === 'internals'}<Fl10Table table={payload.tables['FL10_TAB07']} /><Fl10Table table={payload.tables['FL10_TAB08']} /><Fl10Table table={payload.tables['FL10_TAB12']} />{/if}</div>{/if}
</section>
<section class="limits" aria-label="Limitations"><h2>Interpretation limits</h2><ul>{#each ov.protocol.interpretation_boundaries as l}<li>{l}</li>{/each}<li>Single-machine federation of eight logical clients on simulated data; payload bytes are logical serialized sizes, not network traffic.</li></ul></section>
{/if}
<p class="dim"><a href="/app/observatory">← Observatory</a> · <a href="/app/observatory/storyboard">Storyboard</a> · <a href="/app/observatory/outcomes">Scientific outcomes</a></p>
<style>
	.eyebrow{color:#2bb8b0;font:10px 'JetBrains Mono',monospace;letter-spacing:.14em}h1{font:500 clamp(28px,4vw,42px) 'Space Grotesk',sans-serif;margin:8px 0}h2{font:500 18px 'Space Grotesk',sans-serif;margin:18px 0 8px}h3{font:500 14px 'Space Grotesk',sans-serif;margin:14px 0 6px}.lead{max-width:880px;color:#a7b8c9;line-height:1.6}
	.syn{display:inline-block;border:1px solid rgba(167,139,250,.6);padding:5px 10px;color:#d8ccff;font:11px 'JetBrains Mono',monospace;margin:0 8px 8px 0}.syn.live{border-color:rgba(43,184,176,.7);color:#9fe8e3}.dim,small,li{color:#94a3b8;font-size:13px;line-height:1.6;overflow-wrap:anywhere}.err{color:#fecdd3}.warn{border-left:3px solid #fbbf24;background:rgba(251,191,36,.06);padding:8px 12px;color:#fde68a;font-size:13px}a{color:#2bb8b0;display:inline-block;min-height:24px;line-height:24px}code,.mono{font:12px 'JetBrains Mono',monospace;color:#9fe7e1}
	.controls{display:flex;flex-wrap:wrap;gap:10px;align-items:end;margin:12px 0}.controls label{display:grid;gap:4px;font:10px 'JetBrains Mono',monospace;color:#71829a}select,button{background:#0a0f1f;color:#e2e8f0;border:1px solid rgba(148,163,184,.35);padding:6px 10px;min-height:32px;font:12px 'JetBrains Mono',monospace;cursor:pointer}button.on,.tabs button.on{border-color:#2bb8b0;color:#9fe8e3}button:disabled{opacity:.5;cursor:not-allowed}button.link{border:0;background:none;color:#2bb8b0;text-decoration:underline;padding:2px}
	.job,.panel,.headline,.sel,.limits{border:1px solid rgba(148,163,184,.22);padding:12px 14px;margin:10px 0;background:rgba(10,15,31,.4)}progress{width:100%;margin:6px 0}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,210px),1fr));gap:8px;margin:12px 0}.cards div{border:1px solid rgba(148,163,184,.22);padding:10px 12px;display:grid;gap:3px;min-width:0}.cards span{font:9px 'JetBrains Mono',monospace;color:#71829a;letter-spacing:.1em}.cards strong{font:500 17px 'Space Grotesk',sans-serif;overflow-wrap:anywhere}.cards small{overflow-wrap:anywhere}
	.tabs{display:flex;gap:6px;overflow-x:auto;margin:16px 0 8px;padding-bottom:4px}.tabs button{white-space:nowrap}.charts{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,520px),1fr));gap:12px;margin:12px 0}.tables{display:grid;gap:10px;margin:12px 0}.scroll{overflow-x:auto;max-width:100%}table{border-collapse:collapse;font-size:12px;width:100%}th,td{border-bottom:1px solid rgba(148,163,184,.16);padding:6px 9px;text-align:left}thead th{color:#71829a;font:10px 'JetBrains Mono',monospace}.index,.exp{padding-left:18px;display:grid;gap:4px}.exp button{margin-left:4px;padding:2px 8px;min-height:24px}h1:focus{outline:none}
</style>
