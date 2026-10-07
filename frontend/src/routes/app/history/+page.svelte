<script lang="ts">
	// CAP-009: persisted owner-scoped session list; evidence lives on the detail route.
	import { onMount } from 'svelte';
	import Panel from '$lib/components/dashboard/Panel.svelte';
	import { getProductStore } from '$lib/product/state.svelte';
	const store = getProductStore();
	let loaded = $state(false);
	const when = (us: number | null) => (us === null ? '--' : new Date(us / 1000).toLocaleString());
	onMount(() => { void store.loadSessions().finally(() => (loaded = true)); });
</script>
<svelte:head><title>History | NHM</title></svelte:head>
<div class="eyebrow">NHM / HISTORY</div><h1>Research monitoring history</h1>
{#if store.error}<p class="err" role="alert">{store.error}</p>{/if}
<Panel eyebrow="01 / PERSISTED" title="Monitoring sessions" note="OWNER-SCOPED HISTORY">
	{#if !loaded}<p role="status" class="dim">Loading persisted monitoring sessions…</p>
	{:else if store.sessions.length === 0}<div class="empty"><strong>No monitoring sessions yet</strong><p class="dim">This is expected until a simulated wearable session is run and persisted.</p><a class="cta" href="/app/monitoring">RUN A MONITORING SESSION →</a></div>
	{:else}
		<div class="scroll"><table data-testid="session-table"><caption class="sr">Persisted monitoring sessions, newest first</caption>
			<thead><tr><th scope="col">Session</th><th scope="col">State</th><th scope="col">Evidence</th><th scope="col">Created</th><th scope="col">Scenario</th><th scope="col">Model</th><th scope="col">Started</th><th scope="col">Ended</th><th scope="col">Device</th></tr></thead>
			<tbody>{#each store.sessions as s}<tr><td><code>{s.session_id}</code></td><td><span class="badge" class:complete={s.state === 'COMPLETED'} class:failed={s.state === 'FAILED'}>{s.state}</span></td><td><a href={`/app/history/${encodeURIComponent(s.session_id)}`}>VIEW EVIDENCE</a></td><td>{when(s.created_at_us)}</td><td>{s.simulation_provenance?.scenario_id ?? '--'}</td><td>{s.runtime.model_id}</td><td>{when(s.started_at_us)}</td><td>{when(s.ended_at_us)}</td><td>{s.device_id}</td></tr>{/each}</tbody></table></div>
		<ul class="mobile-list" aria-label="Persisted monitoring sessions">{#each store.sessions as s}<li><div class="card-head"><span class="badge" class:complete={s.state === 'COMPLETED'} class:failed={s.state === 'FAILED'}>{s.state}</span><time>{when(s.created_at_us)}</time></div><strong class="session-id">{s.session_id}</strong><dl><div><dt>Scenario</dt><dd>{s.simulation_provenance?.scenario_id ?? '--'}</dd></div><div><dt>Model</dt><dd>{s.runtime.model_id}</dd></div><div><dt>Device</dt><dd>{s.device_id}</dd></div><div><dt>Started</dt><dd>{when(s.started_at_us)}</dd></div><div><dt>Ended</dt><dd>{when(s.ended_at_us)}</dd></div></dl><a class="cta" href={`/app/history/${encodeURIComponent(s.session_id)}`}>VIEW EVIDENCE →</a></li>{/each}</ul>
	{/if}
	<p class="dim">Completed sessions have a deterministic summary. Failed or unfinished sessions may show partial persisted evidence, but no completed-session summary. The history is engineering monitoring evidence, not a diagnosis or training dataset.</p>
</Panel>
<style>
	.eyebrow { color: #2bb8b0; font: 10px 'JetBrains Mono', monospace; letter-spacing: .14em; } h1 { margin: 10px 0 18px; font: 500 clamp(26px, 4vw, 40px) 'Space Grotesk', sans-serif; } .dim { color: #94a3b8; font-size: 13px; line-height: 1.6; } .err { color: #fecdd3; padding: 10px; border: 1px solid rgba(251,113,133,.4); }
	.scroll { overflow-x: auto; } table { border-collapse: collapse; width: 100%; font-size: 12px; } th, td { padding: 9px 10px; border-bottom: 1px solid var(--nhm-border); text-align: left; white-space: nowrap; } th { color: #71829a; font: 10px 'JetBrains Mono', monospace; letter-spacing: .1em; font-weight: 500; }
	code { font: 11px 'JetBrains Mono', monospace; } .badge { padding: 2px 7px; border: 1px solid rgba(43,184,176,.5); color: #2bb8b0; font: 10px 'JetBrains Mono', monospace; } a { color: #2bb8b0; display: inline-flex; align-items: center; min-height: 24px; } .sr { position: absolute; left: -9999px; }
	.badge.complete{color:#2bb8b0}.badge.failed{color:#fb7185;border-color:rgba(251,113,133,.5)}.empty{padding:18px;border:1px dashed var(--nhm-border)}.empty strong{font:500 18px 'Space Grotesk',sans-serif}.cta{display:inline-flex;align-items:center;min-height:32px;padding:7px 12px;border:1px solid #2bb8b0;text-decoration:none;font:600 11px 'JetBrains Mono',monospace;letter-spacing:.06em}.mobile-list{display:none;list-style:none;margin:0;padding:0;gap:10px}.mobile-list li{border:1px solid var(--nhm-border);padding:14px;min-width:0}.card-head{display:flex;justify-content:space-between;gap:8px;align-items:center}.card-head time{color:#94a3b8;font-size:11px}.session-id{display:block;margin:12px 0;overflow-wrap:anywhere;font:500 13px 'JetBrains Mono',monospace}.mobile-list dl{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;margin:0 0 14px}.mobile-list dt{color:#71829a;font:10px 'JetBrains Mono',monospace}.mobile-list dd{margin:3px 0 0;overflow-wrap:anywhere;font-size:12px}.mobile-list a:focus-visible,a:focus-visible{outline:2px solid #fbbf24;outline-offset:2px}
	@media(max-width:760px){.scroll{display:none}.mobile-list{display:grid}}@media(max-width:390px){.mobile-list dl{grid-template-columns:1fr}}
</style>
