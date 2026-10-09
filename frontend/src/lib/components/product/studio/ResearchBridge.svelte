<script lang="ts">
	// The separate scientific evidence lane (real-ECG federated research) shown next to, and clearly apart from, this synthetic run. Frozen numbers; never merged into the run's trajectory.
	import type { StudioStore } from '$lib/product/studio/store.svelte';
	let { studio }: { studio: StudioStore } = $props();
	const bridge = $derived(studio.overview?.scientific_bridge ?? null);
	const n = (v: unknown, d = 6) => (typeof v === 'number' ? v.toFixed(d) : v === null || v === undefined ? 'UNDEFINED' : String(v));
</script>
<div class="rb" data-testid="research-bridge">
	<h4>Scientific research bridge (separate evidence lane)</h4>
	{#if !bridge}<p class="dim" role="status">Loading the frozen research reference…</p>
	{:else}
		<p class="warn">{bridge.note}</p>
		<div class="scroll" tabindex="-1"><table data-testid="bridge-table"><thead><tr><th scope="col">Dataset</th><th scope="col">Centralized V2 AUPRC</th><th scope="col">Federated V2 FedAvg IID AUPRC</th><th scope="col">AUPRC difference (federated − centralized)</th><th scope="col">Centralized V2 AUROC</th><th scope="col">Federated AUROC</th><th scope="col">AUROC difference</th></tr></thead>
			<tbody>{#each bridge.comparability_rows as r}<tr><th scope="row">{r.dataset}</th><td>{n(r.centralized_V2_AUPRC)}</td><td>{n(r.federated_V2_FedAvg_IID_AUPRC)}</td><td>{n(r.AUPRC_difference_federated_minus_centralized)}</td><td>{n(r.centralized_V2_AUROC)}</td><td>{n(r.federated_V2_FedAvg_IID_AUROC)}</td><td>{n(r.AUROC_difference_federated_minus_centralized)}</td></tr>{/each}</tbody></table></div>
		<p class="dim">{bridge.verdict}. <a href="/app/observatory/outcomes">Open the frozen scientific outcomes →</a> · <a href="/app/observatory/evidence">Evidence explorer →</a></p>
		{#if bridge.limitations.length}<ul>{#each bridge.limitations as l}<li>{l}</li>{/each}</ul>{/if}
	{/if}
</div>
<style>
	.rb { display: grid; grid-template-columns: minmax(0, 1fr); gap: 8px; min-width: 0; } h4 { margin: 0; font: 500 14px 'Space Grotesk', sans-serif; color: #e5f1f0; } .scroll { overflow: auto; max-width: 100%; } table { border-collapse: collapse; font-size: 11.5px; } th, td { border-bottom: 1px solid rgba(148,163,184,.15); padding: 4px 10px; text-align: left; white-space: nowrap; color: #cbd5e1; } thead th { background: #0a0f1f; color: #71829a; font: 10px 'JetBrains Mono', monospace; }
	.dim, li { margin: 0; color: #94a3b8; font-size: 12px; line-height: 1.55; } .warn { margin: 0; color: #fbbf24; font-size: 12px; line-height: 1.55; } a { color: #2bb8b0; } ul { margin: 0; padding-left: 18px; display: grid; gap: 2px; }
	p, li, h4 { overflow-wrap: anywhere; }
</style>
