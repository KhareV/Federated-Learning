<script lang="ts">
	// The guided demonstration, built to be presented from: a story map, a presenter mode with a timer and keyboard control, one card per step (do / understand / say / if it fails),
	// a "covered" tick per step and a pre-flight checklist. The content is pure data (demo-path.ts); nothing here claims more than the evidence supports.
	import { onMount } from 'svelte';
	import { ArrowLeft, ArrowRight, Check, ClipboardCopy, ExternalLink, LifeBuoy, Mic, Pause, Play, RotateCcw, Target, Eye } from '@lucide/svelte';
	import { focusHeading } from '$lib/product/observatory/focus';
	import { DEMO_STEPS, EVIDENCE_MODES, totalMinutes, type EvidenceMode } from '$lib/product/demo-path';

	const total = totalMinutes();
	const STORE = 'nhm-demo-covered';
	const TONE: Record<EvidenceMode, string> = { LIVE_COMPUTED: '#2bb8b0', PREPARED_RUN: '#fbbf24', FROZEN_EVIDENCE: '#a78bfa', RECORDED_SESSION: '#38bdf8', STORED_LIBRARY: '#4ade80', STATEMENT: '#94a3b8' };
	const starts = DEMO_STEPS.map((_, i) => DEMO_STEPS.slice(0, i).reduce((n, s) => n + s.minutes, 0));
	const fmt = (seconds: number) => `${Math.floor(Math.abs(seconds) / 60)}:${String(Math.floor(Math.abs(seconds) % 60)).padStart(2, '0')}`;

	let active = $state(0);
	let presenting = $state(false);
	let running = $state(false);
	let elapsed = $state(0);
	let covered = $state<string[]>([]);
	let copied = $state<string | null>(null);
	let stepEls: HTMLLIElement[] = [];

	onMount(() => {
		try { const raw = localStorage.getItem(STORE); if (raw) covered = (JSON.parse(raw) as unknown[]).filter((x): x is string => typeof x === 'string' && DEMO_STEPS.some((s) => s.id === x)); } catch { /* storage may be unavailable */ }
		const tick = setInterval(() => { if (running) elapsed += 1; }, 1000);
		return () => clearInterval(tick);
	});
	const persist = () => { try { localStorage.setItem(STORE, JSON.stringify(covered)); } catch { /* storage may be unavailable */ } };
	const isCovered = (id: string) => covered.includes(id);
	function toggleCovered(id: string) { covered = isCovered(id) ? covered.filter((x) => x !== id) : [...covered, id]; persist(); }
	function go(index: number, scroll = true) {
		active = Math.min(Math.max(index, 0), DEMO_STEPS.length - 1);
		if (scroll) stepEls[active]?.scrollIntoView?.({ block: 'center', behavior: typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
	}
	function startPresenting() { presenting = true; running = true; go(0); }
	function stopPresenting() { presenting = false; running = false; }
	function reset() { elapsed = 0; running = false; covered = []; persist(); active = 0; }
	function next() { if (!isCovered(DEMO_STEPS[active].id)) toggleCovered(DEMO_STEPS[active].id); go(active + 1); }
	function onKey(event: KeyboardEvent) {
		if (!presenting || event.altKey || event.ctrlKey || event.metaKey) return;
		const target = event.target as HTMLElement | null;
		if (target && (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))) return;
		if (event.key === 'ArrowRight') { event.preventDefault(); next(); }
		else if (event.key === 'ArrowLeft') { event.preventDefault(); go(active - 1); }
		else if (event.key === ' ' && target?.tagName !== 'BUTTON' && target?.tagName !== 'A') { event.preventDefault(); running = !running; }
		else if (event.key === 'Escape') stopPresenting();
	}
	async function copy(text: string, key: string) { try { await navigator.clipboard.writeText(text); copied = key; setTimeout(() => { if (copied === key) copied = null; }, 1400); } catch { copied = null; } }

	const plannedNow = $derived(starts[active] * 60);
	const drift = $derived(elapsed - plannedNow);
	const progress = $derived(Math.round((covered.length / DEMO_STEPS.length) * 100));
	const PREFLIGHT = [
		{ key: 'pre', label: 'Pre-flight the machine', cmd: 'PYTHONPATH=src:. .venv-studio311/bin/python -m scripts.demo_preflight', note: 'Checks the build, ports, model files and the workspace before you are on stage.' },
		{ key: 'run', label: 'Launch with a durable workspace', cmd: 'PYTHONUNBUFFERED=1 PYTHONPATH=src:. .venv-studio311/bin/python -m scripts.run_nhm --durable', note: 'Runs, History and candidates survive a restart. Do not rebuild the frontend while it is running.' },
		{ key: 'url', label: 'Open the site and sign in', cmd: 'http://127.0.0.1:4173/sign-in', note: 'Sign in with your own Clerk account before the audience arrives.' }
	];
	const CHECKS = ['The site is running and you are signed in', 'A completed run exists in “Your federation runs” (the fallback if a live run is slow)', 'A hardware session is listed in History (stored or the generated showcase)', 'You know the three boundaries: not clinical, synthetic labels, no physical-device verification'];
</script>
<svelte:head><title>Guided demonstration | NHM</title></svelte:head>
<svelte:window onkeydown={onKey} />

{#if presenting}
	<div class="bar" role="region" aria-label="Presenter controls" data-testid="presenter-bar">
		<div class="now"><span class="dot" style:background={TONE[DEMO_STEPS[active].mode]}></span><b>{active + 1}/{DEMO_STEPS.length}</b><span class="nowt">{DEMO_STEPS[active].title}</span></div>
		<div class="clock" aria-live="off"><span class="el" data-testid="presenter-elapsed">{fmt(elapsed)}</span><span class="of">of {Math.round(total)}:00</span>
			<span class="drift" class:late={drift > 30} class:early={drift < -30} data-testid="presenter-drift">{Math.abs(drift) <= 30 ? 'on pace' : drift > 0 ? `${fmt(drift)} behind` : `${fmt(drift)} ahead`}</span></div>
		<div class="ctl">
			<button type="button" onclick={() => go(active - 1)} disabled={active === 0} aria-label="Previous step"><ArrowLeft size={16} /></button>
			<button type="button" onclick={() => (running = !running)} aria-pressed={running} aria-label={running ? 'Pause the timer' : 'Resume the timer'} data-testid="presenter-toggle">{#if running}<Pause size={16} />{:else}<Play size={16} />{/if}</button>
			<button type="button" onclick={next} disabled={active === DEMO_STEPS.length - 1 && isCovered(DEMO_STEPS[active].id)} aria-label="Mark covered and go to the next step" data-testid="presenter-next"><ArrowRight size={16} /></button>
			<a class="open" href={DEMO_STEPS[active].href}>Open {DEMO_STEPS[active].open} <ExternalLink size={13} /></a>
			<button type="button" class="stop" onclick={stopPresenting}>Stop</button>
		</div>
	</div>
{/if}

<header class="hero">
	<div class="eyebrow">NHM / GUIDED DEMONSTRATION</div>
	<h1 tabindex="-1" use:focusHeading>One story, about {Math.round(total)} minutes</h1>
	<p class="lead">From a signal entering the monitor to measured, bounded evidence. Each step says what to open, what the audience should take away, how its evidence is produced, and what to do if it fails. A research prototype, not clinical or diagnostic.</p>
	<div class="cta">
		<button type="button" class="primary" onclick={startPresenting} data-testid="start-presenting"><Play size={16} /> Start presenting</button>
		<a class="ghost" href={DEMO_STEPS[0].href}>Open the first page</a>
		<span class="stat"><b>{DEMO_STEPS.length}</b> steps</span><span class="stat"><b>{total}</b> min planned</span>
		<span class="stat" data-testid="covered-count"><b>{covered.length}</b>/{DEMO_STEPS.length} covered</span>
	</div>
	<div class="meter" role="progressbar" aria-label="Steps covered" aria-valuemin="0" aria-valuemax="100" aria-valuenow={progress}><i style:width="{progress}%"></i></div>
</header>

<section aria-label="Story map" class="map" data-testid="story-map">
	<ol>
		{#each DEMO_STEPS as s, i (s.id)}
			<li style:flex="{s.minutes} 1 0" class:on={i === active} class:done={isCovered(s.id)}>
				<button type="button" onclick={() => go(i)} aria-current={i === active ? 'step' : undefined} style:--tone={TONE[s.mode]} title={`${s.title} · ${s.minutes} min`}>
					<span class="idx">{#if isCovered(s.id)}<Check size={12} />{:else}{i + 1}{/if}</span><span class="t">{s.title}</span><span class="m">{s.minutes} min</span>
				</button>
			</li>
		{/each}
	</ol>
</section>

<div class="modes" data-testid="demo-modes" role="note" aria-label="How each step's evidence is produced">
	{#each Object.entries(EVIDENCE_MODES) as [key, m] (m.label)}<p style:--tone={TONE[key as EvidenceMode]}><b>{m.label}</b> {m.meaning}</p>{/each}
</div>

<ol class="steps" data-testid="demo-steps">
	{#each DEMO_STEPS as s, i (s.id)}
		<li data-step={s.id} class:active={i === active} class:done={isCovered(s.id)} style:--tone={TONE[s.mode]} aria-current={i === active ? 'step' : undefined} bind:this={stepEls[i]}>
			<div class="rail"><span class="n">{#if isCovered(s.id)}<Check size={16} />{:else}{i + 1}{/if}</span></div>
			<div class="body">
				<div class="top"><h2>{s.title}</h2><span class="mode" data-testid="demo-mode">{EVIDENCE_MODES[s.mode].label}</span><span class="min">{s.minutes} min · starts at {fmt(starts[i] * 60)}</span></div>
				<div class="grid">
					<div class="cell do"><span class="k"><Target size={13} /> Do</span><p>{s.does}</p></div>
					<div class="cell"><span class="k"><Eye size={13} /> Understand</span><p>{s.understand}</p></div>
					<div class="cell say"><span class="k"><Mic size={13} /> Say</span><p>{s.say}</p></div>
					<div class="cell fail"><span class="k"><LifeBuoy size={13} /> If it fails</span><p>{s.ifItFails}</p></div>
				</div>
				<div class="foot">
					<a class="go" href={s.href}>Open {s.open} →</a>
					<button type="button" class="tick" onclick={() => toggleCovered(s.id)} aria-pressed={isCovered(s.id)} data-testid="covered-{s.id}">{isCovered(s.id) ? 'Covered' : 'Mark covered'}</button>
				</div>
			</div>
		</li>
	{/each}
</ol>

<section class="pre" aria-labelledby="pre-h">
	<h2 id="pre-h">Before you present</h2>
	<div class="cmds">
		{#each PREFLIGHT as p (p.key)}
			<div class="cmd"><b>{p.label}</b><code>{p.cmd}</code><span>{p.note}</span>
				<button type="button" onclick={() => copy(p.cmd, p.key)} aria-label={`Copy: ${p.label}`}><ClipboardCopy size={13} /> {copied === p.key ? 'Copied' : 'Copy'}</button></div>
		{/each}
	</div>
	<ul class="checks">{#each CHECKS as c (c)}<li>{c}</li>{/each}</ul>
</section>
<p class="dim">Pages that tell the same story in more detail: the <a href="/app/observatory/tour">evidence tour</a> and the <a href="/app/observatory/storyboard">run storyboard</a>. While presenting, use the arrow keys to move, space to pause the timer and Escape to stop.
	<button type="button" class="reset" onclick={reset}><RotateCcw size={12} /> Reset timer and ticks</button></p>

<style>
	.eyebrow { color: #2bb8b0; font: 10px 'JetBrains Mono', monospace; letter-spacing: .14em }
	.hero { position: relative; padding: 26px 22px 20px; margin: 0 0 14px; border: 1px solid rgba(148,163,184,.22); overflow: hidden; background:
		radial-gradient(900px 260px at 8% -20%, rgba(43,184,176,.22), transparent 60%), radial-gradient(700px 240px at 96% 0%, rgba(167,139,250,.18), transparent 60%), linear-gradient(180deg, rgba(12,20,38,.9), rgba(8,13,22,.6)); }
	h1 { margin: 10px 0 12px; font: 500 clamp(28px, 4.6vw, 46px)/1.08 'Space Grotesk', sans-serif; letter-spacing: -.01em }
	.lead { max-width: 780px; color: #b4c3d3; font-size: 14.5px; line-height: 1.65; margin: 0 0 16px }
	.cta { display: flex; flex-wrap: wrap; gap: 10px; align-items: center } .stat { color: #94a3b8; font: 11.5px 'JetBrains Mono', monospace; padding: 4px 9px; border: 1px solid rgba(148,163,184,.25) } .stat b { color: #e5f1f0 }
	.primary { display: inline-flex; gap: 8px; align-items: center; min-height: 40px; padding: 0 18px; background: #2bb8b0; color: #021312; font: 600 13px 'Space Grotesk', sans-serif; border: 0; cursor: pointer }
	.primary:hover { background: #3fd2c9 } .ghost { display: inline-flex; align-items: center; min-height: 40px; padding: 0 14px; border: 1px solid rgba(43,184,176,.55); color: #2bb8b0; font: 12px 'JetBrains Mono', monospace }
	.meter { margin-top: 16px; height: 3px; background: rgba(148,163,184,.18) } .meter i { display: block; height: 100%; background: linear-gradient(90deg, #2bb8b0, #a78bfa); transition: width .3s }
	.map ol { list-style: none; margin: 0 0 14px; padding: 0; display: flex; gap: 4px; flex-wrap: nowrap; overflow-x: auto } .map li { min-width: 118px }
	.map button { width: 100%; height: 100%; text-align: left; display: grid; gap: 4px; padding: 9px 10px; background: rgba(8,13,22,.6); border: 1px solid rgba(148,163,184,.2); border-top: 3px solid var(--tone); color: #cbd5e1; cursor: pointer; font-family: inherit }
	.map li.on button { background: rgba(12,20,38,.95); border-color: var(--tone); box-shadow: 0 0 0 1px var(--tone), 0 8px 24px -12px var(--tone) } .map li.done .t { color: #94a3b8 }
	.idx { display: inline-grid; place-items: center; width: 20px; height: 20px; border: 1px solid var(--tone); color: var(--tone); font: 11px 'JetBrains Mono', monospace } .t { font: 500 12.5px/1.25 'Space Grotesk', sans-serif } .m { color: #71829a; font: 10.5px 'JetBrains Mono', monospace }
	.modes { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 260px), 1fr)); gap: 8px; margin: 0 0 16px }
	.modes p { margin: 0; padding: 8px 10px; border: 1px solid rgba(148,163,184,.2); border-left: 3px solid var(--tone); color: #94a3b8; font-size: 12px; line-height: 1.5; overflow-wrap: anywhere } .modes b { display: block; color: var(--tone); font: 10.5px 'JetBrains Mono', monospace; letter-spacing: .08em }
	.steps { list-style: none; margin: 0; padding: 0; display: grid; gap: 12px } .steps > li { display: grid; grid-template-columns: 44px minmax(0, 1fr); gap: 12px; scroll-margin-top: 90px }
	.rail { display: flex; justify-content: center; position: relative } .rail::after { content: ''; position: absolute; top: 40px; bottom: -14px; width: 1px; background: linear-gradient(var(--tone), rgba(148,163,184,.15)) } .steps > li:last-child .rail::after { display: none }
	.n { display: inline-grid; place-items: center; width: 34px; height: 34px; border: 1.5px solid var(--tone); color: var(--tone); font: 13px 'JetBrains Mono', monospace; background: #050a14 } .done .n { background: var(--tone); color: #021312 }
	.body { border: 1px solid rgba(148,163,184,.22); background: rgba(8,13,22,.55); padding: 14px 16px; display: grid; gap: 12px; min-width: 0; transition: border-color .2s, box-shadow .2s } .active .body { border-color: var(--tone); box-shadow: 0 0 0 1px var(--tone), 0 18px 40px -24px var(--tone); background: rgba(12,20,38,.85) }
	.top { display: flex; flex-wrap: wrap; gap: 10px; align-items: center } h2 { margin: 0; font: 500 19px 'Space Grotesk', sans-serif; flex: 1 1 220px }
	.mode { font: 10.5px 'JetBrains Mono', monospace; letter-spacing: .06em; border: 1px solid var(--tone); padding: 2px 8px; color: var(--tone) } .min { color: #71829a; font: 11px 'JetBrains Mono', monospace }
	.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 250px), 1fr)); gap: 8px } .cell { border: 1px solid rgba(148,163,184,.14); padding: 9px 11px; min-width: 0; background: rgba(3,7,18,.35) } .cell.say { border-left: 3px solid #2bb8b0 } .cell.fail { border-left: 3px solid #fbbf24 }
	.k { display: inline-flex; gap: 6px; align-items: center; color: #71829a; font: 10.5px 'JetBrains Mono', monospace; letter-spacing: .08em; text-transform: uppercase } .cell p { margin: 6px 0 0; font-size: 13px; line-height: 1.55; color: #dbe6ee; overflow-wrap: anywhere }
	.foot { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; justify-content: space-between } .go { display: inline-flex; align-items: center; min-height: 28px; color: #2bb8b0; font: 12px 'JetBrains Mono', monospace }
	.tick { min-height: 28px; padding: 0 12px; background: transparent; border: 1px solid rgba(148,163,184,.4); color: #cbd5e1; font: 11px 'JetBrains Mono', monospace; cursor: pointer } .tick[aria-pressed='true'] { border-color: #4ade80; color: #4ade80 }
	.pre { margin: 22px 0 10px; border: 1px solid rgba(148,163,184,.22); padding: 16px; background: rgba(8,13,22,.5) } .pre h2 { font-size: 16px; margin: 0 0 12px }
	.cmds { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr)); gap: 10px } .cmd { display: grid; gap: 6px; border: 1px solid rgba(148,163,184,.16); padding: 10px 12px; min-width: 0; align-content: start } .cmd b { font: 500 13px 'Space Grotesk', sans-serif }
	.cmd code { display: block; padding: 7px 9px; background: #050a14; color: #9fe7e1; font: 11px/1.5 'JetBrains Mono', monospace; overflow-wrap: anywhere } .cmd span { color: #94a3b8; font-size: 12px; line-height: 1.5 }
	.cmd button { justify-self: start; display: inline-flex; gap: 6px; align-items: center; min-height: 28px; padding: 0 10px; border: 1px solid rgba(43,184,176,.5); background: transparent; color: #2bb8b0; font: 11px 'JetBrains Mono', monospace; cursor: pointer }
	.checks { margin: 12px 0 0; padding-left: 18px; display: grid; gap: 4px; color: #b4c3d3; font-size: 13px; line-height: 1.5 }
	.dim { color: #94a3b8; font-size: 12px; line-height: 1.6 } .reset { margin-left: 8px; display: inline-flex; gap: 6px; align-items: center; min-height: 26px; padding: 0 9px; border: 1px solid rgba(148,163,184,.3); background: transparent; color: #94a3b8; font: 11px 'JetBrains Mono', monospace; cursor: pointer }
	.bar { position: sticky; top: 0; z-index: 30; display: flex; flex-wrap: wrap; gap: 12px 20px; align-items: center; justify-content: space-between; padding: 10px 14px; margin: 0 0 12px; background: rgba(3,7,18,.94); backdrop-filter: blur(8px); border: 1px solid rgba(43,184,176,.5); box-shadow: 0 10px 30px -18px #2bb8b0 }
	.now { display: flex; align-items: center; gap: 10px; min-width: 0 } .dot { width: 10px; height: 10px; display: inline-block; flex: none } .nowt { font: 500 15px 'Space Grotesk', sans-serif; overflow-wrap: anywhere } .now b { font: 12px 'JetBrains Mono', monospace; color: #71829a }
	.clock { display: flex; align-items: baseline; gap: 8px } .el { font: 600 22px 'JetBrains Mono', monospace; color: #e5f1f0 } .of { color: #71829a; font: 11px 'JetBrains Mono', monospace } .drift { font: 11px 'JetBrains Mono', monospace; color: #4ade80 } .drift.late { color: #f87171 } .drift.early { color: #38bdf8 }
	.ctl { display: flex; gap: 6px; align-items: center; flex-wrap: wrap } .ctl button { display: inline-grid; place-items: center; min-width: 34px; min-height: 34px; background: rgba(12,20,38,.9); border: 1px solid rgba(148,163,184,.35); color: #e5f1f0; cursor: pointer } .ctl button:disabled { opacity: .4; cursor: default }
	.ctl .stop { padding: 0 12px; font: 11px 'JetBrains Mono', monospace; color: #f87171; border-color: rgba(248,113,113,.5) } .open { display: inline-flex; gap: 6px; align-items: center; min-height: 34px; padding: 0 12px; border: 1px solid rgba(43,184,176,.6); color: #2bb8b0; font: 12px 'JetBrains Mono', monospace }
	@media (max-width: 640px) { .steps > li { grid-template-columns: 1fr } .rail { display: none } .hero { padding: 18px 14px } }
	@media (prefers-reduced-motion: reduce) { .meter i, .body { transition: none } }
</style>
