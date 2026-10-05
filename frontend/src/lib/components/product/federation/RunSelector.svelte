<script lang="ts">
	import type { FederationRun } from '$lib/product/federation/types';
	let { runs, selected, onSelect }: { runs: FederationRun[]; selected: string | null; onSelect: (id: string) => void } = $props();
</script>
<label class="sel">Federation run
	<select value={selected ?? ''} onchange={(e) => onSelect((e.currentTarget as HTMLSelectElement).value)} data-testid="run-selector">
		<option value="" disabled>{runs.length ? 'Select a run' : 'No runs yet'}</option>
		{#each runs as r}<option value={r.run_id}>{r.run_id} · {r.run_type} · {r.algorithm} · {r.secagg_mode} · {r.status}</option>{/each}
	</select>
</label>
<style>
	.sel { display: grid; gap: 4px; max-width: 720px; font: 11px 'JetBrains Mono', monospace; letter-spacing: .06em; color: #94a3b8; margin-bottom: 14px; } select { width: 100%; min-width: 0; box-sizing: border-box; padding: 8px 10px; background: #07101e; color: #e5f1f0; border: 1px solid rgba(148,163,184,.3); font: 12px 'JetBrains Mono', monospace; } select:focus-visible { outline: 2px solid #2bb8b0; }
</style>
