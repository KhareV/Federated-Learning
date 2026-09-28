<script lang="ts">
	import { Globe } from '$lib/components/magic/globe';

	interface ArchitectureLayer {
		id: string;
		index: string;
		title: string;
		role: string;
		protocol: string;
		latency: string;
		dataThroughput: string;
		security: string;
		description: string;
		details: string[];
	}

	const layers: ArchitectureLayer[] = [
		{
			id: 'sensing',
			index: '01',
			title: 'Analog Biosensing',
			role: 'Biopotential & Optical Transduction',
			protocol: 'Analog Microvolt Differential / I2C',
			latency: '< 0.2 ms',
			dataThroughput: '14.4 kbps raw',
			security: 'Direct Skin Contact Guard',
			description: 'Captures electrical cardiac potentials via differential electrodes and optical pulsatile absorption at 660nm and 880nm.',
			details: ['AD8232 Integrated Instrumentation Amp', 'MAX30102 Dual-Wavelength Core', 'Hardware Right-Leg Drive Active Filter']
		},
		{
			id: 'embedded',
			index: '02',
			title: 'Embedded Edge Firmware',
			role: 'Hardware FIFO & Noise Filtering',
			protocol: 'FreeRTOS DMA / Ring Buffer',
			latency: '0.6 ms',
			dataThroughput: '512 KB Internal SRAM',
			security: 'Isolated Local Ring Buffer',
			description: 'Continuous ADC sampling with baseline wander removal, 50Hz notch filter, and circular buffer storage on the ESP32-S3.',
			details: ['24-Bit Sigma-Delta Conversion', 'Zero-Latency Motion Artifact Suppression', 'Dual-Core Asynchronous Core Affinity']
		},
		{
			id: 'features',
			index: '03',
			title: 'Wavelet Feature Extraction',
			role: 'Cross-Modal Vector Synthesis',
			protocol: 'SIMD Vector Floating Point',
			latency: '1.2 ms',
			dataThroughput: '128-D Feature Embedding',
			security: 'Deterministic In-Memory Transform',
			description: 'Real-time Pan-Tompkins QRS peak detection, R-R interval HRV extraction, and Pulse Transit Time (PTT) fusion.',
			details: ['Continuous Beat-to-Beat PTT Tracking', 'Autonomic Sympathovagal LF/HF Decomposition', '128-Dimensional Topological Vector Projection']
		},
		{
			id: 'inference',
			index: '04',
			title: 'On-Device Edge ML',
			role: 'Local Arrhythmia Classifier',
			protocol: 'TensorFlow Lite Micro (INT8)',
			latency: '1.4 ms / Inference',
			dataThroughput: '18 KB Model Flash Footprint',
			security: '100% Zero Raw Data Upload',
			description: 'Quantized neural network performing real-time classification of arrhythmias, PVCs, and sleep desaturations entirely on the wearable.',
			details: ['On-Chip Quantized 8-Bit Inference Engine', 'Zero Cloud Dependency for Immediate Alarms', 'Automated Anomaly Confidence Scoring']
		},
		{
			id: 'privacy',
			index: '05',
			title: 'Differential Privacy Engine',
			role: 'Gradient Perturbation & Noise Addition',
			protocol: 'DP-FedAvg (ε = 0.45, δ = 1e-5)',
			latency: '3.8 ms / Batch',
			dataThroughput: 'Perturbed Weights Only',
			security: 'Formal Differential Privacy Proof',
			description: 'Calculates model parameter weight updates locally and injects Gaussian noise to guarantee zero patient re-identification.',
			details: ['Rényi Differential Privacy Accounting', 'Gradient Clipping Against Outlier Exploits', 'Zero Raw ECG/PPG Exposure Guarantee']
		},
		{
			id: 'federated',
			index: '06',
			title: 'Federated Global Consensus',
			role: 'Collaborative Model Sync',
			protocol: 'WSS / TLS 1.3 Asymmetric Mesh',
			latency: '42 ms / Round',
			dataThroughput: 'Model Delta (~32 KB)',
			security: 'AES-256 / Secure Aggregation',
			description: 'Participating client devices securely broadcast encrypted weight vectors to update a shared global clinical intelligence model.',
			details: ['Secure Multi-Party Aggregation (SecAgg)', 'Byzantine Fault-Tolerant Consensus', 'Worldwide Model Generalization']
		}
	];

	let activeLayer = $state(layers[2]);

	const federationMarkers = [
		{ lat: 28.61, lng: 77.21, size: 0.70 },
		{ lat: 19.07, lng: 72.88, size: 0.70 },
		{ lat: 13.08, lng: 80.27, size: 0.70 },
		{ lat: 12.97, lng: 77.59, size: 0.70 },
		{ lat: 1.35, lng: 103.82, size: 0.55 },
		{ lat: 35.68, lng: 139.65, size: 0.55 },
		{ lat: 51.51, lng: -0.13, size: 0.55 },
		{ lat: 40.71, lng: -74.01, size: 0.55 },
		{ lat: 37.77, lng: -122.42, size: 0.55 }
	];
