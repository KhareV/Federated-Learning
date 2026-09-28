<script lang="ts">
	let { values = [88, 82, 91, 76, 84], labels = ['HR', 'SpO₂', 'ECG', 'PPG', 'BASELINE'], color = '#2bb8b0' }: { values?: number[]; labels?: string[]; color?: string } = $props();
	const size = 220; const center = size / 2; const radius = 76;
	function point(i: number, r: number) { const a = -Math.PI / 2 + (i / values.length) * Math.PI * 2; return `${(center + Math.cos(a) * r).toFixed(1)},${(center + Math.sin(a) * r).toFixed(1)}`; }
	const rings = $derived([.25, .5, .75, 1].map((scale) => Array.from({ length: values.length }, (_, i) => point(i, radius * scale)).join(' ')));
	const shape = $derived(values.map((value, i) => point(i, radius * value / 100)).join(' '));
</script>
<div class="radar"><svg viewBox="0 0 220 220" role="img" aria-label="Multimodal health radar"><defs><radialGradient id="radar-fill"><stop offset="0" stop-color={color} stop-opacity=".3" /><stop offset="1" stop-color={color} stop-opacity=".04" /></radialGradient></defs>{#each rings as ring}<polygon points={ring} fill="none" stroke="rgba(148,163,184,.14)" stroke-width="1" />{/each}{#each values as _, i}<line x1={center} y1={center} x2={point(i, radius).split(',')[0]} y2={point(i, radius).split(',')[1]} stroke="rgba(148,163,184,.12)" />{/each}<polygon points={shape} fill="url(#radar-fill)" stroke={color} stroke-width="2" style={`filter:drop-shadow(0 0 4px ${color}80)`} />{#each values as value, i}<circle cx={point(i, radius * value / 100).split(',')[0]} cy={point(i, radius * value / 100).split(',')[1]} r="3" fill={color} />{/each}</svg>{#each labels as label, i}<span class={`label label-${i}`}>{label}<b>{values[i]}</b></span>{/each}</div>
<style>
	.radar{position:relative;max-width:260px;margin:auto}.radar svg{display:block;width:100%;height:auto}.label{position:absolute;display:grid;gap:3px;color:#71829a;font:8px 'JetBrains Mono',monospace;letter-spacing:.08em}.label b{color:#d5e3e3;font-weight:500}.label-0{top:0;left:50%;transform:translateX(-50%);text-align:center}.label-1{right:-5px;top:42%;text-align:left}.label-2{right:5px;bottom:7%;text-align:left}.label-3{left:5px;bottom:7%;text-align:right}.label-4{left:-5px;top:42%;text-align:right}
</style>
