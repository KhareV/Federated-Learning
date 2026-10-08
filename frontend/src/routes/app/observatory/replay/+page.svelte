<script lang="ts">
	import { onMount } from 'svelte';
	import { getProductStore } from '$lib/product/state.svelte';
	import type { SessionTimeline, SourceTimelineItem } from '$lib/product/history/types';
	const store = getProductStore();
	let sessionId = $state('');
	let timeline = $state<SessionTimeline | null>(null);
	let error = $state<string | null>(null);
	let loading = $state(false);
	let index = $state(0);
	let playing = $state(false);
	let timer: ReturnType<typeof setInterval> | null = null;
	const done = $derived(store.sessions.filter((s) => s.state === 'COMPLETED'));
	const items = $derived((timeline?.source_timeline ?? []).slice().sort((a, b) => a.source_timestamp_us - b.source_timestamp_us || a.sequence_index - b.sequence_index));
	const inferences = $derived(items.filter((i) => i.kind === 'INFERENCE'));
	const changes = $derived(items.filter((i) => i.kind === 'MONITORING_STATE_CHANGE'));
	const cursor = $derived(items[Math.min(index, Math.max(0, items.length - 1))] ?? null);
	const upto = $derived(items.slice(0, index + 1));
	const lastInference = $derived([...upto].reverse().find((i) => i.kind === 'INFERENCE') ?? null);
	const lastState = $derived([...upto].reverse().find((i) => i.kind === 'MONITORING_STATE_CHANGE') ?? null);
	const lastQuality = $derived([...upto].reverse().find((i) => i.kind === 'QUALITY_CHANGE') ?? null);
	const lastContext = $derived([...upto].reverse().find((i) => i.kind === 'CONTEXT_SNAPSHOT') ?? null);
	const t0 = $derived(items[0]?.source_timestamp_us ?? 0);
	const span = $derived(Math.max(1, (items[items.length - 1]?.source_timestamp_us ?? 1) - t0));
	const p = (item: SourceTimelineItem | null, key: string): unknown => (item?.payload as Record<string, unknown> | undefined)?.[key];
	const num = (v: unknown) => (typeof v === 'number' ? v : null);
	const fmt = (v: number | null, d = 4) => (v === null ? '—' : v.toFixed(d));
	const seconds = (item: SourceTimelineItem | null) => (item ? ((item.source_timestamp_us - t0) / 1e6).toFixed(1) : '—');
	const series = $derived(inferences.map((i) => ({ x: ((i.source_timestamp_us - t0) / span) * 100, y: num(p(i, 'source_domain_calibrated_probability')), thr: num(p(i, 'threshold')), state: String(p(i, 'monitoring_state') ?? ''), quality: String(p(i, 'ecg_quality') ?? '') })));
	const threshold = $derived(series.find((s) => s.thr !== null)?.thr ?? null);
	async function load() {
		stop(); timeline = null; error = null; index = 0;
		if (!sessionId) return;
		loading = true;
		try { timeline = await store.api.sessionTimeline(sessionId); } catch (c) { error = c instanceof Error ? c.message : String(c); } finally { loading = false; }
	}
	function step(d: number) { index = Math.min(items.length - 1, Math.max(0, index + d)); }
	function jump(kind: string) { const i = items.findIndex((x, n) => n > index && x.kind === kind); if (i >= 0) index = i; }
	function stop() { playing = false; if (timer) { clearInterval(timer); timer = null; } }
	function toggle() {
		if (playing) { stop(); return; }
		playing = true;
		timer = setInterval(() => { if (index >= items.length - 1) stop(); else index += 1; }, 700);
	}
	onMount(() => { void store.loadSessions(); return stop; });
