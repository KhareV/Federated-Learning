<script lang="ts">
	import { onMount } from 'svelte';
	import { getProductStore } from '$lib/product/state.svelte';
	import type { Architecture, Calibration, XaiCase, XaiIndex } from '$lib/product/observatory/evidence';
	const store = getProductStore();
	let arch = $state<Architecture | null>(null);
	let cal = $state<Calibration | null>(null);
	let error = $state<string | null>(null);
	let xai = $state<XaiIndex | null>(null);
	let xaiCase = $state<XaiCase | null>(null);
	let xaiError = $state<string | null>(null);
	let caseType = $state('TP');
	let xaiRequest = 0;
	let logit = $state(0);
	const T = $derived(Number(cal?.constants.temperature ?? NaN));
	const threshold = $derived(Number(cal?.constants.threshold ?? NaN));
	const sigmoid = (x: number) => 1 / (1 + Math.exp(-x));
	const rawP = $derived(sigmoid(logit));
	const calP = $derived(Number.isFinite(T) ? sigmoid(logit / T) : NaN);
	const blocks = $derived((arch?.dilations ?? []).map((d, i) => ({ d, i })));
	const fmt = (v: number, d = 4) => (Number.isFinite(v) ? v.toFixed(d) : '—');
	const xs = (t: number) => (t / 10) * 100;
	const inputPath = $derived.by(() => {
		const pts = xaiCase?.model_input ?? [];
		if (!pts.length) return '';
		const ys = pts.map((p) => p[1]); const lo = Math.min(...ys); const hi = Math.max(...ys);
		return pts.map((p, i) => `${i ? 'L' : 'M'}${xs(p[0]).toFixed(2)},${(48 - ((p[1] - lo) / (hi - lo || 1)) * 46).toFixed(2)}`).join(' ');
	});
	const bars = $derived.by(() => {
		const pts = xaiCase?.model_input ?? [];
		const peak = Math.max(1e-12, ...pts.map((p) => Math.abs(p[2])));
		return pts.filter((_, i) => i % 5 === 0).map((p) => ({ x: xs(p[0]), h: (Math.abs(p[2]) / peak) * 22, up: p[2] >= 0 }));
	});
	function loadCase(next: string) {
		caseType = next; const mine = ++xaiRequest; xaiError = null;
		void store.api.observatoryExplainabilityCase(next).then((c) => { if (mine === xaiRequest) xaiCase = c; }).catch((c) => { if (mine === xaiRequest) { xaiCase = null; xaiError = c instanceof Error ? c.message : String(c); } });
	}
	onMount(() => {
		void store.api.observatoryExplainability().then((v) => { xai = v; loadCase('TP'); }).catch((c) => { xaiError = c instanceof Error ? c.message : String(c); });
		void Promise.all([store.api.observatoryArchitecture(), store.api.observatoryCalibration()]).then(([a, c]) => { arch = a; cal = c; })
			.catch((c) => { error = c instanceof Error ? c.message : String(c); });
	});
