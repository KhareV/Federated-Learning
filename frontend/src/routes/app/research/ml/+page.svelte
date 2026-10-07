<script lang="ts">
	import { onMount } from 'svelte';
	import Panel from '$lib/components/dashboard/Panel.svelte';
	import QuestionCard from '$lib/components/product/story/QuestionCard.svelte';
	import FlowDiagram from '$lib/components/product/story/FlowDiagram.svelte';
	import TechnicalEvidence from '$lib/components/product/federation/TechnicalEvidence.svelte';
	import FactTable from '$lib/components/product/research/FactTable.svelte';
	import { getProductStore } from '$lib/product/state.svelte';
	import { factMap, type MlResearchEvidence } from '$lib/product/research/types';
	const product = getProductStore();
	let evidence = $state<MlResearchEvidence | null>(null);
	let error = $state<string | null>(null);
	const facts = $derived(factMap(evidence?.facts ?? []));
	const val = (id: string) => String(facts.get(id)?.value ?? 'Unavailable');
	const limitations = $derived(evidence && Array.isArray(facts.get('known_limitations')?.value)
		? facts.get('known_limitations')?.value as string[] : []);
	const truthy = (id: string) => ['true', 'yes'].includes(String(facts.get(id)?.value).toLowerCase());
	const known = (id: string) => facts.get(id)?.value !== undefined;
	onMount(() => { void product.api.researchMl().then((value) => { evidence = value; })
		.catch((cause) => { error = cause instanceof Error ? cause.message : 'Evidence unavailable'; }); });
