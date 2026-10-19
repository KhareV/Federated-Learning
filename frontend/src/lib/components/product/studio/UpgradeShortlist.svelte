<script lang="ts">
	// The upgrade shortlist: which stored engineering candidates could be put forward for REVIEW as a future custom model, judged by an explicit evidence checklist.
	// Read-only. A shortlist is not an upgrade: nothing here promotes, registers or deploys a model, and the released monitoring model never changes.
	import { onMount } from 'svelte';
	import { getProductStore } from '$lib/product/state.svelte';
	import { candidateChipText } from '$lib/product/studio/cohort-text';
	import type { ShortlistEntry, ShortlistTier, UpgradeShortlist } from '$lib/product/studio/types';
	const product = getProductStore();
	let list = $state<UpgradeShortlist | null>(null);
	let error = $state<string | null>(null);
	onMount(() => { void product.api.studioUpgradeShortlist().then((v) => { list = v; }).catch((cause) => { error = cause instanceof Error ? cause.message : String(cause); }); });
	const TIER: Record<ShortlistTier, { text: string; tone: string }> = {
		SHORTLISTED_FOR_REVIEW: { text: 'SHORTLISTED FOR REVIEW', tone: 'ok' },
		COMPARABLE_NOT_BETTER: { text: 'MATCHES THE RELEASED MODEL · NOT BETTER', tone: 'mid' },
		NOT_SHORTLISTED: { text: 'NOT SHORTLISTED', tone: 'no' }
	};
	const MARK = { PASS: '✓', FAIL: '✕', NOT_EVIDENCED: '○' } as const;
	const counts = $derived.by(() => {
		const e = list?.entries ?? [];
		return { shortlisted: e.filter((x) => x.tier === 'SHORTLISTED_FOR_REVIEW').length, comparable: e.filter((x) => x.tier === 'COMPARABLE_NOT_BETTER').length, total: e.length };
	});
	const failingTitles = (e: ShortlistEntry) => e.failing.map((id) => list?.criteria.find((c) => c.id === id)?.title ?? id).join(' · ');
