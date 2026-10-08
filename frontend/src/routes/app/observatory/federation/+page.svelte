<script lang="ts">
	import { onMount } from 'svelte';
	import { getProductStore } from '$lib/product/state.svelte';
	import type { FrozenCohort, RunContributions } from '$lib/product/observatory/federation';
	import type { FederationRun } from '$lib/product/federation/types';

	const store = getProductStore();
	let cohort = $state<FrozenCohort | null>(null);
	let runs = $state<FederationRun[]>([]);
	let selectedRun = $state('');
	let details = $state<RunContributions | null>(null);
	let roundId = $state(1);
	let clientId = $state('SIM_FL_SITE_00');
	let loading = $state(true);
	let error = $state<string | null>(null);
	const round = $derived(details?.rounds.find((r) => r.round_id === roundId));
	const client = $derived(cohort?.clients.find((c) => c.client_id === clientId));
	const contribution = $derived(round?.clients.find((c) => c.client_id === clientId));
	function acceptanceLabel(state: string): string {
		if (state === 'ACCEPTED') return 'Accepted by coordinator';
		if (state === 'DIRECT_OBSERVED_ACCEPTED') return 'Accepted · directly observed';
		if (state === 'GOVERNANCE_ATTESTED_ACCEPTED') return 'Accepted · governance-attested';
		if (state === 'NOT_ACCEPTED') return 'Not accepted';
		if (state === 'TRAINED_ACCEPTANCE_NOT_RECORDED') return 'Trained · acceptance unavailable';
		return 'No client training record';
	}
	function stageFlag(value: boolean | null): string { return value === null ? 'not recorded' : value ? 'yes' : 'no'; }

	async function loadRun(id: string) {
		selectedRun = id; details = null;
		if (!id) return;
		loading = true; error = null;
		try {
			details = await store.api.observatoryRunContributions(id);
			roundId = details.rounds[0]?.round_id ?? 1;
		} catch (cause) { error = cause instanceof Error ? cause.message : String(cause); }
		finally { loading = false; }
	}
	onMount(() => { void (async () => {
		try {
			[cohort, runs] = await Promise.all([store.api.observatoryCohort(), store.api.federationRuns()]);
			await loadRun(runs.find((r) => r.run_type === 'LIVE_RUN' && r.status === 'COMPLETED')?.run_id ?? '');
		} catch (cause) { error = cause instanceof Error ? cause.message : String(cause); }
		finally { loading = false; }
	})(); });
</script>

