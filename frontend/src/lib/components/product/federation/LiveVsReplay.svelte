<script lang="ts">
	// Static comparison used wherever a REPLAY selection could confuse an evaluator.
	let { highlight = null }: { highlight?: 'LIVE_RUN' | 'REPLAY' | null } = $props();
</script>
<div class="cmp" data-testid="live-vs-replay">
	<section class:on={highlight === 'LIVE_RUN'} aria-labelledby="lv-live"><h4 id="lv-live">LIVE RUN</h4>
		<ul><li><span class="ok" aria-hidden="true">✓</span> Local training executes</li><li><span class="ok" aria-hidden="true">✓</span> Updates are produced</li><li><span class="ok" aria-hidden="true">✓</span> Aggregation executes</li><li><span class="ok" aria-hidden="true">✓</span> A new candidate may be created</li></ul></section>
	<section class:on={highlight === 'REPLAY'} class="rp" aria-labelledby="lv-replay"><h4 id="lv-replay">REPLAY</h4>
		<ul><li><span class="no" aria-hidden="true">✕</span> No training executes</li><li><span class="no" aria-hidden="true">✕</span> No new updates</li><li><span class="no" aria-hidden="true">✕</span> No new candidate</li><li><span class="ok" aria-hidden="true">✓</span> Previous events are replayed</li></ul></section>
</div>
<style>
	.cmp { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 200px), 1fr)); gap: 8px; } section { border: 1px solid rgba(148,163,184,.2); padding: 8px 10px; min-width: 0; } section.on { border-color: #a78bfa; background: rgba(167,139,250,.07); } .rp.on { border-color: #94a3b8; background: rgba(148,163,184,.08); }
	h4 { margin: 0 0 6px; font: 10px 'JetBrains Mono', monospace; letter-spacing: .12em; color: #94a3b8; } ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 3px; font-size: 12px; color: #cbd5e1; } .ok { color: #2bb8b0; margin-right: 4px; } .no { color: #94a3b8; margin-right: 4px; }
</style>
