<script lang="ts">
	// GaugeRing — SVG donut gauge
	let { value = 0, max = 100, size = 80, stroke = 8, color = '#2bb8b0', label = '' }:
		{ value?: number; max?: number; size?: number; stroke?: number; color?: string; label?: string } = $props();

	const r = (size - stroke) / 2;
	const circ = 2 * Math.PI * r;
	const pct = Math.min(1, Math.max(0, value / max));
	const dash = pct * circ;
</script>

<div class="gauge-wrap" style={`width:${size}px;height:${size}px`}>
	<svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
		<circle cx={size/2} cy={size/2} r={r} fill="none" stroke="rgba(148,163,184,.12)" stroke-width={stroke} />
		<circle
			cx={size/2} cy={size/2} r={r} fill="none"
			stroke={color} stroke-width={stroke}
			stroke-linecap="round"
			stroke-dasharray={`${dash} ${circ}`}
			stroke-dashoffset={circ / 4}
			style={`filter:drop-shadow(0 0 5px ${color}60)`}
		/>
	</svg>
	<div class="gauge-center">
		<strong style={`color:${color}`}>{value}<small>%</small></strong>
		{#if label}<span>{label}</span>{/if}
	</div>
</div>

<style>
	.gauge-wrap { position: relative; flex-shrink: 0; }
	.gauge-wrap svg { transform: rotate(-90deg); }
	.gauge-center { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px; }
	.gauge-center strong { font: 600 18px 'Space Grotesk', sans-serif; line-height: 1; }
	.gauge-center strong small { font: 10px 'JetBrains Mono', monospace; color: #71829a; margin-left: 1px; }
	.gauge-center span { color: #71829a; font: 8px 'JetBrains Mono', monospace; letter-spacing: .08em; text-transform: uppercase; }
</style>
