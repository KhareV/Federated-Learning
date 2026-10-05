<script lang="ts">
	import type { FederationRun } from '$lib/product/federation/types';
	let { runs }: { runs: FederationRun[] } = $props();
	const time = (us: number | null) => (us ? new Date(us / 1000).toISOString().replace('T', ' ').slice(0, 19) + 'Z' : '--');
</script>
{#if runs.length === 0}<p class="dim">No federation runs yet.</p>{:else}
<ul class="runs" data-testid="run-list">
	{#each runs as r}
		<li><a href={`/app/federation/live?run=${encodeURIComponent(r.run_id)}`}><code>{r.run_id}</code></a>
			<span class="b">{r.run_type}{r.run_type === 'REPLAY' ? ' (not a training run)' : ''}</span><span class="b">{r.algorithm}</span><span class="b">{r.secagg_mode}</span><span class="b st">{r.status}</span>
			<span>round {r.current_round}/{r.planned_rounds}</span><span>candidates: {r.candidate_ids.length ? r.candidate_ids.join(', ') : 'NONE'}</span><span class="t">{time(r.started_at_us)} → {time(r.completed_at_us)}</span></li>
	{/each}
</ul>{/if}
<style>
	.runs { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; } li { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; border: 1px solid rgba(148,163,184,.12); padding: 6px 9px; font-size: 12px; } code { font: 11px 'JetBrains Mono', monospace; } a { color: #2bb8b0; }
	.b { padding: 1px 6px; border: 1px solid rgba(148,163,184,.3); font: 10px 'JetBrains Mono', monospace; } .st { color: #2bb8b0; } .t { color: #71829a; font: 10px 'JetBrains Mono', monospace; } .dim { color: #94a3b8; font-size: 13px; }
</style>