</script>
<div class="sl" data-testid="upgrade-shortlist">
	{#if error}<p class="warn" role="alert">{error}</p>
	{:else if list === null}<p class="dim" role="status">Loading the shortlist…</p>
	{:else}
		<p class="lede" data-testid="shortlist-summary"><b>{counts.shortlisted}</b> of {counts.total} stored candidates are shortlisted for review{counts.comparable ? `, ${counts.comparable} match the released model on real ECG without beating it` : ''}. The released model is <code>{list.released_model.model_id}</code>{list.released_model.real_ecg_auroc !== null ? ` (real-ECG AUROC ${list.released_model.real_ecg_auroc.toFixed(3)}${list.released_model.ci95 ? `, 95% interval ${list.released_model.ci95[0].toFixed(3)}–${list.released_model.ci95[1].toFixed(3)}` : ''})` : ''} and stays unchanged.</p>
		<div class="wall" role="note" data-testid="shortlist-boundary"><span>A SHORTLIST IS NOT AN UPGRADE</span><small>{list.note}</small></div>
		<details class="crit"><summary>The {list.criteria.length} criteria ({list.policy_id})</summary>
			<ol data-testid="shortlist-criteria">{#each list.criteria as c (c.id)}<li><b>{c.id} · {c.title}</b><span>{c.rule}</span></li>{/each}</ol>
		</details>
		{#if list.entries.length === 0}<p class="dim" data-testid="shortlist-empty">No stored candidates yet, so there is nothing to rank.</p>
		{:else}
			<ol class="rows" data-testid="shortlist-entries">
				{#each list.entries as e (e.candidate_id)}
					<li data-candidate={e.candidate_id} data-tier={e.tier}>
						<div class="top"><span class="rank">#{e.rank}</span><b class="id">{e.candidate_id}</b><span class="tier {TIER[e.tier].tone}" data-testid="shortlist-tier">{TIER[e.tier].text}</span><span class="chip">{candidateChipText(e.cohort)}</span></div>
						<div class="marks" aria-label="criteria results">{#each e.checks as c (c.id)}<span class="m {c.status.toLowerCase()}" title={`${c.id}: ${c.detail}`}>{c.id} {MARK[c.status]}</span>{/each}</div>
						{#if e.failing.length}<p class="dim">Fails: {failingTitles(e)}</p>{/if}
						<details><summary>Why</summary><ul>{#each e.checks as c (c.id)}<li><b class="s {c.status.toLowerCase()}">{c.id} {c.status.replace('_', ' ')}</b> {c.detail}</li>{/each}</ul></details>
					</li>
				{/each}
			</ol>
		{/if}
	{/if}
</div>
<style>
	.sl { display: grid; gap: 10px; min-width: 0; } .lede { margin: 0; color: #cbd5e1; font-size: 13px; line-height: 1.6; } code { color: #9fe7e1; overflow-wrap: anywhere; }
	.wall { border: 1px solid rgba(251,191,36,.4); background: rgba(251,191,36,.06); padding: 8px 10px; display: grid; gap: 4px; } .wall span { color: #fbbf24; font: 600 10.5px 'JetBrains Mono', monospace; letter-spacing: .12em; } .wall small { color: #cbd5e1; font-size: 12px; line-height: 1.5; }
	.crit summary { cursor: pointer; color: #9fe7e1; font: 11px 'JetBrains Mono', monospace; letter-spacing: .08em; } .crit ol { margin: 8px 0 0; padding-left: 18px; display: grid; gap: 6px; } .crit li { color: #94a3b8; font-size: 12px; line-height: 1.5; } .crit li b { display: block; color: #e5f1f0; font-weight: 500; }
	.rows { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; } .rows > li { border: 1px solid rgba(148,163,184,.25); background: rgba(8,13,22,.5); padding: 10px 12px; display: grid; gap: 8px; min-width: 0; }
	.top { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; } .rank { font: 600 12px 'JetBrains Mono', monospace; color: #71829a; } .id { font: 600 12px 'JetBrains Mono', monospace; color: #9fe7e1; overflow-wrap: anywhere; }
	.tier { font: 600 10.5px 'JetBrains Mono', monospace; letter-spacing: .08em; padding: 2px 7px; border: 1px solid; } .tier.ok { color: #4ade80; border-color: #4ade80; } .tier.mid { color: #fbbf24; border-color: #fbbf24; } .tier.no { color: #94a3b8; border-color: rgba(148,163,184,.4); }
	.chip { margin-left: auto; font: 10.5px 'JetBrains Mono', monospace; letter-spacing: .08em; border: 1px solid rgba(148,163,184,.4); padding: 2px 7px; color: #cbd5e1; }
	.marks { display: flex; flex-wrap: wrap; gap: 6px; } .m { font: 11px 'JetBrains Mono', monospace; padding: 2px 6px; border: 1px solid rgba(148,163,184,.25); color: #94a3b8; } .m.pass { color: #4ade80; border-color: rgba(74,222,128,.5); } .m.fail { color: #f87171; border-color: rgba(248,113,113,.5); }
	details summary { cursor: pointer; color: #71829a; font: 11px 'JetBrains Mono', monospace; } details ul { margin: 6px 0 0; padding-left: 16px; display: grid; gap: 4px; } details li { color: #94a3b8; font-size: 12px; line-height: 1.5; overflow-wrap: anywhere; } .s { font: 600 10.5px 'JetBrains Mono', monospace; } .s.pass { color: #4ade80; } .s.fail { color: #f87171; } .s.not_evidenced { color: #fbbf24; }
	.dim { margin: 0; color: #94a3b8; font-size: 12px; line-height: 1.5; } .warn { margin: 0; color: #fbbf24; font: 11px 'JetBrains Mono', monospace; }
</style>
