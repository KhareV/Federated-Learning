<script lang="ts">
	// OVERVIEW | PERFORMANCE | TRAINING | CLIENTS | MATRICES | COMPARISON | FIGURES & EXPORTS.
	// Every one of the 20 figures and 12 tables of the delivered FL10 inventory is reachable here with THIS run's data; only the active tab is rendered (no re-render of all figures per event).
	import Fl10Chart from '$lib/components/product/observatory/Fl10Chart.svelte';
	import Fl10Table from '$lib/components/product/observatory/Fl10Table.svelte';
	import ExportPanel from './ExportPanel.svelte';
	import RoundClientPanel from './RoundClientPanel.svelte';
	import RunOverview from './RunOverview.svelte';
	import RoundComparison from './RoundComparison.svelte';
	import ClientHistory from './ClientHistory.svelte';
	import ResearchBridge from './ResearchBridge.svelte';
	import { ANALYSIS_TABS, type AnalysisTab, type StudioStore } from '$lib/product/studio/store.svelte';
	import type { Fl10Spec, Fl10Table as Table } from '$lib/product/observatory/fl10';
	let { studio }: { studio: StudioStore } = $props();
	const LABEL: Record<AnalysisTab, string> = { overview: 'OVERVIEW', performance: 'PERFORMANCE', training: 'TRAINING', clients: 'CLIENTS', matrices: 'MATRICES', comparison: 'COMPARISON', figures: 'FIGURES & EXPORTS' };
	const FIGS: Record<AnalysisTab, string[]> = {
		overview: ['FL10_FIG01', 'FL10_FIG18'], performance: ['FL10_FIG04', 'FL10_FIG05', 'FL10_FIG06', 'FL10_FIG15', 'FL10_FIG20'], training: ['FL10_FIG02', 'FL10_FIG03', 'FL10_FIG12', 'FL10_FIG17', 'FL10_FIG19'],
		clients: ['FL10_FIG11', 'FL10_FIG13', 'FL10_FIG14'], matrices: ['FL10_FIG07', 'FL10_FIG08', 'FL10_FIG09', 'FL10_FIG10'], comparison: ['FL10_FIG16', 'FL10_FIG20'], figures: []
	};
	const TABS_OF: Record<AnalysisTab, string[]> = {
		overview: ['FL10_TAB08', 'FL10_TAB10', 'FL10_TAB12'], performance: ['FL10_TAB01', 'FL10_TAB05'], training: ['FL10_TAB03', 'FL10_TAB04', 'FL10_TAB07'], clients: ['FL10_TAB06'], matrices: [], comparison: ['FL10_TAB02', 'FL10_TAB11'],
		figures: ['FL10_TAB01', 'FL10_TAB02', 'FL10_TAB03', 'FL10_TAB04', 'FL10_TAB05', 'FL10_TAB06', 'FL10_TAB07', 'FL10_TAB08', 'FL10_TAB09', 'FL10_TAB10', 'FL10_TAB11', 'FL10_TAB12']
	};
	const tab = $derived(studio.analysisTab);
	const available = $derived(studio.run?.evaluation.available === true);
	$effect(() => { if (available) { void studio.ensureFigures(); void studio.ensureOverview(); if (TABS_OF[tab].length || tab === 'clients') void studio.ensureTables(); } });
	const spec = (id: string) => studio.figures?.specs[id];
	const table = (id: string) => studio.tables?.tables[id];
	function key(e: KeyboardEvent, i: number) {
		const step = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
		if (!step) return;
		e.preventDefault();
		const next = ANALYSIS_TABS[(i + step + ANALYSIS_TABS.length) % ANALYSIS_TABS.length];
		studio.analysisTab = next;
		queueMicrotask(() => document.getElementById(`atab-${next}`)?.focus());
	}
	const recorded = [{ id: 'recorded-A', label: 'Recorded FL10 Mode A (canonical cohort)' }, { id: 'recorded-B', label: 'Recorded FL10 Mode B (live-monitored SITE_00)' }];
