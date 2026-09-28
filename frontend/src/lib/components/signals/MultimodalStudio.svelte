<script lang="ts">
	import { onMount } from 'svelte';

	type SignalState = 'normal' | 'exertion' | 'nocturnal' | 'pvc';

	interface StateConfig {
		id: SignalState;
		label: string;
		bpm: number;
		spo2: number;
		ptt: number;
		hrv: number;
		status: string;
		statusColor: string;
		description: string;
	}

	const states: StateConfig[] = [
		{
			id: 'normal',
			label: 'Normal Sinus Rhythm',
			bpm: 72,
			spo2: 98.4,
			ptt: 218,
			hrv: 54,
			status: 'OPTIMAL CARDIAC SYNCHRONY',
			statusColor: '#0d9488',
			description: 'Balanced autonomic sympathovagal tone. Crisp QRS complexes followed by regular systolic volume ejection waves.'
		},
		{
			id: 'exertion',
			label: 'Physical Exertion (Tachycardia)',
			bpm: 116,
			spo2: 97.2,
			ptt: 172,
			hrv: 24,
			status: 'ELEVATED SYMPATHETIC DRIVE',
			statusColor: '#0284c7',
			description: 'Shortened R-R intervals with accelerated arterial pulse wave velocity and elevated cardiac output demand.'
		},
		{
			id: 'nocturnal',
			label: 'Deep Sleep (Bradycardia)',
			bpm: 48,
			spo2: 96.1,
			ptt: 264,
			hrv: 78,
			status: 'PARASYMPATHETIC DOMINANCE',
			statusColor: '#6366f1',
			description: 'Prominent sinus respiratory arrhythmia with extended diastolic intervals and vascular relaxation.'
		},
		{
			id: 'pvc',
			label: 'Ectopic PVC Anomaly',
			bpm: 84,
			spo2: 94.8,
			ptt: 290,
			hrv: 92,
			status: 'ARRHYTHMIA DETECTED BY EDGE',
			statusColor: '#e11d48',
			description: 'Premature ventricular depolarization with compensatory pause, captured and classified locally by on-device ML.'
		}
	];

	let currentState = $state<StateConfig>(states[0]);
	let canvasOsc: HTMLCanvasElement | null = $state(null);
	let canvasPoincare: HTMLCanvasElement | null = $state(null);
	let animId: number;
	let time = 0;

	// Draw Synchronized Multi-Channel Oscilloscope
	function drawOscilloscope() {
		if (!canvasOsc) return;
		const ctx = canvasOsc.getContext('2d');
		if (!ctx) return;

		const w = canvasOsc.width;
		const h = canvasOsc.height;
		const channelH = h / 3;

		ctx.clearRect(0, 0, w, h);

		// Channel divider lines
		ctx.strokeStyle = '#f1f5f9';
		ctx.lineWidth = 1;
		ctx.beginPath();
		ctx.moveTo(0, channelH);
		ctx.lineTo(w, channelH);
		ctx.moveTo(0, channelH * 2);
		ctx.lineTo(w, channelH * 2);
		ctx.stroke();

		// Channel Labels
		ctx.font = '600 10px JetBrains Mono, monospace';
		ctx.fillStyle = '#64748b';
		ctx.fillText('CH 1 // AD8232 ECG (LEAD-I)', 16, 22);
		ctx.fillText('CH 2 // MAX30102 PPG (OPTICAL)', 16, channelH + 22);
		ctx.fillText('CH 3 // ARTERIAL SpO2 DELTA', 16, channelH * 2 + 22);

		const speed = (currentState.bpm / 60) * 0.008;
		const cycleLen = (w / (currentState.bpm / 60)) * 0.45;

		// 1. Draw ECG Waveform (Channel 1)
		ctx.beginPath();
		ctx.strokeStyle = '#0f766e';
		ctx.lineWidth = 2;
		const mid1 = channelH * 0.62;

		for (let x = 0; x < w; x++) {
			const phase = ((x + time * speed * 4000) % cycleLen) / cycleLen;
			let ecg = 0;

			if (currentState.id === 'pvc' && Math.floor((x + time * 100) / cycleLen) % 4 === 2) {
				// Ectopic bizarre wide QRS
				if (phase > 0.35 && phase < 0.50) {
					ecg = Math.sin((phase - 0.35) * Math.PI / 0.15) * 45;
				}
			} else {
				// Normal P-Q-R-S-T
				if (phase > 0.20 && phase < 0.28) ecg = Math.sin((phase - 0.20) * Math.PI / 0.08) * 8; // P wave
				else if (phase > 0.38 && phase < 0.40) ecg = -Math.sin((phase - 0.38) * Math.PI / 0.02) * 12; // Q
				else if (phase > 0.40 && phase < 0.43) ecg = Math.sin((phase - 0.40) * Math.PI / 0.03) * 55; // R peak
				else if (phase > 0.43 && phase < 0.46) ecg = -Math.sin((phase - 0.43) * Math.PI / 0.03) * 18; // S
				else if (phase > 0.60 && phase < 0.76) ecg = Math.sin((phase - 0.60) * Math.PI / 0.16) * 14; // T wave
			}

			const y = mid1 - ecg;
			if (x === 0) ctx.moveTo(x, y);
			else ctx.lineTo(x, y);
		}
		ctx.stroke();

		// 2. Draw PPG Plethysmogram Waveform (Channel 2)
		ctx.beginPath();
		ctx.strokeStyle = '#0284c7';
		ctx.lineWidth = 2;
		const mid2 = channelH + channelH * 0.62;
		const pttOffset = (currentState.ptt / 1000) * cycleLen * (currentState.bpm / 60);

		for (let x = 0; x < w; x++) {
			const phase = (((x - pttOffset) + time * speed * 4000) % cycleLen) / cycleLen;
			let ppg = 0;
			if (phase > 0.40 && phase < 0.85) {
				const localP = (phase - 0.40) / 0.45;
				ppg = Math.pow(Math.sin(localP * Math.PI), 1.8) * 40;
				// Dicrotic notch
				if (localP > 0.55 && localP < 0.75) {
					ppg += Math.sin((localP - 0.55) * Math.PI / 0.2) * 8;
				}
			}

			const y = mid2 - ppg;
			if (x === 0) ctx.moveTo(x, y);
			else ctx.lineTo(x, y);
		}
		ctx.stroke();

		// 3. Draw SpO2 Oxygenation Waveform (Channel 3)
		ctx.beginPath();
		ctx.strokeStyle = '#6366f1';
		ctx.lineWidth = 2;
		const mid3 = channelH * 2 + channelH * 0.62;

		for (let x = 0; x < w; x++) {
			const phase = ((x + time * speed * 4000) % cycleLen) / cycleLen;
			const spo2Wave = Math.sin(phase * Math.PI * 2) * 14 + Math.sin(x * 0.05 + time * 2) * 3;
			const y = mid3 - spo2Wave;
			if (x === 0) ctx.moveTo(x, y);
			else ctx.lineTo(x, y);
		}
		ctx.stroke();

		time += 0.02;
		animId = requestAnimationFrame(drawOscilloscope);
	}

	// Draw Poincaré Scatter Plot for HRV Autonomic Tone
	function drawPoincare() {
		if (!canvasPoincare) return;
		const ctx = canvasPoincare.getContext('2d');
		if (!ctx) return;

		const w = canvasPoincare.width;
		const h = canvasPoincare.height;

		ctx.clearRect(0, 0, w, h);

		// Grid & 45-degree identity line
		ctx.strokeStyle = '#e2e8f0';
		ctx.lineWidth = 1;
		ctx.beginPath();
		ctx.moveTo(20, h - 20);
		ctx.lineTo(w - 20, 20);
		ctx.stroke();

		// Axis lines
		ctx.strokeStyle = '#cbd5e1';
		ctx.beginPath();
		ctx.moveTo(20, 20);
		ctx.lineTo(20, h - 20);
		ctx.lineTo(w - 20, h - 20);
		ctx.stroke();

		ctx.font = '500 9px JetBrains Mono, monospace';
		ctx.fillStyle = '#94a3b8';
		ctx.fillText('RR(n+1)', 24, 32);
		ctx.fillText('RR(n)', w - 45, h - 26);

		// Scatter points generated dynamically based on state HRV
		const center = w / 2;
		const spread = currentState.hrv * 0.85;

		const ptsCount = 38;
		for (let i = 0; i < ptsCount; i++) {
			const angle = (i / ptsCount) * Math.PI * 2;
			const rx = (Math.sin(angle * 3 + i) * spread * 0.6) + (Math.cos(i * 1.5) * spread * 0.3);
			const ry = rx + (Math.sin(i * 2.3) * spread * 0.4);

			ctx.beginPath();
			ctx.arc(center + rx, center - ry, 3.5, 0, Math.PI * 2);
			ctx.fillStyle = currentState.statusColor;
			ctx.fill();
		}
	}

	$effect(() => {
		if (currentState) {
			drawPoincare();
		}
	});

	onMount(() => {
		if (canvasOsc) {
			canvasOsc.width = 750;
			canvasOsc.height = 360;
		}
		if (canvasPoincare) {
			canvasPoincare.width = 240;
			canvasPoincare.height = 240;
		}
		animId = requestAnimationFrame(drawOscilloscope);
		drawPoincare();
		return () => cancelAnimationFrame(animId);
	});
