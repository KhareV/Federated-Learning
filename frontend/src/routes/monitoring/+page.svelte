<script lang="ts">
	// T033 canonical NHM research dashboard. Binds ONLY to the frozen API_RUNTIME_V1 contract
	// (POST /v1/infer-window) via the typed client in $lib/api/nhm-v1.ts. No inference,
	// calibration, threshold comparison, K=2/M=2 debouncing, cooldown, or fusion logic is
	// reimplemented here -- every monitoring_state and probability value comes directly from
	// the API response (see $lib/dashboard/session.svelte.ts and state-presentation.ts).
	import { page } from '$app/state';
	import Panel from '$lib/components/dashboard/Panel.svelte';
	import MetricTile from '$lib/components/dashboard/MetricTile.svelte';
	import MultiLine from '$lib/components/dashboard/MultiLine.svelte';
	import { nhmApi, ECG_WINDOW_SAMPLE_COUNT, ECG_WINDOW_TARGET_HZ, ECG_WINDOW_SECONDS } from '$lib/api/nhm-v1';
	import type { InferWindowRequest } from '$lib/api/nhm-v1';
	import { createDashboardSession } from '$lib/dashboard/session.svelte';
	import { STATE_PRESENTATION, httpErrorPresentation } from '$lib/dashboard/state-presentation';
	import { flatDemoWindow } from '$lib/dashboard/demo-window';
	import { loadReplayBundle, runCanonicalRecordedReplay, type ReplayBundleEvent } from '$lib/dashboard/replay';

	function newSessionId(): string {
		return `nhm-dashboard-${Math.random().toString(36).slice(2, 10)}`;
	}

	let session = $state(createDashboardSession(newSessionId()));
	let sending = $state(false);
	let nextTimestampUs = $state(Date.now() * 1000);

	// RECORDED REPLAY mode: /monitoring?mode=replay&replay=PUBLIC_ECG_REPLAY_V1[&speed=1]
	// This is a recorded public-ECG stream (never live hardware, never a real-time feed), fed through
	// the exact same real typed API client and dashboard session as the manual demo control
	// above -- see $lib/dashboard/replay.ts::runCanonicalRecordedReplay. speed=1 paces at the
	// recorded 5-second cadence for a human demo; any other value (default) replays immediately
	// for fast/test use. Pacing is presentation-only and never alters request timestamps.
	const replayMode = $derived(page.url.searchParams.get('mode') === 'replay');
	const replayId = $derived(page.url.searchParams.get('replay') ?? 'PUBLIC_ECG_REPLAY_V1');
	const replaySpeed = $derived(page.url.searchParams.get('speed') === '1' ? 5000 : 0);
	let replayRunning = $state(false);
	let replayCompletedCount = $state(0);
	let replayTotalCount = $state(0);
	let replayError = $state('');

	async function startRecordedReplay() {
		if (replayRunning) return;
		replayRunning = true;
		replayError = '';
		replayCompletedCount = 0;
		session = createDashboardSession(`nhm-replay-${replayId}-${Math.random().toString(36).slice(2, 8)}`);
		try {
			const bundle = await loadReplayBundle(replayId);
			replayTotalCount = bundle.events.length;
			await runCanonicalRecordedReplay(session, bundle, {
				stepDelayMs: replaySpeed,
				onEvent: (_event: ReplayBundleEvent, index: number) => {
					replayCompletedCount = index + 1;
				}
			});
		} catch (cause) {
			replayError = cause instanceof Error ? cause.message : 'Recorded replay failed.';
		} finally {
			replayRunning = false;
		}
	}

	$effect(() => {
		if (replayMode) void startRecordedReplay();
	});

	async function sendNextWindow() {
		if (sending || replayMode) return;
		sending = true;
		const timestamp_us = nextTimestampUs;
		nextTimestampUs += 5_000_000; // matches configs/alert_policy_v1.yaml window_cadence_seconds
		const request: InferWindowRequest = {
			contract_version: 'API_SCHEMA_V1',
			session_id: session.sessionId,
			timestamp_us,
			ecg: { samples: flatDemoWindow(), target_hz: ECG_WINDOW_TARGET_HZ, window_seconds: ECG_WINDOW_SECONDS },
			ecg_quality: 'VALID',
			ppg_context: null,
			model_id: 'MODEL_V1'
		};
		try {
			const result = await nhmApi.inferWindow(request);
			if (result.kind === 'success') session.applySuccessfulWindow(request, result.data);
			else if (result.kind === 'request_error') session.applyRequestError(result.error);
			else if (result.kind === 'signal_window_error') session.applySignalWindowError(result.error);
			else if (result.kind === 'server_error') session.applyServerError(result.error);
			else session.applyTransportError(result.message);
		} finally {
			sending = false;
		}
	}

	function startNewSession() {
		session = createDashboardSession(newSessionId());
		nextTimestampUs = Date.now() * 1000;
	}

	const outcome = $derived(session.latestOutcome);

	const presentation = $derived.by(() => {
		if (!outcome) {
			return { title: 'Awaiting first window', text: 'Send a research window to begin.', tone: 'neutral' as const };
		}
		if (outcome.kind === 'success') {
			return STATE_PRESENTATION[outcome.response.monitoring_state];
		}
		if (outcome.kind === 'transport_error') {
			return { title: 'Network / transport failure', text: outcome.message, tone: 'technical-error' as const };
		}
		return httpErrorPresentation(outcome.status, outcome.error.message);
	});

	const successResponse = $derived(outcome?.kind === 'success' ? outcome.response : null);

	const probabilityHistorySeries = $derived.by(() => {
		const successes = session.history.filter((point) => point.kind === 'success');
		return [
			{
				name: 'Source-domain calibrated probability',
				color: '#2bb8b0',
				values: successes.map((point) => point.source_domain_calibrated_probability ?? 0)
			},
			{ name: 'Raw probability', color: '#64748b', values: successes.map((point) => point.raw_probability ?? 0) }
		];
	});

	const gapEvents = $derived(session.history.filter((point) => point.kind === 'gap'));
