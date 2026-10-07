<script lang="ts">
	import { ALGORITHMS, AGGREGATION_MODES, RUN_TYPES, FROZEN_BASE, FROZEN_CLIENTS, FROZEN_ROUNDS, FROZEN_SCENARIO, type AggregationMode, type Algorithm, type RunType } from '$lib/product/federation/types';
	import { ALGORITHM_LABEL, MODE_LABEL } from '$lib/product/federation/labels';
	import type { FederationRunChoice } from '$lib/product/api';
	import LiveVsReplay from './LiveVsReplay.svelte';

	let { disabled = false, liveBlocked = false, backendEnabled = true, onSubmit }: { disabled?: boolean; liveBlocked?: boolean; backendEnabled?: boolean; onSubmit: (choice: FederationRunChoice) => void } = $props();
	let runType = $state<RunType>('LIVE_RUN');
	let algorithm = $state<Algorithm>('FEDAVG');
	let mode = $state<AggregationMode>('PLAIN');
	const blocked = $derived(!backendEnabled || disabled || (runType === 'LIVE_RUN' && liveBlocked));
</script>
<form class="cfg" onsubmit={(e) => { e.preventDefault(); if (!blocked) onSubmit({ run_type: runType, algorithm, secagg_mode: mode }); }} aria-label="Federation run configuration">
	{#if !backendEnabled}<p class="warn" role="alert">FEDERATION BACKEND NOT ENABLED</p>{/if}
	<label><span>Run mode</span>
		<select bind:value={runType} data-testid="cfg-run-type">{#each RUN_TYPES as t}<option value={t}>{t}</option>{/each}</select>
	</label>
	<p class="help">{runType === 'LIVE_RUN' ? 'LIVE_RUN performs genuine local optimization and federation.' : 'REPLAY re-emits a previously completed compatible LIVE_RUN. No training is executed.'}</p>
	<label><span>Algorithm</span>
		<select bind:value={algorithm} data-testid="cfg-algorithm">{#each ALGORITHMS as a}<option value={a}>{ALGORITHM_LABEL[a].name} — {ALGORITHM_LABEL[a].text}</option>{/each}</select>
	</label>
	{#if algorithm === 'FEDPROX'}<p class="help">The server uses the frozen FedProx configuration.</p>{/if}
	<label><span>Aggregation / protection mode</span>
		<select bind:value={mode} data-testid="cfg-mode">{#each AGGREGATION_MODES as m}<option value={m}>{MODE_LABEL[m].name}</option>{/each}</select>
	</label>
	<p class="help">{MODE_LABEL[mode].text}{mode === 'SECAGG_SHADOW' ? ' ROUND-1 PROTECTED-AGGREGATION SHADOW.' : ''}</p>
	<div class="explain" data-testid="cfg-explain" aria-live="polite">
		<p><b>{runType === 'LIVE_RUN' ? 'LIVE RUN' : 'REPLAY'}</b> — {runType === 'LIVE_RUN' ? 'the backend trains for real: 8 synthetic clients, 3 rounds.' : 'previous events are replayed. Nothing is trained.'}</p>
		<p><b>{algorithm}</b> — {algorithm === 'FEDAVG' ? 'Client updates are combined using sample-count-weighted averaging.' : 'Uses the existing proximal local-training option.'}</p>
		{#if mode === 'SECAGG_SHADOW'}<p><b>SECAGG SHADOW</b> — Round-1 protected-aggregation compatibility exercise. No differential-privacy or anonymity claim.</p>{/if}
	</div>
	{#if runType === 'REPLAY'}<LiveVsReplay highlight="REPLAY" />{/if}
	<dl class="fixed" aria-label="Fixed configuration">
		<div><dt>Scenario</dt><dd>{FROZEN_SCENARIO}</dd></div><div><dt>Clients</dt><dd>{FROZEN_CLIENTS}</dd></div>
		<div><dt>Rounds</dt><dd>{FROZEN_ROUNDS}</dd></div><div><dt>Base</dt><dd>{FROZEN_BASE}</dd></div>
	</dl>
	{#if runType === 'LIVE_RUN' && liveBlocked}<p class="warn" role="status">ONE LIVE FEDERATION RUN AT A TIME IN THIS ONE-LAPTOP DEMONSTRATION.</p>{/if}
	<button type="submit" disabled={blocked} data-testid="cfg-submit">{runType === 'LIVE_RUN' ? 'Create and start live run' : 'Create and start replay'}</button>
</form>
<style>
	.cfg { display: grid; gap: 10px; max-width: 560px; min-width: 0; } select { width: 100%; min-width: 0; } label { display: flex; flex-direction: column; gap: 7px; min-width: 0; font: 11px 'JetBrains Mono', monospace; letter-spacing: .06em; color: #94a3b8; }
	select, button { max-width: 100%; box-sizing: border-box; font: 13px Inter, sans-serif; padding: 8px 10px; background: #07101e; color: #e5f1f0; border: 1px solid rgba(148,163,184,.3); } select:focus-visible, button:focus-visible { outline: 2px solid #2bb8b0; }
	button { background: #2bb8b0; color: #030712; font-weight: 600; cursor: pointer; } button:disabled { opacity: .45; cursor: not-allowed; }
	.help { margin: 0; color: #94a3b8; font-size: 12px; line-height: 1.5; } .warn { margin: 0; color: #fbbf24; font: 11px 'JetBrains Mono', monospace; }
	.explain { display: grid; gap: 6px; border: 1px solid rgba(167,139,250,.3); background: rgba(167,139,250,.05); padding: 9px 11px; } .explain p { margin: 0; font-size: 12.5px; line-height: 1.5; color: #cbd5e1; } .explain b { font: 10.5px 'JetBrains Mono', monospace; letter-spacing: .08em; color: #c4b5fd; }
	.fixed { display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: 6px; margin: 0; } .fixed div { border: 1px solid rgba(148,163,184,.16); padding: 6px 8px; } dt { color: #71829a; font: 9px 'JetBrains Mono', monospace; letter-spacing: .1em; } dd { margin: 2px 0 0; font: 12px 'JetBrains Mono', monospace; }
</style>
