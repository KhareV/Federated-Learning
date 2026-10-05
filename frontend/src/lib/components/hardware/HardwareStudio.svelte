<script lang="ts">
	import WatchScene from '$lib/components/landing/WatchScene.svelte';
	import PhysiologicalWaveform from '$lib/components/landing/PhysiologicalWaveform.svelte';

	interface Subsystem {
		id: string;
		index: string;
		name: string;
		tag: string;
		summary: string;
		waveformMode: 'ecg' | 'ppg' | 'spo2';
		specs: { key: string; val: string; note: string }[];
		highlights: string[];
	}

	// All specs below describe an UNBUILT concept sketch (LEGACY_FIRMWARE_V0, see
	// docs/LEGACY_FIRMWARE_V0_FINDINGS.md). T004 (bench hardware verification) is BLOCKED;
	// T030 (wearable validation) is NOT_STARTED pending real hardware. Nothing here is a
	// verified spec, a shipping product, or live sensor data.
	const subsystems: Subsystem[] = [
		{
			id: 'ecg_frontend',
			index: '01',
			name: 'ECG Analog Front-End (Concept)',
			tag: 'CARDIAC ELECTRICAL SENSING -- UNVERIFIED',
			summary: 'Concept sketch for ECG signal conditioning. The exact front-end chip, gain, filtering, and electrode placement have not been bench-verified against physical hardware.',
			waveformMode: 'ecg',
			specs: [
				{ key: 'CMRR', val: 'Unverified', note: 'Not bench-tested' },
				{ key: 'SAMPLING RATE', val: 'Unverified', note: 'See HW01 bench verification (BLOCKED)' },
				{ key: 'ADC RESOLUTION', val: 'Unverified', note: 'Not bench-tested' },
				{ key: 'POWER DRAW', val: 'Unverified', note: 'Not bench-tested' }
			],
			highlights: [
				'Concept sketch only -- no physical front-end has been bench-verified',
				'Electrode placement and lead-off handling remain VERIFICATION_REQUIRED',
				'T004 bench hardware verification is BLOCKED_HARDWARE'
			]
		},
		{
			id: 'ppg_optical',
			index: '02',
			name: 'PPG Optical Sensor (Concept)',
			tag: 'PULSE OXIMETRY & PPG -- UNVERIFIED',
			summary: 'Concept sketch for an optical PPG/SpO2 sensor. The legacy firmware sketch referenced a MAX3010x-family library call, but register configuration and achieved sample rate are unverified.',
			waveformMode: 'ppg',
			specs: [
				{ key: 'EMITTER SPECTRA', val: 'Unverified', note: 'Not bench-tested' },
				{ key: 'SNR', val: 'Unverified', note: 'Not bench-tested' },
				{ key: 'SAMPLE TIMING', val: 'Unverified', note: 'Library arguments observed, not verified' },
				{ key: 'FIFO DEPTH', val: 'Unverified', note: 'Not bench-tested' }
			],
			highlights: [
				'Legacy sketch computes a PPG-derived pulse-rate estimate, not an ECG heart rate',
				'SpO2 ratio heuristic observed in source is unverified against reference oximetry',
				'No physical enclosure or glass cover has been fabricated or tested'
			]
		},
		{
			id: 'edge_mcu',
			index: '03',
			name: 'Edge Microcontroller (Concept)',
			tag: 'FIRMWARE CONCEPT -- NO ON-DEVICE INFERENCE',
			summary: 'Concept firmware target (ESP32-class). Today, inference runs server-side via the frozen GATEWAY_ARTIFACT_V2 CPU runtime (default research runtime) behind POST /v1/infer-window -- not on this or any device.',
			waveformMode: 'ecg',
			specs: [
				{ key: 'ON-DEVICE INFERENCE', val: 'Not Implemented', note: 'Inference is server-side (default research runtime)' },
				{ key: 'CLOCK / MEMORY', val: 'Unverified', note: 'Not bench-tested' },
				{ key: 'INFERENCE TIME', val: 'See reports/t029/latency_summary.json', note: 'Server-side CPU gateway, 1000-window benchmark' },
				{ key: 'CRYPTO', val: 'Not Implemented', note: 'No device-side crypto claim' }
			],
			highlights: [
				'No on-device/edge ML inference is implemented anywhere in this project',
				'Server-side CPU gateway benchmark is the only measured latency evidence',
				'This tier is a future-direction concept, not a built or verified capability'
			]
		},
		{
			id: 'power_radio',
			index: '04',
			name: 'Power & Radio (Concept)',
			tag: 'POWER & TELEMETRY -- UNVERIFIED',
			summary: 'Concept power/radio sketch. No physical battery, enclosure, or radio link has been built, certified, or bench-tested, and no "medical-grade" claim is made about any component.',
			waveformMode: 'spo2',
			specs: [
				{ key: 'BATTERY LIFE', val: 'Unverified', note: 'No physical unit built' },
				{ key: 'CAPACITY', val: 'Unverified', note: 'No physical unit built' },
				{ key: 'RADIO PROTOCOL', val: 'Unverified', note: 'No physical unit built' },
				{ key: 'ENCLOSURE RATING', val: 'Not Tested', note: 'No IP rating claimed' }
			],
			highlights: [
				'No "medical-grade" claim is made about any hardware component',
				'No water/dust ingress rating has been tested or is claimed',
				'Physical wearable validation (WEARABLE_V1) remains pending real hardware'
			]
		}
	];

	let active = $state(subsystems[0]);
