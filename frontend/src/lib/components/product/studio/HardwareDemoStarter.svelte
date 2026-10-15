<script lang="ts">
	// The "Recorded hardware" branch of the single "Start a federation run" card. It owns no rounds
	// control: the rounds radio of the parent card is the only one, so both data sources share one form.
	import { getProductStore } from '$lib/product/state.svelte';
	import type { HardwareDemoRun, HardwareDemoSession, HardwareStartingModel, StudioCapabilities } from '$lib/product/studio/types';
	let { capabilities = null, disabled = false, rounds = 3 }: { capabilities?: StudioCapabilities | null; disabled?: boolean; rounds?: 3 | 10 } = $props();
	const product = getProductStore();
	let sessions = $state<HardwareDemoSession[]>([]);
	let priorRuns = $state<HardwareDemoRun[]>([]);
	let selected = $state<string[]>([]);
	let algorithm = $state<'FEDAVG' | 'FEDPROX'>('FEDAVG');
	let secagg = $state<'PLAIN' | 'SECAGG_SHADOW'>('PLAIN');
	let startModel = $state<'FRESH_SEEDED' | 'WARM_START'>('FRESH_SEEDED');
	let warmRun = $state('');
	let seed = $state(20261015);
	let running = $state(false);
	let error = $state<string | null>(null);
	let result = $state<HardwareDemoRun | null>(null);
	let loaded = $state(false);
	const hw = $derived(capabilities?.hardware_demo);
	const available = $derived(hw?.available === true);
	const models = $derived<HardwareStartingModel[]>(hw?.starting_models ?? [
		{ id: 'FRESH_SEEDED', label: 'Fresh initialisation (seeded, untrained)', available: true, reason: null }]);
	const v2Model = $derived(models.find((m) => m.id === 'MODEL_V2_FINAL'));
	const warmAvailable = $derived(models.some((m) => m.id === 'WARM_START' && m.available));
	const eligible = $derived(sessions.filter((s) => s.eligible));
	const warmPick = $derived(warmRun || priorRuns[0]?.run_id || '');
	const canStart = $derived(!disabled && !running && selected.length > 0 && (startModel === 'FRESH_SEEDED' || !!warmPick));
	async function load() {
		if (!available) return;
		try {
			sessions = await product.api.hardwareDemoSessions();
			priorRuns = (await product.api.hardwareDemoRuns()).filter((r) => r.model.id === 'HARDWARE_DEMO_MODEL_V1');
		} catch (cause) { error = cause instanceof Error ? cause.message : String(cause); }
	}
	$effect(() => { if (available && !loaded) { loaded = true; void load(); } });
	function toggle(id: string) { selected = selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]; }
	async function start() {
		running = true; error = null; result = null;
		try {
			result = await product.api.hardwareDemoStart({
				session_ids: selected, run_length: rounds, algorithm, secagg_mode: secagg, label_seed: seed,
				initialisation: startModel, ...(startModel === 'WARM_START' ? { warm_start_run_id: warmPick } : {})
			});
			priorRuns = [result, ...priorRuns];
		} catch (cause) { error = cause instanceof Error ? cause.message : String(cause); }
		finally { running = false; }
	}
