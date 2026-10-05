<script lang="ts">
	// STATIC ARCHITECTURE FACTS (not live data): two separate lanes. There is deliberately no arrow from the
	// candidate to MODEL_V2_FINAL or to live monitoring.
	let { releasedModel = 'MODEL_V2_FINAL' }: { releasedModel?: string } = $props();
</script>
<div class="lanes" data-testid="architecture-lanes">
	<section aria-labelledby="lane-a">
		<h3 id="lane-a">Lane A · Released monitoring</h3>
		<ol><li>{releasedModel}</li><li>SOFTWARE_SYSTEM_V2</li><li>Live monitoring</li></ol>
		<p><b>RELEASED RESEARCH DEFAULT</b> — unchanged by federation.</p>
	</section>
	<section aria-labelledby="lane-b">
		<h3 id="lane-b">Lane B · Federated development</h3>
		<ol><li>FL_INIT_V2</li><li>SIM_FL_SITE_00..07 (synthetic)</li><li>Local training</li><li>Model updates only</li><li>FedAvg / FedProx</li><li>Candidate</li><li>Structural governance</li><li>Sandbox-only status</li></ol>
		<p>Never automatically deployed. Architecture facts, not live values.</p>
	</section>
</div>
<style>
	.lanes { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 260px), 1fr)); gap: 10px; } section { border: 1px solid rgba(148,163,184,.16); padding: 12px 14px; min-width: 0; }
	h3 { margin: 0 0 8px; font: 500 14px 'Space Grotesk', sans-serif; color: #e5f1f0; } ol { list-style: none; margin: 0 0 8px; padding: 0; display: grid; gap: 4px; font: 11px 'JetBrains Mono', monospace; }
	li { padding: 4px 8px; border-left: 2px solid rgba(43,184,176,.5); background: rgba(43,184,176,.06); overflow-wrap: anywhere; } li:not(:last-child)::after { content: ' ↓'; color: #71829a; } p { margin: 0; color: #94a3b8; font-size: 12px; line-height: 1.5; }
</style>