</script>
<svelte:head><title>Research ML evidence | NHM</title></svelte:head>
<div class="page"><p class="eyebrow">NHM / FROZEN RESEARCH EVIDENCE</p><h1>ML research evidence</h1>
	<p class="lead">Read-only, non-diagnostic research summaries. This page does not run a model or change the monitoring runtime.</p>
	<p class="tag" data-testid="frozen-tag"><b>MODEL_V2_FINAL</b> · FROZEN RESEARCH EVIDENCE</p>
	{#if error}<p role="alert" class="error">{error}</p>{:else if !evidence}<p class="dim" role="status">Loading frozen evidence…</p>{/if}
	{#if evidence}
		<div class="decision-grid">
			<QuestionCard n="1" testid="q-promotion" question="Was MODEL_V2 promoted by the original model-promotion criterion?" answer={known('promotion_eligible') ? (truthy('promotion_eligible') ? 'YES · PROMOTED' : 'NO · NOT PROMOTED') : 'Unavailable'} tone="no" reason="The predeclared paired release-seed confidence interval crossed zero. This historical negative finding remains true.">
				<TechnicalEvidence label="TECHNICAL EVIDENCE" testid="q1-evidence"><p>V2-007 / HISTORICAL MODEL PROMOTION GATE: <b>{val('promotion_decision')}</b>. Promotion eligible: {val('promotion_eligible')}. Predeclared paired release-seed AUPRC-delta confidence interval [{val('release_ci_lower')}, {val('release_ci_upper')}] crossed zero.</p></TechnicalEvidence>
			</QuestionCard>
			<QuestionCard n="2" testid="q-default" question="Is MODEL_V2_FINAL nevertheless the accepted research software default?" answer={known('system_release_accepted') ? (truthy('system_release_accepted') ? 'YES · ACCEPTED' : 'NO') : 'Unavailable'} tone="yes" reason="A later, different decision accepted the software system as the research default. It does not rewrite the earlier model-promotion result.">
				<TechnicalEvidence label="TECHNICAL EVIDENCE" testid="q2-evidence"><p>V2-REL-001 / LATER RESEARCH SOFTWARE RELEASE: <b>SYSTEM_V2_RESEARCH_DEFAULT_ACCEPTED</b>. Decision: {val('system_release_accepted')}. Current research software default: {val('operational_default')}. Different questions; the later software decision does not rewrite the earlier model-promotion result.</p></TechnicalEvidence>
			</QuestionCard>
		</div>
		<Panel eyebrow="CALIBRATION" title="How a model score becomes a monitoring policy" note="CAL_V2">
			<div data-testid="calibration-flow"><FlowDiagram tone="released" label="Calibration flow" steps={[{ label: 'MODEL SCORE', sub: 'raw model output' }, { label: 'TEMPERATURE CALIBRATION', sub: 'CAL_V2' }, { label: 'THRESHOLD', sub: 'frozen operating point' }, { label: 'MONITORING POLICY', sub: 'research state, not a diagnosis' }]} /></div>
			<p class="warnline">MIT-BIH SOURCE-DOMAIN CALIBRATION ONLY. No cross-domain, wearable, personal, or clinical calibration is established.</p>
			<TechnicalEvidence label="TECHNICAL EVIDENCE (frozen values)" testid="calibration-evidence"><p>Domain: {val('calibration_domain')}. Temperature: {val('temperature')}. Threshold: {val('threshold')}. Calibrated ECE: {val('calibrated_ece')}.</p></TechnicalEvidence>
		</Panel>
		<div class="cards" data-testid="evidence-cards">
			<Panel eyebrow="01 / MODEL LINEAGE" title="Centrally trained released default">
				<p>{val('model_id')} is centrally trained, not a federated checkpoint.</p>
				<p>MODEL_V1 remains the historical reference and explicit rollback lineage, not the current operational default.</p>
				<TechnicalEvidence label="TECHNICAL EVIDENCE" testid="lineage-evidence"><p>Checkpoint SHA256: <code>{val('checkpoint_sha256')}</code></p></TechnicalEvidence>
			</Panel>
			<Panel eyebrow="02 / POST-FREEZE" title="Second-look / runtime evidence">
				<p>V2-010 runtime acceptance: {val('runtime_acceptance')}. INTERNAL_TEST did not participate in the hard runtime decision ({val('internal_test_hard_gate')}).</p>
				<p>INTERNAL_TEST and INCART metrics are POST-FREEZE SECOND-LOOK / RUNTIME EVIDENCE, not untouched validation. INCART is external-domain, project-exposed second-look evidence.</p>
				<TechnicalEvidence label="TECHNICAL EVIDENCE" testid="postfreeze-evidence"><p>The small INTERNAL_TEST contributing-group limitation is listed in the full frozen evidence and the limitations card.</p></TechnicalEvidence>
			</Panel>
			<Panel eyebrow="03 / LIMITATIONS" title="Negative findings remain visible"><ul>{#each limitations as limit}<li>{limit}</li>{/each}</ul>
				<p>No physical wearable validation exists. QUALITY_V1 retains the known stuck-nonzero limitation. SecAgg supports only a narrow protected-aggregation-interface claim.</p>
			</Panel>
		</div>
		<TechnicalEvidence label="FULL FROZEN EVIDENCE" testid="full-frozen-evidence"><FactTable facts={evidence.facts} provenance={evidence.source_provenance} /></TechnicalEvidence>
	{/if}
</div>
<style>
	.page{display:grid;grid-template-columns:minmax(0,1fr);gap:14px;min-width:0;max-width:100%}.eyebrow{color:#2bb8b0;font:11px 'JetBrains Mono',monospace;letter-spacing:.12em}h1{font:500 clamp(28px,4vw,42px) 'Space Grotesk',sans-serif;margin:0}.decision-grid{display:grid;grid-template-columns:minmax(0,1fr);gap:12px}p,li{color:#a7b8c9;font-size:13px;line-height:1.6;overflow-wrap:anywhere}.error{color:#fecdd3}code{overflow-wrap:anywhere}
.lead{color:#94a3b8;font-size:14px;max-width:760px;margin:0}.tag{margin:0;font:11px 'JetBrains Mono',monospace;letter-spacing:.1em;color:#9fe8e3;border:1px solid rgba(43,184,176,.5);padding:6px 10px;justify-self:start}.dim{color:#94a3b8}.warnline{border-left:3px solid #fbbf24;padding:6px 10px;color:#fde68a;background:rgba(251,191,36,.05)}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr));gap:12px;align-items:start}.decision-grid{grid-template-columns:repeat(auto-fit,minmax(min(100%,340px),1fr))}ul{margin:0;padding-left:18px}
</style>
