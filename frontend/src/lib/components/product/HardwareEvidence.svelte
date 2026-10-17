<script lang="ts">
	import { onMount } from 'svelte';
	import Panel from '$lib/components/dashboard/Panel.svelte';
	import type { HardwareSession } from '$lib/product/api';
	import type { HardwareSessionTimeline } from '$lib/product/history/types';
	import { getProductStore } from '$lib/product/state.svelte';

	let { session }: { session: HardwareSession } = $props();
	const store = getProductStore();
	let timeline = $state<HardwareSessionTimeline | null>(null);
	let error = $state<string | null>(null);
	let scoring = $state(true);
	let filter = $state('ALL');

	const ready = $derived(session.status !== 'ACTIVE' && session.readings.length > 0);
	const inferences = $derived((timeline?.source_timeline ?? []).filter((x) => x.kind === 'INFERENCE'));
	const visible = $derived((timeline?.source_timeline ?? []).filter((x) => filter === 'ALL' || x.kind === filter));
	const field = (payload: unknown, key: string): unknown => (payload as Record<string, unknown>)[key];
	const counts = (key: string): [string, number][] => {
		const out = new Map<string, number>();
		for (const item of inferences) { const v = String(field(item.payload, key) ?? 'UNAVAILABLE'); out.set(v, (out.get(v) ?? 0) + 1); }
		return [...out.entries()];
	};
	const stats = (values: number[]): string => values.length ? `${Math.min(...values).toFixed(2)} / ${(values.reduce((a, b) => a + b, 0) / values.length).toFixed(2)} / ${Math.max(...values).toFixed(2)}` : 'Unavailable';
	const probabilities = $derived(inferences.map((x) => field(x.payload, 'raw_probability')).filter((v): v is number => typeof v === 'number'));
	const bpm = $derived(session.readings.map((r) => r.bpm).filter((v): v is number => v != null && v > 0));
	const spo2 = $derived(session.readings.map((r) => r.spo2).filter((v): v is number => v != null && v > 0));
	const seconds = (us: number) => `${(us / 1e6).toFixed(1)} s`;
	const pct = (v: unknown) => typeof v === 'number' ? v.toFixed(3) : '—';

	onMount(() => { void (async () => {
		if (!ready) { scoring = false; return; }
		try {
			// The released model scores the resampled windows in bounded batches (cached per window); the evidence fills in as they arrive.
			for (let batch = 0; batch < 200; batch++) {
				const value = await store.api.hardwareSessionTimeline(session.session_id, 24);
				timeline = value;
				if (value.complete) break;
			}
		} catch (cause) { error = cause instanceof Error ? cause.message : 'Scored evidence is unavailable'; } finally { scoring = false; }
	})(); });
</script>

