<script lang="ts">
	// CAP-009: persisted owner-scoped session list; evidence lives on the detail route.
	import { onMount } from 'svelte';
	import Panel from '$lib/components/dashboard/Panel.svelte';
	import { getProductStore } from '$lib/product/state.svelte';
	const store = getProductStore();
	const when = (us: number | null) => (us === null ? '--' : new Date(us / 1000).toLocaleString());
	onMount(() => { void store.loadSessions(); });
</script>
<svelte:head><title>History | NHM</title></svelte:head>
<div class="eyebrow">NHM / HISTORY</div><h1>Research monitoring history</h1>
{#if store.error}<p class="err" role="alert">{store.error}</p>{/if}
<Panel eyebrow="01 / PERSISTED" title="Monitoring sessions" note="GET /sessions">
	{#if store.sessions.length === 0}<p class="dim">No sessions yet. <a href="/app/monitoring">Run a monitoring session →</a></p>{:else}
		<div class="scroll"><table data-testid="session-table"><caption class="sr">Persisted monitoring sessions, newest first</caption>
			<thead><tr><th scope="col">Session</th><th scope="col">State</th><th scope="col">Created</th><th scope="col">Started</th><th scope="col">Ended</th><th scope="col">Device</th><th scope="col">Scenario</th><th scope="col">Model</th><th scope="col">Evidence</th></tr></thead>
			<tbody>{#each store.sessions as s}<tr><td><code>{s.session_id}</code></td><td><span class="badge">{s.state}</span></td><td>{when(s.created_at_us)}</td><td>{when(s.started_at_us)}</td><td>{when(s.ended_at_us)}</td><td>{s.device_id}</td><td>{s.simulation_provenance?.scenario_id ?? '--'}</td><td>{s.runtime.model_id}</td><td><a href={`/app/history/${encodeURIComponent(s.session_id)}`}>VIEW EVIDENCE</a></td></tr>{/each}</tbody></table></div>
	{/if}
	<p class="dim">Completed sessions have a deterministic summary. Failed or unfinished sessions may show partial persisted evidence, but no completed-session summary. The history is engineering monitoring evidence, not a diagnosis or training dataset.</p>
</Panel>
<style>
	.eyebrow { color: #2bb8b0; font: 10px 'JetBrains Mono', monospace; letter-spacing: .14em; } h1 { margin: 10px 0 18px; font: 500 clamp(26px, 4vw, 40px) 'Space Grotesk', sans-serif; } .dim { color: #94a3b8; font-size: 13px; line-height: 1.6; } .err { color: #fecdd3; padding: 10px; border: 1px solid rgba(251,113,133,.4); }
	.scroll { overflow-x: auto; } table { border-collapse: collapse; width: 100%; font-size: 12px; } th, td { padding: 9px 10px; border-bottom: 1px solid var(--nhm-border); text-align: left; white-space: nowrap; } th { color: #71829a; font: 10px 'JetBrains Mono', monospace; letter-spacing: .1em; font-weight: 500; }
	code { font: 11px 'JetBrains Mono', monospace; } .badge { padding: 2px 7px; border: 1px solid rgba(43,184,176,.5); color: #2bb8b0; font: 10px 'JetBrains Mono', monospace; } a { color: #2bb8b0; } .sr { position: absolute; left: -9999px; }
</style>
