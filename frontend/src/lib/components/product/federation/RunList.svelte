<script lang="ts">
	import type { FederationRun } from '$lib/product/federation/types';
	let { runs }: { runs: FederationRun[] } = $props();
	const time = (us: number | null) => (us ? new Date(us / 1000).toISOString().replace('T', ' ').slice(0, 19) + 'Z' : '--');
</script>
{#if runs.length === 0}
	<div class="empty"><strong>No federation runs yet</strong><p>A live engineering run creates a sandbox candidate. Replay opens recorded run evidence; it does not train.</p><a href="/app/federation/live">CONFIGURE LIVE RUN →</a></div>
{:else}
	<ul class="runs" data-testid="run-list">
		{#each runs as r}
			<li class:replay={r.run_type === 'REPLAY'}>
				<div class="head"><span class="type">{r.run_type === 'REPLAY' ? 'REPLAY — NO TRAINING' : 'LIVE RUN'}</span><span class="status">{r.status}</span></div>
				<div class="primary"><strong>ROUND {r.current_round} / {r.planned_rounds}</strong><span>{r.algorithm}</span><span>{r.candidate_ids.length ? 'CANDIDATE CREATED' : 'NO CANDIDATE'}</span></div>
				<a class="open" href={`/app/federation/live?run=${encodeURIComponent(r.run_id)}`}>OPEN {r.run_type === 'REPLAY' ? 'REPLAY' : 'RUN'} →</a>
				<details><summary>TECHNICAL RUN EVIDENCE</summary><dl>
					<div><dt>Run ID</dt><dd><code>{r.run_id}</code></dd></div><div><dt>Run type</dt><dd>{r.run_type}</dd></div>
					<div><dt>SecAgg mode</dt><dd>{r.secagg_mode}</dd></div><div><dt>Candidate IDs</dt><dd>{r.candidate_ids.length ? r.candidate_ids.join(', ') : 'NONE'}</dd></div>
					<div><dt>Started</dt><dd>{time(r.started_at_us)}</dd></div><div><dt>Completed</dt><dd>{time(r.completed_at_us)}</dd></div>
				</dl></details>
			</li>
		{/each}
	</ul>
{/if}
<style>
	.runs{list-style:none;margin:0;padding:0;display:grid;gap:10px}.runs li,.empty{min-width:0;padding:14px;border:1px solid rgba(148,163,184,.25);background:rgba(15,23,42,.25)}.runs li.replay{border-color:rgba(167,139,250,.45)}.head,.primary{display:flex;flex-wrap:wrap;gap:8px;align-items:center}.head{justify-content:space-between}.type,.status,.primary strong{font:600 11px 'JetBrains Mono',monospace;letter-spacing:.06em}.type{color:#2bb8b0}.replay .type{color:#c4b5fd}.status{color:#fbbf24}.primary{margin:12px 0;color:#cbd5e1;font-size:12px}.primary>*{padding:5px 8px;border:1px solid rgba(148,163,184,.24)}.open,.empty a{display:inline-flex;align-items:center;min-height:32px;padding:6px 10px;border:1px solid #2bb8b0;color:#2bb8b0;text-decoration:none;font:600 11px 'JetBrains Mono',monospace}details{margin-top:12px;border-top:1px solid rgba(148,163,184,.2);padding-top:10px}summary{cursor:pointer;color:#94a3b8;font:10px 'JetBrains Mono',monospace;letter-spacing:.08em}dl{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,180px),1fr));gap:10px;margin:12px 0 0}dt{font:10px 'JetBrains Mono',monospace;color:#71829a}dd{margin:3px 0 0;color:#cbd5e1;font-size:11px;overflow-wrap:anywhere}code{font:inherit}.empty strong{font:500 17px 'Space Grotesk',sans-serif}.empty p{color:#94a3b8;font-size:12px;line-height:1.5}a:focus-visible,summary:focus-visible{outline:2px solid #fbbf24;outline-offset:3px}
	li a { display: inline-flex; align-items: center; min-height: 24px; }
</style>
