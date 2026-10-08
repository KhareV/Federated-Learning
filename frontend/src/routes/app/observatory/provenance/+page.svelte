<script lang="ts">
	import { onMount } from 'svelte';
	import { getProductStore } from '$lib/product/state.svelte';
	import type { Boundaries, Reproducibility } from '$lib/product/observatory/evidence';
	const store = getProductStore();
	let repro = $state<Reproducibility | null>(null);
	let gallery = $state<Boundaries | null>(null);
	let error = $state<string | null>(null);
	onMount(() => {
		void Promise.all([store.api.observatoryReproducibility(), store.api.observatoryBoundaries()]).then(([r, g]) => { repro = r; gallery = g; })
			.catch((c) => { error = c instanceof Error ? c.message : String(c); });
	});
</script>
<svelte:head><title>Provenance and known boundaries | NHM</title></svelte:head>
<div class="eyebrow">NHM / RESEARCH OBSERVATORY / PROVENANCE</div>
<h1>Provenance, history and known boundaries</h1>
<p class="lead">Each statement below points to a committed evidence file and shows its current SHA-256. A listed report is evidence of a result, not proof that this session re-ran it.</p>
{#if error}<p role="alert" class="err">Unavailable: {error}</p>{:else if !repro || !gallery}<p class="dim" role="status">Loading…</p>{:else}
<section aria-label="Reproducibility console" data-testid="reproducibility"><h2>Reproducibility console</h2>
	<dl><div><dt>Git commit</dt><dd>{repro.git_commit ?? 'NOT AVAILABLE'}</dd></div><div><dt>Released model</dt><dd>{repro.released_model}</dd></div><div><dt>Checkpoint SHA256</dt><dd>{repro.released_checkpoint_sha256}</dd></div><div><dt>Calibration</dt><dd>{repro.calibration_id}</dd></div>
		{#each repro.fields as [k, v] (k)}<div><dt>{k}</dt><dd>{v}</dd></div>{/each}</dl><p class="dim">{repro.note}</p></section>
<section aria-label="Decision history" data-testid="chronology"><h2>Decision history (negative results included)</h2>
	<ol class="time">{#each gallery.chronology as item (item.id)}<li><b>{item.title}</b><span class="dec">{item.decision}</span><p>{item.why}</p><small class={item.exists ? '' : 'miss'}>{item.exists ? '✓' : '✕ MISSING'} <code>{item.path}</code> · {item.sha256 ? item.sha256.slice(0, 16) + '…' : 'no file'}</small></li>{/each}</ol>
	<p class="warn">MODEL_V2_NOT_PROMOTED_RELEASE_CI and SYSTEM_V2_RESEARCH_DEFAULT_ACCEPTED are different decisions under different criteria; neither rewrites the other.</p></section>
<section aria-label="Known boundaries" data-testid="boundaries"><h2>Known boundaries</h2>
	<ul class="cards">{#each gallery.boundaries as item (item.id)}<li><b>{item.title}</b><p>{item.statement}</p><small class={item.exists ? '' : 'miss'}>{item.exists ? '✓' : '✕ MISSING'} <code>{item.path}</code> · {item.sha256 ? item.sha256.slice(0, 16) + '…' : 'no file'}</small></li>{/each}</ul></section>
{/if}
<p class="dim"><a href="/app/observatory">← Observatory</a> · <a href="/app/observatory/evidence">Scientific evidence</a> · <a href="/app/observatory/model">Model and calibration</a></p>
<style>
	.eyebrow{color:#2bb8b0;font:10px 'JetBrains Mono',monospace;letter-spacing:.14em}h1{font:500 clamp(26px,4vw,40px) 'Space Grotesk',sans-serif;margin:8px 0}h2{font:500 18px 'Space Grotesk',sans-serif;margin:24px 0 10px}.lead{max-width:860px;color:#a7b8c9;line-height:1.6}.dim,small,p,dd{color:#94a3b8;font-size:13px;line-height:1.6;overflow-wrap:anywhere}.err{color:#fecdd3}a{color:#2bb8b0}code{font:11px 'JetBrains Mono',monospace;color:#9fe7e1;overflow-wrap:anywhere}.miss{color:#fca5a5}
	dl{display:grid;gap:4px}dl div{display:flex;gap:10px;flex-wrap:wrap}dt{color:#71829a;font:11px 'JetBrains Mono',monospace;min-width:180px}dd{margin:0}.warn{border-left:3px solid #fbbf24;background:rgba(251,191,36,.06);padding:8px 12px;color:#fde68a}
	.time{list-style:none;margin:0;padding:0 0 0 12px;border-left:2px solid rgba(43,184,176,.4);display:grid;gap:14px}.time li{display:grid;gap:3px}.time b{font:500 15px 'Space Grotesk',sans-serif}.dec{font:600 12px 'JetBrains Mono',monospace;color:#c4b5fd}.time p{margin:0}
	.cards{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:10px}.cards li{border:1px solid rgba(251,191,36,.35);padding:12px 14px;display:grid;gap:6px;min-width:0}.cards b{font:500 14px 'Space Grotesk',sans-serif}.cards p{margin:0}
</style>
