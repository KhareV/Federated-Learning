<script lang="ts">
	import { onMount } from 'svelte';

	type Props = {
		mode?: 'ecg' | 'ppg' | 'spo2';
		speed?: number;
		amplitude?: number;
		zoom?: number;
		color?: string;
		instanceId?: string;
	};

	let {
		mode = 'ecg',
		speed = 0.55,
		amplitude = 0.75,
		zoom = 1,
		color = '#2dd4bf',
		instanceId = `wave-${Math.random().toString(36).slice(2, 10)}`
	}: Props = $props();

	let pathD = $state('');
	let reducedMotion = $state(false);

	let raf = 0;

	const width = 1200;
	const height = 220;
	const mid = height / 2;

	function gaussian(x: number, center: number, sigma: number) {
		const z = (x - center) / sigma;
		return Math.exp(-0.5 * z * z);
	}

	function ecgSignal(t: number) {
		const phase = ((t % 1) + 1) % 1;
		const p = 0.12 * gaussian(phase, 0.18, 0.025);
		const q = -0.16 * gaussian(phase, 0.39, 0.008);
		const r = 1.0 * gaussian(phase, 0.405, 0.007);
		const s = -0.30 * gaussian(phase, 0.43, 0.012);
		const tw = 0.28 * gaussian(phase, 0.68, 0.055);
		return p + q + r + s + tw;
	}

	function ppgSignal(t: number) {
		const phase = ((t % 1) + 1) % 1;
		return (Math.pow(Math.max(0, Math.sin(Math.PI * phase)), 1.8) * 0.78);
	}

	function valueAt(x: number, time: number) {
		const cycles = (mode === 'ecg' ? 7.2 : mode === 'ppg' ? 5.4 : 4.6) / zoom;
		const t = (x / width) * cycles + time * speed * 0.0015;

		if (mode === 'ecg') return ecgSignal(t);
		if (mode === 'ppg') return ppgSignal(t) - 0.32;

		return (0.12 * Math.sin(t * Math.PI * 2) + 0.025 * Math.sin(t * Math.PI * 11));
	}

	function render(time: number) {
		const segments: string[] = [];
		const samples = 520;

		for (let i = 0; i <= samples; i += 1) {
			const x = (i / samples) * width;
			const noise = mode === 'spo2' ? 0.008 * Math.sin(i * 0.8) : 0.015 * Math.sin(i * 1.43);
			const y = mid - (valueAt(x, time) + noise) * amplitude * 80;
			segments.push(`${i === 0 ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`);
		}

		pathD = segments.join(' ');
		if (!reducedMotion) raf = requestAnimationFrame(render);
	}

	onMount(() => {
		reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
		if (reducedMotion) {
			render(0);
			return;
		}
		raf = requestAnimationFrame(render);
		return () => cancelAnimationFrame(raf);
	});
</script>

<svg
	viewBox={`0 0 ${width} ${height}`}
	preserveAspectRatio="none"
	class="waveform"
	aria-hidden="true"
>
	<defs>
		<!-- Neon glow filter for ultra-aesthetic look -->
		<filter id={`${instanceId}-glow`} x="-20%" y="-20%" width="140%" height="140%">
			<feGaussianBlur stdDeviation="5" result="blur" />
			<feMerge>
				<feMergeNode in="blur" />
				<feMergeNode in="SourceGraphic" />
			</feMerge>
		</filter>

	</defs>

	<path
		d={`M0,${mid} H${width}`}
		stroke="rgba(255,255,255,0.1)"
		stroke-width="1"
		vector-effect="non-scaling-stroke"
		stroke-dasharray="4 4"
	/>

	<path
		d={pathD}
		fill="none"
		stroke={color}
		stroke-width="2.5"
		stroke-linecap="round"
		stroke-linejoin="round"
		filter={`url(#${instanceId}-glow)`}
		vector-effect="non-scaling-stroke"
	/>
</svg>

<style>
	.waveform {
		display: block;
		width: 100%;
		height: 100%;
		overflow: visible;
	}
</style>