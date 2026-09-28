<script lang="ts">
	let { title, subtitle, color = '#2bb8b0', kind = 'anomaly', value = '0.08', unit = '' }: { title: string; subtitle: string; color?: string; kind?: 'anomaly' | 'trend' | 'model'; value?: string; unit?: string } = $props();
	const width = 720;
	const height = 190;
	const points = Array.from({ length: 44 }, (_, index) => {
		const x = index / 43;
		let y = kind === 'anomaly' ? 0.34 + Math.sin(index * 0.44) * 0.08 + (index > 30 ? Math.sin(index * 1.7) * 0.13 : 0) : kind === 'model' ? 0.82 + x * 0.12 - Math.sin(index * 0.5) * 0.025 : 0.48 + Math.sin(index * 0.34) * 0.16 + x * 0.12;
		return `${(x * width).toFixed(1)},${(height - y * 150 - 18).toFixed(1)}`;
	});
</script>

<article class="graph-panel" style={`--graph:${color}`}>
	<header><div><span>{subtitle}</span><h3>{title}</h3></div><strong>{value}<small>{unit}</small></strong></header>
	<div class="graph"><svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img" aria-label={title}><defs><linearGradient id={`fill-${title.replaceAll(' ', '-')}`} x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color={color} stop-opacity=".28" /><stop offset="1" stop-color={color} stop-opacity="0" /></linearGradient></defs><path class="area" d={`M0,${height} L${points.join(' L')} L${width},${height} Z`} fill={`url(#fill-${title.replaceAll(' ', '-')})`} /><polyline points={points.join(' ')} /></svg><div class="threshold"><span>BASELINE</span><i></i></div></div>
	<footer><span>−60 MIN</span><span>NOW</span></footer>
</article>

<style>
	.graph-panel { border:1px solid rgba(148,163,184,.2); background:#080e1d; }.graph-panel header { display:flex; justify-content:space-between; gap:18px; padding:20px 22px 0; }.graph-panel header span,.graph-panel footer,.threshold span { color:#71829a; font:8px 'JetBrains Mono',monospace; letter-spacing:.12em; text-transform:uppercase; }.graph-panel h3 { margin:8px 0 0; color:#eef7f6; font:500 18px 'Space Grotesk',sans-serif; }.graph-panel strong { color:var(--graph); font:500 28px 'Space Grotesk',sans-serif; }.graph-panel strong small { margin-left:4px; color:#71829a; font:9px 'JetBrains Mono',monospace; }.graph { position:relative; height:170px; margin-top:8px; padding:18px 12px 0; background-image:linear-gradient(rgba(148,163,184,.06) 1px,transparent 1px),linear-gradient(90deg,rgba(148,163,184,.06) 1px,transparent 1px); background-size:36px 34px; }.graph svg { width:100%;height:100%;overflow:visible; }.graph polyline { fill:none;stroke:var(--graph);stroke-width:2;vector-effect:non-scaling-stroke;filter:drop-shadow(0 0 4px var(--graph)); }.threshold { position:absolute;left:12px;right:12px;top:48%;display:flex;align-items:center;gap:8px; }.threshold i { flex:1;border-top:1px dashed rgba(251,191,36,.45); }.threshold span { color:#fbbf24;font-size:7px; }.graph-panel footer { display:flex;justify-content:space-between;padding:0 22px 15px; }
</style>
