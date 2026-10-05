<script lang="ts">
	import { onMount } from 'svelte';
	import Panel from '$lib/components/dashboard/Panel.svelte';
	import FactTable from '$lib/components/product/research/FactTable.svelte';
	import { getProductStore } from '$lib/product/state.svelte';
	import { factMap, type FlResearchEvidence } from '$lib/product/research/types';
	const product = getProductStore();
	let evidence = $state<FlResearchEvidence | null>(null);
	let error = $state<string | null>(null);
	const facts = $derived(factMap(evidence?.facts ?? []));
	const val = (id: string) => String(facts.get(id)?.value ?? 'Unavailable');
	const unsupported = $derived(evidence && Array.isArray(facts.get('secagg_unsupported_claims')?.value)
		? facts.get('secagg_unsupported_claims')?.value as string[] : []);
	onMount(() => { void product.api.researchFl().then((value) => { evidence = value; })
		.catch((cause) => { error = cause instanceof Error ? cause.message : 'Evidence unavailable'; }); });
</script>
<svelte:head><title>Research FL evidence | NHM</title></svelte:head>
<div class="page"><p class="eyebrow">NHM / FROZEN RESEARCH EVIDENCE</p><h1>FL research evidence</h1>
	<p>Read-only scientific research summaries, separate from the current product federation engineering demo. The federation clients are logical clients on one laptop, not hospitals or institutions.</p>
	{#if error}<p role="alert" class="error">{error}</p>{/if}
	{#if evidence}
		<Panel eyebrow="V2-FL-001 / IID FEDAVG" title="Frozen validation result"><p>Initial AUPRC: {val('iid_initial_auprc')}; best validation AUPRC: {val('iid_best_auprc')} at round {val('iid_best_round')}. V2-minus-V1 paired AUPRC result: {val('iid_v2_minus_v1_auprc')} [{val('iid_v2_minus_v1_auprc_ci_lower')}, {val('iid_v2_minus_v1_auprc_ci_upper')}]. These are frozen validation-selection facts, not a new evaluation.</p></Panel>
		<Panel eyebrow="V2-FL-002 / NON-IID" title="Synthetic research partitions"><p>IID, LABEL, QUANTITY, FEATURE and COMBINED conditions use synthetic research partitions, not institutions. Values are descriptive; not all differences are statistically significant.</p>
			<div class="grid">{#each ['iid','label','quantity','feature','combined'] as condition}<div><strong>{condition.toUpperCase()}</strong><span>Best validation AUPRC: {val(`${condition}_best_auprc`)}</span></div>{/each}</div></Panel>
		<Panel eyebrow="V2-FL-003 / FEDPROX" title="Mixed transfer, no general promotion"><p>FEDPROX_MU_V2 = {val('fedprox_mu')} was the selected frozen configuration. Transfer was mixed; FedProx was NOT promoted as a generally superior method.</p></Panel>
		<Panel eyebrow="V2-FL-EVAL-001 / ONE-SHOT" title="Held-out FL-lineage evidence"><p>INTERNAL_TEST: {val('internal_claim_label')} ({val('internal_groups')} eligible contributing groups). Frozen V2 FedAvg IID AUPRC: {val('internal_iid_auprc')} [{val('internal_iid_auprc_ci_lower')}, {val('internal_iid_auprc_ci_upper')}], nominal 95% patient-cluster interval. It was held out from V2 FL development, but not globally unseen by the project.</p>
			<p>INCART: {val('incart_claim_label')}. Frozen V2 FedAvg IID AUPRC: {val('incart_iid_auprc')} [{val('incart_iid_auprc_ci_lower')}, {val('incart_iid_auprc_ci_upper')}], nominal 95% patient-cluster interval. This is post-freeze/project-exposed external-domain second-look evidence.</p>
			<p>Frozen evaluation rule: {val('heldout_threshold_rule')}</p><p>This page does not reconstruct a threshold or compare the raw-sigmoid FL F1 to CAL_V2-thresholded results.</p></Panel>
		<Panel eyebrow="V2-FL-004 / SECAGG+" title="Protected aggregation interface only"><p>{val('secagg_supported_claim')}</p>
			<p>Plain clear updates: {val('plain_clear_updates')}; protected clear updates: {val('protected_clear_updates')}; masked vectors visible: {val('masked_vectors_visible')}. The authoritative product aggregation remains PLAIN; SecAgg is a round-1 shadow.</p>
			<p>Overhead accounting: {val('secagg_overhead_boundary')}. Application payload bytes are not exact network bytes ({val('secagg_network_bytes_exact')}). No end-to-end deployment latency was measured.</p>
			<p>Unsupported claims include: {unsupported.join(', ')}. This is not differential privacy, anonymity, hospital privacy, TLS assurance, or production-security certification.</p></Panel>
		<Panel eyebrow="ENGINEERING DEMO SEPARATION" title="V2-FL-005 is not scientific efficacy"><p>The current product federation demo derives from V2-FL-005 engineering lineage. It is not part of the five scientific evidence phases above. No synthetic demo accuracy is reported here. <a href="/app/federation">See Federation →</a></p></Panel>
		<Panel eyebrow="SOURCE FACTS" title="Exact frozen values and provenance"><FactTable facts={evidence.facts} provenance={evidence.source_provenance} /></Panel>
	{/if}
</div>
<style>
	.page{display:grid;gap:14px;min-width:0;max-width:100%}.eyebrow{color:#2bb8b0;font:11px 'JetBrains Mono',monospace;letter-spacing:.12em}h1{font:500 clamp(28px,4vw,42px) 'Space Grotesk',sans-serif;margin:0}p{color:#a7b8c9;font-size:13px;line-height:1.6;overflow-wrap:anywhere}.error{color:#fecdd3}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,170px),1fr));gap:8px}.grid div{padding:10px;border:1px solid var(--nhm-border);display:grid;gap:6px}.grid strong{color:#2bb8b0}.grid span{font-size:12px;color:#a7b8c9}a{color:#2bb8b0}a:focus-visible{outline:2px solid #fbbf24}
</style>
