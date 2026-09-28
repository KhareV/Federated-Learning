<script lang="ts">
	type Channel = { label: string; color: string; mode: 'ecg' | 'ppg' | 'spo2'; value: string; unit: string };
	let { channels = [], duration = '60 MINUTES' }: { channels?: Channel[]; duration?: string } = $props();

	const width = 900;
	const height = 150;
	const samples = 180;

	function series(mode: Channel['mode'], offset: number) {
		return Array.from({ length: samples }, (_, index) => {
			const x = index / samples;
			const cycle = mode === 'ecg' ? 8 : mode === 'ppg' ? 5 : 3;
			const phase = (x * cycle + offset) % 1;
			const spike = mode === 'ecg' ? Math.exp(-Math.pow((phase - 0.42) / 0.035, 2)) - 0.25 * Math.exp(-Math.pow((phase - 0.5) / 0.055, 2)) : mode === 'ppg' ? Math.pow(Math.max(0, Math.sin(Math.PI * phase)), 2) : 0.15 * Math.sin(phase * Math.PI * 2);
			const noise = Math.sin(index * 1.77 + offset * 8) * 0.025;
			return `${(x * width).toFixed(1)},${(offset * 0) + 34 - (spike + noise) * 26}`;
		});
	}
</script>

<article class="ribbon-panel">
	<header><div><span class="eyebrow">SIGNAL FUSION / MULTIMODAL</span><h3>One body. Three traces.</h3></div><span class="duration">{duration}</span></header>
	<div class="ribbon-grid">
		<div class="axis"><span>LIVE</span><span>−30m</span><span>−60m</span></div>
		{#each channels as channel, index}
			<div class="channel" style={`--channel:${channel.color}`}>
				<div class="channel-meta"><span>{channel.label}</span><strong>{channel.value}<small>{channel.unit}</small></strong></div>
				<svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-label={`${channel.label} signal trace`} role="img">
					<path class="baseline" d={`M0,34 H${width}`} />
					<polyline points={series(channel.mode, index * 0.13).join(' ')} />
				</svg>
			</div>
		{/each}
	</div>
	<footer><span>LOCAL EDGE / SENSOR ARRAY</span><span>QUALITY GATE / PASSED</span><span>STREAM / SYNTHETIC READY</span></footer>
</article>

<style>
	.ribbon-panel { border: 1px solid rgba(148,163,184,.2); background: linear-gradient(145deg, rgba(12,20,38,.96), rgba(5,10,21,.96)); box-shadow: inset 0 1px rgba(255,255,255,.03); }
	header { display:flex; justify-content:space-between; gap:20px; align-items:start; padding:24px 26px 18px; border-bottom:1px solid rgba(148,163,184,.14); }.eyebrow,.duration,footer { color:#71829a; font:9px 'JetBrains Mono',monospace; letter-spacing:.13em; }.eyebrow { color:#2bb8b0; } h3 { margin:10px 0 0; color:#eef7f6; font:500 26px/1 'Space Grotesk',sans-serif; }.duration { padding-top:2px; }
	.ribbon-grid { padding:20px 26px 8px; }.axis { display:flex; justify-content:space-between; margin-left:168px; color:#53647b; font:8px 'JetBrains Mono',monospace; }.channel { display:grid; grid-template-columns:150px minmax(0,1fr); align-items:center; min-height:64px; border-top:1px solid rgba(148,163,184,.08); }.channel-meta { display:flex; flex-direction:column; gap:6px; }.channel-meta span { color:#94a3b8; font:10px 'JetBrains Mono',monospace; letter-spacing:.08em; }.channel-meta strong { color:var(--channel); font:500 18px 'Space Grotesk',sans-serif; }.channel-meta small { margin-left:5px; color:#71829a; font:8px 'JetBrains Mono',monospace; }.channel svg { width:100%; height:54px; overflow:visible; background-image:linear-gradient(rgba(148,163,184,.06) 1px,transparent 1px),linear-gradient(90deg,rgba(148,163,184,.06) 1px,transparent 1px); background-size:36px 27px; }.baseline { fill:none; stroke:rgba(148,163,184,.17); stroke-dasharray:4 5; }.channel polyline { fill:none; stroke:var(--channel); stroke-width:2; vector-effect:non-scaling-stroke; filter:drop-shadow(0 0 4px var(--channel)); }
	footer { display:flex; justify-content:space-between; gap:15px; padding:16px 26px; border-top:1px solid rgba(148,163,184,.14); font-size:8px; }.duration { white-space:nowrap; }
	@media(max-width:700px){header,footer{display:block}.duration{margin-top:14px}.channel{grid-template-columns:105px minmax(0,1fr)}.axis{margin-left:105px}footer span{display:block;margin-top:6px}}
</style>