{#if ready}
	<Panel eyebrow="02 / SCORED EVIDENCE" title="Model output on the recorded windows" note="EXPERIMENTAL · NOT DIAGNOSTIC">
		<div data-testid="hardware-evidence">
			{#if scoring}<p class="dim" role="status" data-testid="hardware-evidence-loading">Scoring recorded windows with the released model{timeline ? `: ${timeline.windows_scored} of ${timeline.windows_scored + timeline.windows_pending} usable windows` : '…'}</p>{/if}
			{#if error}<p class="error" role="alert">{error}</p>{/if}
			{#if timeline}
				<p class="dim">{timeline.label}. The recording is resampled to the model's 250 Hz window grid and scored by the unchanged released service; PPG context quality is an assumption (VALID while the device reports a pulse rate and SpO₂). Not validated on this signal chain.</p>
				<dl class="facts" data-testid="hardware-evidence-summary">
					<div><dt>10 s windows</dt><dd>{timeline.windows_total}</dd></div>
					<div><dt>Scored</dt><dd>{timeline.windows_scored}</dd></div>
					<div><dt>Rejected by the quality gate</dt><dd>{timeline.windows_unusable}</dd></div>
					<div><dt>Raw probability min / mean / max</dt><dd>{stats(probabilities)}</dd></div>
					<div><dt>Device BPM min / mean / max</dt><dd>{stats(bpm)}</dd></div>
					<div><dt>Device SpO₂ min / mean / max</dt><dd>{stats(spo2)} %</dd></div>
				</dl>
				<h3>Window monitoring-state labels</h3><ul data-testid="hardware-evidence-states">{#each counts('monitoring_state') as [state, n]}<li>{state}: {n}</li>{/each}</ul>
				<h3>Window ECG-quality labels</h3><ul>{#each counts('ecg_quality') as [quality, n]}<li>{quality}: {n}</li>{/each}</ul>
				<p class="dim">Counts are over scored windows. Device BPM is the firmware's mock value and device SpO₂ is an unverified estimate; both are shown as reported.</p>
			{/if}
		</div>
	</Panel>
	{#if timeline && inferences.length}
		<Panel eyebrow="03 / WINDOW RESULTS" title="Per-window output" note="RESEARCH TECHNICAL METADATA">
			<div class="scroll"><table data-testid="hardware-window-results"><caption class="sr">Model output for each scored 10 s window of this recording</caption>
				<thead><tr><th scope="col">Window end</th><th scope="col">Monitoring state</th><th scope="col">ECG quality</th><th scope="col">Raw prob.</th><th scope="col">Calibrated prob.</th></tr></thead>
				<tbody>{#each inferences as item (item.sequence_index)}<tr><td>{seconds(item.source_timestamp_us)}</td><td>{field(item.payload, 'monitoring_state')}</td><td>{field(item.payload, 'ecg_quality')}</td><td>{pct(field(item.payload, 'raw_probability'))}</td><td>{pct(field(item.payload, 'source_domain_calibrated_probability'))}</td></tr>{/each}</tbody></table></div>
			<p class="dim">Probabilities are research technical metadata, not clinical or diagnostic probabilities.</p>
		</Panel>
		<Panel eyebrow="04 / SOURCE DOMAIN" title="Source-timeline evidence" note={timeline.timeline_version}>
			<p>Derived from the recording's own readings, measured from its first reading. State changes come from consecutive window results; nothing here is a persisted state machine.</p>
			<p class="count">{timeline.source_timeline.length} source events · {visible.length} shown</p>
			<label for="hw-kind-filter">Filter event kind</label><select id="hw-kind-filter" bind:value={filter}>
				<option value="ALL">All kinds</option><option value="INFERENCE">Inference</option><option value="MONITORING_STATE_CHANGE">Monitoring state change</option>
				<option value="QUALITY_CHANGE">Quality change</option><option value="CONTEXT_SNAPSHOT">Context snapshot</option></select>
			<ol class="events">{#each visible as item (item.sequence_index)}<li><strong>{item.kind}</strong> · sequence {item.sequence_index} · source {seconds(item.source_timestamp_us)}
				<details><summary>TECHNICAL EVENT DETAILS</summary><pre>{JSON.stringify(item.payload, null, 2)}</pre></details></li>{/each}</ol>
		</Panel>
	{/if}
{/if}
<style>
	.facts { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 8px; margin: 10px 0; } .facts div { border: 1px solid rgba(148,163,184,.16); padding: 8px 10px; } .facts dt { font: 10px 'JetBrains Mono', monospace; color: #71829a; letter-spacing: .08em; text-transform: uppercase; } .facts dd { margin: 3px 0 0; font-size: 14px; }
	h3 { font: 500 13px Inter, sans-serif; margin: 12px 0 4px; } ul, ol.events { margin: 0; padding-left: 18px; display: grid; gap: 4px; font-size: 12px; } ol.events { max-height: 420px; overflow: auto; } pre { white-space: pre-wrap; overflow-wrap: anywhere; font-size: 11px; }
	.scroll { overflow: auto; max-height: 360px; } table { width: 100%; border-collapse: collapse; font-size: 12px; } th, td { text-align: left; padding: 5px 8px; border-bottom: 1px solid rgba(148,163,184,.12); } th { font: 10px 'JetBrains Mono', monospace; color: #71829a; letter-spacing: .08em; text-transform: uppercase; position: sticky; top: 0; background: #0a111c; }
	.dim { color: #8696ad; font-size: 12px; } .error { color: #fca5a5; } .count { font: 11px 'JetBrains Mono', monospace; color: #8696ad; } .sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
</style>
