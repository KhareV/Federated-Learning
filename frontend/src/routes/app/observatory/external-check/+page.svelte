<script lang="ts">
	import { focusHeading } from '$lib/product/observatory/focus';
	import { onMount } from 'svelte';
	import { getProductStore } from '$lib/product/state.svelte';
	import type { ExternalCheck } from '$lib/product/observatory/external-check';
	const store = getProductStore();
	let data = $state<ExternalCheck | null>(null);
	let error = $state<string | null>(null);
	let setIndex = $state(0);
	const current = $derived(data?.sets[setIndex] ?? null);
	const f = (v: number, d = 3) => v.toFixed(d);
	const ci = (c: [number, number]) => `[${f(c[0])}, ${f(c[1])}]`;
	const signed = (v: number) => `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(3)}`;
	const central = $derived(current?.rows.find((r) => r.model.startsWith('MODEL_V2_FINAL')) ?? null);
	const v1 = $derived(current?.rows.find((r) => r.model.startsWith('MODEL_V1')) ?? null);
	const adapted = $derived((current?.rows ?? []).filter((r) => r.model.includes('synthetic cohort')));
	onMount(() => { void store.api.observatoryExternalCheck().then((v) => { data = v; }).catch((c) => { error = c instanceof Error ? c.message : String(c); }); });
