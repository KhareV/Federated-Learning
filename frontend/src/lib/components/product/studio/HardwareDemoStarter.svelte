<script lang="ts">
	// The "Recorded hardware" branch of the single "Start a federation run" card. It owns no rounds
	// control: the rounds radio of the parent card is the only one, so both data sources share one form.
	import { goto } from '$app/navigation';
	import { getProductStore } from '$lib/product/state.svelte';
	import type { CohortId, HardwareDemoRun, HardwareDemoSession, HardwareStartingModel, HardwareV2Preview, StudioCandidate, StudioCapabilities } from '$lib/product/studio/types';
	let { capabilities = null, disabled = false, rounds = 3, preselect = null, cohort = 'ORIGINAL' }: { capabilities?: StudioCapabilities | null; disabled?: boolean; rounds?: 3 | 10; preselect?: string | null; cohort?: CohortId } = $props();
	const product = getProductStore();
	let sessions = $state<HardwareDemoSession[]>([]);
	let priorRuns = $state<HardwareDemoRun[]>([]);
	let selected = $state<string[]>([]);
	let algorithm = $state<'FEDAVG' | 'FEDPROX'>('FEDAVG');
	let secagg = $state<'PLAIN' | 'SECAGG_SHADOW'>('PLAIN');
	type StartModel = 'FRESH_SEEDED' | 'WARM_START' | 'MODEL_V2_FINAL' | 'CANDIDATE';
	let candidates = $state<StudioCandidate[]>([]);
	let candidatePick = $state('');
	let modelChoice = $state<StartModel | null>(null);       // null = the user has not chosen: the default applies (pretrained V2, as for the synthetic cohort); any explicit choice, including Fresh, is kept
	let warmRun = $state('');
	let seed = $state(20261015);
	let running = $state(false);
	let error = $state<string | null>(null);
	let loaded = $state(false);
	const hw = $derived(capabilities?.hardware_demo);
	const available = $derived(hw?.available === true);
	const models = $derived<HardwareStartingModel[]>(hw?.starting_models ?? [
		{ id: 'FRESH_SEEDED', label: 'Fresh initialisation (seeded, untrained)', available: true, reason: null }]);
	const v2Model = $derived(models.find((m) => m.id === 'MODEL_V2_FINAL'));
	const startModel = $derived<StartModel>(modelChoice ?? (v2Model?.available === true ? 'MODEL_V2_FINAL' : 'FRESH_SEEDED'));
	const warmAvailable = $derived(models.some((m) => m.id === 'WARM_START' && m.available));
	const eligible = $derived(sessions.filter((s) => s.eligible));
	const ordered = $derived([...sessions.filter((s) => s.eligible), ...sessions.filter((s) => !s.eligible)]);
	const warmPick = $derived(warmRun || priorRuns[0]?.run_id || '');
	// Pretrained V2: the chosen sessions are resampled and graded by the unchanged PREPROC_V1 gate; only VALID windows train. The preview shows what is usable BEFORE a run is started.
	let preview = $state<HardwareV2Preview | null>(null);
	let previewing = $state(false);
	let previewError = $state<string | null>(null);
	let previewSeq = 0;
	const v2 = $derived(startModel === 'MODEL_V2_FINAL' || startModel === 'CANDIDATE');      // both start the pretrained-V2 family: same topology, windows and quality gate; only R0 differs
	const candidateId = $derived(candidatePick || candidates[0]?.candidate_id || '');
	const pickedCandidate = $derived(candidates.find((c) => c.candidate_id === candidateId) ?? null);
	$effect(() => {
		const ids = selected;
		if (!v2 || ids.length === 0) { preview = null; previewError = null; previewing = false; return; }
		const mine = ++previewSeq;
		previewing = true; previewError = null; preview = null;
		product.api.hardwareV2Preview(ids).then((value) => { if (mine === previewSeq) preview = value; }).catch((cause) => { if (mine === previewSeq) previewError = cause instanceof Error ? cause.message : String(cause); }).finally(() => { if (mine === previewSeq) previewing = false; });
	});
	// The realistic cohort supplies the seven synthetic peers (and the evaluation holdout) of a pretrained-V2 run; the tabular starts have eight recorded blocks and no peers.
	const cohortNeedsV2 = $derived(cohort === 'REALISTIC' && !v2);
	const canStart = $derived(!disabled && !running && !cohortNeedsV2 && selected.length > 0 && (startModel === 'FRESH_SEEDED' || (startModel === 'WARM_START' && !!warmPick) || (v2 && preview?.eligible === true && (startModel !== 'CANDIDATE' || !!candidateId))));
	async function load() {
		if (!available) return;
		try {
			sessions = await product.api.hardwareDemoSessions();
			// deep link from History ("Use in FL"): preselect that session when it is eligible; the user can still change the selection
			if (preselect && selected.length === 0 && sessions.some((x) => x.id === preselect && x.eligible)) selected = [preselect];
			candidates = await product.api.studioCandidates().catch(() => [] as StudioCandidate[]);
			priorRuns = (await product.api.hardwareDemoRuns()).filter((r) => r.model.id === 'HARDWARE_DEMO_MODEL_V1' && r.status === 'COMPLETED');
		} catch (cause) { error = cause instanceof Error ? cause.message : String(cause); }
	}
	$effect(() => { if (available && !loaded) { loaded = true; void load(); } });
	function toggle(id: string) { selected = selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]; }
	async function start() {
		running = true; error = null;
		try {
			// The run executes on the backend and is observed on the same Live page as every other run.
			const run = await product.api.hardwareDemoStart({
				session_ids: selected, run_length: rounds, algorithm, secagg_mode: secagg, label_seed: seed,
				initialisation: startModel, ...(startModel === 'WARM_START' ? { warm_start_run_id: warmPick } : {}), ...(startModel === 'CANDIDATE' ? { candidate_id: candidateId } : {}), ...(cohort === 'REALISTIC' && v2 ? { cohort } : {})
			});
			await goto(`/app/federation/live?run=${encodeURIComponent(run.run_id)}`);
		} catch (cause) { error = cause instanceof Error ? cause.message : String(cause); }
		finally { running = false; }
	}