</script>
<form class="cfg" data-testid="hardware-demo-starter" onsubmit={(e) => { e.preventDefault(); if (canStart) void start(); }} aria-label={`Recorded hardware ${rounds}-round run configuration`}>
	<p class="boundary" data-testid="hardware-demo-boundary">RECORDED HARDWARE · actual saved MongoDB telemetry features · deterministic SYNTHETIC labels · genuine toy federated optimisation · no clinical meaning. Eight logical clients are partitions of one recording, not eight devices.</p>
	{#if !available}<p class="warn" role="status">Hardware telemetry is unavailable in this backend configuration.</p>
	{:else}
		<fieldset class="sessions" aria-label="Recorded sessions">
			<legend>Recorded sessions <small>{eligible.length} of {sessions.length} eligible</small></legend>
			{#if sessions.length === 0}<p class="dim">No stopped hardware sessions yet. Record one on the Monitor page with “Live hardware (MongoDB)”.</p>{/if}
			{#each sessions as session (session.id)}
				<label class="session" class:ineligible={!session.eligible}>
					<input type="checkbox" data-testid={`hardware-demo-session-${session.id}`} checked={selected.includes(session.id)} disabled={!session.eligible || running} onchange={() => toggle(session.id)} />
					<span><code>{session.id}</code><small>{session.trace_count} stored readings · {new Date(session.started_at).toLocaleString()}{session.eligible ? '' : ' · insufficient data (needs ≥ 8 usable 1 s windows with a 2-class split)'}</small></span>
				</label>
			{/each}
		</fieldset>
		<label><span>Starting model</span>
			<select bind:value={startModel} disabled={running} data-testid="hardware-demo-init">
				{#each models.filter((m) => m.id !== 'MODEL_V2_FINAL') as m (m.id)}<option value={m.id} disabled={!m.available}>{m.label}</option>{/each}
				{#if v2Model}<option value="MODEL_V2_FINAL" disabled>{v2Model.label} — not applicable</option>{/if}
			</select></label>
		{#if startModel === 'WARM_START'}
			<label><span>Warm-start source run</span>
				<select bind:value={warmRun} disabled={running || priorRuns.length === 0} data-testid="hardware-demo-warm-run">
					{#each priorRuns as r (r.run_id)}<option value={r.run_id}>{r.run_id} · {r.algorithm} · {r.rounds_planned} rounds · {new Date(r.completed_at).toLocaleString()}</option>{/each}
				</select></label>
			<p class="help" data-testid="hardware-demo-warm-note">{priorRuns.length ? 'R0 is the final global weights of that earlier recorded-hardware run, unchanged; the rounds then continue training on the sessions selected above. Normalisation is refitted on the new training windows.' : 'No earlier recorded-hardware run exists yet; run once from a fresh initialisation first.'}</p>
		{:else}
			<p class="help" data-testid="hardware-demo-init-note">R0 is a seeded, untrained HARDWARE_DEMO_MODEL_V1 (a small tabular classifier over window features).</p>
		{/if}
		{#if v2Model}<p class="help" data-testid="hardware-demo-v2-note">Pretrained V2 is not offered here: {v2Model.reason}</p>{/if}
		{#if !warmAvailable}<p class="help">Warm start is not advertised by the connected backend.</p>{/if}
		<label><span>Algorithm</span><select bind:value={algorithm} disabled={running} data-testid="hardware-demo-algorithm"><option value="FEDAVG">FedAvg — sample-count-weighted averaging</option><option value="FEDPROX">FedProx — fixed μ {hw?.fedprox_mu ?? 0.1}</option></select></label>
		<label><span>Aggregation / protection mode</span><select bind:value={secagg} disabled={running} data-testid="hardware-demo-secagg"><option value="PLAIN">Plain aggregation</option><option value="SECAGG_SHADOW">Round-1 SecAgg+ shadow verification</option></select></label>
		<p class="help">{secagg === 'SECAGG_SHADOW' ? 'ROUND-1 SECAGG+ SHADOW: a real protected aggregate is compared with the authoritative plain aggregate. It does not make the run private.' : 'Plain, sample-count-weighted aggregation.'}</p>
		<label><span>Label seed</span><input type="number" min="0" max="2147483647" bind:value={seed} disabled={running} data-testid="hardware-demo-seed" /></label>
		<dl class="fixed" aria-label="Fixed configuration"><div><dt>Model</dt><dd>HARDWARE_DEMO_MODEL_V1</dd></div><div><dt>Clients</dt><dd>8 logical</dd></div><div><dt>Rounds</dt><dd>{rounds}</dd></div><div><dt>Labels</dt><dd>SYNTHETIC</dd></div></dl>
		<button type="submit" disabled={!canStart} data-testid="hardware-demo-start">{running ? 'Training…' : `Create and start ${rounds}-round recorded-hardware run`}</button>
		{#if error}<p class="warn" role="alert">{error}</p>{/if}
		{#if result}
			<div class="result" data-testid="hardware-demo-result">
				<b>{result.run_id} · COMPLETED</b>
				<span>{result.dataset.training_windows} train / {result.dataset.holdout_windows} holdout windows · 8 clients · {result.rounds.length} rounds · {result.rounds.reduce((n, r) => n + r.accepted_updates, 0)} accepted updates</span>
				<span>Start: {result.model.initialisation === 'WARM_START' && result.model.warm_start ? `warm start from ${result.model.warm_start.source_run_id}` : 'fresh seeded initialisation'}</span>
				<span>Feature digest <code>{result.dataset.input_feature_sha256.slice(0, 16)}…</code> · final state <code>{result.state_progression[String(result.rounds_planned)].slice(0, 16)}…</code></span>
				{#if result.secagg_shadow}<span>SecAgg+ shadow: {String(result.secagg_shadow.status)} · authoritative aggregate PLAIN</span>{/if}
				<table aria-label="Per-round results"><thead><tr><th>round</th><th>train loss</th><th>holdout BCE</th><th>accuracy</th></tr></thead>
					<tbody>{#each result.rounds as r (r.round)}<tr><td>R{r.round}</td><td>{r.weighted_mean_training_loss.toFixed(4)}</td><td>{r.evaluation.BCE.toFixed(4)}</td><td>{(r.evaluation.accuracy * 100).toFixed(1)}%</td></tr>{/each}</tbody></table>
				<span class="dim">{(result as unknown as { claim_boundary?: string }).claim_boundary ?? ''}</span>
			</div>
		{/if}
	{/if}
</form>
<style>
	.cfg { display: grid; gap: 10px; max-width: 560px; min-width: 0; } .boundary { margin: 0; color: #fbbf24; font: 11px/1.5 'JetBrains Mono', monospace; border: 1px solid rgba(251,191,36,.4); padding: 8px 10px; }
	label { display: flex; flex-direction: column; gap: 7px; min-width: 0; font: 11px 'JetBrains Mono', monospace; letter-spacing: .06em; color: #94a3b8; }
	select, input[type='number'], .cfg button { max-width: 100%; box-sizing: border-box; font: 13px Inter, sans-serif; padding: 8px 10px; background: #07101e; color: #e5f1f0; border: 1px solid rgba(148,163,184,.3); }
	.cfg button { background: #2bb8b0; color: #030712; font-weight: 600; cursor: pointer; } .cfg button:disabled { opacity: .45; cursor: not-allowed; }
	.help, .dim { margin: 0; color: #94a3b8; font-size: 12px; line-height: 1.5; } .warn { margin: 0; color: #fbbf24; font: 11px 'JetBrains Mono', monospace; }
	.sessions { border: 1px solid rgba(148,163,184,.2); padding: 8px 10px; display: grid; gap: 6px; margin: 0; min-width: 0; } legend { font: 11px 'JetBrains Mono', monospace; color: #94a3b8; letter-spacing: .06em; padding: 0 4px; } legend small { color: #71829a; }
	.session { flex-direction: row; align-items: flex-start; gap: 10px; letter-spacing: 0; font: 12px Inter, sans-serif; color: #cbd5e1; border: 1px solid rgba(148,163,184,.14); padding: 8px; } .session.ineligible { opacity: .55; } .session span { display: grid; gap: 2px; min-width: 0; } .session small { color: #71829a; font-size: 11px; }
	code { color: #9fe7e1; overflow-wrap: anywhere; } .fixed { display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: 6px; margin: 0; } .fixed div { border: 1px solid rgba(148,163,184,.16); padding: 6px 8px; }
	dt { color: #71829a; font: 9px 'JetBrains Mono', monospace; letter-spacing: .1em; text-transform: uppercase; } dd { margin: 3px 0 0; font-size: 13px; color: #e5f1f0; }
	.result { display: grid; gap: 6px; border: 1px solid rgba(43,184,176,.4); padding: 10px; font-size: 12px; color: #cbd5e1; } table { border-collapse: collapse; width: 100%; font: 11px 'JetBrains Mono', monospace; } th, td { text-align: left; padding: 3px 6px; border-bottom: 1px solid rgba(148,163,184,.16); }
	p, dd, small, label, button { overflow-wrap: anywhere; }
</style>