</script>

<div class="hardware-pro-showcase">
	<!-- Left: 3D Model Explorer with Tactile Reticle Pins -->
	<div class="viewport-card">
		<div class="viewport-badge-row">
			<span class="pro-tag">NHM-01 CONCEPT MODEL (3D RENDER, NOT A SHIPPING PRODUCT)</span>
			<span class="pro-meta">ILLUSTRATIVE INDUSTRIAL DESIGN ONLY</span>
		</div>

		<!-- 3D Interactive Stage -->
		<div class="model-canvas-stage">
			<WatchScene />

			<!-- Clean Reticle Interactive Pins -->
			<div class="pins-overlay">
				{#each subsystems as sub, i}
					<button
						class="pin-button pin-button--{i + 1}"
						class:pin-button--active={active.id === sub.id}
						onclick={() => active = sub}
						type="button"
					>
						<span class="pin-dot"></span>
						<span class="pin-label">{sub.index} · {sub.name.split(' ')[0]}</span>
					</button>
				{/each}
			</div>
		</div>

		<!-- Horizontal Subsystem Tab Bar -->
		<div class="component-tab-bar">
			{#each subsystems as sub}
				<button
					class="component-tab"
					class:component-tab--active={active.id === sub.id}
					onclick={() => active = sub}
					type="button"
				>
					<span class="tab-number">{sub.index}</span>
					<span class="tab-title">{sub.name.split(' ')[0]}</span>
				</button>
			{/each}
		</div>
	</div>

	<!-- Right: Professional Engineering Blueprint & Spec Matrix -->
	<div class="blueprint-card">
		<div class="blueprint-header">
			<span class="blueprint-category">{active.tag}</span>
			<h3>{active.name}</h3>
			<p class="blueprint-summary">{active.summary}</p>
		</div>

		<!-- Live Signal Stream for Active Subsystem -->
		<div class="signal-preview-box">
			<div class="preview-topline">
				<span>SIMULATED WAVEFORM // {active.name.split(' ')[0]}</span>
				<span class="live-pill"><span class="pulse-dot"></span> ILLUSTRATIVE, NOT LIVE HARDWARE</span>
			</div>
			<div class="preview-waveform">
				<PhysiologicalWaveform mode={active.waveformMode} speed={0.55} amplitude={0.65} />
			</div>
		</div>

		<!-- Engineering Specifications Matrix -->
		<div class="specs-grid">
			{#each active.specs as spec}
				<div class="spec-tile">
					<span class="spec-k">{spec.key}</span>
					<strong class="spec-v">{spec.val}</strong>
					<small class="spec-n">{spec.note}</small>
				</div>
			{/each}
		</div>

		<!-- Key Architectural Highlights -->
		<div class="highlights-box">
			<span class="highlights-label">ENGINEERING ARCHITECTURE</span>
			<ul>
				{#each active.highlights as item}
					<li>
						<span class="check-icon">✓</span>
						<span>{item}</span>
					</li>
				{/each}
			</ul>
		</div>
	</div>
</div>

<style>
	.hardware-pro-showcase {
		display: grid;
		grid-template-columns: 1.15fr 0.85fr;
		gap: 32px;
		align-items: stretch;
		width: 100%;
	}

	.viewport-card, .blueprint-card {
		background: #090d16;
		border: 1px solid rgba(255, 255, 255, 0.08);
		border-radius: 28px;
		padding: 32px;
		box-shadow: 0 30px 80px rgba(0, 0, 0, 0.6);
		position: relative;
	}

	/* Left Viewport */
	.viewport-card {
		display: flex;
		flex-direction: column;
		min-height: 600px;
	}

	.viewport-badge-row {
		display: flex;
		justify-content: space-between;
		align-items: center;
		font-family: var(--font-mono, monospace);
		font-size: 10px;
		padding-bottom: 20px;
		border-bottom: 1px solid rgba(255, 255, 255, 0.06);
	}

	.pro-tag {
		color: #2dd4bf;
		font-weight: 600;
		letter-spacing: 0.1em;
	}
	.pro-meta {
		color: #64748b;
		letter-spacing: 0.08em;
	}

	.model-canvas-stage {
		flex: 1;
		position: relative;
		min-height: 420px;
		border-radius: 20px;
		background: radial-gradient(circle at 50% 50%, rgba(15, 23, 42, 0.6) 0%, rgba(3, 7, 18, 0.9) 100%);
		border: 1px solid rgba(255, 255, 255, 0.04);
		overflow: hidden;
		margin: 20px 0;
	}

	/* Pins */
	.pins-overlay {
		position: absolute;
		inset: 0;
		pointer-events: none;
		z-index: 10;
	}

	.pin-button {
		position: absolute;
		pointer-events: auto;
		display: inline-flex;
		align-items: center;
		gap: 8px;
		padding: 6px 14px;
		background: rgba(15, 23, 42, 0.85);
		border: 1px solid rgba(255, 255, 255, 0.15);
		border-radius: 999px;
		color: #e2e8f0;
		font-family: var(--font-mono, monospace);
		font-size: 11px;
		font-weight: 500;
		cursor: pointer;
		backdrop-filter: blur(12px);
		transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
	}

	.pin-button:hover, .pin-button--active {
		background: rgba(45, 212, 191, 0.2);
		border-color: #2dd4bf;
		color: #ffffff;
		transform: scale(1.05);
		box-shadow: 0 0 20px rgba(45, 212, 191, 0.3);
	}

	.pin-dot {
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background: #2dd4bf;
		box-shadow: 0 0 8px #2dd4bf;
	}

	.pin-button--1 { top: 18%; left: 8%; }
	.pin-button--2 { top: 62%; left: 10%; }
	.pin-button--3 { top: 22%; right: 8%; }
	.pin-button--4 { bottom: 16%; right: 12%; }

	/* Tab Bar */
	.component-tab-bar {
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: 10px;
	}

	.component-tab {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 4px;
		padding: 12px 8px;
		background: rgba(255, 255, 255, 0.02);
		border: 1px solid rgba(255, 255, 255, 0.06);
		border-radius: 12px;
		color: #94a3b8;
		cursor: pointer;
		transition: all 0.2s;
	}

	.component-tab:hover {
		background: rgba(255, 255, 255, 0.05);
		color: #ffffff;
	}

	.component-tab--active {
		background: rgba(45, 212, 191, 0.1) !important;
		border-color: rgba(45, 212, 191, 0.4) !important;
		color: #2dd4bf !important;
	}

	.tab-number {
		font-family: var(--font-mono, monospace);
		font-size: 10px;
		color: #2dd4bf;
	}
	.tab-title {
		font-size: 12px;
		font-weight: 600;
	}

	/* Right Blueprint */
	.blueprint-card {
		display: flex;
		flex-direction: column;
		justify-content: space-between;
	}

	.blueprint-category {
		display: inline-block;
		font-family: var(--font-mono, monospace);
		font-size: 10px;
		color: #2dd4bf;
		letter-spacing: 0.15em;
		margin-bottom: 8px;
	}

	.blueprint-header h3 {
		font-size: 26px;
		font-weight: 600;
		color: #ffffff;
		margin: 0 0 12px;
		letter-spacing: -0.02em;
	}

	.blueprint-summary {
		font-size: 14px;
		color: #94a3b8;
		line-height: 1.6;
		margin: 0 0 24px;
	}

	.signal-preview-box {
		background: rgba(0, 0, 0, 0.5);
		border: 1px solid rgba(255, 255, 255, 0.08);
		border-radius: 16px;
		padding: 16px;
		margin-bottom: 24px;
	}

	.preview-topline {
		display: flex;
		justify-content: space-between;
		align-items: center;
		font-family: var(--font-mono, monospace);
		font-size: 10px;
		color: #64748b;
		margin-bottom: 8px;
	}

	.live-pill {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		color: #2dd4bf;
		font-weight: 600;
	}

	.pulse-dot {
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background: #2dd4bf;
		box-shadow: 0 0 8px #2dd4bf;
	}

	.preview-waveform {
		height: 64px;
		overflow: hidden;
	}

	/* Specs Grid */
	.specs-grid {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: 12px;
		margin-bottom: 24px;
	}

	.spec-tile {
		padding: 12px 14px;
		background: rgba(255, 255, 255, 0.02);
		border: 1px solid rgba(255, 255, 255, 0.06);
		border-radius: 10px;
	}

	.spec-k {
		display: block;
		font-family: var(--font-mono, monospace);
		font-size: 9px;
		color: #64748b;
		margin-bottom: 4px;
		letter-spacing: 0.05em;
	}

	.spec-v {
		display: block;
		font-family: var(--font-mono, monospace);
		font-size: 15px;
		color: #ffffff;
		font-weight: 600;
		margin-bottom: 2px;
	}

	.spec-n {
		display: block;
		font-size: 11px;
		color: #94a3b8;
	}

	/* Highlights */
	.highlights-box {
		border-top: 1px solid rgba(255, 255, 255, 0.06);
		padding-top: 18px;
	}

	.highlights-label {
		display: block;
		font-family: var(--font-mono, monospace);
		font-size: 10px;
		color: #64748b;
		letter-spacing: 0.1em;
		margin-bottom: 10px;
	}

	.highlights-box ul {
		list-style: none;
		padding: 0;
		margin: 0;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.highlights-box li {
		display: flex;
		align-items: flex-start;
		gap: 10px;
		font-size: 13px;
		color: #cbd5e1;
		line-height: 1.5;
	}

	.check-icon {
		color: #2dd4bf;
		font-weight: 700;
		font-size: 12px;
		margin-top: 2px;
	}

	@media (max-width: 1050px) {
		.hardware-pro-showcase {
			grid-template-columns: 1fr;
		}
	}
</style>