</script>
<svelte:head><title>Session replay and policy trace | NHM</title></svelte:head>
<div class="eyebrow">NHM / RESEARCH OBSERVATORY / SESSION REPLAY</div>
<h1>Session replay and monitoring-policy trace</h1>
<p class="lead">Step through the <b>persisted</b> evidence of one owned, completed session in source time. Nothing is re-run: each step reveals records that were stored by the monitoring runtime (quality, calibrated score against the frozen threshold, policy state and its reason codes). Playback speed is presentation only, not real-time acquisition.</p>
<p class="tag">PERSISTED EVIDENCE REPLAY · NO NEW INFERENCE</p>
<label class="pick">Completed session <select bind:value={sessionId} onchange={load}><option value="">— choose an owned session —</option>{#each done as s (s.session_id)}<option value={s.session_id}>{s.session_id}</option>{/each}</select></label>
{#if done.length === 0}<p class="dim">No completed session is available. Run one from <a href="/app/monitoring">Monitor</a>.</p>{/if}
{#if error}<p role="alert" class="err">{error}</p>{/if}
{#if loading}<p class="dim" role="status">Loading persisted timeline…</p>{/if}
{#if timeline && items.length}
<section aria-label="Replay controls" data-testid="replay-controls"><div class="controls"><button onclick={() => step(-1)} disabled={index === 0}>← Step back</button><button onclick={() => step(1)} disabled={index >= items.length - 1}>Step forward →</button><button onclick={toggle}>{playing ? 'Pause' : 'Play'}</button><button onclick={() => jump('INFERENCE')}>Next inference</button><button onclick={() => jump('MONITORING_STATE_CHANGE')}>Next state change</button></div>
	<label class="scrub">Record {index + 1} of {items.length} · source time {seconds(cursor)} s <input type="range" min="0" max={items.length - 1} bind:value={index} aria-valuetext={`record ${index + 1} of ${items.length}`} /></label></section>
<section aria-label="Pipeline at this point" data-testid="replay-state"><h2>At source time {seconds(cursor)} s</h2>
	<div class="lanes"><article><span>QUALITY (signal usability)</span><b>{String(p(lastInference, 'ecg_quality') ?? p(lastQuality, 'ecg_quality') ?? 'not yet recorded')}</b><small>An engineering gate, not a diagnosis.</small></article>
		<article><span>MODEL OUTPUT (research metadata)</span><b>calibrated {fmt(num(p(lastInference, 'source_domain_calibrated_probability')))}</b><small>raw {fmt(num(p(lastInference, 'raw_probability')))} · frozen threshold {fmt(num(p(lastInference, 'threshold')))} · {String(p(lastInference, 'model_id') ?? '—')}</small></article>
		<article><span>POLICY STATE</span><b>{String(p(lastInference, 'monitoring_state') ?? p(lastState, 'monitoring_state') ?? 'not yet recorded')}</b><small>{lastState ? `last change: ${String(p(lastState, 'previous_state') ?? 'start')} → ${String(p(lastState, 'monitoring_state'))} (${String(p(lastState, 'reason_code') ?? 'no reason code')})` : 'no state change recorded yet'}</small></article>
		<article><span>CONTEXT (PPG / SpO₂, not a model signal)</span><b>{lastContext ? (p(lastContext, 'context_available') ? 'available' : 'not available') : 'not yet recorded'}</b><small>{lastContext ? `ECG HR ${fmt(num(p(lastContext, 'hr_ecg_bpm')), 1)} · PPG pulse ${fmt(num(p(lastContext, 'pr_ppg_bpm')), 1)} · SpO₂ valid ${String(p(lastContext, 'spo2_valid'))}` : ''}</small></article></div></section>
<section aria-label="Calibrated score against threshold" data-testid="replay-chart"><h2>Calibrated score vs the frozen threshold · all persisted windows</h2>
	<svg viewBox="0 0 100 52" preserveAspectRatio="none" role="img" aria-label="Calibrated score per window with the frozen threshold line and the replay cursor"><rect x="0" y="0" width="100" height="50" class="frame" />
		{#if threshold !== null}<path d={`M0,${50 - threshold * 50} L100,${50 - threshold * 50}`} class="thr" />{/if}
		{#each series as s}{#if s.y !== null}<circle cx={s.x} cy={50 - s.y * 50} r="0.9" class={`pt s-${s.quality.toLowerCase()}`} />{/if}{/each}
		<path d={`M${((( cursor?.source_timestamp_us ?? t0) - t0) / span) * 100},0 L${(((cursor?.source_timestamp_us ?? t0) - t0) / span) * 100},50`} class="cur" /></svg>
	<p class="dim">Dots are persisted windows (shape-free; quality is stated in the panel above, not by colour alone). The dashed line is the frozen CAL_V2 threshold {fmt(threshold, 4)}. A score above the line is not by itself an alert: the monitoring policy also depends on quality and persisted state, and only the recorded state changes below are authoritative.</p></section>
<section aria-label="State transitions" data-testid="replay-transitions"><h2>Recorded policy state transitions</h2>
	{#if changes.length === 0}<p class="dim">No state change was persisted for this session.</p>{:else}<ol class="tr">{#each changes as c (c.sequence_index)}<li class:now={items.indexOf(c) <= index}><b>{seconds(c)} s</b> {String(p(c, 'previous_state') ?? 'start')} → <b>{String(p(c, 'monitoring_state'))}</b> <small>({String(p(c, 'reason_code') ?? 'no reason code')})</small></li>{/each}</ol>{/if}</section>
<p class="dim">{timeline.time_domain_explanation} Source: persisted session timeline ({timeline.claim_boundary}). Replay of raw ECG stages is available only for armed live captures or deterministic reconstructions in the <a href="/app/observatory">signal journey</a>; this page does not claim intermediate arrays that were not stored.</p>
{/if}
<p class="dim"><a href="/app/observatory">← Observatory</a> · <a href="/app/history">History</a></p>
<style>
	.eyebrow{color:#2bb8b0;font:10px 'JetBrains Mono',monospace;letter-spacing:.14em}h1{font:500 clamp(26px,4vw,40px) 'Space Grotesk',sans-serif;margin:8px 0}h2{font:500 18px 'Space Grotesk',sans-serif;margin:22px 0 8px}.lead{max-width:860px;color:#a7b8c9;line-height:1.6}.tag{display:inline-block;margin:0 0 10px;border:1px solid rgba(167,139,250,.5);padding:5px 10px;color:#c4b5fd;font:11px 'JetBrains Mono',monospace;letter-spacing:.1em}.dim,small,li,p{color:#94a3b8;font-size:13px;line-height:1.6;overflow-wrap:anywhere}.err{color:#fecdd3}a{color:#2bb8b0}
	.pick,.scrub{display:grid;gap:4px;font:10px 'JetBrains Mono',monospace;color:#71829a;margin:8px 0}select,button{background:#0a0f1f;color:#e2e8f0;border:1px solid rgba(148,163,184,.35);padding:6px 10px;min-height:32px;font:12px 'JetBrains Mono',monospace}button:disabled{opacity:.4}.controls{display:flex;flex-wrap:wrap;gap:8px}.scrub input{width:100%;max-width:640px}
	.lanes{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,230px),1fr));gap:10px}.lanes article{border:1px solid rgba(148,163,184,.25);padding:10px 12px;display:grid;gap:4px;min-width:0}.lanes span{font:10px 'JetBrains Mono',monospace;letter-spacing:.1em;color:#71829a}.lanes b{font:500 16px 'Space Grotesk',sans-serif;color:#e2e8f0;overflow-wrap:anywhere}
	svg{width:100%;height:200px;background:#050a15}.frame{fill:none;stroke:rgba(148,163,184,.35)}.thr{stroke:#fbbf24;stroke-dasharray:2 2;fill:none;vector-effect:non-scaling-stroke}.cur{stroke:#a78bfa;fill:none;stroke-width:1.5;vector-effect:non-scaling-stroke}.pt{fill:#2bb8b0}.pt.s-degraded{fill:#fbbf24}.pt.s-unusable{fill:#f87171}.tr{padding-left:18px;display:grid;gap:4px}.tr li{opacity:.55}.tr li.now{opacity:1;color:#e2e8f0}
	a{display:inline-block;min-height:24px;line-height:24px}
</style>
