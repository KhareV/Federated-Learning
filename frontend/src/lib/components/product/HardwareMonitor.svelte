<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import Panel from '$lib/components/dashboard/Panel.svelte';
  import FlowDiagram from '$lib/components/product/story/FlowDiagram.svelte';
  import TechnicalEvidence from '$lib/components/product/federation/TechnicalEvidence.svelte';
  import { getProductStore } from '$lib/product/state.svelte';
  import type { HardwareSession, HardwareReading } from '$lib/product/api';
  import type { HardwareV2Experimental } from '$lib/product/hardware-v2';
  import { hardwareWaveform } from '$lib/product/hardware-waveform';
  import { hardwareStats } from '$lib/product/hardware-stats';
  const product = getProductStore();
  let session = $state<HardwareSession | null>(null);
  let readings = $state<HardwareReading[]>([]);
  let v2 = $state<HardwareV2Experimental | null>(null);
  let v2Error = $state('');
  let error = $state('');
  let busy = $state(false);
  let now = $state(Date.now());
  let timer: ReturnType<typeof setInterval> | undefined;
  let v2Timer: ReturnType<typeof setInterval> | undefined;
  let polling = false;
  let resumed = $state(false);
  let v2Polling = false;
  const latest = $derived(readings.at(-1));
  const display = $derived(readings.slice(-300));
  const waveform = $derived(hardwareWaveform(display));
  const stats = $derived(hardwareStats(readings));
  const latestWindow = $derived(v2?.windows.at(-1));
  const latestInference = $derived([...(v2?.windows ?? [])].reverse().find((w) => w.result.inference)?.result.inference ?? null);
  const sinceLast = $derived(session?.last_received_at ? Math.max(0, (now - Date.parse(session.last_received_at)) / 1000) : null);
  const flow = [
    { label: 'ESP32 SENSORS', sub: 'AD8232 ECG + MAX30102 · ~20 msg/s' },
    { label: 'RENDER → ATLAS', sub: 'server ingestion timestamp' },
    { label: 'NHM READER', sub: 'high-water mark · deduplicated' },
    { label: 'RESAMPLE (EXPERIMENTAL)', sub: 'real points → model-rate grid' },
    { label: 'PREPROC_V1 + MODEL_V2_FINAL', sub: 'NOT VALID for this source' }
  ];
  async function poll() {
    if (!session || session.status !== 'ACTIVE' || polling) return;
    polling = true;
    try {
      const next = await product.api.hardwarePoll(session.session_id, readings.at(-1)?.ordinal ?? 0);
      session = next;
      readings = [...readings, ...next.readings].slice(-2000);
      error = '';
    } catch (cause) { error = cause instanceof Error ? cause.message : String(cause); }
    finally { polling = false; }
  }
  async function refreshV2() {
    if (!session || v2Polling) return;
    v2Polling = true;
    try { v2 = await product.api.hardwareV2Experimental(session.session_id); v2Error = ''; }
    catch (cause) { v2Error = cause instanceof Error ? cause.message : String(cause); }
    finally { v2Polling = false; }
  }
  function attachTimers() {
    if (timer) clearInterval(timer);
    if (v2Timer) clearInterval(v2Timer);
    timer = setInterval(() => { now = Date.now(); void poll(); }, 800);
    v2Timer = setInterval(() => { void refreshV2(); }, 5000);
  }
  async function start() {
    busy = true; error = '';
    try {
      // Start is idempotent on the backend: if this user already has an ACTIVE session it is re-attached.
      session = await product.api.hardwareStart(); readings = []; v2 = null; v2Error = '';
      attachTimers();
    } catch (cause) { error = cause instanceof Error ? cause.message : String(cause); }
    finally { busy = false; }
  }
  // Browser refresh or re-opening Monitor: pick up this user's still-ACTIVE session instead of orphaning it.
  onMount(() => {
    void (async () => {
      try {
        const active = (await product.api.hardwareSessions()).find((s) => s.status === 'ACTIVE');
        if (!active || session) return;
        session = await product.api.hardwareSession(active.session_id);
        readings = session.readings.slice(-2000);
        resumed = true;
        attachTimers();
        void refreshV2();
      } catch { /* no resumable session; the Start button remains available */ }
    })();
  });
  async function stop() {
    if (!session) return;
    if (timer) clearInterval(timer);
    if (v2Timer) clearInterval(v2Timer);
    busy = true;
    try { session = await product.api.hardwareStop(session.session_id); await refreshV2(); }
    catch (cause) { error = cause instanceof Error ? cause.message : String(cause); }
    finally { busy = false; }
  }
  const pct = (v: number | null | undefined) => (v == null ? 'Unavailable' : `${(v * 100).toFixed(2)}%`);
  // Leaving the page only detaches this view (timers). It never stops the session: only the explicit
  // Stop button does. The backend ingests inside authenticated polls, so while the page is away nothing is
  // read; on return the session's saved high-water mark makes the next polls catch up from MongoDB.
  onDestroy(() => {
    if (timer) clearInterval(timer);
    if (v2Timer) clearInterval(v2Timer);
  });
