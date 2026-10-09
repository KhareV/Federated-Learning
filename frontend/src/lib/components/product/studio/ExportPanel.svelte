<script lang="ts">
	// Run-specific exports: each file is downloaded from THIS run's verified export set and re-hashed in the browser against the manifest; a recorded figure is never offered under a live run id.
	import { getProductStore } from '$lib/product/state.svelte';
	import type { StudioStore } from '$lib/product/studio/store.svelte';
	let { studio }: { studio: StudioStore } = $props();
	const product = getProductStore();
	const ex = $derived(studio.exports);
	let note = $state<string | null>(null);
	let busy = $state(false);
	const FIG_FORMATS: [string, string][] = [['svg', 'SVG'], ['png', 'PNG 300 dpi'], ['csv', 'CSV'], ['provenance', 'JSON provenance']];
	const TAB_FORMATS: [string, string][] = [['csv', 'CSV'], ['json', 'JSON'], ['md', 'Markdown']];
	const hex = (buf: ArrayBuffer) => [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('');
	async function get(item: string, fmt: string, expected: string | undefined) {
		const runId = studio.trackedRunId;
		if (!runId || busy) return;
		busy = true; note = null;
		try {
			const { blob, sha256 } = await product.api.studioExportFile(runId, item, fmt);
			const actual = hex(await crypto.subtle.digest('SHA-256', await blob.arrayBuffer()));
			const ok = actual === (sha256 ?? '') && (expected === undefined || actual === expected);
			const url = URL.createObjectURL(blob);
			const a = document.createElement('a'); a.href = url; a.download = `${runId}_${item}.${fmt === 'provenance' ? 'provenance.json' : fmt}`; a.click();
			setTimeout(() => URL.revokeObjectURL(url), 1000);
			note = `${item}.${fmt} · sha256 ${actual.slice(0, 16)}… ${ok ? 'verified against the export manifest' : 'MISMATCH — do not use this file'}`;
		} catch (cause) {
			note = `export failed: ${cause instanceof Error ? cause.message : String(cause)}`;
		} finally { busy = false; }
	}
	const figures = $derived(ex?.figures ? Object.entries(ex.figures) : []);
	const tables = $derived(ex?.tables ? Object.entries(ex.tables) : []);
	const data = $derived(ex?.data ? Object.entries(ex.data) : []);
</script>
<div class="ep" data-testid="export-panel">
	{#if !ex || ex.status !== 'READY'}
		<p class="prep" role="status" data-testid="export-status">{ex?.status === 'PREPARING' || studio.run?.export_status === 'PREPARING' ? 'EXPORT PREPARING — figures, tables and evidence are generated after the run completes and every evaluation has settled.' : ex?.message ?? studio.run?.export_status === 'FAILED' ? 'EXPORT FAILED — see the run status.' : 'Exports are generated when the run completes and every evaluation has settled.'}</p>
	{:else}
		<p class="ok" data-testid="export-status">EXPORT READY · {ex.source_label ?? ''} · run {ex.run_id}</p>
		<p class="dim">Every file below was generated from this run's verified bundle ({figures.length} figures, {tables.length} tables, {data.length} evidence files). Cohort: {ex.cohort_use}.</p>
		<h4>Figures</h4>
		<ul>{#each figures as [id, files] (id)}<li><b>{id.replace('FL10_', '')}</b>{#each FIG_FORMATS as [fmt, label] (fmt)}{#if files[fmt]}<button type="button" disabled={busy} onclick={() => void get(id, fmt, files[fmt].sha256)} data-testid={`export-${id}-${fmt}`}>{label}</button>{/if}{/each}</li>{/each}</ul>
		<h4>Tables</h4>
		<ul>{#each tables as [id, files] (id)}<li><b>{id.replace('FL10_', '')}</b>{#each TAB_FORMATS as [fmt, label] (fmt)}{#if files[fmt]}<button type="button" disabled={busy} onclick={() => void get(id, fmt, files[fmt].sha256)} data-testid={`export-${id}-${fmt}`}>{label}</button>{/if}{/each}</li>{/each}</ul>
		<h4>Evidence data (full precision)</h4>
		<ul>{#each data as [id, files] (id)}<li><b>{id}</b>{#each Object.keys(files) as fmt (fmt)}<button type="button" disabled={busy} onclick={() => void get(id, fmt, files[fmt].sha256)} data-testid={`export-${id}-${fmt}`}>{fmt.toUpperCase()}</button>{/each}</li>{/each}</ul>
	{/if}
	{#if note}<p class="dim" role="status" data-testid="export-note">{note}</p>{/if}
</div>
<style>
	.ep { display: grid; gap: 8px; min-width: 0; } h4 { margin: 8px 0 2px; font: 11px 'JetBrains Mono', monospace; letter-spacing: .1em; color: #a78bfa; } ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 5px; } li { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; font-size: 12px; color: #cbd5e1; } li b { min-width: 6.5em; font: 11px 'JetBrains Mono', monospace; color: #e2e8f0; }
	button { background: #0a0f1f; color: #e2e8f0; border: 1px solid rgba(148,163,184,.35); padding: 4px 9px; min-height: 28px; font: 11px 'JetBrains Mono', monospace; cursor: pointer; } button:disabled { opacity: .5; cursor: wait; } button:focus-visible { outline: 2px solid #2bb8b0; } .dim { margin: 0; color: #94a3b8; font-size: 12px; line-height: 1.5; } .prep { margin: 0; border: 1px solid rgba(251,191,36,.5); padding: 8px 12px; color: #fde68a; font: 12px 'JetBrains Mono', monospace; } .ok { margin: 0; color: #86efac; font: 12px 'JetBrains Mono', monospace; }
</style>
