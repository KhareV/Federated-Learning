<script lang="ts">
	// STATIC ARCHITECTURE FACTS (not live data): two separate lanes with a wall between them. There is deliberately no arrow from the
	// federated lane into the released lane or into live monitoring.
	let { releasedModel = 'MODEL_V2_FINAL' }: { releasedModel?: string } = $props();
	const laneB = ['FL_INIT_V2', '8 synthetic clients', 'Local training', 'Aggregation', 'Federated candidate', 'Engineering sandbox'];
</script>
<div class="lanes" data-testid="architecture-lanes">
	<section class="a" aria-labelledby="lane-a">
		<span class="tag">RELEASED / FROZEN</span>
		<h3 id="lane-a">Lane A · Released monitoring</h3>
		<ol><li>{releasedModel}</li><li>SOFTWARE_SYSTEM_V2</li><li>Live research monitoring</li></ol>
		<p><b>RELEASED RESEARCH DEFAULT</b> — unchanged by federation.</p>
	</section>
	<div class="wall" role="separator" aria-label="No automatic promotion between the lanes"><span class="x" aria-hidden="true">⊘</span><b>NO AUTOMATIC PROMOTION</b><span class="s">The two lanes never connect.</span></div>
	<section class="b" aria-labelledby="lane-b">
		<span class="tag">FEDERATED DEVELOPMENT · ENGINEERING</span>
		<h3 id="lane-b">Lane B · Federated development</h3>
		<ol>{#each laneB as item}<li>{item}</li>{/each}</ol>
		<p>Never automatically deployed. Architecture facts, not live values.</p>
	</section>
</div>
<style>
	.lanes { display: grid; grid-template-columns: minmax(0, 1fr) auto minmax(0, 1.5fr); gap: 12px; align-items: stretch; } section { border: 1px solid rgba(148,163,184,.16); padding: 12px 14px; min-width: 0; }
	.a { border-color: rgba(43,184,176,.5); background: rgba(43,184,176,.05); } .b { border-color: rgba(167,139,250,.45); background: rgba(167,139,250,.05); } .tag { display: inline-block; margin-bottom: 6px; font: 9px 'JetBrains Mono', monospace; letter-spacing: .12em; padding: 2px 7px; border: 1px solid currentColor; } .a .tag { color: #2bb8b0; } .b .tag { color: #c4b5fd; }
	h3 { margin: 0 0 8px; font: 500 14px 'Space Grotesk', sans-serif; color: #e5f1f0; } ol { list-style: none; margin: 0 0 8px; padding: 0; display: grid; gap: 4px; font: 11px 'JetBrains Mono', monospace; }
	li { padding: 4px 8px; border-left: 2px solid rgba(148,163,184,.5); background: rgba(148,163,184,.06); overflow-wrap: anywhere; } .a li { border-left-color: rgba(43,184,176,.7); } .b li { border-left-color: rgba(167,139,250,.7); } li:not(:last-child)::after { content: ' ↓'; color: #71829a; } p { margin: 0; color: #94a3b8; font-size: 12px; line-height: 1.5; }
	.wall { display: grid; align-content: center; justify-items: center; gap: 4px; padding: 8px 10px; border-left: 2px dashed rgba(251,191,36,.6); border-right: 2px dashed rgba(251,191,36,.6); color: #fbbf24; text-align: center; font: 10px 'JetBrains Mono', monospace; letter-spacing: .1em; max-width: 120px; } .x { font-size: 22px; line-height: 1; } .s { color: #94a3b8; letter-spacing: 0; font-size: 11px; }
	@media (max-width: 820px) { .lanes { grid-template-columns: 1fr; } .wall { max-width: none; border: 0; border-top: 2px dashed rgba(251,191,36,.6); border-bottom: 2px dashed rgba(251,191,36,.6); grid-auto-flow: column; justify-content: center; gap: 10px; padding: 8px; } }
</style>