</script>
<div class="at" data-testid="analysis-tabs">
	<div class="tabs" role="tablist" aria-label="Analysis views">
		{#each ANALYSIS_TABS as t, i (t)}<button type="button" role="tab" id={`atab-${t}`} aria-selected={tab === t} aria-controls={`apanel-${t}`} tabindex={tab === t ? 0 : -1} class:on={tab === t} data-testid={`atab-${t}`} onclick={() => { studio.analysisTab = t; }} onkeydown={(e) => key(e, i)}>{LABEL[t]}</button>{/each}
	</div>
	<div role="tabpanel" id={`apanel-${tab}`} aria-labelledby={`atab-${tab}`} class="panel" data-testid={`apanel-${tab}`}>
		{#if !available}
			<p class="dim" data-testid="analysis-unavailable">No per-round evaluation or training records were captured for this run ({studio.run?.evaluation.reason ?? 'unavailable'}). Open a run started with the unified Studio, or a recorded FL10 run, to inspect figures and tables.</p>
		{:else}
			{#if tab === 'overview'}
				<p class="dim" data-testid="overview-summary">{studio.run?.label} · {studio.run?.source_label} · evaluated rounds {studio.records.filter((r) => r.evaluation_status === 'COMPLETED').length}/{studio.rounds.length} · {studio.summary?.cohort_use}</p>
				<RunOverview {studio} />
			{/if}
			{#if tab === 'clients'}<RoundClientPanel {studio} /><ClientHistory {studio} />{/if}
			{#if tab === 'comparison'}
				<p class="dim">Same-cohort paired comparison: round {studio.summary?.comparison.comparator_round} → round {studio.summary?.comparison.endpoint_round} ({studio.summary?.comparison.paired_available ? 'both evaluated' : 'pending until both states are evaluated'}). It is an exploratory effect on a reused cohort with nominal intervals, not a significance test, and the same run's states are never compared with a different run's.</p>
				<RoundComparison {studio} />
				<ResearchBridge {studio} />
				<ul class="refs" data-testid="recorded-refs">{#each recorded as r (r.id)}<li><a href={`/app/federation/live?run=${r.id}`}>{r.label}</a> — frozen NHM_FL10_001 evidence (R0–R10), opened read-only as a historical run.</li>{/each}</ul>
			{/if}
			{#if tab === 'figures'}<ExportPanel {studio} />{/if}
			{#if !studio.figures && FIGS[tab].length}<p class="dim" role="status" data-testid="figures-loading">Loading figures…</p>{/if}
			<div class="grid">
				{#each FIGS[tab] as id (id)}{@const s = spec(id)}{#if s}
					<div class="one" data-testid={`fig-${id}`} data-availability={s.availability}>
						<Fl10Chart spec={s as unknown as Fl10Spec} selectedX={['FL10_FIG02', 'FL10_FIG03', 'FL10_FIG04', 'FL10_FIG05', 'FL10_FIG06', 'FL10_FIG17'].includes(id) && studio.selectedRound >= (id === 'FL10_FIG02' || id === 'FL10_FIG03' || id === 'FL10_FIG17' ? 1 : 0) ? studio.selectedRound : null} onPickX={['FL10_FIG04', 'FL10_FIG05', 'FL10_FIG06'].includes(id) ? (x) => studio.selectRound(x) : undefined} />
						{#if s.availability !== 'AVAILABLE'}<p class="avail" data-testid={`avail-${id}`}>{s.availability}: {s.availability_detail}</p>{/if}
					</div>{/if}{/each}
			</div>
			{#if TABS_OF[tab].length}
				{#if !studio.tables}<p class="dim" role="status" data-testid="tables-loading">Loading tables…</p>{/if}
				<div class="tbls">{#each TABS_OF[tab] as id (id)}{@const t = table(id)}{#if t}<Fl10Table table={t as unknown as Table} />{/if}{/each}</div>
			{/if}
		{/if}
	</div>
</div>
<style>
	.at { display: grid; grid-template-columns: minmax(0, 1fr); gap: 10px; min-width: 0; } .tabs { display: flex; flex-wrap: wrap; gap: 2px; border-bottom: 1px solid rgba(148,163,184,.25); } .tabs button { background: transparent; color: #94a3b8; border: 1px solid transparent; border-bottom: 0; padding: 8px 12px; min-height: 40px; font: 11px 'JetBrains Mono', monospace; letter-spacing: .08em; cursor: pointer; } .tabs button.on { color: #9fe8e3; border-color: rgba(148,163,184,.25); background: rgba(43,184,176,.07); box-shadow: inset 0 -2px 0 #2bb8b0; } .tabs button:focus-visible { outline: 2px solid #2bb8b0; outline-offset: -2px; }
	.panel { display: grid; grid-template-columns: minmax(0, 1fr); gap: 10px; min-width: 0; } .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 440px), 1fr)); gap: 10px; min-width: 0; } .one { min-width: 0; display: grid; grid-template-columns: minmax(0, 1fr); gap: 4px; } .tbls { display: grid; grid-template-columns: minmax(0, 1fr); gap: 8px; min-width: 0; } .dim { margin: 0; color: #94a3b8; font-size: 12.5px; line-height: 1.6; } .avail { margin: 0; font: 11px 'JetBrains Mono', monospace; color: #fbbf24; } .refs { margin: 0; padding-left: 18px; font-size: 12.5px; color: #cbd5e1; display: grid; gap: 3px; } .refs a { color: #2bb8b0; }
	@media (max-width: 520px) { .tabs button { padding: 8px 8px; font-size: 10px; } }
	p, li, button { overflow-wrap: anywhere; }
</style>
