<script lang="ts">
  import { onDestroy } from 'svelte';
  import Panel from '$lib/components/dashboard/Panel.svelte';
  import { getProductStore } from '$lib/product/state.svelte';
  import type { HardwareSession, HardwareReading } from '$lib/product/api';
  import { hardwareWaveform } from '$lib/product/hardware-waveform';
  const product = getProductStore();
  let session = $state<HardwareSession | null>(null);
  let readings = $state<HardwareReading[]>([]);
  let error = $state('');
  let busy = $state(false);
  let now = $state(Date.now());
  let timer: ReturnType<typeof setInterval> | undefined;
  let polling = false;
  const latest = $derived(readings.at(-1));
  const display = $derived(readings.slice(-300));
  const waveform = $derived(hardwareWaveform(display));
  async function poll() {
    if (!session || session.status !== 'ACTIVE' || polling) return;
    polling = true;
    try {
      const next = await product.api.hardwarePoll(session.session_id, readings.at(-1)?.ordinal ?? 0);
      session = next;
      readings = [...readings, ...next.readings].slice(-300);
      error = '';
    } catch (cause) { error = cause instanceof Error ? cause.message : String(cause); }
    finally { polling = false; }
  }
  async function start() {
    busy = true; error = '';
    try {
      session = await product.api.hardwareStart(); readings = [];
      timer = setInterval(() => { now = Date.now(); void poll(); }, 800);
    } catch (cause) { error = cause instanceof Error ? cause.message : String(cause); }
    finally { busy = false; }
  }
  async function stop() {
    if (!session) return;
    if (timer) clearInterval(timer);
    busy = true;
    try { session = await product.api.hardwareStop(session.session_id); }
    catch (cause) { error = cause instanceof Error ? cause.message : String(cause); }
    finally { busy = false; }
  }
  onDestroy(() => {
    if (timer) clearInterval(timer);
    if (session?.status === 'ACTIVE') void product.api.hardwareStop(session.session_id).catch(() => {});
  });
</script>

<p class="lead">MongoDB telemetry from the configured source; the session panel identifies the source after Start. Timestamps are server ingestion time. ECG values are transmitted ADC readings; no verified ADC sampling rate or model inference is available.</p>
{#if error}<p role="alert" class="err">{error}</p>{/if}
<Panel eyebrow="01 / HARDWARE SESSION" title="Live hardware telemetry" note="OWNER-SCOPED SESSION · SHARED SOURCE">
  <p class="status" role="status">{session?.source_state ?? 'SESSION STOPPED'}</p>
  {#if session}<p><code>{session.session_id}</code> · {session.record_count} records · elapsed {Math.max(0, Math.floor(((session.stopped_at ? new Date(session.stopped_at).getTime() : now) - new Date(session.started_at).getTime()) / 1000))} s · started {new Date(session.started_at).toLocaleString()}</p>
    <p>{session.source} · collection {session.collection}</p>{/if}
  <div class="actions">
    <button class="primary" onclick={start} disabled={busy || session?.status === 'ACTIVE'}>Start Monitoring</button>
    <button onclick={stop} disabled={busy || session?.status !== 'ACTIVE'}>Stop Monitoring</button>
    {#if session?.status === 'STOPPED'}<a href={`/app/history/${encodeURIComponent(session.session_id)}`}>View saved History →</a>{/if}
  </div>
</Panel>
<Panel eyebrow="02 / ECG" title="MongoDB ECG values" note="SERVER INGESTION TIME · GAPS ARE NOT FILLED">
  {#if display.length}
    <svg viewBox="0 0 1000 180" preserveAspectRatio="none" role="img" aria-label="Actual MongoDB ECG readings over server ingestion time, with gaps">
      {#each waveform.paths as path}<path d={path} fill="none" stroke="#2bb8b0" stroke-width="2" vector-effect="non-scaling-stroke" />{/each}
      {#each waveform.points as point}<circle cx={point.x} cy={point.y} r="2.5" fill="#2bb8b0" />{/each}
      {#if waveform.points.length}<circle cx={waveform.points.at(-1)!.x} cy={waveform.points.at(-1)!.y} r="4" fill="#fbbf24" />{/if}
    </svg>
    <p>{new Date(waveform.points[0].ingested_at).toLocaleTimeString()} → {new Date(waveform.points.at(-1)!.ingested_at).toLocaleTimeString()} · {waveform.points.length} actual points displayed</p>
    <p>Latest received: MongoDB ID <code>{latest?.id}</code> · ECG <strong>{latest?.ecg}</strong> · stored {latest ? new Date(latest.ingested_at).toLocaleString() : '--'}</p>
  {:else}<p>Waiting for new readings. Earlier MongoDB documents are excluded.</p>{/if}
</Panel>
<div class="vitals">
  <Panel eyebrow="03 / DEVICE REPORTED" title="BPM"><p class="value">{latest?.bpm ?? 'Unavailable'}</p></Panel>
  <Panel eyebrow="04 / UNVERIFIED" title="Device-reported SpO₂ — unverified"><p class="value">{latest?.spo2 == null ? 'Unavailable' : `${latest.spo2}%`}</p></Panel>
</div>
<p class="lead">No clinical classification, calibrated prediction, signal quality verdict or hardware identity claim is made for this source. A flat ECG value can also mean the sketch's lead-off fallback; the current payload has no lead-off flag.</p>
<style>
  .lead,p{color:#a7b8c9;font-size:13px;line-height:1.6}.err{color:#fecdd3}.status{font:600 16px 'JetBrains Mono',monospace;color:#2bb8b0}.actions{display:flex;flex-wrap:wrap;gap:10px}.actions button{padding:10px 14px;border:1px solid var(--nhm-border);background:transparent;color:#e2e8f0;cursor:pointer}.actions button.primary{background:#2bb8b0;color:#03110f}.actions button:disabled{opacity:.4}.actions a{color:#2bb8b0;padding:10px}svg{display:block;width:100%;height:220px;background:#07101d;border:1px solid var(--nhm-border)}.vitals{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px}.value{font:500 28px 'Space Grotesk',sans-serif;color:#e2e8f0}code{color:#9fe7e1;overflow-wrap:anywhere}
</style>
