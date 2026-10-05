<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import Panel from '$lib/components/dashboard/Panel.svelte';
	import { getProductStore } from '$lib/product/state.svelte';
	import type { MonitoringSession } from '$lib/product/types';
	import type { SessionSummary, SessionTimeline, SourceKind, WaveformPreview } from '$lib/product/history/types';

	const product = getProductStore();
	let session = $state<MonitoringSession | null>(null);
	let summary = $state<SessionSummary | null>(null);
	let timeline = $state<SessionTimeline | null>(null);
	let error = $state<string | null>(null);
	let loading = $state(true);
	let filter = $state<SourceKind | 'ALL'>('ALL');
	const visible = $derived(timeline?.source_timeline.filter((x) => filter === 'ALL' || x.kind === filter) ?? []);
	const when = (us: number | null) => us === null ? '—' : new Date(us / 1000).toLocaleString();
	const metric = (v: number | null) => v === null ? 'Unavailable' : v.toFixed(2);

	onMount(() => { void (async () => {
		try {
			const id = page.params.session_id;
			if (!id) throw new Error('Session ID is missing');
			session = await product.api.session(id);
			const work: Promise<unknown>[] = [product.api.sessionTimeline(id).then((v) => { timeline = v; })];
			if (session.state === 'COMPLETED')
				work.push(product.api.sessionSummary(id).then((v) => { summary = v; }));
			await Promise.all(work);
		} catch (cause) {
			error = cause instanceof Error ? cause.message : 'Malformed or unavailable history evidence';
		} finally { loading = false; }
	})(); });

	// Each null source bucket closes the current polyline. It is never zero-filled or interpolated.
	function paths(preview: WaveformPreview): string[] {
		const values = preview.points.filter((v): v is number => v !== null);
		if (values.length === 0) return [];
		const low = Math.min(...values), high = Math.max(...values), span = Math.max(1, high - low);
		const output: string[] = []; let path = '';
		preview.points.forEach((value, i) => {
			if (value === null) { if (path) output.push(path); path = ''; return; }
			const x = preview.points.length < 2 ? 0 : (i / (preview.points.length - 1)) * 1000;
			const y = 155 - ((value - low) / span) * 130;
			path += `${path ? ' L' : 'M'}${x.toFixed(2)} ${y.toFixed(2)}`;
		});
		if (path) output.push(path);
		return output;
	}
</script>

