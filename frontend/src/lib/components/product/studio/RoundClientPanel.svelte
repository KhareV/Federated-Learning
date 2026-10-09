<script lang="ts">
	// Per-client evidence of the SELECTED round (loss, update norm, FedAvg weight, acceptance) from this run's committed-round record; never current state relabelled as history.
	import DigestText from '$lib/components/product/federation/DigestText.svelte';
	import type { StudioStore } from '$lib/product/studio/store.svelte';
	let { studio }: { studio: StudioStore } = $props();
	const round = $derived(studio.selectedRound);
	const detail = $derived(studio.roundDetail[round]);
	$effect(() => { if (studio.run?.evaluation.available && round >= 1) void studio.loadRound(round); });
	const num = (v: unknown, d = 6) => (typeof v === 'number' ? (Number.isInteger(v) ? String(v) : v.toFixed(d)) : v === null || v === undefined ? 'NOT CAPTURED' : String(v));
	const rows = $derived(detail?.client_rounds ?? []);
	const sum = $derived(rows.reduce((a, r) => a + (typeof r.aggregation_weight === 'number' ? (r.aggregation_weight as number) : 0), 0));
</script>
<div class="rc" data-testid="round-client-panel">
	<h4>Client contributions in round {round}</h4>
	{#if round === 0}<p class="dim">Round 0 is the initial global state: no client has trained yet.</p>
	{:else if !studio.run?.evaluation.available}<p class="dim">No per-round training records were captured for this run.</p>
	{:else if !detail}<p class="dim" role="status">Loading round {round} evidence…</p>
	{:else if !detail.committed}<p class="dim" data-testid="round-uncommitted">Round {round} has not been committed yet: its client records do not exist. Nothing is shown in their place.</p>
	{:else}
		<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
		<div class="scroll" tabindex="0" role="region" aria-label={`Client contributions in round ${round}`}><table><thead><tr><th scope="col">client</th><th scope="col">examples</th><th scope="col">mean training loss</th><th scope="col">update L2 norm</th><th scope="col">FedAvg weight</th><th scope="col">acceptance</th><th scope="col">update digest</th><th scope="col">duration s</th></tr></thead>
			<tbody>{#each rows as r (r.client_id)}<tr class:sel={studio.selectedClientId === r.client_id} data-testid={`client-row-${r.client_id}`}>
				<th scope="row"><button type="button" onclick={() => studio.selectClient(String(r.client_id))} aria-pressed={studio.selectedClientId === r.client_id}>{String(r.client_id).replace('SIM_FL_', '')}</button></th>
				<td>{num(r.examples_processed)}</td><td>{num(r.mean_training_loss)}</td><td>{num(r.local_update_norm)}</td><td>{num(r.aggregation_weight, 8)}</td><td>{num(r.acceptance_status)}</td><td>{#if typeof r.update_sha256 === 'string'}<DigestText value={r.update_sha256} label="update digest" />{:else}NOT CAPTURED{/if}</td><td>{num(r.client_duration_seconds, 3)}</td></tr>{/each}</tbody></table></div>
		<p class="dim" data-testid="weights-sum">Aggregation weights sum to {sum.toFixed(12)} · {rows.filter((r) => r.acceptance_status === 'ACCEPTED').length}/{rows.length} updates accepted by the coordinator · round digest {#if detail.state && typeof detail.state.sha256 === 'string'}<DigestText value={detail.state.sha256 as string} label={`round ${round} state digest`} />{/if}</p>
	{/if}
</div>
<style>
	.rc { display: grid; gap: 8px; min-width: 0; } h4 { margin: 0; font: 500 14px 'Space Grotesk', sans-serif; color: #e5f1f0; } .dim { margin: 0; color: #94a3b8; font-size: 12px; line-height: 1.55; } .scroll { overflow: auto; max-height: 320px; } table { border-collapse: collapse; font-size: 11.5px; width: 100%; } th, td { border-bottom: 1px solid rgba(148,163,184,.15); padding: 5px 9px; text-align: left; white-space: nowrap; color: #cbd5e1; } thead th { position: sticky; top: 0; background: #0a0f1f; color: #71829a; font: 10px 'JetBrains Mono', monospace; letter-spacing: .06em; } tr.sel { background: rgba(43,184,176,.1); }
	th button { background: none; border: 1px solid rgba(148,163,184,.3); color: #e2e8f0; padding: 2px 8px; min-height: 24px; cursor: pointer; font: 11px 'JetBrains Mono', monospace; } button:focus-visible { outline: 2px solid #2bb8b0; }
</style>