<svelte:head><title>Federation Observatory | NHM</title></svelte:head>
<div class="eyebrow">NHM / RESEARCH OBSERVATORY / FEDERATION</div>
<h1>Who contributed to federation?</h1>
<p class="lead">Eight synthetic logical clients, all on one demonstration machine. Their scheduled engineering-event labels are <strong>not</strong> the AAMI-SVF scientific ECG target. Sample-count weight is neither accuracy nor clinical importance.</p>
<nav aria-label="Observatory views"><a href="/app/observatory">← Signal journey</a> <a href="/app/federation">Federation Studio →</a></nav>
{#if error}<p class="error" role="alert">{error}</p>{/if}
{#if loading}<p role="status">Loading frozen cohort and owned-run evidence…</p>{/if}
{#if cohort}
	<section aria-labelledby="roster-title">
		<div class="section-head"><div><span>FROZEN SYNTHETIC COHORT</span><h2 id="roster-title">Every participant has a distinct data profile</h2></div><p>{cohort.clients.length} clients · {cohort.clients.reduce((n,c)=>n+c.windows_emitted,0)} emitted windows · {cohort.clients.reduce((n,c)=>n+c.trainable,0)} trainable</p></div>
		<p class="notice">Training target: <b>{cohort.label_contract}</b> — scheduled synthetic engineering events, not annotated AAMI-SVF beats.</p>
		<div class="roster">{#each cohort.clients as c}
			<button class:selected={clientId===c.client_id} type="button" onclick={() => clientId=c.client_id} aria-pressed={clientId===c.client_id}>
				<small>{c.client_id} · {c.participant_id}</small><strong>{c.scenario}</strong><span><b>{c.trainable}</b> trainable · {c.degraded} degraded · {c.unusable} unusable</span>
			</button>
		{/each}</div>
		{#if client}<article class="detail"><div><span>SELECTED PARTICIPANT</span><h2>{client.client_id}</h2><p>{client.participant_id} · {client.session_id} · {client.scenario}</p><p>{client.windows_emitted} windows emitted; {client.valid} valid, {client.degraded} degraded, {client.unusable} unusable. {client.trainable} eligible for local training: {client.synthetic_positive} scheduled-event positive, {client.synthetic_negative} negative.</p><p>Source: synthetic physiology at {client.source_rate_hz} Hz. Local dataset digest <code>{client.dataset_sha256}</code>.</p><a href={`/app/observatory/federation/${encodeURIComponent(client.client_id)}`}>Inspect this client's actual synthetic source windows →</a></div><div><span>ACTUAL FROZEN FAULT SCHEDULE</span>{#if client.faults.length}<ul>{#each client.faults as fault}<li>{fault[0]} · {fault[1]}–{fault[2]} s source time</li>{/each}</ul>{:else}<p>No scheduled fault.</p>{/if}</div></article>{/if}
	</section>
	<section aria-labelledby="contribution-title">
		<div class="section-head"><div><span>OWNER-SCOPED RUN EVIDENCE</span><h2 id="contribution-title">Accepted contribution, round by round</h2></div></div>
		<label class="select">RUN <select value={selectedRun} onchange={(e)=>void loadRun(e.currentTarget.value)}><option value="">Frozen cohort only — choose an owned live run</option>{#each runs as run}<option value={run.run_id}>{run.run_id} · {run.run_type} · {run.status}</option>{/each}</select></label>
		{#if details}<p class="notice">{details.run_type === 'REPLAY' ? 'REPLAY — NO LOCAL TRAINING EXECUTING. Contribution data is not relabelled as a new run.' : `${details.run_status} · ${details.algorithm} · ${details.evidence_status} · ${details.reported_total_accepted_updates ?? 'unknown'} coordinator-reported accepted updates across rounds`}</p>
			{#if details.rounds.length}<div class="rounds" aria-label="Select round">{#each details.rounds as r}<button class:selected={roundId===r.round_id} onclick={()=>roundId=r.round_id}>Round {r.round_id} · {r.reported_accepted_update_count ?? 'unknown'} aggregate count{r.accepted_update_count === null ? ' · client map unavailable' : ''}</button>{/each}</div>{/if}
			{#if round}<p class="math">Accepted examples: <b>{round.accepted_example_total ?? 'NOT RECORDED'}</b>. Weight = client accepted examples ÷ accepted total. Basis: <b>{round.acceptance_basis === 'DIRECT_OBSERVED_COORDINATOR_MAP' ? 'post-run Observatory snapshot of actual coordinator-accepted map' : round.acceptance_basis === 'GOVERNANCE_ATTESTED_SERVER_JOURNAL' ? 'server journal + persisted coordinator-map governance attestation' : round.acceptance_basis === 'DIRECT_COORDINATOR_MAP' ? 'direct coordinator-accepted digest map' : 'acceptance not recorded'}</b>. A SUBMITTED event alone is never treated as acceptance.</p>
				<div class="table-wrap"><table><thead><tr><th>Client</th><th>Local trainable</th><th>Examples seen</th><th>Training / update stages</th><th>Acceptance evidence</th><th>Accepted examples</th><th>Aggregation weight</th></tr></thead><tbody>{#each round.clients as c}<tr class:selected={c.client_id===clientId}><th scope="row"><button class="client-link" onclick={()=>clientId=c.client_id}>{c.client_id}</button></th><td>{c.local_trainable_windows}</td><td>{c.examples_seen ?? 'NOT RECORDED'}</td><td>Trained: {stageFlag(c.training_completed)}<br />Produced: {stageFlag(c.update_produced)}<br />Submitted: {stageFlag(c.update_submitted)}<br />Aggregated: {stageFlag(c.aggregated)}</td><td title={c.evidence_state}>{acceptanceLabel(c.evidence_state)}</td><td>{c.accepted_examples ?? '—'}</td><td>{c.weight === null ? '—' : `${(c.weight*100).toFixed(2)}%`}{#if c.weight !== null}<div class="bar"><i style={`width:${c.weight*100}%`}></i></div>{/if}</td></tr>{/each}</tbody></table></div>
				<div class="digests"><span>Base state: <code>{round.base_state_digest ?? 'NOT RECORDED'}</code></span><span>Committed state: <code>{round.committed_state_digest ?? 'NOT RECORDED'}</code></span></div>
				{#if contribution}<details><summary>Selected client-round technical evidence</summary><p>Examples seen: {contribution.examples_seen ?? 'NOT RECORDED'} · shuffle seed: {contribution.shuffle_seed ?? 'NOT RECORDED'} · update digest: <code>{contribution.update_digest ?? 'NOT RECORDED'}</code>.</p><p>Stage ledger: trained {stageFlag(contribution.training_completed)}, produced {stageFlag(contribution.update_produced)}, submitted {stageFlag(contribution.update_submitted)}, coordinator accepted {stageFlag(contribution.accepted)}, aggregated {stageFlag(contribution.aggregated)}.</p>{#if contribution.training_readout}{@const d = contribution.training_readout}<p>Engineering readout, not a score, LOCAL TRAINING DIAGNOSTIC (never model accuracy): {d.batch_count} mini-batches · {d.examples_seen} examples · mean local loss {d.mean_local_loss.toFixed(4)} · update norm {d.update_norm.toFixed(4)} · update payload {d.update_bytes} bytes. Recorded once at the end of the local epoch by an Observatory observer; per-batch values are not recorded.</p>{:else}<p>NOT RECORDED FOR THIS RUN, so no local training diagnostic is shown. Nothing is reconstructed or invented.</p>{/if}</details>{/if}
				<article class="training"><span>ACTUAL LOCAL OPTIMIZATION PATH</span><h3>What happens inside a client?</h3><p>Client-local eligible ECG windows → deterministic shuffle → mini-batches → MODEL_V2_TCN_MEAN forward pass → BCE-with-logits loss → backward pass → AdamW local update → state delta → update envelope. This describes the unchanged local trainer, not a replayed batch-by-batch capture.</p><p>For this run, examples seen, shuffle seed, and update digest are recorded per client and round. Batch count, local mean loss, update norm, and serialized payload size are <b>NOT RECORDED FOR THIS RUN</b> in the durable summary. A changing digest is not a performance result.</p><a href={`/app/federation/live?run=${encodeURIComponent(details.run_id)}`}>Inspect the actual federation event journal →</a></article>
			{/if}
			{#if details.rounds.length}
				<details class="matrix"><summary>ALL-ROUND CONTRIBUTION MATRIX</summary><p>Each cell separates recorded local training from coordinator acceptance. A missing client map is unknown, not a rejection.</p><div class="table-wrap"><table><thead><tr><th>Client</th>{#each details.rounds as r}<th>Round {r.round_id}</th>{/each}</tr></thead><tbody>{#each cohort.clients as c}<tr><th scope="row">{c.client_id}</th>{#each details.rounds as r}{@const evidence = r.clients.find((item) => item.client_id === c.client_id)}<td>{#if evidence}{evidence.examples_seen === null ? 'Training not recorded' : `${evidence.examples_seen} seen`}<br /><span title={evidence.evidence_state}>{acceptanceLabel(evidence.evidence_state)}</span>{#if evidence.weight !== null}<br />{(evidence.weight * 100).toFixed(2)}% accepted weight{/if}{:else}No client record{/if}</td>{/each}</tr>{/each}</tbody></table></div></details>
			{/if}
		{:else}<p class="empty">No owned run selected. The roster above is frozen cohort evidence, not a claim that a live training run occurred.</p>{/if}
	</section>
	<details class="evidence"><summary>PROVENANCE & CLAIM BOUNDARY</summary><p>{cohort.source_relative_path} · SHA256 <code>{cohort.source_sha256}</code></p><p>{cohort.label_contract} · {cohort.claim_boundary}</p><p>The observatory reads frozen cohort summaries and owner-scoped run artifacts. It does not read raw local training tensors or execute training.</p></details>
{/if}
<style>
	.eyebrow,.section-head span,.detail span,.training span{color:#2bb8b0;font:10px 'JetBrains Mono',monospace;letter-spacing:.13em}h1{margin:9px 0;font:500 clamp(28px,4vw,42px) 'Space Grotesk',sans-serif}.lead{max-width:850px;color:#a7b8c9;line-height:1.6}.lead strong{color:#fbbf24}nav{display:flex;gap:20px;margin:14px 0 22px}a{color:#2bb8b0}section{margin:22px 0}.section-head{display:flex;justify-content:space-between;align-items:end;gap:16px}.section-head h2{font:500 21px 'Space Grotesk',sans-serif;margin:6px 0}.section-head p{font:12px 'JetBrains Mono',monospace;color:#94a3b8}.roster{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.roster button,.rounds button{background:#071421;color:#dce8e8;border:1px solid #334155;cursor:pointer;text-align:left}.roster button{display:grid;gap:9px;padding:14px;min-width:0}.roster button.selected,.rounds button.selected{border-color:#2bb8b0;background:#0b262b}.roster small{font:10px 'JetBrains Mono',monospace;color:#2bb8b0}.roster strong{font:500 16px 'Space Grotesk',sans-serif}.roster span{font-size:12px;color:#9aaec0}.detail{display:grid;grid-template-columns:2fr 1fr;gap:20px;background:#081523;border:1px solid #334155;padding:17px;margin-top:10px}.detail h2{margin:7px 0;font-size:22px}.detail p,.detail li{color:#a7b8c9;font-size:13px;line-height:1.55}.select{display:grid;gap:8px;font:10px 'JetBrains Mono',monospace;color:#94a3b8}.select select{min-height:38px;background:#071421;color:#e5f1f0;border:1px solid #475569;padding:7px}.notice,.math,.empty{color:#b9cad7;font-size:13px;line-height:1.6}.rounds{display:flex;gap:8px;flex-wrap:wrap}.rounds button{min-height:36px;padding:7px 10px}.table-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:12px;margin-top:10px}th,td{text-align:left;border-bottom:1px solid #334155;padding:11px 8px;vertical-align:top}thead th{color:#94a3b8;font:10px 'JetBrains Mono',monospace}tr.selected{background:#0b262b}.client-link{background:none;border:0;color:#2bb8b0;text-decoration:underline;cursor:pointer}.bar{height:5px;background:#1e293b;min-width:60px;margin-top:6px}.bar i{display:block;background:#2bb8b0;height:100%}.digests{display:grid;gap:5px;margin:15px 0;color:#94a3b8;font-size:12px}code{overflow-wrap:anywhere}details{border:1px solid #334155;padding:10px;color:#a7b8c9;font-size:12px}summary{cursor:pointer;color:#2bb8b0;font:11px 'JetBrains Mono',monospace}.training{border:1px solid #334155;background:#071421;padding:15px;margin:16px 0;color:#b9cad7}.training h3{font:500 18px 'Space Grotesk',sans-serif;margin:8px 0}.training p,.matrix p{font-size:13px;line-height:1.6}.matrix{margin:16px 0}.matrix td{min-width:150px}.evidence{margin:20px 0}.error{color:#f87171}button:focus-visible,a:focus-visible,select:focus-visible,summary:focus-visible{outline:2px solid #2bb8b0;outline-offset:2px}@media(max-width:1024px){.roster{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:650px){.roster{grid-template-columns:1fr}.detail{grid-template-columns:1fr}.section-head{display:block}.table-wrap{overflow-x:auto}table{min-width:650px}}
</style>