<svelte:head><title>Session evidence | NHM</title></svelte:head>
<div class="evidence">
	<p class="eyebrow"><a href="/app/history">HISTORY</a> / SESSION EVIDENCE</p>
	<h1>Session evidence</h1>
	{#if loading}<p role="status">Loading persisted evidence…</p>{/if}
	{#if error}<p class="error" role="alert">{error}</p>{/if}
	{#if session}
		<Panel eyebrow="01 / SESSION" title={session.session_id} note={session.state}>
			<p>Research/engineering monitoring history. Runtime identity was fixed at session creation.</p>
			<dl class="facts"><div><dt>State</dt><dd>{session.state}</dd></div><div><dt>Device adapter</dt><dd>{session.device_adapter_type}</dd></div>
				<div><dt>Scenario provenance</dt><dd>{session.simulation_provenance?.scenario_id ?? 'Unavailable'}</dd></div>
				<div><dt>Created</dt><dd>{when(session.created_at_us)}</dd></div><div><dt>Started</dt><dd>{when(session.started_at_us)}</dd></div>
				<div><dt>Ended</dt><dd>{when(session.ended_at_us)}</dd></div>
				<div><dt>Software system</dt><dd>{session.runtime.software_system_id}</dd></div>
				<div><dt>Model</dt><dd>{session.runtime.model_id}</dd></div><div><dt>Calibration</dt><dd>{session.runtime.calibration_id}</dd></div>
				<div><dt>Preprocess</dt><dd>{session.runtime.preprocess_id}</dd></div><div><dt>Alert policy binding</dt><dd>{session.runtime.alert_policy_binding_id}</dd></div></dl>
		</Panel>
		{#if session.state !== 'COMPLETED'}
			<p class="notice" role="status">PARTIAL / FAILED SESSION EVIDENCE. A completed-session summary is unavailable for {session.state} sessions.</p>
		{:else if summary}
			<Panel eyebrow="02 / COMPLETED" title="Persisted session summary" note={summary.summary_version}>
				<div class="facts"><div><dt>Product-clock duration</dt><dd>{summary.duration_ms} ms</dd></div>
					<div><dt>Windows inferred</dt><dd>{summary.windows_inferred} persisted inference events</dd></div>
					<div><dt>Disconnects</dt><dd>{summary.disconnect_count}</dd></div><div><dt>Reconnects</dt><dd>{summary.reconnect_count}</dd></div>
					<div><dt>ECG HR min / mean / max</dt><dd>{metric(summary.hr_min)} / {metric(summary.hr_mean)} / {metric(summary.hr_max)} bpm</dd></div>
					<div><dt>Valid SpO₂ min / mean / max</dt><dd>{metric(summary.spo2_min)} / {metric(summary.spo2_mean)} / {metric(summary.spo2_max)} %</dd></div></div>
				<h2>Inferred-window monitoring-state counts</h2><ul>{#each Object.entries(summary.state_counts) as [state, count]}<li>{state}: {count}</li>{/each}</ul>
				<h2>Inferred-window ECG-quality counts</h2><ul>{#each Object.entries(summary.quality_counts) as [quality, count]}<li>{quality}: {count}</li>{/each}</ul>
				<p>All counts above are based on PERSISTED INFERENCE EVENTS. Windows without inference, including some UNUSABLE windows, are not counted as inferred windows.</p>
				<p>Quality changes are persisted change-only. These summary quality counts are based on persisted inference events, not every source window.</p>
				<p>Duration uses the PRODUCT LIFECYCLE CLOCK, not physiological source time. Accelerated simulation can make these durations very different.</p>
			</Panel>
		{/if}
		{#if timeline}
			<Panel eyebrow="03 / SOURCE DOMAIN" title="Source-timeline evidence" note={timeline.timeline_version}>
				<p>Persisted evidence view, not a byte-for-byte WebSocket replay. Source timestamps are not product-clock timestamps.</p>
				<label for="kind-filter">Filter event kind</label><select id="kind-filter" bind:value={filter}>
					<option value="ALL">All kinds</option><option value="INFERENCE">Inference</option>
					<option value="MONITORING_STATE_CHANGE">Monitoring state change</option>
					<option value="QUALITY_CHANGE">Quality change</option><option value="CONTEXT_SNAPSHOT">Context snapshot</option>
				</select>
				<p>Inference probabilities below are RESEARCH TECHNICAL METADATA, not clinical or diagnostic probabilities. Quality-change rows are change-only events.</p>
				<ol class="events">{#each visible as item}<li><strong>{item.kind}</strong> · sequence {item.sequence_index} · source {item.source_timestamp_us} µs
					<pre>{JSON.stringify(item.payload, null, 2)}</pre></li>{/each}</ol>
			</Panel>
			<Panel eyebrow="04 / PRODUCT CLOCK" title="Device lifecycle" note="SEPARATE TIME DOMAIN">
				<p>{timeline.time_domain_explanation} Device events below use PRODUCT_CLOCK; source events above use SOURCE_TIMELINE.</p>
				<ol class="events">{#each timeline.device_lifecycle as item}<li>{item.event_type} · {item.device_state} · {when(item.at_us)} · {item.reason_code ?? 'No reason code'}</li>{/each}</ol>
			</Panel>
			<Panel eyebrow="05 / PREVIEW" title="Bounded decimated ECG preview" note="NOT RAW STREAM STORAGE">
				{#each timeline.waveform_previews as preview}<div><p>{preview.channel} · {preview.point_count} points · {preview.source_rate_hz} Hz source · decimation {preview.decimation_factor}×</p>
					<svg viewBox="0 0 1000 180" role="img" aria-label={`Bounded decimated ${preview.channel} preview; missing source buckets are gaps`} preserveAspectRatio="none">
						{#each paths(preview) as path}<path d={path} fill="none" stroke="#2bb8b0" stroke-width="2" vector-effect="non-scaling-stroke" />{/each}
					</svg><p>Null points mark missing delivered source buckets; no gaps are interpolated.</p></div>{/each}
				{#if timeline.waveform_previews.length === 0}<p>No persisted preview available.</p>{/if}
			</Panel>
		{/if}
	{/if}
</div>
<style>
	.evidence { display:grid; gap:16px; min-width:0; max-width:100%; } .eyebrow{font:11px 'JetBrains Mono',monospace;color:#2bb8b0;letter-spacing:.12em} h1{font:500 clamp(26px,4vw,40px) 'Space Grotesk',sans-serif;margin:0} h2{font-size:15px;margin:20px 0 8px} p,li,dd{color:#a7b8c9;line-height:1.55;font-size:13px;overflow-wrap:anywhere} a{color:#2bb8b0}.error{color:#fecdd3}.notice{padding:12px;border:1px solid #fbbf24;color:#fbbf24}.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,220px),1fr));gap:12px}.facts div{min-width:0}dt{font:10px 'JetBrains Mono',monospace;color:#71829a}dd{margin:4px 0 0}.events{max-height:500px;overflow:auto;padding-left:20px}.events li{padding:8px;border-bottom:1px solid var(--nhm-border)}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px}select{margin:8px;padding:8px;background:#0f172a;color:#dce9e8;border:1px solid #64748b}select:focus-visible,a:focus-visible{outline:2px solid #fbbf24;outline-offset:3px}svg{display:block;width:100%;height:180px;background:#07101d;border:1px solid var(--nhm-border)}
</style>
