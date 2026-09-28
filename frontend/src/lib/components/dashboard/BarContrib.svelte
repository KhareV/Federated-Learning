<script lang="ts">
	// BarContrib — horizontal SHAP-style bar chart
	let { features = [], maxAbs = 0.4, height = 260 }:
		{ features?: { name: string; value: number }[]; maxAbs?: number; height?: number } = $props();

	const barH = $derived(Math.max(16, (height - features.length * 4) / (features.length || 1)));
</script>

<div class="bar-contrib" style={`height:${height}px`}>
	{#each features as f, i}
		<div class="row" style={`height:${barH}px`}>
			<span class="name">{f.name}</span>
			<div class="track">
				<div class="zero"></div>
				<div
					class="bar"
					class:pos={f.value > 0}
					class:neg={f.value < 0}
					style={`
						width:${Math.abs(f.value) / maxAbs * 50}%;
						${f.value > 0 ? 'left:50%' : 'right:50%'};
					`}
				></div>
			</div>
			<span class="val" class:pos={f.value > 0} class:neg={f.value < 0}>
				{f.value > 0 ? '+' : ''}{f.value.toFixed(3)}
			</span>
		</div>
	{/each}
</div>

<style>
	.bar-contrib { display: flex; flex-direction: column; gap: 4px; }
	.row { display: grid; grid-template-columns: 160px 1fr 56px; align-items: center; gap: 8px; }
	.name { color: #94a3b8; font: 10px 'JetBrains Mono', monospace; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.track { position: relative; height: 10px; background: rgba(148,163,184,.08); border-radius: 2px; overflow: hidden; }
	.zero { position: absolute; left: 50%; top: 0; bottom: 0; width: 1px; background: rgba(148,163,184,.3); }
	.bar { position: absolute; top: 1px; bottom: 1px; border-radius: 2px; transition: width .3s ease; }
	.bar.pos { background: #3b82f6; box-shadow: 0 0 6px #3b82f640; }
	.bar.neg { background: #f87171; box-shadow: 0 0 6px #f8717140; }
	.val { font: 10px 'JetBrains Mono', monospace; text-align: right; }
	.val.pos { color: #60a5fa; }
	.val.neg { color: #f87171; }
</style>
