<script lang="ts">
	// STATIC explanation of the existing federation process (not live data). Desktop: a horizontal flow; mobile: the same stages stacked.
	const steps = [
		{ id: 'clients', title: '8 local clients', text: 'Synthetic clients, each with its own local data buffer.' },
		{ id: 'train', title: 'Local training', text: 'Every client trains on its own local examples.' },
		{ id: 'updates', title: 'Model updates', text: 'Only model updates leave a client - not its examples.' },
		{ id: 'coord', title: 'Coordinator', text: 'Collects the updates for the round.' },
		{ id: 'agg', title: 'FedAvg / FedProx', text: 'Combines the updates into one result.' },
		{ id: 'state', title: 'New global state', text: 'The shared model state after the round.' },
		{ id: 'cand', title: 'Final candidate', text: 'After 3 rounds the last state becomes a candidate.' },
		{ id: 'sandbox', title: 'Engineering sandbox', text: 'Structural checks only. Not deployed.' }
	];
</script>
<ol class="pipe" data-testid="federation-pipeline" aria-label="Federated training pipeline">
	{#each steps as s, i (s.id)}
		<li class={`s s-${s.id}`}><span class="n" aria-hidden="true">{i + 1}</span><b>{s.title}</b><span class="t">{s.text}</span>{#if i < steps.length - 1}<span class="arr" aria-hidden="true"></span>{/if}</li>
	{/each}
</ol>
<style>
	.pipe { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 150px), 1fr)); gap: 10px; counter-reset: s; }
	.s { position: relative; border: 1px solid rgba(167,139,250,.35); background: rgba(167,139,250,.06); padding: 10px 11px 12px; display: grid; gap: 5px; min-width: 0; align-content: start; }
	.n { width: 22px; height: 22px; display: inline-grid; place-items: center; border: 1px solid rgba(167,139,250,.6); border-radius: 50%; font: 11px 'JetBrains Mono', monospace; color: #c4b5fd; } b { font: 500 13px 'Space Grotesk', sans-serif; color: #e5f1f0; } .t { font-size: 12px; line-height: 1.45; color: #94a3b8; }
	.s-cand, .s-sandbox { border-color: rgba(251,191,36,.45); background: rgba(251,191,36,.05); } .s-cand .n, .s-sandbox .n { border-color: rgba(251,191,36,.7); color: #fcd34d; }
	.arr::after { content: '→'; position: absolute; right: -10px; top: 50%; transform: translateY(-50%); color: #71829a; font-size: 14px; background: #030712; line-height: 1; }
	@media (max-width: 760px) { .pipe { grid-template-columns: 1fr; } .arr::after { content: '↓'; right: auto; left: 50%; top: auto; bottom: -11px; transform: translateX(-50%); } .s { padding-bottom: 14px; } }
</style>
