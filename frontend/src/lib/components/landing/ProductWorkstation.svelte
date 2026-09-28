<script lang="ts">
	import { onMount } from 'svelte';
	import PhysiologicalWaveform from '$lib/components/landing/PhysiologicalWaveform.svelte';

	type SimMode = 'normal' | 'brady' | 'tachy' | 'pvc';

	let simMode = $state<SimMode>('normal');
	let bpm = $state(72);
	let spo2 = $state(98);
	let respRate = $state(14);
	let statusText = $state('NORMAL SINUS RHYTHM');
	let statusColor = $state('#0d9488');

	function setMode(mode: SimMode) {
		simMode = mode;
		if (mode === 'normal') {
			bpm = 72;
			spo2 = 98;
			respRate = 14;
			statusText = 'NORMAL SINUS RHYTHM // OPTIMAL';
			statusColor = '#0d9488';
		} else if (mode === 'brady') {
			bpm = 48;
			spo2 = 97;
			respRate = 10;
			statusText = 'NOCTURNAL BRADYCARDIA // STABLE';
			statusColor = '#6366f1';
		} else if (mode === 'tachy') {
			bpm = 118;
			spo2 = 97;
			respRate = 22;
			statusText = 'EXERTIONAL TACHYCARDIA // ELEVATED';
			statusColor = '#0284c7';
		} else if (mode === 'pvc') {
			bpm = 84;
			spo2 = 95;
			respRate = 16;
			statusText = 'ECTOPIC PVC BEAT DETECTED';
			statusColor = '#e11d48';
		}
	}

	onMount(() => {
		const timer = setInterval(() => {
			if (simMode === 'normal') {
				bpm = 70 + Math.floor(Math.sin(Date.now() * 0.002) * 3);
			}
		}, 1500);
		return () => clearInterval(timer);
	});
</script>

<div class="workstation-frame">
	<!-- Workstation Chrome Header -->
	<div class="workstation-chrome">
		<div class="chrome-left">
			<div class="chrome-traffic-lights">
				<span></span><span></span><span></span>
			</div>
			<span class="chrome-session">SESSION // #NHM-84920-LIVE</span>
		</div>

		<div class="chrome-center">
			<span class="chrome-title">NHM CLINICAL MONITORING ENVIRONMENT</span>
		</div>

		<div class="chrome-right">
			<span class="live-badge" style="color: {statusColor};">
				<span class="live-dot" style="background: {statusColor}; box-shadow: 0 0 10px {statusColor};"></span>
				{statusText}
			</span>
		</div>
	</div>

	<!-- Workstation Body Grid -->
	<div class="workstation-body">
		<!-- Top Row: Interactive State Controller -->
		<div class="workstation-toolbar">
			<span class="toolbar-label">TELEMETRY SCENARIO SIMULATOR:</span>
			<div class="toolbar-btns">
				<button class="t-btn" class:t-btn--active={simMode === 'normal'} onclick={() => setMode('normal')} type="button">
					Normal Sinus (72 BPM)
				</button>
				<button class="t-btn" class:t-btn--active={simMode === 'brady'} onclick={() => setMode('brady')} type="button">
					Bradycardia (48 BPM)
				</button>
				<button class="t-btn" class:t-btn--active={simMode === 'tachy'} onclick={() => setMode('tachy')} type="button">
					Exertion (118 BPM)
				</button>
				<button class="t-btn" class:t-btn--active={simMode === 'pvc'} onclick={() => setMode('pvc')} type="button">
					PVC Arrhythmia
				</button>
			</div>
		</div>

		<!-- Middle: Primary Biosignal Waveform Console -->
		<div class="waveform-console">
			<div class="waveform-box">
				<div class="wave-topline">
					<span>LEAD-I CARDIAC BIOPOTENTIAL (AD8232)</span>
					<code>360 Hz // GAIN 1100x</code>
				</div>
				<div class="wave-screen">
					<PhysiologicalWaveform mode="ecg" speed={simMode === 'tachy' ? 0.9 : simMode === 'brady' ? 0.35 : 0.55} amplitude={0.78} />
				</div>
			</div>

			<div class="waveform-box">
				<div class="wave-topline">
					<span>PHOTOPLETHYSMOGRAM (MAX30102)</span>
					<code>660 / 880 nm DUAL-WAVE</code>
				</div>
				<div class="wave-screen">
					<PhysiologicalWaveform mode="ppg" speed={simMode === 'tachy' ? 0.9 : simMode === 'brady' ? 0.35 : 0.55} amplitude={0.65} />
				</div>
			</div>
		</div>

		<!-- Bottom: Real-Time Vitals Cards -->
		<div class="vitals-dashboard-row">
			<div class="vital-tile">
				<span class="v-label">HEART RATE</span>
				<strong class="v-val">{bpm} <small>BPM</small></strong>
				<span class="v-sub">R-R Variance: 54ms</span>
			</div>

			<div class="vital-tile">
				<span class="v-label">BLOOD OXYGEN (SpO₂)</span>
				<strong class="v-val">{spo2} <small>%</small></strong>
				<span class="v-sub">Calibrated Optical R: 0.52</span>
			</div>

			<div class="vital-tile">
				<span class="v-label">RESPIRATION RATE</span>
				<strong class="v-val">{respRate} <small>BR/MIN</small></strong>
				<span class="v-sub">ECG Derived Respiration (EDR)</span>
			</div>

			<div class="vital-tile">
				<span class="v-label">EDGE PRIVACY STATUS</span>
				<strong class="v-val text-teal">LOCAL ONLY</strong>
				<span class="v-sub">0 Bytes Uploaded</span>
			</div>
		</div>

		<!-- Footer CTA bar -->
		<div class="workstation-cta-bar">
			<div class="cta-left-copy">
				<strong>Ready to experience the continuous health telemetry environment?</strong>
				<p>Explore live historical graphs, signal replay, and privacy-preserving federated training logs.</p>
			</div>
			<a href="/monitor" class="enter-monitor-btn">
				<span>Launch Full Monitor Environment</span>
				<span>↗</span>
			</a>
		</div>
	</div>
