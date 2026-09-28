<script lang="ts">
	import MiniSpark from './MiniSpark.svelte';
	let { label, value, unit = '', tone = 'teal', detail = '', trend = '', values = [] }: { label: string; value: string | number; unit?: string; tone?: string; detail?: string; trend?: string; values?: number[] } = $props();
	const color = $derived(tone === 'rose' ? '#fb7185' : tone === 'cyan' ? '#38bdf8' : tone === 'amber' ? '#fbbf24' : '#2bb8b0');
</script>

<article class={`metric-tile metric-tile--${tone}`}>
	<div class="metric-head"><span>{label}</span>{#if trend}<b>{trend}</b>{/if}</div>
	<div class="metric-body"><div><div class="metric-value">{value}<small>{unit}</small></div>{#if detail}<div class="metric-detail">{detail}</div>{/if}</div>{#if values.length}<MiniSpark {values} color={color} width={92} height={34} animated={false} />{/if}</div>
</article>

<style>
	.metric-tile{min-height:112px;box-sizing:border-box;padding:16px 18px;border:1px solid rgba(148,163,184,.16);background:linear-gradient(145deg,rgba(11,19,35,.96),rgba(6,11,23,.96))}.metric-tile--teal{border-top:2px solid #2bb8b0}.metric-tile--cyan{border-top:2px solid #0ea5e9}.metric-tile--amber{border-top:2px solid #fbbf24}.metric-tile--rose{border-top:2px solid #fb7185}.metric-head,.metric-body{display:flex;align-items:center;justify-content:space-between;gap:12px}.metric-head span,.metric-detail{color:#64748b;font:8px 'JetBrains Mono',monospace;letter-spacing:.11em;text-transform:uppercase}.metric-head b{color:#2bb8b0;font:7px 'JetBrains Mono',monospace}.metric-value{margin-top:15px;color:#eef7f6;font:500 clamp(25px,3vw,36px)/1 'Space Grotesk',sans-serif}.metric-value small{margin-left:5px;color:#64748b;font:9px 'JetBrains Mono',monospace}.metric-detail{margin-top:7px;color:#71829a;font-size:7px}.metric-body :global(svg){align-self:end;margin-bottom:3px}
</style>