</script>

<svelte:head>
	<title>NHM Research Dashboard</title>
	<meta name="description" content="NHM research-prototype monitoring dashboard: frozen API_RUNTIME_V1 contract, five canonical monitoring states, no diagnosis claim." />
</svelte:head>

<main class="nhm-dashboard">
	<header class="dash-top">
		<div>
			<span class="eyebrow">NHM RESEARCH DASHBOARD -- RESEARCH PROTOTYPE</span>
			<h1>Monitoring, as the API decided it.</h1>
			<p class="lede">This dashboard presents the frozen NHM research-runtime API (POST /v1/infer-window): signal quality, debounced monitoring state, technical/calibration provenance, and a clearly labeled research-only probability history. It is not a diagnosis, not a medical device, and not validated on real wearable hardware.</p>
		</div>
		<div class="session-box">
			{#if replayMode}
				<span class="replay-badge">RECORDED REPLAY -- {replayId}</span>
			{:else}
				<span>SESSION</span>
			{/if}
			<strong>{session.sessionId}</strong>
			{#if replayMode}
				<span>WINDOWS: {replayCompletedCount} / {replayTotalCount || '--'}</span>
				{#if replayError}<span class="replay-error">{replayError}</span>{/if}
				<small>Recorded public-ECG stream (MIT-BIH TRAIN, PUBLIC_ECG_REPLAY_V1) replayed through the real typed API client and this same dashboard session -- not live hardware, not a real-time feed. Every monitoring_state/probability shown is the real API response for that recorded window, not a prerecorded outcome.</small>
			{:else}
				<span>WINDOWS SENT: {session.requestCount}</span>
				<div class="session-actions">
					<button type="button" onclick={sendNextWindow} disabled={sending}>
						{sending ? 'SENDING…' : 'SEND NEXT RESEARCH WINDOW'}
					</button>
					<button type="button" class="ghost" onclick={startNewSession}>NEW SESSION</button>
				</div>
				<small>No live wearable hardware is connected (WEARABLE_V1 pending). Each window is a deterministic placeholder sent to the real API -- see $lib/dashboard/demo-window.ts, or <a href="/monitoring?mode=replay&replay=PUBLIC_ECG_REPLAY_V1">play back a recorded public-ECG stream</a>.</small>
			{/if}
		</div>
	</header>

	<section class="panel-grid">
		<Panel eyebrow="01 / LIVE WAVEFORMS" title="ECG model-ready window">
			{#if session.latestEcgWindow}
				<p class="panel-note">Most recent accepted {ECG_WINDOW_SAMPLE_COUNT}-sample / {ECG_WINDOW_TARGET_HZ} Hz MODEL_V1 interface window (10 seconds). This is the preprocessed model input, not raw hardware ADC output.</p>
				<MultiLine
					series={[{ name: 'ECG (model input)', color: '#2bb8b0', values: session.latestEcgWindow }]}
					height={160}
					yMin={Math.min(...session.latestEcgWindow, -1)}
					yMax={Math.max(...session.latestEcgWindow, 1)}
				/>
			{:else}
				<p class="panel-note">No window accepted yet. Send a research window to populate this panel.</p>
			{/if}
			<p class="panel-footnote">PPG waveform unavailable in the current API contract (API_SCHEMA_V1 returns PPG-derived context only, not a raw PPG waveform).</p>
		</Panel>

		<Panel eyebrow="02 / SIGNAL QUALITY" title="Signal quality">
			{#if successResponse}
				<div class="quality-grid">
					<MetricTile label="ECG quality" value={successResponse.ecg_quality} tone={successResponse.ecg_quality === 'VALID' ? 'teal' : 'amber'} />
					<MetricTile label="PPG quality" value={successResponse.context?.ppg_quality ?? 'UNAVAILABLE'} tone="cyan" />
					<MetricTile label="SpO2" value={successResponse.context?.spo2_valid ? `${successResponse.context?.spo2_pct ?? '--'}%` : 'UNAVAILABLE'} tone="cyan" />
					<MetricTile label="ECG HR" value={successResponse.context?.hr_ecg_bpm != null ? successResponse.context.hr_ecg_bpm.toFixed(1) : '--'} unit="bpm" tone="teal" />
					<MetricTile label="PPG pulse rate" value={successResponse.context?.pr_ppg_bpm != null ? successResponse.context.pr_ppg_bpm.toFixed(1) : '--'} unit="bpm" tone="cyan" />
					<MetricTile label="Context available" value={successResponse.context?.context_available ? 'YES' : 'NO'} tone={successResponse.context?.context_available ? 'teal' : 'amber'} />
				</div>
				{#if successResponse.context?.quality_warning}
					<p class="quality-warning-badge">QUALITY_WARNING -- {successResponse.context.quality_warning_reasons.join(', ')} (metadata annotation, not a sixth monitoring state)</p>
				{/if}
			{:else}
				<p class="panel-note">No successful window yet to report signal quality for.</p>
			{/if}
		</Panel>

		<Panel eyebrow="03 / CURRENT MONITORING STATE" title={presentation.title} note="Authoritative: from response.monitoring_state, never recomputed locally.">
			<p class="state-tone state-tone--{presentation.tone}" role="status" aria-live="polite">{presentation.text}</p>
			{#if outcome?.kind === 'success'}
				<div class="state-meta">
					<span>STATE: {outcome.response.monitoring_state}</span>
					<span>ECG QUALITY: {outcome.response.ecg_quality}</span>
				</div>
			{:else if outcome && outcome.kind !== 'transport_error'}
				<div class="state-meta"><span>HTTP {outcome.status}</span></div>
			{/if}
		</Panel>

		<Panel eyebrow="04 / TECHNICAL METADATA" title="Provenance">
			{#if successResponse}
				<div class="meta-grid">
					<MetricTile label="model_id" value={successResponse.model_id ?? '--'} />
					<MetricTile label="target" value={successResponse.target} />
					<MetricTile label="preprocess_version" value={successResponse.preprocess_version ?? '--'} />
					<MetricTile label="contract_version" value={successResponse.contract_version} />
					<MetricTile label="alert_policy_id" value={successResponse.alert_policy_id ?? '--'} />
					<MetricTile label="calibration_id" value={successResponse.calibration_id ?? '--'} />
					<MetricTile label="threshold" value={successResponse.threshold != null ? successResponse.threshold.toFixed(4) : '--'} />
					<MetricTile label="timestamp_us" value={successResponse.timestamp_us} />
					<MetricTile label="latency_ms" value={successResponse.latency_ms != null ? successResponse.latency_ms.toFixed(2) : '--'} />
				</div>
			{:else}
				<p class="panel-note">No successful window yet to report provenance for.</p>
			{/if}
		</Panel>
	</section>

	<section class="research-panel">
		<Panel eyebrow="05 / RESEARCH ONLY" title="Window probability / history" note="Research-only -- not a diagnosis, risk score, or clinical confidence.">
			<div class="calibration-banner">
				<span>SOURCE-DOMAIN CALIBRATION: {successResponse?.calibration_domain ?? '--'}</span>
				<span>CALIBRATION GROUPS: {successResponse?.calibration_patient_count ?? '--'}</span>
				<span>NOT WEARABLE-DOMAIN CLINICAL CALIBRATION</span>
			</div>
			{#if probabilityHistorySeries[0].values.length}
				<MultiLine series={probabilityHistorySeries} height={200} yMin={0} yMax={1} yLabel="probability" />
				<p class="panel-footnote">Frozen source-domain research threshold: {successResponse?.threshold != null ? successResponse.threshold.toFixed(4) : '--'} (not a danger threshold or diagnostic cutoff; not editable here).</p>
			{:else}
				<p class="panel-note">No successful windows recorded yet.</p>
			{/if}
			{#if gapEvents.length}
				<div class="gap-events">
					<span>MISSING / FAILED WINDOWS ({gapEvents.length})</span>
					<ul>
						{#each gapEvents.slice(-5) as gap, index (index)}
							<li><b>{gap.monitoring_state}</b><span>{gap.reason}</span></li>
						{/each}
					</ul>
				</div>
			{/if}
		</Panel>
	</section>
</main>

<style>
	.nhm-dashboard { min-height: 100vh; background: #030712; color: #eef7f6; font-family: Inter, sans-serif; padding: clamp(20px, 4vw, 56px); box-sizing: border-box; }
	.dash-top { display: flex; flex-wrap: wrap; gap: 32px; justify-content: space-between; margin-bottom: 32px; }
	.eyebrow { color: #2bb8b0; font: 10px 'JetBrains Mono', monospace; letter-spacing: .12em; }
	h1 { max-width: 640px; margin: 14px 0; font: 500 clamp(28px, 4vw, 44px)/1.1 'Space Grotesk', sans-serif; }
	.lede { max-width: 620px; color: #94a3b8; font-size: 13px; line-height: 1.7; }
	.session-box { min-width: 260px; padding: 18px; border: 1px solid rgba(148,163,184,.18); background: rgba(10,18,34,.6); display: flex; flex-direction: column; gap: 6px; }
	.session-box span { color: #64748b; font: 9px 'JetBrains Mono', monospace; letter-spacing: .1em; }
	.session-box strong { font: 500 13px 'Space Grotesk', sans-serif; word-break: break-all; }
	.session-actions { display: flex; gap: 8px; margin-top: 10px; }
	.session-actions button { flex: 1; padding: 10px; border: 1px solid #2bb8b0; background: #2bb8b0; color: #03100f; font: 9px 'JetBrains Mono', monospace; letter-spacing: .08em; cursor: pointer; }
	.session-actions button.ghost { background: transparent; color: #2bb8b0; }
	.session-actions button:disabled { opacity: .55; cursor: wait; }
	.session-box small { margin-top: 8px; color: #53647b; font-size: 10px; line-height: 1.6; }
	.session-box small a { color: #2bb8b0; }
	.replay-badge { color: #0ea5e9 !important; }
	.replay-error { color: #fb7185 !important; }
	.panel-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 1px; background: rgba(148,163,184,.14); margin-bottom: 1px; }
	.panel-note { color: #94a3b8; font-size: 12px; line-height: 1.6; margin: 0 0 12px; }
	.panel-footnote { margin-top: 12px; color: #64748b; font: 10px 'JetBrains Mono', monospace; letter-spacing: .04em; line-height: 1.6; }
	.quality-grid, .meta-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
	.quality-warning-badge { margin-top: 12px; padding: 10px; border: 1px solid rgba(251,191,36,.4); background: rgba(120,53,15,.18); color: #fde68a; font: 10px 'JetBrains Mono', monospace; letter-spacing: .04em; }
	.state-tone { padding: 14px; font-size: 14px; line-height: 1.6; border-left: 3px solid #64748b; }
	.state-tone--neutral { border-color: #2bb8b0; color: #dce9e8; }
	.state-tone--notice { border-color: #0ea5e9; color: #bae6fd; }
	.state-tone--warning { border-color: #fbbf24; color: #fde68a; }
	.state-tone--technical-error { border-color: #fb7185; color: #fecdd3; }
	.state-meta { display: flex; gap: 16px; margin-top: 12px; color: #64748b; font: 10px 'JetBrains Mono', monospace; letter-spacing: .08em; }
	.research-panel { margin-top: 1px; }
	.calibration-banner { display: flex; flex-wrap: wrap; gap: 16px; margin-bottom: 16px; padding: 10px 0; border-bottom: 1px solid rgba(148,163,184,.14); color: #64748b; font: 9px 'JetBrains Mono', monospace; letter-spacing: .08em; }
	.gap-events { margin-top: 16px; padding-top: 12px; border-top: 1px solid rgba(148,163,184,.14); }
	.gap-events > span { color: #64748b; font: 9px 'JetBrains Mono', monospace; letter-spacing: .1em; }
	.gap-events ul { list-style: none; margin: 10px 0 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
	.gap-events li { display: flex; justify-content: space-between; gap: 12px; color: #94a3b8; font-size: 11px; }
	.gap-events b { color: #fecdd3; }
	@media (max-width: 860px) {
		.panel-grid, .quality-grid, .meta-grid { grid-template-columns: 1fr; }
	}
</style>
