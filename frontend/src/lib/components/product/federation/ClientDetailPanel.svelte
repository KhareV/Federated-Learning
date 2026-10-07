<script lang="ts">
	// Focused detail for ONE client: friendly facts first, exact evidence behind a disclosure. Only reported values; no loss/accuracy/duration is shown or invented.
	import DigestText from './DigestText.svelte';
	import TechnicalEvidence from './TechnicalEvidence.svelte';
	import { CLIENT_LABEL } from '$lib/product/federation/labels';
	import { LOCAL_STEPS, localStepIndex } from '$lib/product/federation/presentation';
	import type { ClientView } from '$lib/product/federation/live-model';
	import type { FLClientIdentity } from '$lib/product/federation/types';
	let { clientId, client, ownerBound = false, plannedRounds = 3, replay = false, identity = undefined }: { clientId: string; client: ClientView | undefined; ownerBound?: boolean; plannedRounds?: number; replay?: boolean; identity?: FLClientIdentity | undefined } = $props();
	const step = $derived(localStepIndex(client));
	const completed = $derived(client ? Object.values(client.milestones).filter((m) => m === 1).length : 0);
	const produced = $derived(client ? Object.keys(client.updateDigests).length : 0);
	const examples = $derived(client?.localExamples ?? identity?.local_example_count ?? null);
</script>
<section class="dp" data-testid="client-detail" aria-label={`Details for ${clientId}`}>
	<h4>{clientId} <span class="role">{ownerBound ? 'OWNER-BOUND CLIENT' : 'SYNTHETIC LOGICAL CLIENT'}</span></h4>
	<dl class="facts">
		<div><dt>Local examples</dt><dd>{examples ?? '--'}</dd></div><div><dt>Current state</dt><dd>{client ? CLIENT_LABEL[client.state] : 'WAITING'}</dd></div>
		<div><dt>Rounds completed</dt><dd>{completed} / {plannedRounds}</dd></div><div><dt>Updates produced</dt><dd>{produced} / {plannedRounds}</dd></div>
	</dl>
	<div class="flow" data-testid="local-training-flow" aria-label="What happens inside this client">
		<p class="q">What is happening on this client?</p>
		<ol>{#each LOCAL_STEPS as s, i (s.id)}<li class={i < step ? 'done' : i === step ? 'act' : ''} data-step={s.id}><span aria-hidden="true">{i < step ? '✓' : i === step ? '●' : '○'}</span> {s.label}{#if s.id === 'BUFFER' && examples !== null}<small> ({examples} synthetic examples)</small>{/if}</li>{/each}</ol>
		<p class="sent">RAW TRAINING EXAMPLES SENT: <b>0</b></p>
		{#if replay}<p class="rp">REPLAY — the steps above are historical events; nothing is executing.</p>{/if}
	</div>
	<TechnicalEvidence label="TECHNICAL EVIDENCE (IDs, digests, milestones)">
		<dl class="ev"><div><dt>Client ID</dt><dd>{clientId}</dd></div><div><dt>Edge node</dt><dd>{identity?.edge_node_id ?? '--'}</dd></div><div><dt>Reported state</dt><dd>{client?.state ?? 'IDLE'}</dd></div>
			{#each Object.entries(client?.updateDigests ?? {}) as [r, d]}<div><dt>Round {r} update digest</dt><dd><DigestText value={d} label={`round ${r} update digest`} /></dd></div>{/each}
			{#each Object.entries(client?.milestones ?? {}) as [r, m]}<div><dt>Round {r} milestone</dt><dd>{m === 1 ? 'completed' : 'started'}</dd></div>{/each}</dl>
	</TechnicalEvidence>
</section>
<style>
	.dp { border: 1px solid rgba(167,139,250,.35); padding: 12px 14px; display: grid; gap: 10px; min-width: 0; } h4 { margin: 0; font: 500 15px 'JetBrains Mono', monospace; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; } .role { font: 9.5px 'JetBrains Mono', monospace; letter-spacing: .12em; color: #c4b5fd; border: 1px solid rgba(167,139,250,.5); padding: 2px 7px; }
	dl { margin: 0; display: grid; gap: 4px; } .facts { grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); } .facts div { border: 1px solid rgba(148,163,184,.14); padding: 6px 8px; } dt { color: #71829a; font: 9px 'JetBrains Mono', monospace; letter-spacing: .1em; } dd { margin: 2px 0 0; font: 13px 'JetBrains Mono', monospace; overflow-wrap: anywhere; }
	.ev div { display: flex; justify-content: space-between; gap: 8px; font-size: 12px; } .ev dd { font-size: 11px; text-align: right; margin: 0; }
	.flow { display: grid; gap: 6px; } .q { margin: 0; font: 10px 'JetBrains Mono', monospace; letter-spacing: .1em; color: #94a3b8; } ol { list-style: none; margin: 0; padding: 0; display: grid; gap: 3px; font-size: 12px; color: #71829a; } li.done { color: #2bb8b0; } li.act { color: #e9e3ff; background: rgba(167,139,250,.12); } li { padding: 3px 6px; } small { color: #94a3b8; }
	.sent { margin: 0; font: 11px 'JetBrains Mono', monospace; color: #cbd5e1; } .rp { margin: 0; border: 1px solid rgba(148,163,184,.5); color: #cbd5e1; padding: 5px 9px; font: 11px 'JetBrains Mono', monospace; }
</style>