</script>

<div class="arch-master-wrapper">
	<!-- 6-Tier Architecture Step Cards -->
	<div class="arch-tiers-strip">
		{#each layers as layer}
			<button
				class="tier-box"
				class:tier-box--active={activeLayer.id === layer.id}
				onclick={() => activeLayer = layer}
				type="button"
			>
				<span class="tier-idx">{layer.index}</span>
				<strong class="tier-title">{layer.title}</strong>
				<span class="tier-role">{layer.role}</span>
				<div class="tier-indicator"></div>
			</button>
		{/each}
	</div>

	<!-- Interactive Architectural Explorer Matrix -->
	<div class="arch-content-grid">
		<!-- Left: Detailed Tier Specs & Security Breakdown -->
		<div class="tier-detail-card">
			<div class="tier-header">
				<div class="tier-tag-group">
					<span class="tier-tag">TIER {activeLayer.index} // ARCHITECTURE</span>
					<span class="tier-latency">LATENCY: {activeLayer.latency}</span>
				</div>
				<h3>{activeLayer.title}</h3>
				<p class="tier-desc">{activeLayer.description}</p>
			</div>

			<div class="tier-metrics-grid">
				<div class="t-metric">
					<span>PROTOCOL / INTERFACE</span>
					<strong>{activeLayer.protocol}</strong>
				</div>
				<div class="t-metric">
					<span>THROUGHPUT / MEMORY</span>
					<strong>{activeLayer.dataThroughput}</strong>
				</div>
				<div class="t-metric">
					<span>PRIVACY & SECURITY</span>
					<strong class="text-teal">{activeLayer.security}</strong>
				</div>
			</div>

			<div class="tier-subsystems-list">
				<span class="subsys-label">SUBSYSTEM IMPLEMENTATION</span>
				<ul>
					{#each activeLayer.details as item}
						<li><span class="bullet">▹</span> {item}</li>
					{/each}
				</ul>
			</div>
		</div>

		<!-- Right: 3D Federated Global Intelligence Network -->
		<div class="federated-globe-card">
			<div class="globe-top-bar">
				<div>
					<span class="globe-tag">FEDERATED LEARNING MESH</span>
					<h4>One Global Model · Many Private Devices</h4>
				</div>
				<span class="globe-status-pill"><span class="globe-dot"></span> LIVE CONSENSUS</span>
			</div>

			<!-- 3D Globe Visualizer -->
			<div class="globe-viewport">
				<Globe config={{ width: 520, height: 520, dark: 1, diffuse: 1.8, mapSamples: 12000, mapBrightness: 4.5, baseColor: [0.04, 0.12, 0.18], markerColor: [0.17, 0.83, 0.75], glowColor: [0.05, 0.25, 0.28], markers: federationMarkers.map(m => ({ location: [m.lat, m.lng], size: m.size * 0.05 })) }} />
			</div>

			<div class="globe-stats-dock">
				<div class="g-stat">
					<span>ACTIVE NODES</span>
					<strong>9 NODES</strong>
				</div>
				<div class="g-stat">
					<span>ROUND</span>
					<strong>#142</strong>
				</div>
				<div class="g-stat">
					<span>ACCURACY</span>
					<strong class="text-teal">98.6%</strong>
				</div>
				<div class="g-stat">
					<span>PRIVACY (ε)</span>
					<strong class="text-teal">0.45 DP</strong>
				</div>
			</div>
		</div>
	</div>
</div>

<style>
	.arch-master-wrapper {
		width: 100%;
		display: flex;
		flex-direction: column;
		gap: 32px;
	}

	/* 6-Tier Strip */
	.arch-tiers-strip {
		display: grid;
		grid-template-columns: repeat(6, 1fr);
		gap: 12px;
	}

	.tier-box {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: 6px;
		padding: 20px 16px;
		background: rgba(255, 255, 255, 0.02);
		border: 1px solid rgba(255, 255, 255, 0.08);
		border-radius: 18px;
		color: #94a3b8;
		cursor: pointer;
		position: relative;
		overflow: hidden;
		transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
		text-align: left;
	}

	.tier-box:hover {
		background: rgba(255, 255, 255, 0.05);
		color: #ffffff;
		border-color: rgba(255, 255, 255, 0.2);
	}

	.tier-box--active {
		background: rgba(45, 212, 191, 0.1) !important;
		border-color: rgba(45, 212, 191, 0.4) !important;
		color: #ffffff !important;
	}

	.tier-idx {
		font-family: var(--font-mono, monospace);
		font-size: 11px;
		color: #2dd4bf;
		font-weight: 600;
	}

	.tier-title {
		font-size: 14px;
		font-weight: 600;
		color: #ffffff;
		line-height: 1.2;
	}

	.tier-role {
		font-size: 11px;
		color: #64748b;
		line-height: 1.3;
	}

	.tier-indicator {
		position: absolute;
		bottom: 0;
		left: 0;
		right: 0;
		height: 3px;
		background: transparent;
		transition: background 0.25s;
	}

	.tier-box--active .tier-indicator {
		background: #2dd4bf;
		box-shadow: 0 0 10px #2dd4bf;
	}

	/* Content Grid */
	.arch-content-grid {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 32px;
		align-items: stretch;
	}

	.tier-detail-card, .federated-globe-card {
		background: #090d16;
		border: 1px solid rgba(255, 255, 255, 0.08);
		border-radius: 28px;
		padding: 32px;
		box-shadow: 0 30px 80px rgba(0, 0, 0, 0.6);
		display: flex;
		flex-direction: column;
		justify-content: space-between;
	}

	.tier-tag-group {
		display: flex;
		justify-content: space-between;
		font-family: var(--font-mono, monospace);
		font-size: 10px;
		margin-bottom: 8px;
	}
	.tier-tag { color: #2dd4bf; font-weight: 600; letter-spacing: 0.1em; }
	.tier-latency { color: #64748b; }

	.tier-header h3 {
		font-size: 26px;
		font-weight: 600;
		color: #ffffff;
		margin: 0 0 12px;
	}

	.tier-desc {
		font-size: 14px;
		color: #94a3b8;
		line-height: 1.6;
		margin: 0 0 24px;
	}

	.tier-metrics-grid {
		display: grid;
		grid-template-columns: 1fr;
		gap: 12px;
		margin-bottom: 24px;
	}

	.t-metric {
		padding: 12px 16px;
		background: rgba(255, 255, 255, 0.02);
		border: 1px solid rgba(255, 255, 255, 0.06);
		border-radius: 12px;
	}

	.t-metric span {
		display: block;
		font-family: var(--font-mono, monospace);
		font-size: 9px;
		color: #64748b;
		margin-bottom: 4px;
	}

	.t-metric strong {
		font-family: var(--font-mono, monospace);
		font-size: 13px;
		color: #ffffff;
	}

	.text-teal {
		color: #2dd4bf !important;
	}

	.tier-subsystems-list {
		border-top: 1px solid rgba(255, 255, 255, 0.06);
		padding-top: 18px;
	}

	.subsys-label {
		display: block;
		font-family: var(--font-mono, monospace);
		font-size: 10px;
		color: #64748b;
		margin-bottom: 10px;
	}

	.tier-subsystems-list ul {
		list-style: none;
		padding: 0;
		margin: 0;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.tier-subsystems-list li {
		font-size: 13px;
		color: #cbd5e1;
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.bullet {
		color: #2dd4bf;
		font-size: 12px;
	}

	/* Globe Card */
	.globe-top-bar {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		margin-bottom: 16px;
	}

	.globe-tag {
		display: block;
		font-family: var(--font-mono, monospace);
		font-size: 10px;
		color: #2dd4bf;
		letter-spacing: 0.1em;
		margin-bottom: 4px;
	}

	.globe-top-bar h4 {
		margin: 0;
		font-size: 18px;
		font-weight: 600;
		color: #ffffff;
	}

	.globe-status-pill {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		padding: 4px 10px;
		background: rgba(45, 212, 191, 0.1);
		border: 1px solid rgba(45, 212, 191, 0.3);
		border-radius: 999px;
		color: #2dd4bf;
		font-family: var(--font-mono, monospace);
		font-size: 10px;
		font-weight: 600;
	}

	.globe-dot {
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background: #2dd4bf;
		box-shadow: 0 0 8px #2dd4bf;
	}

	.globe-viewport {
		position: relative;
		height: 380px;
		display: grid;
		place-items: center;
		overflow: hidden;
		margin: 10px 0;
	}

	.globe-stats-dock {
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: 8px;
		padding-top: 16px;
		border-top: 1px solid rgba(255, 255, 255, 0.06);
	}

	.g-stat span {
		display: block;
		font-family: var(--font-mono, monospace);
		font-size: 9px;
		color: #64748b;
		margin-bottom: 2px;
	}

	.g-stat strong {
		font-family: var(--font-mono, monospace);
		font-size: 13px;
		color: #ffffff;
	}

	@media (max-width: 1050px) {
		.arch-tiers-strip {
			grid-template-columns: repeat(3, 1fr);
		}
		.arch-content-grid {
			grid-template-columns: 1fr;
		}
	}

	@media (max-width: 640px) {
		.arch-tiers-strip {
			grid-template-columns: repeat(2, 1fr);
		}
		.globe-stats-dock {
			grid-template-columns: repeat(2, 1fr);
			gap: 12px;
		}
	}
</style>
