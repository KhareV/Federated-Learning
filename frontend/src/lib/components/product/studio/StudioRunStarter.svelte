<script lang="ts">
	// One continuous start workflow for both run lengths and both starting models. The default starting model is the pretrained V2 (MODEL_V2_FINAL, federated fine-tuning); the untrained start stays available.
	// 3 rounds from the UNTRAINED start keeps the ORIGINAL run form and the frozen 3-round product contract untouched; every other combination uses the verified extended engine.
	import RunConfigForm from '$lib/components/product/federation/RunConfigForm.svelte';
	import HardwareDemoStarter from '$lib/components/product/studio/HardwareDemoStarter.svelte';
	import { onMount } from 'svelte';
	import { getProductStore } from '$lib/product/state.svelte';
	import type { FederationRunChoice } from '$lib/product/api';
	import type { Initialisation, RunLength, SourceMode, StudioCapabilities, StudioRunChoice } from '$lib/product/studio/types';
	let { disabled = false, liveBlocked = false, backendEnabled = true, capabilities = null, dataSource = $bindable<'SYNTHETIC' | 'HARDWARE'>('SYNTHETIC'), preselectSession = null, onStartThree, onStartTen }: {
		disabled?: boolean; liveBlocked?: boolean; backendEnabled?: boolean; capabilities?: StudioCapabilities | null; dataSource?: 'SYNTHETIC' | 'HARDWARE'; preselectSession?: string | null;
		onStartThree: (choice: FederationRunChoice) => void; onStartTen: (choice: StudioRunChoice) => void } = $props();
	let length = $state<RunLength>(3);              // default stays 3
	let source = $state<SourceMode>('CANONICAL_SYNTHETIC');
	let monitoredSite = $state(0);                  // source mode LIVE_MONITORED_SITE_00 only: which canonical cohort site is genuinely live-monitored (0 = SITE_00, the original behaviour)
	const sites = $derived(capabilities?.ten_round.monitored_sites ?? []);
	// Signal of the monitored client: a NEW simulated session of the cohort site (default), or a COMPLETED monitoring session from History whose signal is regenerated from its frozen scenario.
	const product = getProductStore();
	// ONE place chooses the training data: the synthetic cohort, one of YOUR completed monitoring sessions (History), or recorded hardware. Only the first has a "source mode".
	let choice = $state<'SYNTHETIC' | 'SESSION' | 'HARDWARE'>(dataSource === 'HARDWARE' ? 'HARDWARE' : 'SYNTHETIC');
	let sessionPick = $state('');
	$effect(() => { const next = choice === 'HARDWARE' ? 'HARDWARE' : 'SYNTHETIC'; if (dataSource !== next) dataSource = next; });
	$effect(() => { if (dataSource === 'HARDWARE' && choice !== 'HARDWARE') choice = 'HARDWARE'; });      // a deep link from History sets the bindable from the parent
	const historySessions = $derived(product.sessions.filter((x) => x.state === 'COMPLETED' && !!x.simulation_provenance));
	onMount(() => { void product.loadSessions(); });
	$effect(() => { if (choice === 'SESSION' && !historySessions.some((x) => x.session_id === sessionPick)) sessionPick = historySessions[0]?.session_id ?? ''; });
	const fromHistory = $derived(choice === 'SESSION');
	const sessionText = (h: { session_id: string; created_at_us?: number | null; simulation_provenance?: { scenario_id: string } | null }) => `${h.simulation_provenance?.scenario_id ?? 'session'} · ${h.session_id.slice(0, 13)}…${h.created_at_us ? ' · ' + new Date(h.created_at_us / 1000).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : ''}`;
	const siteLabel = $derived(`SITE_${String(monitoredSite).padStart(2, '0')}`);
	// Training data: the synthetic cohort (default, unchanged) or readings recorded from the MongoDB hardware source.
	const hardwareOffered = $derived(capabilities?.hardware_demo?.available === true);
	const hardware = $derived(choice === 'HARDWARE' && hardwareOffered);
	let algorithm = $state<'FEDAVG' | 'FEDPROX'>('FEDAVG');
	let secaggMode = $state<'PLAIN' | 'SECAGG_SHADOW'>('PLAIN');
	let initChoice = $state<Initialisation | null>(null);                           // null = follow the backend's default (pretrained V2); the user's choice then overrides it
	const inits = $derived(capabilities?.ten_round.initialisations ?? []);
	const defaultInit = $derived<Initialisation>(capabilities?.ten_round.default_initialisation ?? (inits.some((i) => i.id === 'MODEL_V2_FINAL') ? 'MODEL_V2_FINAL' : 'FL_INIT_V2'));
	const initialisation = $derived<Initialisation>(initChoice ?? defaultInit);
	const v2Rounds = $derived(capabilities?.ten_round.rounds_by_initialisation?.MODEL_V2_FINAL ?? [10]);
	const v2ThreeUnsupported = $derived(inits.length > 0 && initialisation === 'MODEL_V2_FINAL' && length === 3 && !v2Rounds.includes(3));
	/** The original frozen form: 3 rounds from the untrained start (or a backend that offers no starting-model choice). */
	const original = $derived(!hardware && !fromHistory && length === 3 && (!inits.length || initialisation === 'FL_INIT_V2' || v2ThreeUnsupported));
	const tenAvailable = $derived(capabilities?.ten_round.available === true);
	const modes = $derived(capabilities?.ten_round.source_modes ?? ['CANONICAL_SYNTHETIC']);
	const fedproxAvailable = $derived(capabilities?.ten_round.algorithms.includes('FEDPROX') === true);
	const shadowAvailable = $derived(capabilities?.ten_round.aggregation_modes.includes('SECAGG_SHADOW') === true);
	const fedproxUnavailable = $derived(capabilities?.ten_round.unsupported?.FEDPROX ?? 'not advertised by the connected backend');
	const shadowUnavailable = $derived(capabilities?.ten_round.unsupported?.SECAGG_SHADOW ?? 'not advertised by the connected backend');
	const sessionNeedsV2 = $derived(fromHistory && length === 3 && initialisation !== 'MODEL_V2_FINAL');       // 3 rounds from the untrained start use the frozen product contract, which has no history source
	const blocked = $derived(!backendEnabled || disabled || liveBlocked || !tenAvailable || (fromHistory && (!sessionPick || sessionNeedsV2)));
	const OPTIONS: { value: RunLength; title: string; tag: string }[] = [{ value: 3, title: '★ 3 ROUNDS', tag: 'DEFAULT' }, { value: 10, title: '10 ROUNDS', tag: 'EXTENDED' }];
	const SOURCE_TEXT: Record<SourceMode, string> = { CANONICAL_SYNTHETIC: 'Canonical synthetic cohort — eight frozen synthetic clients.', LIVE_MONITORED_SITE_00: 'Live-monitored simulated site — the simulated monitoring stream of that site is genuinely executed and feeds it. This is NOT real patient physiology.' };
	const sourceNote = $derived(fromHistory ? `Your synthetic monitoring session ${sessionPick ? sessionPick.slice(0, 13) + '…' : '—'} — its signal is regenerated from its frozen scenario (no new monitoring session, no new inference) and becomes the local data of your client, SITE_00; the other seven clients stay canonical synthetic. Labels are synthetic-assigned for the demonstration (a monitoring session has no scheduled engineering events), exactly as for recorded hardware. This is NOT real patient physiology.` : source === 'LIVE_MONITORED_SITE_00' ? `Live-monitored simulated ${siteLabel} — the simulated monitoring stream of ${siteLabel} is genuinely executed (real monitoring runtime, real inference) and its windows become that client's local data; the other seven clients stay canonical synthetic. This is NOT real patient physiology.` : SOURCE_TEXT[source]);
	function radioKey(e: KeyboardEvent) {
		if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
		e.preventDefault();
		const next: RunLength = length === 3 ? 10 : 3;
		if (next === 10 && !tenAvailable) return;
		length = next;
		queueMicrotask(() => document.getElementById(`rounds-${next}`)?.focus());
	}