</script>
<form class="cfg" data-testid="hardware-demo-starter" onsubmit={(e) => { e.preventDefault(); if (canStart) void start(); }} aria-label={`Recorded hardware ${rounds}-round run configuration`}>
	<p class="boundary" data-testid="hardware-demo-boundary">{v2 ? 'RECORDED HARDWARE · actual saved MongoDB telemetry windows (resampled, quality-gated) · deterministic SYNTHETIC labels · genuine federated fine-tuning of the pretrained V2 (one recorded client + seven synthetic peers) · no clinical meaning.' : 'RECORDED HARDWARE · actual saved MongoDB telemetry features · deterministic SYNTHETIC labels · genuine toy federated optimisation · no clinical meaning.'} {v2 ? 'The recorded client holds one recording, not a fleet of devices; its seven peers are synthetic.' : 'Eight logical clients are partitions of one recording, not eight devices.'}</p>
	{#if !available}<p class="warn" role="status">Hardware telemetry is unavailable in this backend configuration.</p>
	{:else}
		<fieldset class="sessions" aria-label="Recorded sessions">
			<legend>Recorded sessions <small>{eligible.length} of {sessions.length} eligible</small></legend>
			{#if sessions.length === 0}<p class="dim">No stopped hardware sessions yet. Record one on the Monitor page with “Live hardware (MongoDB)”.</p>{/if}
			{#if sessions.length > 0}
				<details class="picker" data-testid="hardware-demo-session-picker">
					<summary data-testid="hardware-demo-session-summary"><span>{selected.length === 0 ? 'Choose recorded sessions' : selected.length === 1 ? selected[0] : `${selected.length} sessions selected`}</span><small>{eligible.length} eligible</small></summary>
					<div class="options">
						{#each ordered as session (session.id)}
							<label class="session" class:ineligible={!session.eligible}>
								<input type="checkbox" data-testid={`hardware-demo-session-${session.id}`} checked={selected.includes(session.id)} disabled={!session.eligible || running} onchange={() => toggle(session.id)} />
								<span><code>{session.id}</code><small>{session.trace_count} stored readings · {new Date(session.started_at).toLocaleString()}{session.eligible ? '' : ' · insufficient data (needs ≥ 8 usable 1 s windows with a 2-class split)'}</small></span>
							</label>
						{/each}
					</div>
				</details>
			{/if}
		</fieldset>
		<label><span>Starting model</span>
			<select value={startModel} onchange={(e) => { modelChoice = (e.currentTarget as HTMLSelectElement).value as StartModel; }} disabled={running} data-testid="hardware-demo-init">
				{#each models as m (m.id)}<option value={m.id} disabled={!m.available}>{m.id === 'MODEL_V2_FINAL' ? 'Pretrained V2 — MODEL_V2_FINAL, federated fine-tuning' : m.label}</option>{/each}
			</select></label>
		{#if startModel === 'WARM_START'}
			<label><span>Warm-start source run</span>
				<select bind:value={warmRun} disabled={running || priorRuns.length === 0} data-testid="hardware-demo-warm-run">
					{#each priorRuns as r (r.run_id)}<option value={r.run_id}>{r.run_id} · {r.algorithm} · {r.rounds_planned} rounds · {new Date(r.completed_at).toLocaleString()}</option>{/each}
				</select></label>
			<p class="help" data-testid="hardware-demo-warm-note">{priorRuns.length ? 'R0 is the final global weights of that earlier recorded-hardware run, unchanged; the rounds then continue training on the sessions selected above. Normalisation is refitted on the new training windows.' : 'No earlier recorded-hardware run exists yet; run once from a fresh initialisation first.'}</p>
		{:else if v2}
			<p class="help" data-testid="hardware-demo-v2-note">{startModel === 'CANDIDATE' ? 'R0 is the final state of the stored candidate chosen below, unchanged.' : 'R0 is the verified pretrained MODEL_V2_FINAL checkpoint, unchanged.'} Your recording becomes ONE recorded client (up to 93 windows) federated with the seven {cohort === 'REALISTIC' ? 'realistic' : 'canonical'} synthetic peers of the cohort. {v2Model?.note ?? 'Your recorded windows are resampled onto the V2 source grid and graded by the unchanged quality gate; only VALID windows train.'} The model changes from the small tabular classifier to the V2 ECG network, and the topology from eight recorded blocks to one recorded client plus seven peers (their labels stay the cohort's synthetic event-window labels; yours are assigned), so this is a different run family from the fresh and warm-start choices.</p>
			{#if startModel === 'CANDIDATE'}
				<label><span>Candidate</span><select bind:value={candidatePick} disabled={running} data-testid="hardware-demo-candidate">{#each candidates as c (c.candidate_id)}<option value={c.candidate_id}>{c.candidate_id} · {c.cohort === 'REALISTIC' ? 'realistic' : 'original'} cohort · {c.run_length} rounds{c.metrics?.AUPRC !== undefined ? ` · AUPRC ${c.metrics.AUPRC.toFixed(3)}` : ''}</option>{/each}</select></label>
				{#if pickedCandidate}<p class="help" data-testid="hardware-demo-candidate-note">Started from {pickedCandidate.candidate_id} (trained on the {pickedCandidate.cohort === 'REALISTIC' ? 'realistic' : 'original'} cohort; this run's peers come from the {cohort === 'REALISTIC' ? 'realistic' : 'original'} cohort).</p>{/if}
			{/if}
			{#if selected.length === 0}<p class="help">Select at least one recorded session to see how many V2 windows it provides.</p>
			{:else if previewing}<p class="help" role="status">Checking what the unchanged quality gate accepts…</p>
			{:else if previewError}<p class="warn" role="alert" data-testid="hardware-v2-preview-error">{previewError}</p>
			{:else if preview}
				<div class="result" data-testid="hardware-v2-preview" class:bad={!preview.eligible}>
					<b>{preview.eligible ? 'ENOUGH USABLE WINDOWS' : 'NOT ENOUGH USABLE WINDOWS'}</b>
					<span>{preview.train_windows} training · {preview.holdout_windows} holdout windows (needs {preview.min_train_windows} and {preview.min_holdout_windows}); time-purged so no training window overlaps the holdout.</span>
					<table aria-label="V2 windows per recorded session"><thead><tr><th scope="col">Session</th><th scope="col">10 s windows</th><th scope="col">Quality-VALID</th><th scope="col">Train</th><th scope="col">Holdout</th></tr></thead>
						<tbody>{#each preview.sessions as row (row.session_id)}<tr><th scope="row"><code>{row.session_id}</code></th><td>{row.windows}</td><td>{row.usable}</td><td>{row.train}</td><td>{row.holdout}</td></tr>{/each}</tbody></table>
					{#if preview.reason}<span class="warn" data-testid="hardware-v2-preview-reason">{preview.reason}</span>{/if}
				</div>
			{/if}
		{:else}
			<p class="help" data-testid="hardware-demo-init-note">R0 is a seeded, untrained HARDWARE_DEMO_MODEL_V1 (a small tabular classifier over window features).</p>
		{/if}
		{#if cohortNeedsV2}<p class="warn" role="status" data-testid="hardware-cohort-needs-v2">The realistic cohort supplies the seven synthetic peers of a pretrained-V2 recorded-hardware run. Choose the pretrained V2 starting model, or switch the cohort back to original.</p>{/if}
		{#if !warmAvailable}<p class="help">Warm start is not advertised by the connected backend.</p>{/if}
		<label><span>Algorithm</span><select bind:value={algorithm} disabled={running} data-testid="hardware-demo-algorithm"><option value="FEDAVG">FedAvg — sample-count-weighted averaging</option><option value="FEDPROX">FedProx — fixed μ {hw?.fedprox_mu ?? 0.1}</option></select></label>
		<label><span>Aggregation / protection mode</span><select bind:value={secagg} disabled={running} data-testid="hardware-demo-secagg"><option value="PLAIN">Plain aggregation</option><option value="SECAGG_SHADOW">Round-1 SecAgg+ shadow verification</option></select></label>
		<p class="help">{secagg === 'SECAGG_SHADOW' ? 'ROUND-1 SECAGG+ SHADOW: a real protected aggregate is compared with the authoritative plain aggregate. It does not make the run private.' : 'Plain, sample-count-weighted aggregation.'}</p>
		<label><span>Label seed</span><input type="number" min="0" max="2147483647" bind:value={seed} disabled={running} data-testid="hardware-demo-seed" /></label>
		<dl class="fixedcfg" aria-label="Fixed configuration"><div><dt>Model</dt><dd>{startModel === 'CANDIDATE' ? 'stored candidate (fine-tuned)' : v2 ? 'MODEL_V2_FINAL (fine-tuned)' : 'HARDWARE_DEMO_MODEL_V1'}</dd></div><div><dt>Clients</dt><dd>{v2 ? '1 recorded + 7 peers' : '8 logical'}</dd></div><div><dt>Rounds</dt><dd>{rounds}</dd></div><div><dt>Labels</dt><dd>SYNTHETIC</dd></div></dl>
		<button type="submit" disabled={!canStart} data-testid="hardware-demo-start">{running ? 'Preparing the run…' : `Create and start ${rounds}-round recorded-hardware run · ${startModel === 'MODEL_V2_FINAL' ? 'pretrained V2' : startModel === 'CANDIDATE' ? 'candidate start' : startModel === 'WARM_START' ? 'warm start' : 'fresh initialisation'}`}</button>
		{#if error}<p class="warn" role="alert">{error}</p>{/if}
	{/if}
</form>
<style>
	.cfg { display: grid; gap: 10px; max-width: 560px; min-width: 0; } .boundary { margin: 0; color: #fbbf24; font: 11px/1.5 'JetBrains Mono', monospace; border: 1px solid rgba(251,191,36,.4); padding: 8px 10px; }
	label { display: flex; flex-direction: column; gap: 7px; min-width: 0; font: 11px 'JetBrains Mono', monospace; letter-spacing: .06em; color: #94a3b8; }
	select, input[type='number'], .cfg button { max-width: 100%; box-sizing: border-box; font: 13px Inter, sans-serif; padding: 8px 10px; background: #07101e; color: #e5f1f0; border: 1px solid rgba(148,163,184,.3); }
	.cfg button { background: #2bb8b0; color: #030712; font-weight: 600; cursor: pointer; } .cfg button:disabled { opacity: .45; cursor: not-allowed; }
	.help, .dim { margin: 0; color: #94a3b8; font-size: 12px; line-height: 1.5; } .warn { margin: 0; color: #fbbf24; font: 11px 'JetBrains Mono', monospace; }
	.sessions { border: 1px solid rgba(148,163,184,.2); padding: 8px 10px; display: grid; gap: 6px; margin: 0; min-width: 0; } legend { font: 11px 'JetBrains Mono', monospace; color: #94a3b8; letter-spacing: .06em; padding: 0 4px; } legend small { color: #71829a; }
	.picker { border: 1px solid rgba(148,163,184,.22); background: rgba(8,13,22,.6); } .picker > summary { display: flex; justify-content: space-between; align-items: center; gap: 10px; padding: 9px 10px; cursor: pointer; font: 12px Inter, sans-serif; color: #e2e8f0; letter-spacing: 0; } .picker > summary small { color: #71829a; } .picker .options { display: grid; max-height: 280px; overflow: auto; border-top: 1px solid rgba(148,163,184,.14); }
	.session { flex-direction: row; align-items: flex-start; gap: 10px; letter-spacing: 0; font: 12px Inter, sans-serif; color: #cbd5e1; border: 1px solid rgba(148,163,184,.14); padding: 8px; } .session.ineligible { opacity: .55; } .session span { display: grid; gap: 2px; min-width: 0; } .session small { color: #71829a; font-size: 11px; }
	code { color: #9fe7e1; overflow-wrap: anywhere; } .fixedcfg { display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: 6px; margin: 0; } .fixedcfg div { border: 1px solid rgba(148,163,184,.16); padding: 6px 8px; }
	dt { color: #71829a; font: 10.5px 'JetBrains Mono', monospace; letter-spacing: .1em; text-transform: uppercase; } dd { margin: 3px 0 0; font-size: 13px; color: #e5f1f0; }
	.result.bad { border-color: rgba(251,191,36,.5); } .result { display: grid; gap: 6px; border: 1px solid rgba(43,184,176,.4); padding: 10px; font-size: 12px; color: #cbd5e1; } table { border-collapse: collapse; width: 100%; font: 11px 'JetBrains Mono', monospace; } th, td { text-align: left; padding: 3px 6px; border-bottom: 1px solid rgba(148,163,184,.16); }
	p, dd, small, label, button { overflow-wrap: anywhere; }
</style>
