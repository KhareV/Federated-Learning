<script lang="ts">
	import { focusHeading } from '$lib/product/observatory/focus';
	import { onMount } from 'svelte';
	import { getProductStore } from '$lib/product/state.svelte';
	import { federationSocketUrl } from '$lib/product/api';
	import { LiveSocket } from '$lib/product/socket';
	import type { FederationView } from '$lib/product/federation/live-model';
	import { buildSnapshots } from '$lib/product/observatory/replay.svelte';
	import type { StudioRun } from '$lib/product/studio/types';
	import { clientIdsOfRun, runDataSource } from '$lib/product/federation/data-source';
	import ProcessStepper from '$lib/components/product/federation/ProcessStepper.svelte';
	import RoundProgress from '$lib/components/product/federation/RoundProgress.svelte';
	import ClientGrid from '$lib/components/product/federation/ClientGrid.svelte';
	import CandidateLifecycle from '$lib/components/product/federation/CandidateLifecycle.svelte';
	const store = getProductStore();
	let runs = $state<StudioRun[]>([]);
	let runId = $state('');
	let raw: unknown[] = [];
	let snapshots = $state.raw<FederationView[]>([]);
	let index = $state(0);
	let status = $state<'IDLE' | 'COLLECTING' | 'READY' | 'FAILED'>('IDLE');
	let error = $state<string | null>(null);
	let playing = $state(false);
	let timer: ReturnType<typeof setInterval> | null = null;
	let socket: LiveSocket | null = null;
	let selectedClient = $state('SIM_FL_SITE_00');
	const view = $derived(snapshots[Math.min(index, Math.max(0, snapshots.length - 1))] ?? null);
	const run = $derived(runs.find((r) => r.run_id === runId) ?? null);
	const dataSource = $derived(runDataSource(runId, run?.engine));
	const planned = $derived(view?.plannedRounds || run?.planned_rounds || 3);
	const jumpRounds = $derived([...new Set([1, Math.ceil(planned / 2), planned])].filter((n) => n >= 1 && n <= planned));
	const sourceName = (r: StudioRun) => (r.source_mode === 'RECORDED_HARDWARE' ? 'RECORDED HARDWARE' : r.source_mode === 'LIVE_MONITORED_SITE_00' ? `${r.signal_session_id ? 'HISTORY SESSION · SITE_' : 'LIVE-MONITORED SITE_'}${String(r.monitored_site ?? 0).padStart(2, '0')}` : r.origin === 'RECORDED' ? 'RECORDED SYNTHETIC' : 'SYNTHETIC');
	function build() {
		const out = buildSnapshots(runId, raw);
		if (out === null) { error = 'The event journal failed integrity validation; replay is not shown as trustworthy.'; status = 'FAILED'; return; }
		snapshots = out; index = 0; status = 'READY';
	}
	function stopPlay() { playing = false; if (timer) { clearInterval(timer); timer = null; } }
	async function load() {
		stopPlay(); socket?.close(); socket = null; snapshots = []; raw = []; error = null; index = 0;
		const picked = runs.find((r) => r.run_id === runId);
		selectedClient = clientIdsOfRun(runDataSource(runId, picked?.engine), picked?.client_ids)[0];
		if (!runId) { status = 'IDLE'; return; }
		status = 'COLLECTING';
		socket = new LiveSocket({
			url: federationSocketUrl(runId, location),
			getToken: store.authState.mode === 'CLERK' ? () => store.auth.getSessionToken() : undefined,       // the journal socket is owner-scoped: without the Clerk token the server refuses it (4401), which looked like a disconnect
			handlers: {
				onReset: () => { raw = []; },
				onMessage: (data) => {
					let parsed: { event_type?: string } | null = null;
					try { parsed = typeof data === 'string' ? JSON.parse(data) : null; } catch { parsed = null; }
					raw.push(parsed);
					// The server closes the journal only after every evaluation and export has settled, which can be minutes after training completed. The terminal event IS the end of the
					// training journal, so replay starts there instead of waiting for the socket to close (a long-idle socket was being reported as a disconnect).
					if (status === 'COLLECTING' && (parsed?.event_type === 'federation.completed' || parsed?.event_type === 'federation.error')) { socket?.close(); socket = null; build(); }
				},
				onStatus: (s) => { if (s === 'CLOSED_NORMAL') build(); else if (s === 'DISCONNECTED') { status = 'FAILED'; error = 'The journal stream disconnected before replay data was complete; no events are invented.'; } }
			}
		});
		socket.connect();
	}
	function step(d: number) { index = Math.min(snapshots.length - 1, Math.max(0, index + d)); }
	function firstWhere(test: (v: FederationView) => boolean, from = 0) { const i = snapshots.findIndex((v, n) => n >= from && test(v)); if (i >= 0) index = i; }
	function toggle() { if (playing) { stopPlay(); return; } playing = true; timer = setInterval(() => { if (index >= snapshots.length - 1) stopPlay(); else index += 1; }, 450); }
	onMount(() => { void store.api.studioRuns().then((r) => { runs = r.filter((x) => x.status === 'COMPLETED' && x.origin !== 'REPLAY'); }).catch((c) => { error = c instanceof Error ? c.message : String(c); }); return () => { stopPlay(); socket?.close(); }; });
