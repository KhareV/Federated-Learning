<script lang="ts">
	import { getProductStore } from '$lib/product/state.svelte';
	import type { HardwareDemoRun, HardwareDemoSession, StudioCapabilities } from '$lib/product/studio/types';
	let { capabilities = null, disabled = false }: { capabilities?: StudioCapabilities | null; disabled?: boolean } = $props();
	const product = getProductStore();
	let sessions = $state<HardwareDemoSession[]>([]);
	let selected = $state<string[]>([]);
	let rounds = $state<3 | 10>(3);
	let algorithm = $state<'FEDAVG' | 'FEDPROX'>('FEDAVG');
	let secagg = $state<'PLAIN' | 'SECAGG_SHADOW'>('PLAIN');
	let seed = $state(20261015);
	let running = $state(false);
	let error = $state<string | null>(null);
	let result = $state<HardwareDemoRun | null>(null);
	let loaded = $state(false);
	const available = $derived(capabilities?.hardware_demo?.available === true);
	async function load() { if (!available) return; try { sessions = await product.api.hardwareDemoSessions(); } catch (cause) { error = cause instanceof Error ? cause.message : String(cause); } }
	$effect(() => { if (available && !loaded) { loaded = true; void load(); } });
	function toggle(id: string) { selected = selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]; }
	async function start() {
		running = true; error = null; result = null;
		try { result = await product.api.hardwareDemoStart({ session_ids: selected, run_length: rounds, algorithm, secagg_mode: secagg, label_seed: seed }); }
		catch (cause) { error = cause instanceof Error ? cause.message : String(cause); }
		finally { running = false; }
	}
</script>
<section class="demo" data-testid="hardware-demo-starter">
	<h3>Recorded hardware — demo FL</h3>
	<p class="boundary">Actual saved MongoDB telemetry features · deterministic synthetic labels · genuine toy federated optimization · no clinical meaning.</p>
	{#if !available}<p class="warn">Hardware telemetry is unavailable in this backend configuration.</p>
	{:else}
		<div class="sessions"><b>Eligible stopped sessions</b>
			{#if sessions.length === 0}<p>No stopped hardware sessions are available.</p>{/if}
			{#each sessions as session (session.id)}<label class:ineligible={!session.eligible}><input type="checkbox" data-testid={`hardware-demo-session-${session.id}`} checked={selected.includes(session.id)} disabled={!session.eligible || running} onchange={() => toggle(session.id)} /> <code>{session.id}</code> · {session.trace_count} stored records {session.eligible ? '' : '· insufficient data'}</label>{/each}
		</div>
		<div class="choices">
			<label>Rounds<select bind:value={rounds} disabled={running} data-testid="hardware-demo-rounds"><option value={3}>3</option><option value={10}>10</option></select></label>
			<label>Algorithm<select bind:value={algorithm} disabled={running} data-testid="hardware-demo-algorithm"><option value="FEDAVG">FedAvg</option><option value="FEDPROX">FedProx (μ 0.1)</option></select></label>
			<label>Aggregation<select bind:value={secagg} disabled={running} data-testid="hardware-demo-secagg"><option value="PLAIN">Plain</option><option value="SECAGG_SHADOW">Round-1 SecAgg+ shadow</option></select></label>
			<label>Label seed<input type="number" min="0" max="2147483647" bind:value={seed} disabled={running} /></label>
		</div>
		<p class="note">Model: HARDWARE_DEMO_MODEL_V1 · eight logical partitions from recorded windows · MODEL_V2_FINAL initialization and G1 Generalisation are not applicable.</p>
		<button onclick={start} disabled={disabled || running || selected.length === 0} data-testid="hardware-demo-start">{running ? 'Training…' : `Run genuine ${rounds}-round demo`}</button>
		{#if error}<p class="warn" role="alert">{error}</p>{/if}
		{#if result}<div class="result" data-testid="hardware-demo-result"><b>{result.run_id} · COMPLETED</b><span>{result.dataset.training_windows} train / {result.dataset.holdout_windows} holdout windows</span><span>8 clients · {result.rounds.length} rounds · {result.rounds.reduce((n, r) => n + r.accepted_updates, 0)} accepted updates</span><span>Feature digest <code>{result.dataset.input_feature_sha256.slice(0, 16)}…</code></span><span>Final state <code>{result.state_progression[String(result.rounds_planned)].slice(0, 16)}…</code></span>{#if result.secagg_shadow}<span>SecAgg+ shadow: {String(result.secagg_shadow.status)} · authoritative aggregate PLAIN</span>{/if}<span>{result.claim_boundary}</span></div>{/if}
	{/if}
</section>
<style>
	.demo { margin-top: 18px; border-top: 1px solid rgba(148,163,184,.22); padding-top: 16px; display: grid; gap: 10px; } h3 { margin: 0; font: 600 18px 'Space Grotesk', sans-serif; } .boundary,.note,.sessions p { margin: 0; color: #94a3b8; font-size: 12px; line-height: 1.5; } .sessions { display: grid; gap: 7px; } .sessions label { font-size: 12px; color: #cbd5e1; } .sessions label.ineligible { opacity: .55; } .choices { display: grid; grid-template-columns: repeat(auto-fit,minmax(130px,1fr)); gap: 8px; } .choices label { display: grid; gap: 5px; color: #94a3b8; font: 10px 'JetBrains Mono',monospace; } select,input,button { padding: 8px; background: #07101e; color: #e5f1f0; border: 1px solid rgba(148,163,184,.3); } button { background: #2bb8b0; color: #031015; font-weight: 700; cursor: pointer; } button:disabled { opacity: .45; } .warn { color: #fbbf24; font: 11px 'JetBrains Mono',monospace; } .result { display: grid; gap: 5px; border: 1px solid rgba(43,184,176,.5); padding: 10px; color: #cbd5e1; font-size: 12px; } code { overflow-wrap: anywhere; }
</style>
