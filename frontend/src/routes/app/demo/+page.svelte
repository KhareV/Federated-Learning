<script lang="ts">
	import { focusHeading } from '$lib/product/observatory/focus';
	import { DEMO_STEPS, EVIDENCE_MODES, totalMinutes } from '$lib/product/demo-path';
	const total = totalMinutes();
</script>
<svelte:head><title>Guided demonstration | NHM</title></svelte:head>
<div class="eyebrow">NHM / GUIDED DEMONSTRATION</div>
<h1 tabindex="-1" use:focusHeading>One story, about {Math.round(total)} minutes</h1>
<p class="lead">From a signal entering the monitor to measured, bounded evidence. Each step says what to open, what the audience should take away, how its evidence is produced, and what to do if it fails. A research prototype, not clinical or diagnostic.</p>
<div class="modes" data-testid="demo-modes" role="note" aria-label="How each step's evidence is produced">
	{#each Object.values(EVIDENCE_MODES) as m (m.label)}<p><b>{m.label}</b> {m.meaning}</p>{/each}
</div>
<ol class="steps" data-testid="demo-steps">
	{#each DEMO_STEPS as s, i (s.id)}
		<li data-step={s.id}>
			<div class="top"><span class="n">{i + 1}</span><h2>{s.title}</h2><span class="mode" data-testid="demo-mode">{EVIDENCE_MODES[s.mode].label}</span><span class="min">{s.minutes} min</span></div>
			<dl>
				<div><dt>Do</dt><dd>{s.does}</dd></div>
				<div><dt>Understand</dt><dd>{s.understand}</dd></div>
				<div><dt>Say</dt><dd>{s.say}</dd></div>
				<div><dt>If it fails</dt><dd>{s.ifItFails}</dd></div>
			</dl>
			<a class="go" href={s.href}>Open {s.open} →</a>
		</li>
	{/each}
</ol>
<p class="dim">Pages that tell the same story in more detail: the <a href="/app/observatory/tour">evidence tour</a> and the <a href="/app/observatory/storyboard">run storyboard</a>. Before presenting, run <code>python -m scripts.demo_preflight</code> and launch with <code>--durable</code> so runs and History survive a restart.</p>
<style>
	.eyebrow { color: #2bb8b0; font: 10px 'JetBrains Mono', monospace; letter-spacing: .14em } h1 { margin: 10px 0 12px; font: 500 clamp(26px, 4vw, 40px) 'Space Grotesk', sans-serif }
	.lead { max-width: 760px; color: #a7b8c9; font-size: 14px; line-height: 1.6 } .modes { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 260px), 1fr)); gap: 8px; margin: 14px 0; }
	.modes p { margin: 0; padding: 8px 10px; border: 1px solid rgba(148,163,184,.2); color: #94a3b8; font-size: 12px; line-height: 1.5; overflow-wrap: anywhere } .modes b { display: block; color: #9fe7e1; font: 10.5px 'JetBrains Mono', monospace; letter-spacing: .08em }
	.steps { list-style: none; margin: 0; padding: 0; display: grid; gap: 10px } .steps li { border: 1px solid rgba(148,163,184,.25); background: rgba(8,13,22,.5); padding: 14px; display: grid; gap: 10px; min-width: 0 }
	.top { display: flex; flex-wrap: wrap; gap: 10px; align-items: center } .n { display: inline-grid; place-items: center; width: 26px; height: 26px; border: 1px solid #2bb8b0; color: #2bb8b0; font: 12px 'JetBrains Mono', monospace } h2 { margin: 0; font: 500 18px 'Space Grotesk', sans-serif; flex: 1 1 200px }
	.mode { font: 10.5px 'JetBrains Mono', monospace; letter-spacing: .06em; border: 1px solid rgba(148,163,184,.4); padding: 2px 7px; color: #cbd5e1 } .min { color: #71829a; font: 11px 'JetBrains Mono', monospace }
	dl { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 240px), 1fr)); gap: 8px; margin: 0 } dl div { border: 1px solid rgba(148,163,184,.14); padding: 8px 10px; min-width: 0 } dt { color: #71829a; font: 10.5px 'JetBrains Mono', monospace; letter-spacing: .08em } dd { margin: 4px 0 0; font-size: 13px; line-height: 1.5; color: #dbe7f0; overflow-wrap: anywhere }
	.go { display: inline-flex; align-items: center; min-height: 24px; color: #2bb8b0; font: 12px 'JetBrains Mono', monospace } .dim { color: #94a3b8; font-size: 12px; line-height: 1.5 } code { color: #9fe7e1 }
</style>
