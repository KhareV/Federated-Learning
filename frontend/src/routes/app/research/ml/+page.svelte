<script lang="ts">
	import { onMount } from 'svelte';
	import Panel from '$lib/components/dashboard/Panel.svelte';
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
	onMount(() => { void product.api.researchMl().then((value) => { evidence = value; })
		.catch((cause) => { error = cause instanceof Error ? cause.message : 'Evidence unavailable'; }); });
</script>
<svelte:head><title>Research ML evidence | NHM</title></svelte:head>
<div class="page"><p class="eyebrow">NHM / FROZEN RESEARCH EVIDENCE</p><h1>ML research evidence</h1>
	<p>Read-only, non-diagnostic research summaries. This page does not run a model or change the monitoring runtime.</p>
	{#if error}<p role="alert" class="error">{error}</p>{/if}
	{#if evidence}
		<div class="decision-grid">
			<Panel eyebrow="V2-007 / HISTORICAL MODEL PROMOTION GATE" title={val('promotion_decision')} note="PREDECLARED PAIRED RELEASE-SEED CI">
				<p>Promotion eligible: {val('promotion_eligible')}. The release-seed paired AUPRC-delta confidence interval [{val('release_ci_lower')}, {val('release_ci_upper')}] crossed zero. This historical negative finding remains true.</p>
			</Panel>
			<Panel eyebrow="V2-REL-001 / LATER RESEARCH SOFTWARE RELEASE" title="SYSTEM_V2_RESEARCH_DEFAULT_ACCEPTED" note={`Decision: ${val('system_release_accepted')}`}>
				<p>Current research software default: {val('operational_default')}. Different questions; the later software decision does not rewrite the earlier model-promotion result.</p>
			</Panel>
		</div>
		<Panel eyebrow="01 / MODEL LINEAGE" title="Centrally trained released default">
			<p>{val('model_id')} is centrally trained, not a federated checkpoint. Checkpoint SHA256: <code>{val('checkpoint_sha256')}</code>.</p>
			<p>MODEL_V1 remains the historical reference and explicit rollback lineage, not the current operational default.</p>
		</Panel>
		<Panel eyebrow="02 / CALIBRATION" title="CAL_V2 source-domain calibration">
			<p>MIT-BIH SOURCE-DOMAIN CALIBRATION ONLY. Domain: {val('calibration_domain')}. Temperature: {val('temperature')}. Threshold: {val('threshold')}. Calibrated ECE: {val('calibrated_ece')}.</p>
			<p>No cross-domain, wearable, personal, or clinical calibration is established.</p>
		</Panel>
		<Panel eyebrow="03 / POST-FREEZE" title="Second-look / runtime evidence">
			<p>V2-010 runtime acceptance: {val('runtime_acceptance')}. INTERNAL_TEST did not participate in the hard runtime decision ({val('internal_test_hard_gate')}). INTERNAL_TEST and INCART metrics below are POST-FREEZE SECOND-LOOK / RUNTIME EVIDENCE, not untouched validation.</p>
			<p>The small INTERNAL_TEST contributing-group limitation is listed below. INCART is external-domain, project-exposed second-look evidence.</p>
		</Panel>
		<Panel eyebrow="04 / LIMITATIONS" title="Negative findings remain visible"><ul>{#each limitations as limit}<li>{limit}</li>{/each}</ul>
			<p>No physical wearable validation exists. QUALITY_V1 retains the known stuck-nonzero limitation. SecAgg supports only a narrow protected-aggregation-interface claim.</p>
		</Panel>
		<Panel eyebrow="05 / SOURCE FACTS" title="Exact frozen values and provenance"><FactTable facts={evidence.facts} provenance={evidence.source_provenance} /></Panel>
	{/if}
</div>
<style>
	.page{display:grid;grid-template-columns:minmax(0,1fr);gap:14px;min-width:0;max-width:100%}.eyebrow{color:#2bb8b0;font:11px 'JetBrains Mono',monospace;letter-spacing:.12em}h1{font:500 clamp(28px,4vw,42px) 'Space Grotesk',sans-serif;margin:0}.decision-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr));gap:12px}p,li{color:#a7b8c9;font-size:13px;line-height:1.6;overflow-wrap:anywhere}.error{color:#fecdd3}code{overflow-wrap:anywhere}
</style>