</script>

<p class="lead">MongoDB telemetry from the configured source; the session panel identifies the source after Start. Timestamps are server ingestion time. ECG values are transmitted ADC readings with no verified ADC sampling rate; any model analysis of this source is experimental and not valid. The V2 panels below are an <b>experimental, resampled, not-valid</b> analysis, kept separate from the software ECG source.</p>
<p class="note" data-testid="hardware-lifecycle-note">Session lifecycle: a session ends only when you press <b>Stop Monitoring</b> (or the backend restarts, which marks it INTERRUPTED). Leaving this page does not stop it, but readings are collected only while this page is open; on return the session catches up from MongoDB, so records written meanwhile are still counted (the newest {session?.trace_limit ?? 2000} are retained).</p>
{#if error}<p role="alert" class="err">{error}</p>{/if}
<div class="flowbox" data-testid="hardware-flow"><FlowDiagram label="Hardware telemetry pipeline" steps={flow} /></div>
<Panel eyebrow="01 / HARDWARE SESSION" title="Live hardware telemetry" note="OWNER-SCOPED SESSION · SHARED SOURCE">
  <p class="status" role="status" data-testid="hardware-state">{session?.source_state ?? 'SESSION STOPPED'}</p>
  {#if session}<p><code data-testid="hardware-session-id">{session.session_id}</code> · <span data-testid="hardware-record-count">{session.record_count}</span> records · elapsed {Math.max(0, Math.floor(((session.stopped_at ? new Date(session.stopped_at).getTime() : now) - new Date(session.started_at).getTime()) / 1000))} s · started {new Date(session.started_at).toLocaleString()}</p>
    <p>{session.source} · collection {session.collection}</p>
    <dl class="facts" data-testid="hardware-session-facts">
      <div><dt>STATUS</dt><dd>{session.status}</dd></div>
      <div><dt>LAST RECEIVED</dt><dd>{session.last_received_at ? new Date(session.last_received_at).toLocaleTimeString() : '--'}{sinceLast !== null && session.status === 'ACTIVE' ? ` (${sinceLast.toFixed(1)} s ago)` : ''}</dd></div>
      <div><dt>STALE AFTER</dt><dd>{session.stale_threshold_seconds} s</dd></div>
      <div><dt>TRACE LIMIT</dt><dd>{session.trace_limit} readings</dd></div>
    </dl>{/if}
  <div class="actions">
    <button class="primary" onclick={start} disabled={busy || session?.status === 'ACTIVE'} data-testid="hardware-start">Start Monitoring</button>
    <button onclick={stop} disabled={busy || session?.status !== 'ACTIVE'} data-testid="hardware-stop">Stop Monitoring</button>
    {#if resumed && session?.status === 'ACTIVE'}<span class="dim" data-testid="hardware-resumed">Resumed your active session after a reload.</span>{/if}
    {#if session && session.status !== 'ACTIVE'}<a href={`/app/history/${encodeURIComponent(session.session_id)}`}>View saved History →</a> <a href={`/app/observatory/replay?session=${encodeURIComponent(session.session_id)}`} data-testid="hardware-monitor-replay">Replay in Observatory →</a>{/if}
  </div>
</Panel>
<Panel eyebrow="02 / ECG" title="MongoDB ECG values · actual stored points" note="SERVER INGESTION TIME · GAPS ARE NOT FILLED">
  {#if display.length}
    <svg viewBox="0 0 1000 180" preserveAspectRatio="none" role="img" aria-label="Actual MongoDB ECG readings over server ingestion time, with gaps" data-testid="hardware-waveform" data-points={waveform.points.length} data-paths={waveform.paths.length}>
      {#each waveform.paths as path}<path d={path} fill="none" stroke="#2bb8b0" stroke-width="2" vector-effect="non-scaling-stroke" />{/each}
      {#each waveform.points as point}<circle cx={point.x} cy={point.y} r="2.5" fill="#2bb8b0" />{/each}
      {#if waveform.points.length}<circle cx={waveform.points.at(-1)!.x} cy={waveform.points.at(-1)!.y} r="4" fill="#fbbf24" />{/if}
    </svg>
    <p>{new Date(waveform.points[0].ingested_at).toLocaleTimeString()} → {new Date(waveform.points.at(-1)!.ingested_at).toLocaleTimeString()} · {waveform.points.length} actual points displayed</p>
    <p>Latest received: MongoDB ID <code>{latest?.id}</code> · ECG <strong>{latest?.ecg}</strong> · stored {latest ? new Date(latest.ingested_at).toLocaleString() : '--'}</p>
  {:else}<p>Waiting for new readings. Earlier MongoDB documents are excluded.</p>{/if}
</Panel>
<Panel eyebrow="SOURCE VS MODEL INPUT" title="What is drawn is not what the model would read" note="EXPERIMENTAL">
  <p class="banner" data-testid="v2-banner">{v2?.label ?? 'EXPERIMENTAL · RESAMPLED FROM LOW-RATE MONGODB TELEMETRY · NOT VALID · NOT DIAGNOSTIC'}</p>
  <p>The chart above shows only real stored readings. For the V2 analysis the backend linearly interpolates between consecutive real readings onto the source-rate grid the frozen pipeline expects (never across gaps over 1 s), then the unchanged PREPROC_V1 resamples to 250 Hz and builds 10 s windows. MODEL_V2_FINAL was validated on MIT-BIH ECG, not on this signal chain.</p>
  {#if v2}<TechnicalEvidence label="TECHNICAL EVIDENCE (assumptions)" testid="v2-assumptions"><dl class="facts">{#each Object.entries(v2.assumptions) as [k, val]}<div><dt>{k}</dt><dd>{val}</dd></div>{/each}</dl><p>Input readings {v2.summary.input_readings} → resampled records {v2.summary.resampled_records} → windows {v2.summary.windows ?? 0}</p></TechnicalEvidence>{/if}
</Panel>
<div class="grid">
  <Panel eyebrow="03 / SIGNAL QUALITY" title="Signal quality · is the signal usable?" note="DESCRIPTIVE · NOT A MODEL VERDICT">
    <p class="big" data-testid="hardware-quality-state">{latestWindow?.ecg_quality ?? (stats.count ? 'AWAITING WINDOW' : '--')}</p>
    <p class="label">{latestWindow ? `V2 runtime quality for the window ending ${latestWindow.stream_seconds.toFixed(0)} s: ${latestWindow.quality_reasons.join(', ') || 'no issues flagged'}` : `The first 10 s window needs ${v2?.min_seconds_for_first_window ?? 15} s of data.`}</p>
    <dl class="facts" data-testid="hardware-stats">
      <div><dt>READINGS</dt><dd>{stats.count}</dd></div>
      <div><dt>ARRIVAL RATE</dt><dd>{stats.arrivalHz === null ? '--' : `${stats.arrivalHz.toFixed(1)} msg/s (server time, not ADC rate)`}</dd></div>
      <div><dt>ADC RANGE</dt><dd>{stats.min ?? '--'} … {stats.max ?? '--'} (p-p {stats.peakToPeak ?? '--'})</dd></div>
      <div><dt>MEAN / STD</dt><dd>{stats.mean === null ? '--' : `${stats.mean.toFixed(0)} / ${stats.std!.toFixed(1)}`}</dd></div>
      <div><dt>AT 2048 (LEAD-OFF FALLBACK)</dt><dd>{(stats.flatFraction * 100).toFixed(0)}%</dd></div>
      <div><dt>GAPS &gt; 1 s</dt><dd>{stats.gaps.length} (max {stats.maxGapSeconds.toFixed(1)} s)</dd></div>
    </dl>
    <p class="label" data-testid="hardware-stats-verdict">{stats.verdict.replaceAll('_', ' ')}</p>
  </Panel>
  <Panel eyebrow="04 / MONITORING STATE" title="Research monitoring state · EXPERIMENTAL" note="NOT VALID">
    {#if latestInference}
      <p class="big" data-testid="hardware-v2-state">{latestInference.monitoring_state}</p>
      <p class="warn">Experimental output of MODEL_V2_FINAL on resampled hardware data. Not validated, not a diagnosis.</p>
    {:else}<p class="dim" data-testid="hardware-v2-none">{v2 ? (latestWindow?.result.outcome === 'EXPECTED_UNUSABLE_WINDOW' ? 'The latest window was not usable; the model was not scored.' : 'No scored window yet.') : 'No window yet. A scored window needs about 15 s of readings.'}</p>{/if}
  </Panel>
  <Panel eyebrow="05 / CONTEXT" title="PPG / SpO₂ · device-reported context" note="CONTEXT, NOT A MODEL SIGNAL">
    <dl class="facts">
      <div><dt>DEVICE BPM</dt><dd data-testid="hardware-bpm">{latest?.bpm ?? 'Unavailable'}</dd></div>
      <div><dt>DEVICE SpO₂ — UNVERIFIED</dt><dd data-testid="hardware-spo2">{latest?.spo2 == null ? 'Unavailable' : `${latest.spo2}%`}</dd></div>
      <div><dt>CONTEXT SENT TO V2</dt><dd>{latestWindow?.ppg_context ? `PR ${latestWindow.ppg_context.pr_bpm ?? '--'} bpm · SpO₂ ${latestWindow.ppg_context.spo2_pct ?? '--'}% · quality ${latestWindow.ppg_context.quality ?? 'not supplied'}` : 'none'}</dd></div>
    </dl>
    <p class="label">Zero is shown as unavailable, not as a measured value. No PPG quality metric is available, so V2 reports CONTEXT_UNAVAILABLE for this source.</p>
  </Panel>
  <Panel eyebrow="06 / INFERENCE" title="MODEL_V2_FINAL result · EXPERIMENTAL" note="inference.result · NOT VALID">
    {#if latestInference}
      <dl class="facts" data-testid="hardware-v2-result">
        <div><dt>model</dt><dd>{latestInference.model_id}</dd></div>
        <div><dt>calibration</dt><dd>{latestInference.calibration_id} ({latestInference.calibration_domain})</dd></div>
        <div><dt>raw probability</dt><dd data-testid="hardware-v2-raw">{pct(latestInference.raw_probability)}</dd></div>
        <div><dt>source-domain calibrated</dt><dd data-testid="hardware-v2-cal">{pct(latestInference.source_domain_calibrated_probability)}</dd></div>
        <div><dt>threshold</dt><dd>{latestInference.threshold ?? '--'}</dd></div>
        <div><dt>latency</dt><dd>{latestInference.latency_ms === null ? '--' : `${latestInference.latency_ms.toFixed(0)} ms`}</dd></div>
        <div><dt>preprocess</dt><dd>{latestInference.preprocess_version}</dd></div>
      </dl>
      <p class="warn">Calibration is MIT-BIH source-domain only; it does not apply to this device.</p>
    {:else}<p class="dim">Waiting for the first scored window.</p>{/if}
    {#if v2Error}<p class="err" role="alert" data-testid="hardware-v2-error">{v2Error}</p>{/if}
  </Panel>
  <Panel eyebrow="07 / DEVICE LINK" title="Source connection" note="NOT PROOF THE DEVICE IS CONNECTED">
    <p class="big" data-testid="hardware-link-state">{session?.source_state ?? 'SESSION STOPPED'}</p>
    <p class="label">MongoDB reachability and fresh documents are what NHM can observe; it cannot confirm the ESP32 is physically attached.</p>
  </Panel>
</div>
{#if v2?.windows.length}
  <Panel eyebrow="08 / TECHNICAL" title="Window log · latest {v2.windows.length} windows" note="EXPERIMENTAL">
    <TechnicalEvidence label="TECHNICAL EVIDENCE (per-window results)" testid="hardware-v2-windows">
      <table><thead><tr><th>window</th><th>end</th><th>quality</th><th>outcome</th><th>state</th><th>raw</th><th>calibrated</th></tr></thead>
        <tbody>{#each [...v2.windows].reverse() as w}<tr><td>{w.window_id}</td><td>{new Date(w.wall_time).toLocaleTimeString()}</td><td>{w.ecg_quality}{w.quality_reasons.length ? ` (${w.quality_reasons.join(', ')})` : ''}</td><td>{w.result.outcome}</td><td>{w.result.inference?.monitoring_state ?? '--'}</td><td>{pct(w.result.inference?.raw_probability)}</td><td>{pct(w.result.inference?.source_domain_calibrated_probability)}</td></tr>{/each}</tbody></table>
    </TechnicalEvidence>
  </Panel>
{/if}
{#if stats.gaps.length}
  <Panel eyebrow="09 / TECHNICAL" title="Source gaps observed" note="NEVER FILLED">
    <TechnicalEvidence label="TECHNICAL EVIDENCE (gap ranges)" testid="hardware-gap-evidence"><ol>{#each stats.gaps.slice(-20) as g}<li>{new Date(g.from).toLocaleTimeString()} → {new Date(g.to).toLocaleTimeString()} · {g.seconds.toFixed(1)} s</li>{/each}</ol></TechnicalEvidence>
  </Panel>
{/if}
<p class="lead">No clinical classification, validated prediction or hardware identity claim is made for this source. A flat ECG value can also mean the sketch's lead-off fallback; the current payload has no lead-off flag.</p>
<style>
  .lead,p{color:#a7b8c9;font-size:13px;line-height:1.6}.err{color:#fecdd3}.warn{color:#fbbf24}.banner{font:600 12px 'JetBrains Mono',monospace;color:#fbbf24;border:1px solid #fbbf24;padding:8px 10px;letter-spacing:.04em}.status{font:600 16px 'JetBrains Mono',monospace;color:#2bb8b0}.actions{display:flex;flex-wrap:wrap;gap:10px}.actions button{padding:10px 14px;border:1px solid var(--nhm-border);background:transparent;color:#e2e8f0;cursor:pointer}.actions button.primary{background:#2bb8b0;color:#03110f}.actions button:disabled{opacity:.4}.actions a{color:#2bb8b0;padding:10px}svg{display:block;width:100%;height:220px;background:#07101d;border:1px solid var(--nhm-border)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,340px),1fr));gap:10px}.big{font:500 24px 'Space Grotesk',sans-serif;color:#e2e8f0;overflow-wrap:anywhere}.label{color:#a7b8c9}.facts{display:grid;gap:6px;margin:8px 0}.facts div{display:flex;justify-content:space-between;gap:12px;border-bottom:1px solid var(--nhm-border);padding-bottom:4px}dt{color:#7f93a8;font:11px 'JetBrains Mono',monospace}dd{margin:0;color:#e2e8f0;text-align:right;overflow-wrap:anywhere}code{color:#9fe7e1;overflow-wrap:anywhere}.flowbox{margin:10px 0}table{width:100%;border-collapse:collapse;font:12px 'JetBrains Mono',monospace}th,td{text-align:left;padding:4px 6px;border-bottom:1px solid var(--nhm-border);color:#cbd5e1}
</style>