</div>

<style>
	.workstation-frame {
		width: 100%;
		background: #ffffff;
		border: 1px solid #e2e8f0;
		border-radius: 28px;
		box-shadow: 0 40px 100px rgba(15, 23, 42, 0.08);
		overflow: hidden;
	}

	/* Chrome Header */
	.workstation-chrome {
		display: grid;
		grid-template-columns: 1fr auto 1fr;
		align-items: center;
		height: 52px;
		padding: 0 24px;
		background: #f8fafc;
		border-bottom: 1px solid #e2e8f0;
		font-family: var(--font-mono, monospace);
		font-size: 11px;
	}

	.chrome-left {
		display: flex;
		align-items: center;
		gap: 16px;
	}

	.chrome-traffic-lights {
		display: flex;
		gap: 6px;
	}
	.chrome-traffic-lights span {
		width: 10px;
		height: 10px;
		border-radius: 50%;
	}
	.chrome-traffic-lights span:nth-child(1) { background: #fca5a5; }
	.chrome-traffic-lights span:nth-child(2) { background: #fcd34d; }
	.chrome-traffic-lights span:nth-child(3) { background: #86efac; }

	.chrome-session {
		color: #64748b;
	}

	.chrome-title {
		font-weight: 600;
		color: #0f172a;
		letter-spacing: 0.05em;
	}

	.chrome-right {
		justify-self: end;
	}

	.live-badge {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		font-weight: 600;
	}

	.live-dot {
		width: 7px;
		height: 7px;
		border-radius: 50%;
	}

	/* Body */
	.workstation-body {
		padding: 32px;
		display: flex;
		flex-direction: column;
		gap: 24px;
	}

	/* Toolbar */
	.workstation-toolbar {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: 16px;
		padding-bottom: 20px;
		border-bottom: 1px solid #f1f5f9;
	}

	.toolbar-label {
		font-family: var(--font-mono, monospace);
		font-size: 11px;
		font-weight: 600;
		color: #64748b;
		letter-spacing: 0.08em;
	}

	.toolbar-btns {
		display: flex;
		gap: 8px;
		flex-wrap: wrap;
	}

	.t-btn {
		padding: 6px 14px;
		border-radius: 999px;
		background: #f8fafc;
		border: 1px solid #e2e8f0;
		color: #475569;
		font-family: var(--font-sans, sans-serif);
		font-size: 12px;
		font-weight: 500;
		cursor: pointer;
		transition: all 0.2s;
	}

	.t-btn:hover {
		background: #f1f5f9;
		color: #0f172a;
	}

	.t-btn--active {
		background: #0f172a !important;
		border-color: #0f172a !important;
		color: #ffffff !important;
		font-weight: 600;
	}

	/* Waveforms */
	.waveform-console {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 20px;
	}

	.waveform-box {
		background: #f8fafc;
		border: 1px solid #f1f5f9;
		border-radius: 18px;
		padding: 16px;
	}

	.wave-topline {
		display: flex;
		justify-content: space-between;
		font-family: var(--font-mono, monospace);
		font-size: 10px;
		color: #64748b;
		margin-bottom: 8px;
	}
	.wave-topline code { color: #0d9488; }

	.wave-screen {
		height: 120px;
		background: #ffffff;
		border: 1px solid #e2e8f0;
		border-radius: 12px;
		overflow: hidden;
	}

	/* Vitals */
	.vitals-dashboard-row {
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: 16px;
	}

	.vital-tile {
		padding: 20px;
		background: #f8fafc;
		border: 1px solid #f1f5f9;
		border-radius: 18px;
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.v-label {
		font-family: var(--font-mono, monospace);
		font-size: 9px;
		color: #64748b;
		letter-spacing: 0.08em;
	}

	.v-val {
		font-family: var(--font-sans, sans-serif);
		font-size: 28px;
		font-weight: 600;
		color: #0f172a;
		line-height: 1.1;
		margin: 4px 0;
	}

	.v-val small {
		font-size: 13px;
		font-weight: 500;
		color: #94a3b8;
		font-family: var(--font-mono, monospace);
	}

	.v-sub {
		font-size: 11px;
		color: #64748b;
	}

	.text-teal {
		color: #0d9488 !important;
	}

	/* CTA Bar */
	.workstation-cta-bar {
		display: flex;
		justify-content: space-between;
		align-items: center;
		flex-wrap: wrap;
		gap: 20px;
		padding-top: 24px;
		border-top: 1px solid #f1f5f9;
	}

	.cta-left-copy strong {
		display: block;
		font-size: 15px;
		color: #0f172a;
		margin-bottom: 2px;
	}

	.cta-left-copy p {
		margin: 0;
		font-size: 13px;
		color: #64748b;
	}

	.enter-monitor-btn {
		display: inline-flex;
		align-items: center;
		gap: 12px;
		padding: 14px 24px;
		background: #0f172a;
		border-radius: 999px;
		color: #ffffff !important;
		font-family: var(--font-mono, monospace);
		font-size: 12px;
		font-weight: 600;
		letter-spacing: 0.05em;
		transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
	}

	.enter-monitor-btn span { color: #ffffff !important; }

	.enter-monitor-btn:hover {
		background: #1e293b;
		transform: translateY(-2px);
		box-shadow: 0 10px 25px rgba(15, 23, 42, 0.14);
	}

	@media (max-width: 1050px) {
		.workstation-chrome {
			grid-template-columns: 1fr;
			height: auto;
			padding: 16px;
			gap: 10px;
		}
		.chrome-right {
			justify-self: start;
		}
		.waveform-console {
			grid-template-columns: 1fr;
		}
		.vitals-dashboard-row {
			grid-template-columns: repeat(2, 1fr);
		}
	}

	@media (max-width: 640px) {
		.vitals-dashboard-row {
			grid-template-columns: 1fr;
		}
	}
</style>