</script>

<div class="multimodal-studio-wrap">
	<!-- Top Preset Controls -->
	<div class="state-presets-bar">
		<span class="presets-label">SIMULATION PRESETS:</span>
		<div class="presets-buttons">
			{#each states as st}
				<button
					class="preset-btn"
					class:preset-btn--active={currentState.id === st.id}
					onclick={() => currentState = st}
					type="button"
				>
					<span>{st.label}</span>
				</button>
			{/each}
		</div>
	</div>

	<!-- Main Workbench Grid -->
	<div class="workbench-grid">
		<!-- Left: Multi-Channel Synchronized Oscilloscope -->
		<div class="osc-panel">
			<div class="osc-topline">
				<div class="osc-title-group">
					<span class="osc-badge" style="color: {currentState.statusColor}; background: {currentState.statusColor}15;">
						{currentState.status}
					</span>
					<p>{currentState.description}</p>
				</div>
			</div>

			<div class="osc-canvas-frame">
				<canvas bind:this={canvasOsc} class="main-osc-canvas"></canvas>
			</div>
		</div>

		<!-- Right: Poincaré Dispersion & Telemetry Metrics -->
		<div class="telemetry-panel">
			<div class="vitals-metrics-column">
				<div class="metric-card">
					<span class="metric-label">HEART RATE</span>
					<strong class="metric-value">{currentState.bpm} <small>BPM</small></strong>
				</div>

				<div class="metric-card">
					<span class="metric-label">ARTERIAL SpO₂</span>
					<strong class="metric-value">{currentState.spo2} <small>%</small></strong>
				</div>

				<div class="metric-card">
					<span class="metric-label">PULSE TRANSIT (PTT)</span>
					<strong class="metric-value">{currentState.ptt} <small>ms</small></strong>
				</div>

				<div class="metric-card">
					<span class="metric-label">HRV DISPERSION (SDNN)</span>
					<strong class="metric-value">{currentState.hrv} <small>ms</small></strong>
				</div>
			</div>

			<!-- Poincaré Plot Box -->
			<div class="poincare-box">
				<span class="poincare-title">POINCARÉ AUTONOMIC DISPERSION</span>
				<div class="poincare-canvas-frame">
					<canvas bind:this={canvasPoincare} class="poincare-canvas"></canvas>
				</div>
			</div>
		</div>
	</div>
</div>

<style>
	.multimodal-studio-wrap {
		width: 100%;
		background: #ffffff;
		border: 1px solid #e2e8f0;
		border-radius: 28px;
		padding: 32px;
		box-shadow: 0 20px 50px rgba(15, 23, 42, 0.05);
	}

	/* Presets Bar */
	.state-presets-bar {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: 16px;
		padding-bottom: 24px;
		border-bottom: 1px solid #f1f5f9;
		margin-bottom: 24px;
	}

	.presets-label {
		font-family: var(--font-mono, monospace);
		font-size: 11px;
		font-weight: 600;
		color: #64748b;
		letter-spacing: 0.1em;
	}

	.presets-buttons {
		display: flex;
		gap: 8px;
		flex-wrap: wrap;
	}

	.preset-btn {
		padding: 8px 16px;
		border-radius: 999px;
		background: #f8fafc;
		border: 1px solid #e2e8f0;
		color: #475569;
		font-family: var(--font-sans, sans-serif);
		font-size: 13px;
		font-weight: 500;
		cursor: pointer;
		transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
	}

	.preset-btn:hover {
		background: #f1f5f9;
		color: #0f172a;
	}

	.preset-btn--active {
		background: #0f172a !important;
		border-color: #0f172a !important;
		color: #ffffff !important;
		font-weight: 600;
		box-shadow: 0 4px 12px rgba(15, 23, 42, 0.15);
	}

	/* Workbench Grid */
	.workbench-grid {
		display: grid;
		grid-template-columns: 1.35fr 0.65fr;
		gap: 28px;
	}

	.osc-panel {
		display: flex;
		flex-direction: column;
		justify-content: space-between;
	}

	.osc-topline {
		margin-bottom: 16px;
	}

	.osc-badge {
		display: inline-block;
		font-family: var(--font-mono, monospace);
		font-size: 10px;
		font-weight: 600;
		letter-spacing: 0.12em;
		padding: 4px 10px;
		border-radius: 6px;
		margin-bottom: 8px;
	}

	.osc-topline p {
		margin: 0;
		font-size: 14px;
		color: #475569;
		line-height: 1.5;
	}

	.osc-canvas-frame {
		width: 100%;
		height: 360px;
		background: #f8fafc;
		border: 1px solid #f1f5f9;
		border-radius: 20px;
		overflow: hidden;
	}

	.main-osc-canvas {
		width: 100%;
		height: 100%;
		display: block;
	}

	/* Telemetry Panel */
	.telemetry-panel {
		display: flex;
		flex-direction: column;
		gap: 20px;
	}

	.vitals-metrics-column {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: 12px;
	}

	.metric-card {
		padding: 16px;
		background: #f8fafc;
		border: 1px solid #f1f5f9;
		border-radius: 14px;
	}

	.metric-label {
		display: block;
		font-family: var(--font-mono, monospace);
		font-size: 9px;
		color: #64748b;
		margin-bottom: 4px;
		letter-spacing: 0.08em;
	}

	.metric-value {
		font-family: var(--font-sans, sans-serif);
		font-size: 24px;
		font-weight: 600;
		color: #0f172a;
	}

	.metric-value small {
		font-size: 12px;
		font-weight: 500;
		color: #94a3b8;
		font-family: var(--font-mono, monospace);
	}

	/* Poincaré Box */
	.poincare-box {
		padding: 18px;
		background: #f8fafc;
		border: 1px solid #f1f5f9;
		border-radius: 18px;
		display: flex;
		flex-direction: column;
		align-items: center;
	}

	.poincare-title {
		display: block;
		font-family: var(--font-mono, monospace);
		font-size: 10px;
		color: #64748b;
		letter-spacing: 0.1em;
		margin-bottom: 12px;
		text-align: center;
	}

	.poincare-canvas-frame {
		width: 220px;
		height: 220px;
		background: #ffffff;
		border: 1px solid #e2e8f0;
		border-radius: 14px;
		overflow: hidden;
		display: grid;
		place-items: center;
	}

	.poincare-canvas {
		width: 100%;
		height: 100%;
		display: block;
	}

	@media (max-width: 1050px) {
		.workbench-grid {
			grid-template-columns: 1fr;
		}
	}
</style>
