<script module lang="ts">
	export type FlowTone = 'released' | 'federated' | 'candidate' | 'neutral' | 'blocked';
	export interface FlowStep { label: string; sub?: string; tone?: FlowTone; mark?: string; status?: 'done' | 'active' | 'pending' }
</script>
<script lang="ts">
	// Ordered explanatory flow; callers may supply current step statuses. It stacks on narrow screens.
	let { steps, tone = 'neutral', vertical = false, testid = undefined, label = 'Flow' }: { steps: FlowStep[]; tone?: FlowTone; vertical?: boolean; testid?: string; label?: string } = $props();
</script>
<ol class="flow" class:vertical data-testid={testid} aria-label={label}>
	{#each steps as s, i (i)}
		<li class={`t-${s.tone ?? tone}${s.status ? ` st-${s.status}` : ''}`} data-status={s.status}>
			<span class="box"><b>{#if s.mark}<span aria-hidden="true">{s.mark} </span>{/if}{s.label}</b>{#if s.sub}<small>{s.sub}</small>{/if}{#if s.status}<span class="sr">{s.status}</span>{/if}</span>
		</li>
	{/each}
</ol>
<style>
	.flow { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: nowrap; gap: 22px; align-items: stretch; }
	li { position: relative; flex: 1 1 0; min-width: 0; display: flex; }
	li:not(:last-child)::after { content: '→'; position: absolute; right: -19px; top: 50%; transform: translateY(-50%); color: #71829a; font: 14px 'JetBrains Mono', monospace; }
	.box { flex: 1; border: 1px solid rgba(148,163,184,.3); background: #0a0f1f; padding: 9px 10px; display: grid; gap: 3px; align-content: start; min-width: 0; }
	b { font: 600 12px 'JetBrains Mono', monospace; letter-spacing: .03em; overflow-wrap: anywhere; } small { color: #94a3b8; font-size: 11px; line-height: 1.4; overflow-wrap: anywhere; }
	.t-released .box { border-color: rgba(43,184,176,.6); } .t-released b { color: #9fe8e3; }
	.t-federated .box { border-color: rgba(167,139,250,.6); } .t-federated b { color: #c4b5fd; }
	.t-candidate .box { border-color: rgba(251,191,36,.6); } .t-candidate b { color: #fbbf24; }
	.t-blocked .box { border: 1px dashed rgba(248,113,113,.6); } .t-blocked b { color: #fca5a5; }
	.st-done .box { background: rgba(43,184,176,.07); } .st-active .box { box-shadow: 0 0 0 2px rgba(167,139,250,.6); } .st-pending .box { opacity: .65; }
	.sr { position: absolute; left: -9999px; }
	.vertical, :global(.flow.force-vertical) { flex-direction: column; gap: 20px; }
	.vertical li:not(:last-child)::after { content: '↓'; right: auto; left: 50%; top: auto; bottom: -18px; transform: translateX(-50%); }
	@media (max-width: 900px) { .flow { flex-direction: column; gap: 20px; } li:not(:last-child)::after { content: '↓'; right: auto; left: 50%; top: auto; bottom: -18px; transform: translateX(-50%); } }
</style>