</script>
<svelte:head><title>Model and calibration explorer | NHM</title></svelte:head>
<div class="eyebrow">NHM / RESEARCH OBSERVATORY / MODEL</div>
<h1>MODEL_V2_FINAL: architecture and calibration</h1>
<p class="lead">The architecture is derived by running an all-zero tensor through the real module (no weights, no data, no inference). Calibration constants are the frozen CAL_V2 values. The federated engineering candidate shares this architecture but is never calibrated by CAL_V2.</p>
{#if error}<p role="alert" class="err">Unavailable: {error}</p>{:else if !arch || !cal}<p class="dim" role="status">Loading…</p>{:else}
<section aria-label="Architecture"><h2>{arch.architecture_id} · {arch.parameter_count.toLocaleString()} parameters</h2>
	<ol class="flow" data-testid="architecture-flow"><li><b>Input</b><small>shape {arch.input_shape.join(' × ')}<br />per-window normalized ECG</small></li><li><b>Stem conv</b><small>{arch.channels} channels, stride 2</small></li>
		{#each blocks as b (b.i)}<li><b>Residual block {b.i + 1}</b><small>kernel {arch.kernel_size}, dilation {b.d}</small></li>{/each}
		<li><b>Global mean pool</b><small>{arch.pooling}</small></li><li><b>Dropout + linear</b><small>{arch.channels} → 1</small></li><li class="out"><b>Raw logit</b><small>shape {arch.output_shape.join(' × ')}</small></li></ol>
	<p class="dim">Causal-structure facts from the implementation: receptive field {arch.receptive_field_samples.toLocaleString()} input samples; dilations {arch.dilations.join(', ')}. {arch.notes.join(' ')}</p>
	<details><summary>TECHNICAL EVIDENCE · layer shapes and parameter counts</summary><div class="scroll"><table><thead><tr><th>Layer</th><th>Type</th><th>Parameters</th><th>Output shape (batch 1)</th></tr></thead><tbody>{#each arch.layers as l (l.name)}<tr><th scope="row">{l.name}</th><td>{l.type}</td><td>{l.parameters.toLocaleString()}</td><td>{l.output_shape.join(' × ')}</td></tr>{/each}</tbody></table></div></details></section>
<section aria-label="Calibration"><h2>CAL_V2 · {cal.label}</h2>
	<ol class="flow" data-testid="calibration-flow"><li><b>Raw logit</b><small>model output</small></li><li><b>Raw probability</b><small>{cal.semantics.raw}</small></li><li><b>÷ temperature {fmt(T, 6)}</b><small>{cal.semantics.calibrated}</small></li><li><b>Threshold ≥ {fmt(threshold, 6)}</b><small>fixed frozen policy binding</small></li></ol>
	<p class="warn">Calibrated on MIT-BIH source-domain records only ({String(cal.constants.calibration_window_count)} windows from {String(cal.constants.calibration_patient_count)} patients). No cross-domain, wearable, personal or clinical calibration is established. {cal.not_applicable_to}</p>
	<div class="demo" data-testid="hypothetical-calibration"><p class="tag">HYPOTHETICAL ARITHMETIC · not a monitoring output · does not change any frozen policy</p>
		<label>Hypothetical raw logit <input type="range" min="-300" max="300" step="1" bind:value={logit} aria-valuetext={`${logit}`} /></label>
		<p>logit {logit} → raw probability {fmt(rawP)} → calibrated {fmt(calP)} → {calP >= threshold ? 'at or above' : 'below'} the frozen threshold {fmt(threshold, 4)}. This is only the CAL_V2 formula; real outputs come from the server-side monitoring runtime.</p></div>
	<h3>Reliability (equal-width 10 bins)</h3>
	<div class="rel">{#each [{ name: 'Raw', series: cal.raw }, { name: 'After temperature scaling', series: cal.scaled }] as panel (panel.name)}<figure><figcaption>{panel.name} · mean predicted probability vs observed positive fraction</figcaption>
		<svg viewBox="-8 -4 116 116" role="img" aria-label={`${panel.name} reliability plot`}><rect x="0" y="0" width="100" height="100" class="frame" /><path d="M0,100 L100,0" class="diag" />{#each panel.series as b (b.lower)}{#if b.count > 0}<circle cx={b.mean_probability * 100} cy={(1 - b.observed_positive_fraction) * 100} r={1.6 + Math.min(3, Math.sqrt(b.count) / 6)} class="pt" />{/if}{/each}</svg></figure>{/each}</div>
	<p class="dim">Point area grows with bin count. Calibrated ECE {fmt(Number(cal.constants.calibrated_ece))} vs raw ECE {fmt(Number(cal.constants.raw_ece))} on the calibration population. {String(cal.constants.small_patient_sample_uncertainty)}</p>
	<details><summary>TECHNICAL EVIDENCE · frozen constants and hashes</summary><dl>{#each Object.entries(cal.constants) as [k, v] (k)}<div><dt>{k}</dt><dd>{typeof v === 'object' ? JSON.stringify(v) : String(v)}</dd></div>{/each}<div><dt>CAL_V2.json SHA256</dt><dd>{cal.source.calibration_sha256}</dd></div><div><dt>reliability.json SHA256</dt><dd>{cal.source.reliability_sha256}</dd></div></dl></details></section>
{/if}

<section aria-label="Explainability" data-testid="explainability"><h2>Frozen explainability examples (Integrated Gradients)</h2>
	<p class="tag">FROZEN RESEARCH EVIDENCE · MODEL_V2_FINAL · zero-baseline signed Integrated Gradients</p>
	{#if xaiError}<p role="alert" class="err">{xaiError}</p>{:else if !xai}<p class="dim" role="status">Loading…</p>{:else}
	<p class="warn">{xai.limitations.join(' ')} A highlighted region is never a confirmed clinical cause.</p>
	<div class="cases">{#each xai.cases as c (c.case_type)}<button class:on={caseType===c.case_type} aria-pressed={caseType===c.case_type} onclick={() => loadCase(c.case_type)}>{c.case_type} · record {c.record_id}</button>{/each}</div>
	{#if xaiCase}<figure><figcaption>Model input window (normalized, top) and signed attribution (below: purple = pushes the logit up, amber = down; bar height normalized by the window maximum). Time 0–10 s of the model window.</figcaption>
		<svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label={`Attribution overlay for the ${xaiCase.case_type} example`}><rect x="0" y="0" width="100" height="50" class="frame" /><path d={inputPath} class="inp" />{#each bars as b}<rect x={b.x} y={b.up ? 75 - b.h : 75} width="0.45" height={b.h} class={b.up ? 'up' : 'down'} />{/each}<path d="M0,75 L100,75" class="diag" /></svg></figure>
		<p class="dim">Mapped beats in the displayed source window: {xaiCase.annotations.filter((a) => a.position === 'INSIDE_MODEL_WINDOW').map((a) => `${a.symbol}→${a.aami_class}`).join(', ') || 'none'}. {xaiCase.overlay_normalization}. These four cases were chosen by a frozen rule (highest or lowest calibrated probability per outcome type), not as representative samples.</p>{/if}{/if}</section>
<p class="dim"><a href="/app/observatory">← Observatory</a> · <a href="/app/observatory/evidence">Scientific evidence</a> · <a href="/app/research/ml">Research ML summary</a></p>
<style>
	.eyebrow{color:#2bb8b0;font:10px 'JetBrains Mono',monospace;letter-spacing:.14em}h1{font:500 clamp(26px,4vw,40px) 'Space Grotesk',sans-serif;margin:8px 0}h2{font:500 18px 'Space Grotesk',sans-serif;margin:24px 0 10px}h3{font:500 15px 'Space Grotesk',sans-serif}.lead{max-width:860px;color:#a7b8c9;line-height:1.6}.dim,small,li,dd{color:#94a3b8;font-size:13px;line-height:1.6;overflow-wrap:anywhere}p{overflow-wrap:anywhere}.err{color:#fecdd3}a{color:#2bb8b0}.warn{border-left:3px solid #fbbf24;background:rgba(251,191,36,.06);padding:8px 12px;color:#fde68a;font-size:13px}
	.flow{list-style:none;margin:0 0 12px;padding:0;display:flex;flex-wrap:wrap;gap:8px}.flow li{border:1px solid rgba(43,184,176,.5);padding:8px 10px;background:#0a0f1f;display:grid;gap:3px;min-width:120px;flex:1 1 130px}.flow b{font:600 12px 'JetBrains Mono',monospace;color:#9fe8e3}.flow li.out{border-color:#a78bfa}.flow li.out b{color:#c4b5fd}
	.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:12px}th,td{padding:6px 9px;border-bottom:1px solid rgba(148,163,184,.16);text-align:left}thead th{font:10px 'JetBrains Mono',monospace;color:#71829a}details{margin-top:10px;border:1px solid rgba(148,163,184,.2);padding:8px 12px}summary{cursor:pointer;color:#2bb8b0;font:11px 'JetBrains Mono',monospace;min-height:24px}dl{display:grid;gap:4px}dl div{display:flex;gap:10px;flex-wrap:wrap}dt{color:#71829a;font:11px 'JetBrains Mono',monospace}
	.demo{border:1px dashed rgba(251,191,36,.5);padding:10px 14px;margin:12px 0;display:grid;gap:6px}.tag{margin:0;font:10px 'JetBrains Mono',monospace;color:#fbbf24;letter-spacing:.08em}.demo label{display:grid;gap:4px;font:11px 'JetBrains Mono',monospace;color:#cbd5e1}.demo input{width:100%;max-width:420px}
	.rel{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr));gap:14px}figure{margin:0;display:grid;gap:6px}figcaption{font:10px 'JetBrains Mono',monospace;color:#71829a}svg{width:100%;max-width:320px;height:auto;background:#050a15}.frame{fill:none;stroke:rgba(148,163,184,.35)}.diag{stroke:rgba(148,163,184,.4);stroke-dasharray:3 3;fill:none}.pt{fill:#a78bfa;opacity:.85}
	.cases{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}.cases button{background:#0a0f1f;color:#e2e8f0;border:1px solid rgba(148,163,184,.35);padding:6px 10px;min-height:32px;font:12px 'JetBrains Mono',monospace}.cases button.on{border-color:#2bb8b0;color:#9fe8e3}svg[aria-label^='Attribution']{width:100%;height:220px;background:#050a15}.inp{fill:none;stroke:#2bb8b0;stroke-width:1;vector-effect:non-scaling-stroke}.up{fill:#a78bfa}.down{fill:#fbbf24}
	a{display:inline-block;min-height:24px;line-height:24px}summary{min-height:24px}
</style>