</script>
<svelte:head><title>Federation journal replay | NHM</title></svelte:head>
<div class="eyebrow">NHM / RESEARCH OBSERVATORY / FEDERATION REPLAY</div>
<h1 tabindex="-1" use:focusHeading>Federation event-journal replay</h1>
<p class="tag" data-testid="replay-label">REPLAY — NO LOCAL TRAINING EXECUTING</p>
<p class="lead">Step through the persisted event journal of one owned, completed run (synthetic, live-monitored site or recorded hardware). The journal is read from sequence 0 and every step is derived by the same validated view model as the live page. Nothing trains, no candidate is created, and pace is presentation only.</p>
<label class="pick">Completed run <select bind:value={runId} onchange={load}><option value="">— choose an owned run —</option>{#each runs as r (r.run_id)}<option value={r.run_id}>{r.run_id} · {sourceName(r)} · {r.planned_rounds} rounds · {r.algorithm}</option>{/each}</select></label>
{#if status === 'COLLECTING'}<p class="dim" role="status">Reading the journal…</p>{/if}
{#if error}<p role="alert" class="err">{error}</p>{/if}
{#if status === 'READY' && view}
<section aria-label="Replay controls" data-testid="fed-replay-controls"><div class="controls"><button onclick={() => step(-1)} disabled={index === 0}>← Step back</button><button onclick={() => step(1)} disabled={index >= snapshots.length - 1}>Step forward →</button><button onclick={toggle}>{playing ? 'Pause' : 'Play'}</button>
	{#each jumpRounds as r (r)}<button onclick={() => firstWhere((v) => v.currentRound >= r)}>Jump to round {r}</button>{/each}
	<button onclick={() => firstWhere((v) => v.rounds.some((x) => x.aggregationMode !== null))}>Jump to aggregation</button><button onclick={() => firstWhere((v) => v.candidate !== null)}>Jump to candidate</button>
	<button onclick={() => firstWhere((v) => (v.clients.find((c) => c.clientId === selectedClient)?.state ?? 'IDLE') !== 'IDLE')}>Jump to selected client</button></div>
	<label class="scrub">Event {index + 1} of {snapshots.length} <input type="range" min="0" max={snapshots.length - 1} bind:value={index} aria-valuetext={`event ${index + 1} of ${snapshots.length}`} /></label>
	<p class="dim" data-testid="fed-replay-event">Latest journal entry: {view.timeline[view.timeline.length - 1]?.kind ?? '—'} — {view.timeline[view.timeline.length - 1]?.summary ?? ''}</p></section>
<section aria-label="Process" data-testid="fed-replay-state"><ProcessStepper {view} replay={true} /><div class="gap"></div><RoundProgress {view} plannedRounds={planned} />
	<h2>Clients at this event</h2><ClientGrid live={view.clients} round={view.currentRound} replay={true} clientIds={run?.client_ids} ownerBoundClientId={null} selected={selectedClient} onSelect={(id) => (selectedClient = id)} runDone={view.runStatus === 'COMPLETED'} {dataSource} />
	<h2>Candidate</h2><CandidateLifecycle {view} replay={true} /></section>
<p class="dim">Rejected updates are shown only if they appear in the journal. Rejection scenarios exercised in frozen engineering evidence (stale, duplicate, wrong-base, unknown-client) are not animated here unless they occurred in this run.</p>
{/if}
<p class="dim"><a href="/app/observatory/federation">← Federation observatory</a> · <a href="/app/federation/live">Live federation page</a></p>
<style>
	.eyebrow{color:#2bb8b0;font:10px 'JetBrains Mono',monospace;letter-spacing:.14em}h1{font:500 clamp(26px,4vw,40px) 'Space Grotesk',sans-serif;margin:8px 0}h2{font:500 16px 'Space Grotesk',sans-serif;margin:18px 0 8px}.tag{display:inline-block;margin:0 0 10px;border:1px solid rgba(148,163,184,.6);padding:6px 12px;color:#e5e7eb;font:12px 'JetBrains Mono',monospace;letter-spacing:.1em}.lead{max-width:860px;color:#a7b8c9;line-height:1.6}.dim,p{color:#94a3b8;font-size:13px;line-height:1.6;overflow-wrap:anywhere}.err{color:#fecdd3}a{color:#2bb8b0}.gap{height:10px}
	.pick,.scrub{display:grid;gap:4px;font:10px 'JetBrains Mono',monospace;color:#71829a;margin:8px 0}select,button{background:#0a0f1f;color:#e2e8f0;border:1px solid rgba(148,163,184,.35);padding:6px 10px;min-height:32px;font:12px 'JetBrains Mono',monospace}button:disabled{opacity:.4}.controls{display:flex;flex-wrap:wrap;gap:8px}.scrub input{width:100%;max-width:640px}
	a{display:inline-block;min-height:24px;line-height:24px}
	h1:focus{outline:none}
</style>