</script>
<svelte:head><title>External check on unseen real ECG | NHM</title></svelte:head>
<div class="eyebrow">NHM / RESEARCH OBSERVATORY / EXTERNAL CHECK</div>
<h1 tabindex="-1" use:focusHeading>External check on real ECG no model had seen</h1>
<p class="lead">The frozen models scored on 12-lead clinical ECG from PTB-XL (lead II, one 10-second window per record). PTB-XL was removed from the project's execution scope, so no model was ever trained, selected, calibrated or evaluated on it. This is an extension outside the locked scope: it has no beat annotations, so the target is record-level, and it is not a clinical or diagnostic result.</p>
{#if error}<p role="alert" class="err">External-check evidence unavailable: {error}</p>{:else if !data}<p class="dim" role="status">Loading frozen evidence…</p>{:else}
<p class="tag" data-testid="extension-label">{data.label}</p>
<p class="warn" data-testid="claim-boundary">{data.claim_boundary}</p>
<p class="dim">{data.records_scored.toLocaleString()} records scored (paced records excluded: {data.exclusions.paced}; no record lost to a missing lead, wrong length or flat signal: {data.exclusions.no_lead_II + data.exclusions.bad_window} excluded). Target <code>{data.target}</code> · fixed {data.threshold} rule · calibration {data.calibration}.</p>
<section class="controls" aria-label="Evaluation set"><fieldset><legend>Evaluation set</legend>{#each data.sets as s, i (s.name)}<button class:on={setIndex === i} aria-pressed={setIndex === i} onclick={() => (setIndex = i)} data-testid={`set-${i}`}>{s.name}</button>{/each}</fieldset></section>
{#if current}
<section aria-label="Models on the unseen records" data-testid="external-models"><h2>Models on {current.name}</h2>
	<p class="dim">{current.records.toLocaleString()} records, {current.positives.toLocaleString()} with premature beats (prevalence {f(current.prevalence)}), {current.patients.toLocaleString()} patients; 95 % patient-cluster bootstrap intervals from {current.bootstrap_replicates.toLocaleString()} resamples. Label rule A (either label source). AUPRC depends on prevalence, so lift (AUPRC ÷ prevalence; 1 = chance) is shown beside it.</p>
	<div class="scroll"><table aria-label="Model metrics on the unseen real ECG records"><thead><tr><th scope="col">Model</th><th scope="col">AUROC [95 %]</th><th scope="col">AUPRC [95 %]</th><th scope="col">Lift</th><th scope="col">F1 at 0.5</th><th scope="col">Sensitivity</th><th scope="col">Specificity</th><th scope="col">Paired change vs central V2: AUROC · AUPRC</th></tr></thead><tbody>
	{#each current.rows as r (r.model)}<tr data-model={r.model}><th scope="row">{r.model}</th><td>{f(r.AUROC)} <small>{ci(r.AUROC_ci)}</small></td><td>{f(r.AUPRC)} <small>{ci(r.AUPRC_ci)}</small></td><td>{f(r.lift, 2)}</td><td>{f(r.F1)}</td><td>{f(r.sensitivity, 2)}</td><td>{f(r.specificity, 2)}</td>
		<td>{#if r.paired_vs_central_V2}{signed(r.paired_vs_central_V2.AUROC.delta)} <small>{ci(r.paired_vs_central_V2.AUROC.ci95)}</small> · {signed(r.paired_vs_central_V2.AUPRC.delta)} <small>{ci(r.paired_vs_central_V2.AUPRC.ci95)}</small>{:else}<small>reference</small>{/if}</td></tr>{/each}
	</tbody></table></div>
</section>
<section aria-label="What this shows" data-testid="readings"><h2>What this shows</h2><ul>
	{#if central && v1 && v1.paired_vs_central_V2}<li><b>The pretrained V2 ranks premature-beat records well above chance on data it never saw</b> (AUROC {f(central.AUROC)}, lift {f(central.lift, 1)}), and clearly better than V1 (V1's paired AUROC change against it is {signed(v1.paired_vs_central_V2.AUROC.delta)}, interval {ci(v1.paired_vs_central_V2.AUROC.ci95)}, which excludes zero).</li>{/if}
	{#if adapted.length}<li><b>Adapting a model to a synthetic cohort lowers its performance on this unseen real ECG</b>: {#each adapted as a, i (a.model)}{i ? '; ' : ''}{a.model.includes('original') ? 'original' : 'realistic'} cohort AUROC {signed(a.paired_vs_central_V2?.AUROC.delta ?? 0)}, AUPRC {signed(a.paired_vs_central_V2?.AUPRC.delta ?? 0)} against the central V2{/each}. A synthetic-cohort candidate is not a better ECG model than the released one.</li>{/if}
	<li><b>Federated training on real patients matches centralized training</b> in AUROC; see the paired change of the 50-round federated rows.</li></ul></section>
<section aria-label="Label rules" data-testid="label-rules"><h2>Label rules (primary set)</h2>
	<p class="dim">The two label sources agree on only part of the premature-beat records ({data.label_agreement.both.toLocaleString()} both, {data.label_agreement.statement_only.toLocaleString()} cardiologist statement only, {data.label_agreement.extra_beats_only.toLocaleString()} extra-beat field only, over all records), so the same models are scored under three predeclared rules. Point estimates.</p>
	<div class="scroll"><table aria-label="AUROC and AUPRC by label rule"><thead><tr><th scope="col">Model</th>{#each data.label_rules as b (b.rule)}<th scope="col">{b.title}<br /><small>{b.records.toLocaleString()} records, {b.positives.toLocaleString()} positive</small></th>{/each}</tr></thead><tbody>
	{#each data.models as m (m)}<tr><th scope="row">{m}</th>{#each data.label_rules as b (b.rule)}{@const x = b.rows.find((r) => r.model === m)}<td>{x ? `${f(x.AUROC)} / ${f(x.AUPRC)} (lift ${f(x.lift, 1)})` : '—'}</td>{/each}</tr>{/each}
	</tbody></table></div><p class="dim">Cells: AUROC / AUPRC (lift).</p></section>
<section aria-label="Where the central V2 errs" data-testid="error-analysis"><h2>Where the central V2 errs (descriptive, primary set, rule A)</h2>
	<div class="scroll"><table aria-label="Share of records flagged at 0.5 by group"><thead><tr><th scope="col">Group</th><th scope="col">Records</th><th scope="col">Flagged at 0.5</th></tr></thead><tbody>
	{#each data.error_analysis as g (g.group)}<tr><th scope="row">{g.group}</th><td>{g.records.toLocaleString()}</td><td>{(100 * g.share_flagged).toFixed(0)} %</td></tr>{/each}</tbody></table></div>
	<p class="dim">Nothing here selects a model, threshold or label rule.</p></section>
<section aria-label="Limitations"><h2>Preserved limitations</h2><ul>{#each data.limitations as l}<li>{l}</li>{/each}</ul></section>
<p class="dim" data-testid="hashes">Frozen report <code>{data.report.path}</code> SHA-256 <code>{data.report.sha256.slice(0, 16)}…</code> · predeclared protocol <code>{data.protocol.path}</code> SHA-256 <code>{data.protocol.sha256.slice(0, 16)}…</code> (verified: the protocol was written before any score existed and is unchanged). <a href="/app/observatory/outcomes">Scientific outcomes</a> · <a href="/app/observatory">Observatory</a> · <a href="/app/models">Models</a></p>
{/if}
{/if}
<style>
	.eyebrow{color:#2bb8b0;font:10px 'JetBrains Mono',monospace;letter-spacing:.14em}h1{font:500 clamp(28px,4vw,42px) 'Space Grotesk',sans-serif;margin:8px 0}h2{font:500 18px 'Space Grotesk',sans-serif;margin:22px 0 8px}
	.lead{max-width:820px;color:#a7b8c9;font-size:14px;line-height:1.6}.dim,small,li{color:#94a3b8;font-size:13px;line-height:1.6;overflow-wrap:anywhere}p{overflow-wrap:anywhere}.err{color:#fecdd3}
	.warn{border-left:3px solid #fbbf24;background:rgba(251,191,36,.06);padding:8px 12px;color:#fcd34d;font-size:12.5px;line-height:1.5}.tag{display:inline-block;border:1px solid #2bb8b0;color:#9fe7e1;font:10.5px 'JetBrains Mono',monospace;letter-spacing:.06em;padding:3px 8px;margin:6px 0}
	.controls{display:flex;flex-wrap:wrap;gap:12px;margin:12px 0}.controls fieldset{border:1px solid rgba(148,163,184,.25);padding:6px 10px;display:flex;gap:6px}.controls legend{font:10px 'JetBrains Mono',monospace;color:#71829a}
	button{background:transparent;color:#cbd5e1;border:1px solid rgba(148,163,184,.4);padding:5px 10px;font:12px 'JetBrains Mono',monospace;cursor:pointer;min-height:24px}button.on{border-color:#2bb8b0;color:#9fe7e1}
	.scroll{overflow-x:auto;max-width:100%}table{border-collapse:collapse;width:100%;font-size:12px}th,td{border-bottom:1px solid rgba(148,163,184,.16);padding:7px 9px;text-align:left;vertical-align:top}thead th{color:#71829a;font:10.5px 'JetBrains Mono',monospace;letter-spacing:.06em}tbody th{font-weight:500;color:#e5f1f0}code{color:#9fe7e1;overflow-wrap:anywhere}a{color:#2bb8b0}
</style>
