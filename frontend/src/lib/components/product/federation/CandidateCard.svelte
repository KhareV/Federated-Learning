<script lang="ts">
	import TechnicalEvidence from './TechnicalEvidence.svelte';
	import DigestText from './DigestText.svelte';
	import { GOVERNANCE_CHECK_IDS, type CandidateModel } from '$lib/product/federation/types';
	let { candidate, checksPassed = null }: { candidate: CandidateModel; checksPassed?: string[] | null } = $props();
	const accepted = $derived(candidate.governance_status === 'ACCEPTED_TO_SANDBOX' && candidate.sandbox_status === 'IN_SANDBOX');
	const rejected = $derived(candidate.governance_status === 'REJECTED');
</script>
<article class="card" data-testid="candidate-card" aria-label={candidate.candidate_id}>
	<h3>{candidate.candidate_id}</h3>
	<ul class="badges">
		<li class="b-fed"><span aria-hidden="true">✓</span> FEDERATED TRAINING COMPLETE</li>
		{#if accepted}<li class="b-sbx"><span aria-hidden="true">◆</span> SANDBOX</li>{:else if rejected}<li class="b-bad"><span aria-hidden="true">✕</span> REJECTED</li>{/if}
		<li class="b-nd"><span aria-hidden="true">■</span> NOT DEPLOYED</li>
	</ul>
	{#if accepted}
		<p class="ok" data-testid="accepted-copy"><b>ACCEPTED TO ENGINEERING SANDBOX REGISTRY</b><br />STRUCTURAL CHECKS PASSED · NOT A SCIENTIFIC RELEASE · NOT DEPLOYED · NO CANDIDATE INFERENCE RUNTIME ENABLED.</p>
	{:else if rejected}
		<p class="bad" data-testid="rejected-copy"><b>REJECTED BY ENGINEERING GOVERNANCE</b><br />NOT IN SANDBOX · NOT DEPLOYED.</p>
	{:else}<p class="pending">Governance state: {candidate.governance_status}</p>{/if}
	<dl class="sum">
		<div><dt>Algorithm</dt><dd>{candidate.algorithm}</dd></div><div><dt>Final round</dt><dd>{candidate.round}</dd></div><div><dt>Clients</dt><dd>{candidate.client_count} synthetic</dd></div><div><dt>Started from</dt><dd>{candidate.parent_model_id}</dd></div>
	</dl>
	<TechnicalEvidence label="TECHNICAL EVIDENCE" testid="candidate-evidence">
		<dl>
			<div><dt>Federation run</dt><dd>{candidate.federation_run_id}</dd></div>
			<div><dt>State digest</dt><dd><DigestText value={candidate.state_digest} label="candidate state digest" /></dd></div>
			<div><dt>Validation</dt><dd>{candidate.validation_status}</dd></div><div><dt>Governance</dt><dd>{candidate.governance_status}</dd></div><div><dt>Sandbox</dt><dd>{candidate.sandbox_status}</dd></div>
			<div><dt>production_deployed</dt><dd data-testid="production-deployed">{candidate.production_deployed ? 'TRUE' : 'FALSE'}</dd></div>
			<div class="wide"><dt>Claim boundary</dt><dd>{candidate.claim_boundary}</dd></div>
		</dl>
		<details><summary>Five frozen structural checks (engineering, not clinical or performance validation)</summary>
			<ul>{#each GOVERNANCE_CHECK_IDS as id}<li>{id}{#if checksPassed}<span class="r"> — {checksPassed.includes(id) ? 'PASSED' : 'not reported as passed'}</span>{/if}</li>{/each}</ul>
			{#if !checksPassed}<p class="note">Per-check results are shown only when reported by a live validation event.</p>{/if}
		</details>
	</TechnicalEvidence>
</article>
<style>
	.card { border: 1px solid rgba(43,184,176,.4); padding: 14px 16px; min-width: 0; } h3 { margin: 0 0 8px; font: 500 15px 'JetBrains Mono', monospace; overflow-wrap: anywhere; } p { margin: 0 0 10px; font-size: 12px; line-height: 1.6; }
	.ok { color: #2bb8b0; } .bad { color: #f87171; } .pending, .note { color: #94a3b8; } dl { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 6px; margin: 0; } dl div { border: 1px solid rgba(148,163,184,.12); padding: 5px 8px; min-width: 0; } .wide { grid-column: 1 / -1; }
	dt { color: #71829a; font: 9px 'JetBrains Mono', monospace; letter-spacing: .1em; } dd { margin: 2px 0 0; font: 12px 'JetBrains Mono', monospace; overflow-wrap: anywhere; } details { margin-top: 10px; font-size: 12px; color: #94a3b8; } li { font: 11px 'JetBrains Mono', monospace; }
.badges { list-style: none; margin: 0 0 10px; padding: 0; display: flex; flex-wrap: wrap; gap: 6px; } .badges li { font: 600 10.5px 'JetBrains Mono', monospace; letter-spacing: .08em; padding: 3px 8px; border: 1px solid; } .b-fed { color: #c4b5fd; border-color: rgba(167,139,250,.6); } .b-sbx, .b-nd { color: #fbbf24; border-color: rgba(251,191,36,.6); } .b-bad { color: #f87171; border-color: rgba(248,113,113,.6); } .sum { margin-bottom: 8px; }
</style>
