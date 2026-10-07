<script module lang="ts">
	export interface CompareRow { label: string; left: string; right: string }
</script>
<script lang="ts">
	// Side-by-side comparison of two things using ONLY facts supplied by the caller. Rows stack into labelled cards on narrow screens. No winner badge, no scoring.
	import type { Snippet } from 'svelte';
	let { leftTitle, rightTitle, leftSub = '', rightSub = '', leftTone = 'released', rightTone = 'candidate', rows, testid = undefined, leftStatus = '', rightStatus = '', evidence = undefined }: {
		leftTitle: string; rightTitle: string; leftSub?: string; rightSub?: string; leftTone?: 'released' | 'federated' | 'candidate' | 'neutral'; rightTone?: 'released' | 'federated' | 'candidate' | 'neutral'; rows: CompareRow[]; testid?: string; leftStatus?: string; rightStatus?: string; evidence?: Snippet;
	} = $props();
</script>
<div class="cmp" data-testid={testid}>
	<div class="hd"><span></span>
		<div class={`col h-${leftTone}`}><b>{leftTitle}</b>{#if leftSub}<small>{leftSub}</small>{/if}{#if leftStatus}<em>{leftStatus}</em>{/if}</div>
		<div class={`col h-${rightTone}`}><b>{rightTitle}</b>{#if rightSub}<small>{rightSub}</small>{/if}{#if rightStatus}<em>{rightStatus}</em>{/if}</div></div>
	{#each rows as r (r.label)}
		<div class="row" data-row={r.label}><span class="lab">{r.label}</span>
			<div class={`cell c-${leftTone}`}><span class="side">{leftTitle}</span>{r.left}</div>
			<div class={`cell c-${rightTone}`}><span class="side">{rightTitle}</span>{r.right}</div></div>
	{/each}
	{#if evidence}{@render evidence()}{/if}
</div>
<style>
	.cmp { display: grid; gap: 6px; min-width: 0; } .hd, .row { display: grid; grid-template-columns: 130px minmax(0, 1fr) minmax(0, 1fr); gap: 8px; align-items: stretch; }
	.col { border: 1px solid rgba(148,163,184,.3); padding: 10px 12px; display: grid; gap: 3px; min-width: 0; } .col b { font: 600 13px 'JetBrains Mono', monospace; overflow-wrap: anywhere; } .col small { color: #94a3b8; font-size: 11px; } .col em { font: normal 10px 'JetBrains Mono', monospace; letter-spacing: .1em; color: #cbd5e1; }
	.h-released { border-color: rgba(43,184,176,.7); background: rgba(43,184,176,.06); } .h-released b { color: #9fe8e3; } .h-candidate { border-color: rgba(251,191,36,.7); background: rgba(251,191,36,.05); } .h-candidate b { color: #fbbf24; } .h-federated { border-color: rgba(167,139,250,.7); background: rgba(167,139,250,.06); } .h-federated b { color: #c4b5fd; }
	.lab { font: 10px 'JetBrains Mono', monospace; letter-spacing: .1em; color: #71829a; padding-top: 10px; text-transform: uppercase; }
	.cell { border: 1px solid rgba(148,163,184,.16); padding: 9px 12px; font-size: 13px; line-height: 1.5; color: #e2e8f0; overflow-wrap: anywhere; min-width: 0; } .side { display: none; }
	.c-released { border-left: 2px solid #2bb8b0; } .c-candidate { border-left: 2px solid #fbbf24; } .c-federated { border-left: 2px solid #a78bfa; }
	@media (max-width: 760px) {
		.hd { grid-template-columns: 1fr 1fr; } .hd > span { display: none; }
		.row { grid-template-columns: 1fr; gap: 4px; border: 1px solid rgba(148,163,184,.14); padding: 8px; } .lab { padding: 0 0 2px; } .side { display: block; font: 9.5px 'JetBrains Mono', monospace; letter-spacing: .08em; color: #71829a; margin-bottom: 2px; }
	}
</style>
