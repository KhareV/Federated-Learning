<script lang="ts">
	// One continuous start workflow for both run lengths. 3 rounds (default) keeps the ORIGINAL run form and the frozen 3-round contract untouched; 10 rounds uses the separate verified engine.
	import RunConfigForm from '$lib/components/product/federation/RunConfigForm.svelte';
	import type { FederationRunChoice } from '$lib/product/api';
	import type { RunLength, SourceMode, StudioCapabilities, StudioRunChoice } from '$lib/product/studio/types';
	let { disabled = false, liveBlocked = false, backendEnabled = true, capabilities = null, onStartThree, onStartTen }: {
		disabled?: boolean; liveBlocked?: boolean; backendEnabled?: boolean; capabilities?: StudioCapabilities | null;
		onStartThree: (choice: FederationRunChoice) => void; onStartTen: (choice: StudioRunChoice) => void } = $props();
	let length = $state<RunLength>(3);              // default stays 3
	let source = $state<SourceMode>('CANONICAL_SYNTHETIC');
	const tenAvailable = $derived(capabilities?.ten_round.available === true);
	const unsupported = $derived(capabilities?.ten_round.unsupported ?? {});
	const modes = $derived(capabilities?.ten_round.source_modes ?? ['CANONICAL_SYNTHETIC']);
	const blocked = $derived(!backendEnabled || disabled || liveBlocked || !tenAvailable);
	const OPTIONS: { value: RunLength; title: string; tag: string }[] = [{ value: 3, title: '★ 3 ROUNDS', tag: 'DEFAULT' }, { value: 10, title: '10 ROUNDS', tag: 'EXTENDED' }];
	const SOURCE_TEXT: Record<SourceMode, string> = { CANONICAL_SYNTHETIC: 'Canonical synthetic cohort — eight frozen synthetic clients.', LIVE_MONITORED_SITE_00: 'Live-monitored simulated SITE_00 — the simulated monitoring stream is genuinely executed and feeds SITE_00. This is NOT real patient physiology.' };
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
		<span class="cap">Communication rounds</span>
		<div class="opts">{#each OPTIONS as o (o.value)}
			<button type="button" role="radio" id={`rounds-${o.value}`} aria-checked={length === o.value} tabindex={length === o.value ? 0 : -1} class:on={length === o.value} disabled={o.value === 10 && !tenAvailable} data-testid={`rounds-${o.value}`} onclick={() => { length = o.value; }} onkeydown={radioKey}><b>{o.title}</b><small>{o.tag}</small></button>{/each}</div>
		{#if !tenAvailable}<p class="warn" role="status" data-testid="ten-unavailable">10 ROUNDS UNAVAILABLE: the connected backend does not provide the extended 10-round engine. The 3-round default is unaffected.</p>{/if}
		<table class="exp" aria-label="Expected communication structure"><thead><tr><th scope="col">Choice</th><th scope="col">Clients</th><th scope="col">Rounds</th><th scope="col">Expected accepted updates</th></tr></thead>
			<tbody><tr class:cur={length === 3}><th scope="row">Default</th><td>8</td><td>3</td><td data-testid="expected-3">24</td></tr><tr class:cur={length === 10}><th scope="row">Extended</th><td>8</td><td>10</td><td data-testid="expected-10">80</td></tr></tbody></table>
		<p class="dim">These are expected counts, not evidence of completed work. The running page shows only updates the coordinator actually accepted.</p>
	</div>
	{#if length === 3}
		<RunConfigForm {disabled} {liveBlocked} {backendEnabled} onSubmit={onStartThree} />
	{:else}
		<form class="cfg" onsubmit={(e) => { e.preventDefault(); if (!blocked) onStartTen({ run_length: 10, source_mode: source }); }} aria-label="Ten-round federation run configuration">
			<label><span>Run mode</span><select disabled data-testid="cfg10-run-type"><option>LIVE_RUN</option><option disabled>REPLAY — open a completed run instead</option></select></label>
			<p class="help">LIVE_RUN performs genuine local optimization and federation for ten rounds. A replay never trains: open a completed 10-round run from “Your federation runs”, or a recorded FL10 run, to replay it.</p>
			<label><span>Source mode</span><select bind:value={source} data-testid="cfg10-source">{#each modes as m (m)}<option value={m}>{m === 'CANONICAL_SYNTHETIC' ? 'Canonical synthetic cohort' : 'Live-monitored simulated SITE_00'}</option>{/each}</select></label>
			<p class="help" data-testid="cfg10-source-note">{SOURCE_TEXT[source]}</p>
			<label><span>Algorithm</span><select disabled data-testid="cfg10-algorithm"><option>FedAvg — sample-count-weighted averaging</option><option disabled>FedProx — unavailable</option></select></label>
			<p class="help" data-testid="cfg10-algorithm-note">{unsupported.FEDPROX ? `FedProx is disabled: ${unsupported.FEDPROX}.` : 'FedAvg only.'}</p>
			<label><span>Aggregation / protection mode</span><select disabled data-testid="cfg10-mode"><option>Plain aggregation</option><option disabled>SecAgg+ shadow — unavailable</option></select></label>
			<p class="help" data-testid="cfg10-mode-note">{unsupported.SECAGG_SHADOW ? `SecAgg+ shadow is disabled: ${unsupported.SECAGG_SHADOW}.` : 'Plain aggregation only.'} An unsupported setting is never silently reinterpreted as FedAvg/plain.</p>
			<dl class="fixed" aria-label="Fixed configuration"><div><dt>Clients</dt><dd>8</dd></div><div><dt>Rounds</dt><dd>10</dd></div><div><dt>Base</dt><dd>FL_INIT_V2</dd></div><div><dt>Evaluation</dt><dd>per committed round</dd></div></dl>
			{#if liveBlocked}<p class="warn" role="status">ONE LIVE FEDERATION RUN AT A TIME IN THIS ONE-LAPTOP DEMONSTRATION.</p>{/if}
			<button type="submit" disabled={blocked} data-testid="cfg10-submit">Create and start 10-round live run</button>
		</form>
	{/if}
</div>
<style>
	.rs { display: grid; gap: 14px; min-width: 0; } .sel { display: grid; gap: 8px; max-width: 560px; } .cap { font: 11px 'JetBrains Mono', monospace; letter-spacing: .06em; color: #94a3b8; } .opts { display: flex; flex-wrap: wrap; gap: 8px; }
	.opts button { display: grid; gap: 2px; text-align: left; background: #07101e; color: #e5f1f0; border: 1px solid rgba(148,163,184,.3); padding: 9px 14px; min-height: 48px; cursor: pointer; font: 13px Inter, sans-serif; } .opts button b { font: 600 13px 'Space Grotesk', sans-serif; letter-spacing: .04em; } .opts button small { font: 10px 'JetBrains Mono', monospace; letter-spacing: .12em; color: #71829a; } .opts button.on { border-color: #a78bfa; background: rgba(167,139,250,.1); } .opts button.on small { color: #c4b5fd; } .opts button:disabled { opacity: .45; cursor: not-allowed; } .opts button:focus-visible { outline: 2px solid #2bb8b0; outline-offset: 2px; }
	.exp { border-collapse: collapse; font-size: 12px; width: 100%; } .exp th, .exp td { border: 1px solid rgba(148,163,184,.18); padding: 5px 9px; text-align: left; color: #cbd5e1; } .exp thead th { color: #71829a; font: 10px 'JetBrains Mono', monospace; letter-spacing: .06em; } .exp tr.cur td, .exp tr.cur th { background: rgba(167,139,250,.08); }
	.cfg { display: grid; gap: 10px; max-width: 560px; min-width: 0; } label { display: flex; flex-direction: column; gap: 7px; min-width: 0; font: 11px 'JetBrains Mono', monospace; letter-spacing: .06em; color: #94a3b8; } select, .cfg button { max-width: 100%; box-sizing: border-box; font: 13px Inter, sans-serif; padding: 8px 10px; background: #07101e; color: #e5f1f0; border: 1px solid rgba(148,163,184,.3); } select:disabled { opacity: .7; } select:focus-visible, .cfg button:focus-visible { outline: 2px solid #2bb8b0; }
	.cfg button { background: #2bb8b0; color: #030712; font-weight: 600; cursor: pointer; } .cfg button:disabled { opacity: .45; cursor: not-allowed; } .help, .dim { margin: 0; color: #94a3b8; font-size: 12px; line-height: 1.5; } .warn { margin: 0; color: #fbbf24; font: 11px 'JetBrains Mono', monospace; }
	.fixed { display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: 6px; margin: 0; } .fixed div { border: 1px solid rgba(148,163,184,.16); padding: 6px 8px; } dt { color: #71829a; font: 9px 'JetBrains Mono', monospace; letter-spacing: .1em; text-transform: uppercase; } dd { margin: 3px 0 0; font-size: 13px; color: #e5f1f0; }
</style>
