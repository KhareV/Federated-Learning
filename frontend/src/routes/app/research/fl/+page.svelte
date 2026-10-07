<script lang="ts">
	import { onMount } from 'svelte';
	import Panel from '$lib/components/dashboard/Panel.svelte';
	import ComparisonPanel from '$lib/components/product/story/ComparisonPanel.svelte';
	import FlowDiagram from '$lib/components/product/story/FlowDiagram.svelte';
	import TechnicalEvidence from '$lib/components/product/federation/TechnicalEvidence.svelte';
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
	const CONDITIONS: [string, string][] = [['iid', 'Balanced reference partition'], ['label', 'Label-distribution skew'], ['quantity', 'Client-size imbalance'], ['feature', 'Feature-distribution shift'], ['combined', 'Multiple non-IID effects']];
	const bar = (id: string) => { const n = Number(facts.get(id)?.value); return Number.isFinite(n) && n >= 0 && n <= 1 ? n * 100 : null; };
	onMount(() => { void product.api.researchFl().then((value) => { evidence = value; })
		.catch((cause) => { error = cause instanceof Error ? cause.message : 'Evidence unavailable'; }); });
</script>
<svelte:head><title>Research FL evidence | NHM</title></svelte:head>
<div class="page"><p class="eyebrow">NHM / FROZEN RESEARCH EVIDENCE</p><h1>FL research evidence</h1>
	<p class="lead">Read-only scientific research summaries, separate from the current product federation engineering demo. The federation clients are logical clients on one laptop, not hospitals or institutions.</p>
	<div class="two" data-testid="science-vs-demo">
		<section class="sci"><p class="k">SCIENTIFIC FL EXPERIMENTS</p><h2>Frozen research evidence</h2><p>Five experiment phases (V2-FL-001 to V2-FL-004 and V2-FL-EVAL-001) with frozen results. This is where federated-learning performance is discussed.</p></section>
		<section class="demo"><p class="k">CURRENT PRODUCT ENGINEERING DEMO</p><h2>8 synthetic clients · 3 rounds · 24 updates</h2><p>Real local training that ends in a sandbox candidate. No demo-performance claim.</p></section>
	</div>
	{#if error}<p role="alert" class="error">{error}</p>{:else if !evidence}<p class="dim" role="status">Loading frozen evidence…</p>{/if}
	{#if evidence}
		<Panel eyebrow="EXPERIMENT MAP" title="How the scientific evidence was built" note="FROZEN RESEARCH EVIDENCE">
			<div data-testid="experiment-map"><FlowDiagram tone="federated" label="Scientific FL experiment sequence" steps={[
				{ label: 'IID FEDAVG', sub: 'V2-FL-001 · reference run on balanced partitions' }, { label: 'NON-IID STRESS', sub: 'V2-FL-002 · same method on skewed partitions' }, { label: 'FEDPROX COMPARISON', sub: 'V2-FL-003 · adds a proximal local objective' },
				{ label: 'HELD-OUT EVALUATION', sub: 'V2-FL-EVAL-001 · one-shot held-out check' }, { label: 'SECAGG COMPATIBILITY', sub: 'V2-FL-004 · protected-aggregation interface' }]} /></div>
		</Panel>
		<Panel eyebrow="V2-FL-001 / IID FEDAVG" title="Frozen validation result" note="FROZEN RESEARCH EVIDENCE"><p>Initial AUPRC: {val('iid_initial_auprc')}; best validation AUPRC: {val('iid_best_auprc')} at round {val('iid_best_round')}. V2-minus-V1 paired AUPRC result: {val('iid_v2_minus_v1_auprc')} [{val('iid_v2_minus_v1_auprc_ci_lower')}, {val('iid_v2_minus_v1_auprc_ci_upper')}]. These are frozen validation-selection facts, not a new evaluation.</p></Panel>
		<Panel eyebrow="V2-FL-002 / NON-IID" title="Synthetic research partitions" note="FROZEN RESEARCH EVIDENCE"><p>IID, LABEL, QUANTITY, FEATURE and COMBINED conditions use synthetic research partitions, not institutions. Values are descriptive; not all differences are statistically significant. Bars show best validation AUPRC on a 0 to 1 scale.</p>
			<div class="grid" data-testid="condition-cards">{#each CONDITIONS as [condition, meaning]}{@const w = bar(`${condition}_best_auprc`)}<div><strong>{condition.toUpperCase()}</strong><em>{meaning}</em><span>Best validation AUPRC: {val(`${condition}_best_auprc`)}</span>{#if w !== null}<i class="bar" aria-hidden="true"><i style={`width:${w}%`}></i></i>{/if}</div>{/each}</div></Panel>
		<Panel eyebrow="V2-FL-003 / FEDPROX" title="FedAvg vs FedProx" note="NO WINNER">
			<ComparisonPanel testid="fedavg-vs-fedprox" leftTitle="FEDAVG" leftSub="Aggregation" leftTone="released" rightTitle="FEDPROX" rightSub="Proximal local objective" rightTone="federated" rows={[
				{ label: 'What it does', left: 'Sample-count-weighted aggregation of local updates', right: 'Adds the frozen proximal local objective' },
				{ label: 'Product status', left: 'Canonical live-demo algorithm', right: 'Supported' },
				{ label: 'Research result', left: 'Reference method', right: 'Mixed / selective transfer' },
				{ label: 'Conclusion', left: 'Used as the reference', right: 'NOT promoted as a generally superior method' }]} />
			<p>FEDPROX_MU_V2 = {val('fedprox_mu')} was the selected frozen configuration. Transfer was mixed; FedProx was NOT promoted as a generally superior method.</p></Panel>
		<Panel eyebrow="V2-FL-EVAL-001 / ONE-SHOT" title="Held-out FL-lineage evidence" note="FROZEN RESEARCH EVIDENCE"><p>INTERNAL_TEST: {val('internal_claim_label')} ({val('internal_groups')} eligible contributing groups). Frozen V2 FedAvg IID AUPRC: {val('internal_iid_auprc')} [{val('internal_iid_auprc_ci_lower')}, {val('internal_iid_auprc_ci_upper')}], nominal 95% patient-cluster interval. It was held out from V2 FL development, but not globally unseen by the project.</p>
			<p>INCART: {val('incart_claim_label')}. Frozen V2 FedAvg IID AUPRC: {val('incart_iid_auprc')} [{val('incart_iid_auprc_ci_lower')}, {val('incart_iid_auprc_ci_upper')}], nominal 95% patient-cluster interval. This is post-freeze/project-exposed external-domain second-look evidence.</p>
			<TechnicalEvidence label="TECHNICAL EVIDENCE (evaluation rule)" testid="heldout-evidence"><p>Frozen evaluation rule: {val('heldout_threshold_rule')}</p><p>This page does not reconstruct a threshold or compare the raw-sigmoid FL F1 to CAL_V2-thresholded results.</p></TechnicalEvidence></Panel>
		<Panel eyebrow="V2-FL-004 / SECAGG+" title="Protected aggregation interface only" note="FROZEN RESEARCH EVIDENCE"><p>{val('secagg_supported_claim')}</p>
			<p>The authoritative product aggregation remains PLAIN; SecAgg is a round-1 shadow. This is not differential privacy, anonymity, hospital privacy, TLS assurance, or production-security certification.</p>
			<TechnicalEvidence label="TECHNICAL EVIDENCE" testid="secagg-evidence"><p>Plain clear updates: {val('plain_clear_updates')}; protected clear updates: {val('protected_clear_updates')}; masked vectors visible: {val('masked_vectors_visible')}.</p>
				<p>Overhead accounting: {val('secagg_overhead_boundary')}. Application payload bytes are not exact network bytes ({val('secagg_network_bytes_exact')}). No end-to-end deployment latency was measured.</p>
				<p>Unsupported claims include: {unsupported.join(', ')}.</p></TechnicalEvidence></Panel>
		<Panel eyebrow="ENGINEERING DEMO SEPARATION" title="V2-FL-005 is not scientific efficacy" note="CURRENT ENGINEERING DEMO">
			<p>The current product federation demo derives from V2-FL-005 engineering lineage. It is not part of the five scientific evidence phases above. No synthetic demo accuracy is reported here.</p>
			<div class="bridge" data-testid="research-to-demo"><ul><li>8 logical synthetic clients</li><li>3 rounds</li><li>real local training</li><li>engineering candidate</li><li>no performance claim</li></ul><a class="cta" href="/app/federation">OPEN FEDERATION STUDIO →</a></div></Panel>
		<TechnicalEvidence label="FULL FROZEN EVIDENCE" testid="full-frozen-evidence"><FactTable facts={evidence.facts} provenance={evidence.source_provenance} /></TechnicalEvidence>
	{/if}
</div>
<style>
	.page{display:grid;gap:14px;min-width:0;max-width:100%}.eyebrow{color:#2bb8b0;font:11px 'JetBrains Mono',monospace;letter-spacing:.12em}h1{font:500 clamp(28px,4vw,42px) 'Space Grotesk',sans-serif;margin:0}p{color:#a7b8c9;font-size:13px;line-height:1.6;overflow-wrap:anywhere}.error{color:#fecdd3}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,170px),1fr));gap:8px}.grid div{padding:10px;border:1px solid var(--nhm-border);display:grid;gap:6px}.grid strong{color:#2bb8b0}.grid span{font-size:12px;color:#a7b8c9}a{color:#2bb8b0}a:focus-visible{outline:2px solid #fbbf24}
.lead{color:#94a3b8;font-size:14px;max-width:760px;margin:0}.dim{color:#94a3b8}.two{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr));gap:12px}.two section{padding:14px 16px;border:1px solid;min-width:0}.two h2{margin:4px 0 6px;font:500 18px 'Space Grotesk',sans-serif}.two p{margin:0}.k{font:10px 'JetBrains Mono',monospace;letter-spacing:.14em;color:#71829a}.sci{border-color:rgba(167,139,250,.55)}.demo{border-color:rgba(251,191,36,.55)}
.grid em{font-style:normal;color:#94a3b8;font-size:11.5px}.bar{display:block;height:6px;background:rgba(148,163,184,.18)}.bar i{display:block;height:100%;background:#a78bfa}.bridge{display:flex;flex-wrap:wrap;gap:14px;align-items:center;justify-content:space-between}.bridge ul{margin:0;padding-left:18px;color:#a7b8c9;font-size:13px}.cta{display:inline-flex;align-items:center;min-height:32px;padding:6px 14px;border:1px solid #fbbf24;color:#fbbf24;font:600 12px 'JetBrains Mono',monospace;letter-spacing:.08em;text-decoration:none}
</style>
