<script lang="ts">
	// Coherent claim strip shown on every federation / model page.
	let { runType = null }: { runType?: string | null } = $props();
</script>
<div class="claims" role="note" aria-label="Federation claims">
	<span class="eng">ENGINEERING FEDERATION DEMO</span>
	<span>RESEARCH PROTOTYPE</span>
	<span>SIMULATED CLIENTS</span>
	<span>NOT CLINICAL</span>
	<span>NOT DEPLOYED</span>
	{#if runType === 'REPLAY'}<span class="replay" data-testid="replay-badge">REPLAY · NO TRAINING IS EXECUTING</span>{/if}
</div>
<style>
	.claims { display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 16px; font: 10px 'JetBrains Mono', monospace; letter-spacing: .1em; }
	.claims span { padding: 3px 8px; border: 1px solid rgba(148,163,184,.3); color: #94a3b8; }
	.claims .eng { border-color: rgba(43,184,176,.6); color: #2bb8b0; }
	.claims .replay { border-color: rgba(251,191,36,.7); color: #fbbf24; }
</style>