</script>
<div class="rs" data-testid="studio-run-starter">
	<div class="sel" role="radiogroup" aria-label="Communication rounds">
		{#if hardwareOffered || historySessions.length}
			<span class="cap">Training data</span>
			<div class="opts data" role="radiogroup" aria-label="Training data">
				<button type="button" role="radio" aria-checked={choice === 'SYNTHETIC'} class:on={choice === 'SYNTHETIC'} data-testid="data-source-synthetic" onclick={() => { choice = 'SYNTHETIC'; }}><b>SYNTHETIC COHORT</b><small>EIGHT FROZEN SYNTHETIC CLIENTS</small></button>
				<button type="button" role="radio" aria-checked={choice === 'SESSION'} class:on={choice === 'SESSION'} data-testid="data-source-session" disabled={!historySessions.length} title={historySessions.length ? '' : 'Run a synthetic monitoring session to completion first'} onclick={() => { choice = 'SESSION'; }}><b>SYNTHETIC MONITORING</b><small>{historySessions.length ? 'COMPLETED · FROM HISTORY' : 'NO COMPLETED SESSION YET'}</small></button>
				{#if hardwareOffered}<button type="button" role="radio" aria-checked={choice === 'HARDWARE'} class:on={choice === 'HARDWARE'} data-testid="data-source-hardware" onclick={() => { choice = 'HARDWARE'; }}><b>RECORDED HARDWARE</b><small>YOUR SAVED MONGODB SESSIONS</small></button>{/if}
			</div>
		{/if}
		{#if !hardware && !original}
		{#if fromHistory}
			<label><span>Synthetic monitoring session</span><select bind:value={sessionPick} data-testid="cfg10-session">{#each historySessions as h (h.session_id)}<option value={h.session_id}>{sessionText(h)}</option>{/each}</select></label>
			{#if sessionNeedsV2}<p class="warn" role="status" data-testid="session-needs-v2">3 rounds from the untrained start use the frozen product form, which has no monitoring-session source. Choose the pretrained V2 start or 10 rounds.</p>{/if}
		{:else}
			<label><span>Source mode</span><select bind:value={source} data-testid="cfg10-source">{#each modes as m (m)}<option value={m}>{m === 'CANONICAL_SYNTHETIC' ? 'Canonical synthetic cohort' : 'Live-monitored simulated site'}</option>{/each}</select></label>
			{#if source === 'LIVE_MONITORED_SITE_00' && sites.length}
				<label><span>Monitored site</span><select bind:value={monitoredSite} data-testid="cfg10-site">{#each sites as site (site.index)}<option value={site.index}>{site.label} — {site.profile}</option>{/each}</select></label>
			{/if}
		{/if}
		<p class="help" data-testid="cfg10-source-note">{sourceNote}</p>
		{/if}
		<span class="cap">Communication rounds</span>
		<div class="opts">{#each OPTIONS as o (o.value)}
			<button type="button" role="radio" id={`rounds-${o.value}`} aria-checked={length === o.value} tabindex={length === o.value ? 0 : -1} class:on={length === o.value} disabled={o.value === 10 && !tenAvailable} data-testid={`rounds-${o.value}`} onclick={() => { length = o.value; }} onkeydown={radioKey}><b>{o.title}</b><small>{o.tag}</small></button>{/each}</div>
		{#if !tenAvailable}<p class="warn" role="status" data-testid="ten-unavailable">10 ROUNDS UNAVAILABLE: the connected backend does not provide the extended 10-round engine. The 3-round default is unaffected.</p>{/if}
		<table class="exp" aria-label="Expected communication structure"><thead><tr><th scope="col">Choice</th><th scope="col">Clients</th><th scope="col">Rounds</th><th scope="col">Expected accepted updates</th></tr></thead>
			<tbody><tr class:cur={length === 3}><th scope="row">Default</th><td>8</td><td>3</td><td data-testid="expected-3">24</td></tr><tr class:cur={length === 10}><th scope="row">Extended</th><td>8</td><td>10</td><td data-testid="expected-10">80</td></tr></tbody></table>
		<p class="dim">These are expected counts, not evidence of completed work. The running page shows only updates the coordinator actually accepted.</p>
		{#if inits.length && !hardware}
			<label><span>Starting model</span><select value={initialisation} onchange={(e) => { initChoice = (e.currentTarget as HTMLSelectElement).value as Initialisation; }} data-testid="cfg10-init">{#each inits as i (i.id)}<option value={i.id}>{i.id === 'FL_INIT_V2' ? 'Untrained V2 architecture — FL_INIT_V2' : 'Pretrained V2 (default) — MODEL_V2_FINAL, federated fine-tuning'}</option>{/each}</select></label>
			<p class="help" data-testid="cfg10-init-note">{inits.find((i) => i.id === initialisation)?.label}. {initialisation === 'MODEL_V2_FINAL' ? 'R0 is the verified pretrained checkpoint, unchanged; the federated rounds adapt it on the synthetic engineering-event task. The Generalisation tab then compares every round with frozen V2 on an unseen cohort.' : length === 3 ? 'Original frozen 3-round contract: FedAvg or FedProx, optional protected-aggregation shadow. R0 is a fresh untrained model.' : 'R0 is a fresh untrained model; frozen V2 is shown only as an external reference.'}</p>
			{#if v2ThreeUnsupported}<p class="warn" role="status" data-testid="v2-three-unsupported">3 rounds from the pretrained start are not offered by the connected backend; the original untrained 3-round form is shown.</p>{/if}
		{/if}
	</div>
	{#if hardware}
		<HardwareDemoStarter {capabilities} {disabled} rounds={length} preselect={preselectSession} />
	{:else if original}
		<RunConfigForm {disabled} {liveBlocked} {backendEnabled} onSubmit={onStartThree} />
	{:else}
		<form class="cfg" onsubmit={(e) => { e.preventDefault(); if (!blocked) onStartTen({ run_length: length, source_mode: fromHistory ? 'LIVE_MONITORED_SITE_00' : source, ...(!fromHistory && source === 'LIVE_MONITORED_SITE_00' && monitoredSite ? { monitored_site: monitoredSite } : {}), ...(fromHistory ? { signal_session_id: sessionPick } : {}), ...(inits.length ? { initialisation } : {}), ...(algorithm !== 'FEDAVG' ? { algorithm } : {}), ...(secaggMode !== 'PLAIN' ? { secagg_mode: secaggMode } : {}) }); }} aria-label={`${length === 3 ? 'Three' : 'Ten'}-round federation run configuration`}>
			<label><span>Algorithm</span><select bind:value={algorithm} disabled={!fedproxAvailable} data-testid="cfg10-algorithm"><option value="FEDAVG">FedAvg — sample-count-weighted averaging</option><option value="FEDPROX">FedProx — frozen μ 0.1</option></select></label>
			<p class="help" data-testid="cfg10-algorithm-note">{!fedproxAvailable ? `FedProx is disabled: ${fedproxUnavailable}.` : algorithm === 'FEDPROX' ? 'Genuine proximal local objective against the current round-start global weights; μ 0.1.' : 'Genuine local BCE optimization with weighted FedAvg.'}</p>
			<label><span>Aggregation / protection mode</span><select bind:value={secaggMode} disabled={!shadowAvailable} data-testid="cfg10-mode"><option value="PLAIN">Plain aggregation</option><option value="SECAGG_SHADOW">Round-1 SecAgg+ shadow verification</option></select></label>
			<p class="help" data-testid="cfg10-mode-note">{!shadowAvailable ? `SecAgg+ shadow is disabled: ${shadowUnavailable}; an unsupported request is never silently reinterpreted.` : secaggMode === 'SECAGG_SHADOW' ? 'The real protected shadow is compared with the authoritative plain aggregate in round 1. It does not make anonymity or DP claims.' : 'Authoritative sample-count-weighted plain aggregation.'}</p>
			<label><span>Run mode</span><select disabled data-testid="cfg10-run-type"><option>LIVE_RUN</option><option disabled>REPLAY — open a completed run instead</option></select></label>
			<p class="help">LIVE_RUN performs genuine local optimization and federation for {length} rounds. A replay never trains: open a completed run from “Your federation runs”, or a recorded FL10 run, to replay it.</p>
			<dl class="fixedcfg" aria-label="Fixed configuration"><div><dt>Clients</dt><dd>8</dd></div><div><dt>Rounds</dt><dd>{length}</dd></div><div><dt>Base</dt><dd>{initialisation}</dd></div><div><dt>Evaluation</dt><dd>per committed round</dd></div></dl>
			{#if liveBlocked}<p class="warn" role="status">ONE LIVE FEDERATION RUN AT A TIME IN THIS ONE-LAPTOP DEMONSTRATION.</p>{/if}
			<button type="submit" disabled={blocked} data-testid="cfg10-submit">Create and start {length}-round live run</button>
		</form>
	{/if}
</div>
<style>
	.opts.data { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); } .opts.data button { min-width: 0; }
	/* The original run form (RunConfigForm) names a block class="fixed", which Tailwind's global .fixed{position:fixed} pulled out of flow on top of the form. */
	:global(.cfg dl.fixed) { position: static; }
	.fixedcfg dd { overflow-wrap: break-word; word-break: normal; }
	.rs { display: grid; grid-template-columns: minmax(0, 1fr); gap: 14px; min-width: 0; } .sel { display: grid; grid-template-columns: minmax(0, 1fr); gap: 8px; max-width: 560px; } .cap { font: 11px 'JetBrains Mono', monospace; letter-spacing: .06em; color: #94a3b8; } .opts { display: flex; flex-wrap: wrap; gap: 8px; }
	.opts button { display: grid; gap: 2px; text-align: left; background: #07101e; color: #e5f1f0; border: 1px solid rgba(148,163,184,.3); padding: 9px 14px; min-height: 48px; cursor: pointer; font: 13px Inter, sans-serif; } .opts button b { font: 600 13px 'Space Grotesk', sans-serif; letter-spacing: .04em; } .opts button small { font: 10.5px 'JetBrains Mono', monospace; letter-spacing: .12em; color: #71829a; } .opts button.on { border-color: #a78bfa; background: rgba(167,139,250,.1); } .opts button.on small { color: #c4b5fd; } .opts button:disabled { opacity: .45; cursor: not-allowed; } .opts button:focus-visible { outline: 2px solid #2bb8b0; outline-offset: 2px; }
	.exp { border-collapse: collapse; font-size: 12px; width: 100%; } .exp th, .exp td { border: 1px solid rgba(148,163,184,.18); padding: 5px 9px; text-align: left; color: #cbd5e1; } .exp thead th { color: #71829a; font: 10.5px 'JetBrains Mono', monospace; letter-spacing: .06em; } .exp tr.cur td, .exp tr.cur th { background: rgba(167,139,250,.08); }
	.cfg { display: grid; gap: 10px; max-width: 560px; min-width: 0; } label { display: flex; flex-direction: column; gap: 7px; min-width: 0; font: 11px 'JetBrains Mono', monospace; letter-spacing: .06em; color: #94a3b8; } select, .cfg button { max-width: 100%; box-sizing: border-box; font: 13px Inter, sans-serif; padding: 8px 10px; background: #07101e; color: #e5f1f0; border: 1px solid rgba(148,163,184,.3); } select:disabled { opacity: .7; } select:focus-visible, .cfg button:focus-visible { outline: 2px solid #2bb8b0; }
	.cfg button { background: #2bb8b0; color: #030712; font-weight: 600; cursor: pointer; } .cfg button:disabled { opacity: .45; cursor: not-allowed; } .help, .dim { margin: 0; color: #94a3b8; font-size: 12px; line-height: 1.5; } .warn { margin: 0; color: #fbbf24; font: 11px 'JetBrains Mono', monospace; }
	.fixedcfg { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 6px; margin: 0; } .fixedcfg div { border: 1px solid rgba(148,163,184,.16); padding: 6px 8px; } dt { color: #71829a; font: 10.5px 'JetBrains Mono', monospace; letter-spacing: .1em; text-transform: uppercase; } dd { margin: 3px 0 0; font-size: 13px; color: #e5f1f0; }
	p, dd, small, label, button { overflow-wrap: anywhere; }
</style>
