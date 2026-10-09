<script lang="ts">
	// Evaluation of the selected round: every value is the stored, measured record of THIS run's checkpoint; pending / undefined / failed are shown as such (never zero-filled).
	import DigestText from '$lib/components/product/federation/DigestText.svelte';
	import { HEADLINE, METRIC_GROUPS, display } from '$lib/product/studio/metrics';
	import type { StudioStore } from '$lib/product/studio/store.svelte';
	let { studio }: { studio: StudioStore } = $props();
	const round = $derived(studio.metricRound);
	const record = $derived(studio.records.find((r) => r.round_id === round));
	const detail = $derived(studio.roundEval[round]);
	const status = $derived(studio.statusOf(round));
	const substituted = $derived(studio.selectedRound !== round);
	const selectedStatus = $derived(studio.statusOf(studio.selectedRound));
	$effect(() => { if (studio.run?.evaluation.available && status === 'COMPLETED') void studio.loadRound(round); });
	const participants = $derived(detail?.participant_metrics ? Object.entries(detail.participant_metrics) : []);
	const ptext = (v: unknown) => (typeof v === 'number' ? v.toFixed(4) : v === null || v === undefined ? 'UNDEFINED' : String(v));
</script>
<div class="mc" data-testid="metric-cards">
	{#if !studio.run}
		<p class="none" role="status" data-testid="evaluation-loading">Evaluation state not loaded yet. Measurements appear only after the run's evaluation records exist.</p>
	{:else if !studio.run.evaluation.available}
		<p class="none" role="status" data-testid="no-evaluation">NO LIVE EVALUATION WAS CAPTURED FOR THIS RUN ({studio.run.evaluation.reason ?? 'unavailable'}). Nothing is invented: only runs started after the evaluation observer existed carry per-round metrics.</p>
	{:else}
		{#if substituted}<p class="sub" role="status" data-testid="metric-substitution">ROUND {studio.selectedRound} EVALUATION {selectedStatus === 'NOT_SUBMITTED' ? 'NOT YET AVAILABLE' : selectedStatus} — showing the latest evaluated round R{round}. Its values belong to R{round} only.</p>{/if}
		<h3 data-testid="metric-round">ROUND R{round}{#if record?.candidate_id} · FINAL CANDIDATE STATE{/if} <span class={`st st-${status.toLowerCase()}`} data-testid="metric-status">{status === 'NOT_SUBMITTED' ? 'NOT YET AVAILABLE' : status}</span></h3>
		<div class="cards" role="list">
			{#each HEADLINE as m (m.key)}
				{@const d = display(record, m.key, m.format)}
				<article class={`card ${d.tone}`} role="listitem" data-testid={`metric-${m.key}`} title={d.full ? `${m.label}: ${d.full} — ${m.hint}` : m.hint}><span>{m.label}</span><b>{d.text}</b></article>
			{/each}
		</div>
		<dl class="meta">
			<div><dt>Evaluation cohort</dt><dd data-testid="metric-cohort">{record?.cohort_id ?? '--'} · {record?.windows ?? '--'} windows · 16 participants</dd></div>
			<div><dt>Committed state digest</dt><dd>{#if record}<DigestText value={record.global_state_digest} label={`round ${round} state digest`} />{:else}--{/if}</dd></div>
			<div><dt>Decision rule</dt><dd>raw sigmoid ≥ {record?.threshold ?? 0.5} · calibration {record?.calibration ?? 'NONE'} (never tuned)</dd></div>
			<div><dt>Protocol</dt><dd>{record?.evaluation_protocol_id ?? '--'}</dd></div>
		</dl>
		<p class="label" data-testid="cohort-use-label">{record?.cohort_use ?? studio.summary?.cohort_use ?? studio.capabilities?.evaluation.cohort_use ?? 'evaluation cohort label loading…'}</p>
		<p class="dim">{studio.summary?.claim_boundary ?? 'SYNTHETIC_ENGINEERING_EVENT_EVALUATION_ONLY_NOT_AAMI_SVF_OR_CLINICAL'} · no clinical or diagnostic claim · no round, threshold or candidate is selected from these values.</p>
		{#if record?.failure}<p class="fail" role="alert">EVALUATION FAILED — {record.failure.code}: {record.failure.message}</p>{/if}
		<details class="all"><summary>All measured metrics for R{round}</summary>
			{#each METRIC_GROUPS as g (g.id)}
				<h4>{g.title}</h4>
				<div class="grid">{#each g.items as m (m.key)}{@const d = display(record, m.key, m.format)}<div class={`cell ${d.tone}`} data-testid={`all-${m.key}`} title={d.full}><span>{m.label}</span><b>{d.text}</b></div>{/each}</div>
			{/each}
			<h4>Participant evaluation</h4>
			{#if detail?.participant_summary}
				<p class="dim" data-testid="participant-summary">Participant-macro F1: <b>{ptext(detail.participant_summary.participant_macro_F1)}</b> · contributing participants {detail.participant_summary.participants_defined} · undefined {detail.participant_summary.participants_undefined}</p>
				<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
				<div class="scroll" tabindex="0" role="region" aria-label="Participant-level metrics"><table><thead><tr><th scope="col">participant</th>{#each ['AUPRC', 'AUROC', 'F1', 'recall', 'specificity'] as k}<th scope="col">{k}</th>{/each}</tr></thead>
					<tbody>{#each participants as [pid, m] (pid)}<tr><th scope="row">{pid}</th>{#each ['AUPRC', 'AUROC', 'F1', 'recall', 'specificity'] as k}<td class:undef={m[k] === null}>{ptext(m[k])}</td>{/each}</tr>{/each}</tbody></table></div>
			{:else}<p class="dim">{status === 'COMPLETED' ? 'Loading participant detail…' : 'Participant metrics appear once this round is evaluated.'}</p>{/if}
			<p class="dim">Displayed at 6 decimals; exports keep full precision. Hover a value for the exact number.</p>
		</details>
	{/if}
</div>
<style>
	.mc { display: grid; gap: 10px; min-width: 0; } h3 { margin: 0; font: 500 16px 'Space Grotesk', sans-serif; color: #e5f1f0; display: flex; gap: 10px; align-items: center; flex-wrap: wrap; } .st { font: 11px 'JetBrains Mono', monospace; letter-spacing: .08em; border: 1px solid rgba(148,163,184,.4); padding: 2px 8px; color: #94a3b8; } .st-completed { color: #86efac; border-color: rgba(134,239,172,.5); } .st-evaluating { color: #fbbf24; border-color: rgba(251,191,36,.5); } .st-failed { color: #f87171; border-color: rgba(248,113,113,.5); }
	.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 150px), 1fr)); gap: 8px; } .card { border: 1px solid rgba(148,163,184,.2); background: rgba(10,15,31,.7); padding: 10px 12px; display: grid; gap: 4px; min-width: 0; } .card span, .cell span { font: 10px 'JetBrains Mono', monospace; letter-spacing: .1em; color: #71829a; text-transform: uppercase; } .card b { font: 500 clamp(15px, 1.6vw, 20px) 'Space Grotesk', sans-serif; color: #e5f1f0; overflow-wrap: anywhere; }
	.card.pending b, .cell.pending b { color: #fbbf24; font: 600 12px 'JetBrains Mono', monospace; letter-spacing: .08em; } .card.undefined b, .cell.undefined b { color: #94a3b8; font: 12px 'JetBrains Mono', monospace; } .card.failed b, .cell.failed b { color: #f87171; font: 600 12px 'JetBrains Mono', monospace; } .card.value { border-color: rgba(43,184,176,.35); }
	.meta { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 230px), 1fr)); gap: 6px; margin: 0; } .meta div { border: 1px solid rgba(148,163,184,.16); padding: 6px 9px; min-width: 0; } dt { font: 9px 'JetBrains Mono', monospace; letter-spacing: .1em; color: #71829a; text-transform: uppercase; } dd { margin: 2px 0 0; font-size: 12px; color: #cbd5e1; overflow-wrap: anywhere; }
	.label { margin: 0; display: inline-block; width: fit-content; max-width: 100%; border: 1px solid rgba(251,191,36,.6); background: rgba(251,191,36,.07); padding: 5px 10px; font: 600 11px 'JetBrains Mono', monospace; letter-spacing: .05em; color: #fde68a; } .dim { margin: 0; color: #94a3b8; font-size: 12px; line-height: 1.55; } .sub { margin: 0; border: 1px solid rgba(251,191,36,.5); padding: 7px 10px; color: #fde68a; font: 12px 'JetBrains Mono', monospace; } .none { margin: 0; border: 1px solid rgba(148,163,184,.4); padding: 9px 12px; color: #cbd5e1; font-size: 13px; line-height: 1.6; } .fail { margin: 0; color: #f87171; font: 12px 'JetBrains Mono', monospace; }
	summary { cursor: pointer; font-size: 13px; color: #e2e8f0; } h4 { margin: 12px 0 6px; font: 11px 'JetBrains Mono', monospace; letter-spacing: .1em; color: #a78bfa; } .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 190px), 1fr)); gap: 6px; } .cell { border: 1px solid rgba(148,163,184,.14); padding: 6px 9px; display: grid; gap: 2px; } .cell b { font: 12.5px 'JetBrains Mono', monospace; color: #e2e8f0; overflow-wrap: anywhere; }
	.scroll { overflow: auto; max-height: 300px; } table { border-collapse: collapse; font-size: 11px; width: 100%; } th, td { border-bottom: 1px solid rgba(148,163,184,.15); padding: 4px 9px; text-align: left; white-space: nowrap; color: #cbd5e1; } thead th { position: sticky; top: 0; background: #0a0f1f; color: #71829a; font: 10px 'JetBrains Mono', monospace; } td.undef { color: #71829a; }
</style>
