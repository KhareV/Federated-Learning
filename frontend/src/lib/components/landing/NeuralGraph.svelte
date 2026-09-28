<script lang="ts">
	import { onMount } from 'svelte';

	interface SignalNode {
		id: string;
		name: string;
		layer: number;
		x: number;
		y: number;
		category: 'Sensor Input' | 'Waveform Feature' | 'Autonomic / Context' | 'Edge Diagnostic';
		clinicalRole: string;
		signalSource: string;
		samplingRate: string;
		normalRange: string;
		currentValue: string;
	}

	interface SynapticLink {
		from: string;
		to: string;
		weight: number;
		pulseProgress: number;
		pulseSpeed: number;
	}

	let activeView: 'continuous' | 'snapshots' = $state('continuous');
	let hoveredNode: SignalNode | null = $state(null);
	let selectedNode: SignalNode | null = $state(null);
	let canvasElement: HTMLCanvasElement | null = $state(null);
	let animId: number;
	let animTime = 0;

	// Curated authentic physiological nodes across 4 architectural tiers
	const nodes: SignalNode[] = [
		// Tier 0: Biosensors
		{ id: 'ecg_lead', name: 'ECG Biopotential', layer: 0, x: 0.12, y: 0.22, category: 'Sensor Input', clinicalRole: 'Differential cardiac electrical vector', signalSource: 'AD8232 Front-End', samplingRate: '360 Hz', normalRange: '0.5 – 2.0 mV', currentValue: '1.14 mV (QRS)' },
		{ id: 'ppg_red', name: 'PPG 660nm (Red)', layer: 0, x: 0.12, y: 0.50, category: 'Sensor Input', clinicalRole: 'Oxygenated pulsatile arterial volume', signalSource: 'MAX30102 Optical', samplingRate: '100 Hz', normalRange: '660 nm Peak', currentValue: '0.84 AC/DC' },
		{ id: 'ppg_ir', name: 'PPG 880nm (IR)', layer: 0, x: 0.12, y: 0.78, category: 'Sensor Input', clinicalRole: 'Deoxygenated infrared tissue transmission', signalSource: 'MAX30102 Optical', samplingRate: '100 Hz', normalRange: '880 nm Peak', currentValue: '0.92 AC/DC' },

		// Tier 1: Morphological Features
		{ id: 'qrs_morph', name: 'QRS Morphology', layer: 1, x: 0.38, y: 0.18, category: 'Waveform Feature', clinicalRole: 'Ventricular depolarization duration & axis', signalSource: 'Pan-Tompkins Filter', samplingRate: 'Real-time', normalRange: '80 – 120 ms', currentValue: '92 ms (Normal)' },
		{ id: 'hrv_sdnn', name: 'HRV (SDNN)', layer: 1, x: 0.38, y: 0.44, category: 'Waveform Feature', clinicalRole: 'Standard deviation of R-R intervals', signalSource: 'Edge Peak Detector', samplingRate: '5-Min Window', normalRange: '35 – 80 ms', currentValue: '54.2 ms' },
		{ id: 'ptt_calc', name: 'Pulse Transit Time', layer: 1, x: 0.38, y: 0.70, category: 'Waveform Feature', clinicalRole: 'ECG R-peak to PPG foot interval', signalSource: 'Cross-Modal Sync', samplingRate: 'Beat-to-Beat', normalRange: '180 – 260 ms', currentValue: '218 ms' },
		{ id: 'spo2_ratio', name: 'Optical Delta (R)', layer: 1, x: 0.38, y: 0.88, category: 'Waveform Feature', clinicalRole: 'Ratio-of-ratios oxygen saturation proxy', signalSource: 'Red/IR AC-DC Demod', samplingRate: 'Continuous', normalRange: '0.4 – 1.0 R', currentValue: '0.52 R (98% SpO₂)' },

		// Tier 2: Latent Physiological Space
		{ id: 'cardiac_state', name: 'Cardiac Embedding', layer: 2, x: 0.65, y: 0.28, category: 'Autonomic / Context', clinicalRole: 'Multi-beat topological vector space', signalSource: '128-D Edge Latent', samplingRate: 'Continuous', normalRange: 'Cosine Sim > 0.92', currentValue: '0.96 (Nominal)' },
		{ id: 'autonomic_tone', name: 'Autonomic Balance', layer: 2, x: 0.65, y: 0.62, category: 'Autonomic / Context', clinicalRole: 'Sympathovagal circadian balance (LF/HF)', signalSource: 'Spectral Fusion', samplingRate: 'Continuous', normalRange: '0.8 – 2.2 LF/HF', currentValue: '1.24 LF/HF' },

		// Tier 3: Continuous Clinical Output
		{ id: 'arrhythmia_out', name: 'Sinus Rhythm Guard', layer: 3, x: 0.88, y: 0.24, category: 'Edge Diagnostic', clinicalRole: 'Continuous ectopic beat & flutter detector', signalSource: 'Local TFLite Micro', samplingRate: 'Instantaneous', normalRange: 'Risk < 0.05', currentValue: '0.01 (Normal Sinus)' },
		{ id: 'vital_stability', name: 'Hemodynamic Stability', layer: 3, x: 0.88, y: 0.52, category: 'Edge Diagnostic', clinicalRole: 'Continuous micro-vascular perfusion index', signalSource: 'Multi-Sensor Fusion', samplingRate: 'Instantaneous', normalRange: 'Score 90 – 100', currentValue: '98 / 100 (Optimal)' },
		{ id: 'federated_grad', name: 'Federated Gradient', layer: 3, x: 0.88, y: 0.80, category: 'Edge Diagnostic', clinicalRole: 'Differential privacy model update weight', signalSource: 'Privacy Engine', samplingRate: 'Periodic Sync', normalRange: 'DP Epsilon < 1.0', currentValue: 'Ready (ε = 0.45)' }
	];

	// Synapses connecting the layers
	const links: SynapticLink[] = [
		{ from: 'ecg_lead', to: 'qrs_morph', weight: 0.95, pulseProgress: 0.1, pulseSpeed: 0.007 },
		{ from: 'ecg_lead', to: 'hrv_sdnn', weight: 0.90, pulseProgress: 0.5, pulseSpeed: 0.006 },
		{ from: 'ecg_lead', to: 'ptt_calc', weight: 0.85, pulseProgress: 0.3, pulseSpeed: 0.008 },
		{ from: 'ppg_red', to: 'ptt_calc', weight: 0.88, pulseProgress: 0.7, pulseSpeed: 0.007 },
		{ from: 'ppg_red', to: 'spo2_ratio', weight: 0.92, pulseProgress: 0.2, pulseSpeed: 0.009 },
		{ from: 'ppg_ir', to: 'spo2_ratio', weight: 0.94, pulseProgress: 0.6, pulseSpeed: 0.008 },
		{ from: 'qrs_morph', to: 'cardiac_state', weight: 0.95, pulseProgress: 0.3, pulseSpeed: 0.009 },
		{ from: 'hrv_sdnn', to: 'cardiac_state', weight: 0.89, pulseProgress: 0.8, pulseSpeed: 0.006 },
		{ from: 'hrv_sdnn', to: 'autonomic_tone', weight: 0.92, pulseProgress: 0.2, pulseSpeed: 0.008 },
		{ from: 'ptt_calc', to: 'autonomic_tone', weight: 0.84, pulseProgress: 0.6, pulseSpeed: 0.007 },
		{ from: 'spo2_ratio', to: 'vital_stability', weight: 0.93, pulseProgress: 0.4, pulseSpeed: 0.009 },
		{ from: 'cardiac_state', to: 'arrhythmia_out', weight: 0.96, pulseProgress: 0.1, pulseSpeed: 0.010 },
		{ from: 'cardiac_state', to: 'federated_grad', weight: 0.88, pulseProgress: 0.5, pulseSpeed: 0.007 },
		{ from: 'autonomic_tone', to: 'vital_stability', weight: 0.87, pulseProgress: 0.7, pulseSpeed: 0.008 },
		{ from: 'autonomic_tone', to: 'federated_grad', weight: 0.82, pulseProgress: 0.9, pulseSpeed: 0.006 }
	];

	// Real clinical blind spot occurrences
	const clinicalBlindspots = [
		{
			hour: '03:45 AM',
			title: 'Nocturnal Bradycardia & Sleep Apnea Desaturation',
			severity: 'High Clinical Risk',
			snapshotStatus: 'Undetected (Patient Asleep)',
			nhmStatus: 'Continuous Flag: SpO₂ dipped to 87% for 22s'
		},
		{
			hour: '11:20 AM',
			title: 'Transient Ischemic ST-Segment Shift',
			severity: 'Moderate Clinical Risk',
			snapshotStatus: 'Undetected (Between Visits)',
			nhmStatus: 'Continuous Flag: 0.16 mV ST deflection during exertion'
		},
		{
			hour: '18:15 PM',
			title: 'Post-Work Autonomic Sympathetic Overdrive',
			severity: 'Sub-Clinical Stress Spike',
			snapshotStatus: 'Undetected (Normal at clinic)',
			nhmStatus: 'Continuous Flag: HRV SDNN dropped to 18ms'
		}
	];

	function drawGraph() {
		if (!canvasElement) return;
		const ctx = canvasElement.getContext('2d');
		if (!ctx) return;

		const w = canvasElement.width;
		const h = canvasElement.height;

		ctx.clearRect(0, 0, w, h);

		if (activeView === 'continuous') {
			drawContinuousNeuralMesh(ctx, w, h);
		} else {
			drawDiscontinuousTimeline(ctx, w, h);
		}

		animTime += 0.018;
		animId = requestAnimationFrame(drawGraph);
	}

	function drawContinuousNeuralMesh(ctx: CanvasRenderingContext2D, w: number, h: number) {
		// Draw Synaptic Connectors
		for (const link of links) {
			const src = nodes.find(n => n.id === link.from);
			const dst = nodes.find(n => n.id === link.to);
			if (!src || !dst) continue;

			const x1 = src.x * w;
			const y1 = src.y * h;
			const x2 = dst.x * w;
			const y2 = dst.y * h;

			const isFocused = (hoveredNode || selectedNode) &&
				((hoveredNode || selectedNode)?.id === src.id || (hoveredNode || selectedNode)?.id === dst.id);

			ctx.beginPath();
			ctx.moveTo(x1, y1);
			const cx1 = x1 + (x2 - x1) * 0.45;
			const cy1 = y1;
			const cx2 = x1 + (x2 - x1) * 0.55;
			const cy2 = y2;
			ctx.bezierCurveTo(cx1, cy1, cx2, cy2, x2, y2);

			if (isFocused) {
				ctx.strokeStyle = '#0d9488';
				ctx.lineWidth = 2.4;
			} else {
				ctx.strokeStyle = '#cbd5e1';
				ctx.lineWidth = 1.2;
			}
			ctx.stroke();

			// Traveling signal packet
			link.pulseProgress = (link.pulseProgress + link.pulseSpeed) % 1;
			const t = link.pulseProgress;
			const px = Math.pow(1 - t, 3) * x1 + 3 * Math.pow(1 - t, 2) * t * cx1 + 3 * (1 - t) * Math.pow(t, 2) * cx2 + Math.pow(t, 3) * x2;
			const py = Math.pow(1 - t, 3) * y1 + 3 * Math.pow(1 - t, 2) * t * cy1 + 3 * (1 - t) * Math.pow(t, 2) * cy2 + Math.pow(t, 3) * y2;

			ctx.beginPath();
			ctx.arc(px, py, isFocused ? 3.5 : 2.5, 0, Math.PI * 2);
			ctx.fillStyle = isFocused ? '#0d9488' : '#0284c7';
			ctx.fill();
		}

		// Draw Nodes
		for (const node of nodes) {
			const nx = node.x * w;
			const ny = node.y * h;
			const isHovered = hoveredNode?.id === node.id;
			const isSelected = selectedNode?.id === node.id;

			const radius = isHovered || isSelected ? 9 : 6.5;

			// Outer aura
			if (isHovered || isSelected) {
				ctx.beginPath();
				ctx.arc(nx, ny, radius + 6, 0, Math.PI * 2);
				ctx.fillStyle = 'rgba(13, 148, 136, 0.15)';
				ctx.fill();
			}

			// Main node dot
			ctx.beginPath();
			ctx.arc(nx, ny, radius, 0, Math.PI * 2);
			if (node.category === 'Sensor Input') ctx.fillStyle = '#0f766e';
			else if (node.category === 'Waveform Feature') ctx.fillStyle = '#0369a1';
			else if (node.category === 'Autonomic / Context') ctx.fillStyle = '#4f46e5';
			else ctx.fillStyle = '#059669';
			ctx.fill();

			ctx.strokeStyle = '#ffffff';
			ctx.lineWidth = 1.8;
			ctx.stroke();

			// Clean typography labels
			ctx.font = isHovered || isSelected ? '600 11px Inter, sans-serif' : '500 10px Inter, sans-serif';
			ctx.fillStyle = isHovered || isSelected ? '#0f172a' : '#475569';
			ctx.textAlign = 'center';
			ctx.fillText(node.name, nx, ny + radius + 15);
		}
	}

	function drawDiscontinuousTimeline(ctx: CanvasRenderingContext2D, w: number, h: number) {
		const midY = h * 0.48;

		// Baseline track
		ctx.beginPath();
		ctx.moveTo(w * 0.08, midY);
		ctx.lineTo(w * 0.92, midY);
		ctx.strokeStyle = '#e2e8f0';
		ctx.lineWidth = 3;
		ctx.stroke();

		// 3 Blind Spot Zones
		const zones = [
			{ x1: 0.15, x2: 0.38, hours: '4.5 Hours Unmonitored' },
			{ x1: 0.38, x2: 0.62, hours: '4.5 Hours Unmonitored' },
			{ x1: 0.62, x2: 0.85, hours: '4.5 Hours Unmonitored' }
		];

		for (const z of zones) {
			const startX = z.x1 * w;
			const endX = z.x2 * w;
			const boxW = endX - startX;

			ctx.fillStyle = 'rgba(239, 68, 68, 0.04)';
			ctx.fillRect(startX, midY - 60, boxW, 120);

			ctx.strokeStyle = 'rgba(239, 68, 68, 0.2)';
			ctx.lineWidth = 1;
			ctx.setLineDash([4, 4]);
			ctx.strokeRect(startX, midY - 60, boxW, 120);
			ctx.setLineDash([]);

			ctx.font = '500 10px JetBrains Mono, monospace';
			ctx.fillStyle = '#e11d48';
			ctx.textAlign = 'center';
			ctx.fillText(`◷ ${z.hours}`, startX + boxW / 2, midY + 75);
		}

		// Sporadic Checkpoints
		const checkpoints = [
			{ x: 0.15, time: '08:30 AM', label: 'Clinic ECG Test', val: 'Normal 72 BPM' },
			{ x: 0.38, time: '13:00 PM', label: 'Follow-Up Check', val: 'Normal 76 BPM' },
			{ x: 0.62, time: '17:30 PM', label: 'Pharmacy Cuff', val: 'Normal 74 BPM' },
			{ x: 0.85, time: '22:00 PM', label: 'Evening Log', val: 'Normal 70 BPM' }
		];

		for (const cp of checkpoints) {
			const cx = cp.x * w;

			// Pillar
			ctx.beginPath();
			ctx.moveTo(cx, midY - 35);
			ctx.lineTo(cx, midY + 35);
			ctx.strokeStyle = '#0284c7';
			ctx.lineWidth = 2;
			ctx.stroke();

			// Dot
			ctx.beginPath();
			ctx.arc(cx, midY, 7, 0, Math.PI * 2);
			ctx.fillStyle = '#0284c7';
			ctx.strokeStyle = '#ffffff';
			ctx.lineWidth = 2;
			ctx.fill();
			ctx.stroke();

			// Card
			ctx.fillStyle = '#ffffff';
			ctx.strokeStyle = '#cbd5e1';
			ctx.lineWidth = 1;
			ctx.beginPath();
			ctx.roundRect(cx - 55, midY - 95, 110, 48, 8);
			ctx.fill();
			ctx.stroke();

			ctx.font = '600 10px Inter, sans-serif';
			ctx.fillStyle = '#0f172a';
			ctx.textAlign = 'center';
			ctx.fillText(cp.time, cx, midY - 78);

			ctx.font = '400 9px Inter, sans-serif';
			ctx.fillStyle = '#64748b';
			ctx.fillText(cp.val, cx, midY - 64);
		}
	}

	function handleMouseMove(e: MouseEvent) {
		if (!canvasElement || activeView === 'snapshots') return;
		const rect = canvasElement.getBoundingClientRect();
		const scaleX = canvasElement.width / rect.width;
		const scaleY = canvasElement.height / rect.height;
		const mx = (e.clientX - rect.left) * scaleX;
		const my = (e.clientY - rect.top) * scaleY;

		let found: SignalNode | null = null;
		for (const node of nodes) {
			const nx = node.x * canvasElement.width;
			const ny = node.y * canvasElement.height;
			if (Math.hypot(mx - nx, my - ny) < 24) {
				found = node;
				break;
			}
		}
		hoveredNode = found;
	}

	onMount(() => {
		if (canvasElement) {
			canvasElement.width = 1100;
			canvasElement.height = 420;
		}
		animId = requestAnimationFrame(drawGraph);
		return () => cancelAnimationFrame(animId);
	});
</script>

<div class="neural-clean-wrapper">
	<!-- Top Bar Segmented Control -->
	<div class="neural-header-row">
		<div class="view-switch-pills">
			<button
				class="pill-btn"
				class:pill-btn--active={activeView === 'continuous'}
				onclick={() => { activeView = 'continuous'; selectedNode = null; }}
				type="button"
			>
				<span class="pill-dot pill-dot--teal"></span>
				<span>Continuous Neural Stream</span>
				<small>99.8% Coverage</small>
			</button>
			<button
				class="pill-btn"
				class:pill-btn--active={activeView === 'snapshots'}
				onclick={() => { activeView = 'snapshots'; selectedNode = null; }}
				type="button"
			>
				<span class="pill-dot pill-dot--amber"></span>
				<span>Intermittent Snapshots</span>
				<small>Legacy Care</small>
			</button>
		</div>

		<div class="header-caption">
			{#if activeView === 'continuous'}
				<span class="caption-tag">LIVE EDGE SYNAPSE GRAPH</span>
				<p>Hover any node to inspect real-time feature vectors and cross-modal correlation paths.</p>
			{:else}
				<span class="caption-tag caption-tag--warn">EPISODIC SAMPLING GAP</span>
				<p>Illustrates the 99.8% unmonitored blind intervals between sporadic clinic visits.</p>
			{/if}
		</div>
	</div>

	<!-- Interactive Visualizer Stage -->
	<div class="visualizer-stage">
		<canvas
			bind:this={canvasElement}
			onmousemove={handleMouseMove}
			onmouseleave={() => hoveredNode = null}
			onclick={() => { if (hoveredNode) selectedNode = hoveredNode; }}
			class="stage-canvas"
		></canvas>
	</div>

	<!-- Bottom Architectural Detail Drawer -->
	<div class="detail-drawer">
		{#if activeView === 'continuous'}
			{@const activeNode = hoveredNode || selectedNode || nodes[0]}
			<div class="node-profile-card">
				<div class="profile-header">
					<div>
						<span class="profile-cat">{activeNode.category}</span>
						<h4>{activeNode.name}</h4>
					</div>
					<div class="profile-badge">{activeNode.signalSource}</div>
				</div>

				<p class="profile-role">{activeNode.clinicalRole}</p>

				<div class="profile-meta-row">
					<div class="meta-item">
						<span>SAMPLING FREQUENCY</span>
						<strong>{activeNode.samplingRate}</strong>
					</div>
					<div class="meta-item">
						<span>CLINICAL REFERENCE</span>
						<strong>{activeNode.normalRange}</strong>
					</div>
					<div class="meta-item">
						<span>LIVE VECTOR VALUE</span>
						<strong class="text-teal">{activeNode.currentValue}</strong>
					</div>
				</div>
			</div>
		{:else}
			<div class="blindspot-feed">
				{#each clinicalBlindspots as bs}
					<div class="blindspot-item">
						<div class="bs-time">{bs.hour}</div>
						<div class="bs-body">
							<strong>{bs.title}</strong>
							<div class="bs-comparison">
								<span class="bs-bad">✕ {bs.snapshotStatus}</span>
								<span class="bs-good">✓ {bs.nhmStatus}</span>
							</div>
						</div>
					</div>
				{/each}
			</div>
		{/if}
	</div>
</div>

<style>
	.neural-clean-wrapper {
		width: 100%;
		background: #ffffff;
		border: 1px solid #e2e8f0;
		border-radius: 28px;
		padding: 32px;
		box-shadow: 0 20px 50px rgba(15, 23, 42, 0.05);
	}

	.neural-header-row {
		display: flex;
		justify-content: space-between;
		align-items: center;
		flex-wrap: wrap;
		gap: 20px;
		padding-bottom: 24px;
		border-bottom: 1px solid #f1f5f9;
	}

	.view-switch-pills {
		display: flex;
		gap: 8px;
		background: #f8fafc;
		padding: 6px;
		border-radius: 14px;
		border: 1px solid #e2e8f0;
	}

	.pill-btn {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		padding: 8px 16px;
		border-radius: 10px;
		background: transparent;
		border: none;
		color: #64748b;
		font-family: var(--font-sans, sans-serif);
		font-size: 13px;
		font-weight: 500;
		cursor: pointer;
		transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
	}

	.pill-btn:hover {
		color: #0f172a;
	}

	.pill-btn--active {
		background: #ffffff;
		color: #0f172a !important;
		font-weight: 600;
		box-shadow: 0 4px 12px rgba(15, 23, 42, 0.06);
	}

	.pill-btn small {
		font-size: 10px;
		color: #94a3b8;
		margin-left: 4px;
	}

	.pill-dot {
		width: 7px;
		height: 7px;
		border-radius: 50%;
	}
	.pill-dot--teal { background: #0d9488; }
	.pill-dot--amber { background: #e11d48; }

	.header-caption {
		text-align: right;
	}
	.caption-tag {
		font-family: var(--font-mono, monospace);
		font-size: 10px;
		font-weight: 600;
		letter-spacing: 0.12em;
		color: #0d9488;
	}
	.caption-tag--warn {
		color: #e11d48;
	}
	.header-caption p {
		margin: 4px 0 0;
		font-size: 12px;
		color: #64748b;
	}

	.visualizer-stage {
		position: relative;
		width: 100%;
		height: 420px;
		margin: 20px 0;
		background: #f8fafc;
		border: 1px solid #f1f5f9;
		border-radius: 20px;
		display: grid;
		place-items: center;
		overflow: hidden;
	}

	.stage-canvas {
		width: 100%;
		height: 100%;
		display: block;
		cursor: crosshair;
	}

	.detail-drawer {
		border-top: 1px solid #f1f5f9;
		padding-top: 24px;
	}

	.node-profile-card {
		display: flex;
		flex-direction: column;
		gap: 12px;
	}

	.profile-header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
	}

	.profile-cat {
		display: block;
		font-family: var(--font-mono, monospace);
		font-size: 10px;
		font-weight: 600;
		color: #0d9488;
		letter-spacing: 0.1em;
		text-transform: uppercase;
		margin-bottom: 2px;
	}

	.profile-header h4 {
		margin: 0;
		font-size: 20px;
		font-weight: 600;
		color: #0f172a;
	}

	.profile-badge {
		font-family: var(--font-mono, monospace);
		font-size: 11px;
		padding: 4px 10px;
		background: #f1f5f9;
		border-radius: 6px;
		color: #475569;
	}

	.profile-role {
		margin: 0;
		font-size: 14px;
		color: #64748b;
		line-height: 1.5;
	}

	.profile-meta-row {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: 16px;
		margin-top: 8px;
		padding-top: 16px;
		border-top: 1px solid #f1f5f9;
	}

	.meta-item span {
		display: block;
		font-family: var(--font-mono, monospace);
		font-size: 9px;
		color: #94a3b8;
		letter-spacing: 0.08em;
		margin-bottom: 4px;
	}

	.meta-item strong {
		font-family: var(--font-mono, monospace);
		font-size: 13px;
		font-weight: 600;
		color: #0f172a;
	}

	.text-teal {
		color: #0d9488 !important;
	}

	/* Blindspot Feed */
	.blindspot-feed {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: 16px;
	}

	.blindspot-item {
		padding: 16px;
		background: #f8fafc;
		border: 1px solid #f1f5f9;
		border-radius: 14px;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.bs-time {
		font-family: var(--font-mono, monospace);
		font-size: 10px;
		font-weight: 600;
		color: #e11d48;
	}

	.bs-body strong {
		display: block;
		font-size: 13px;
		color: #0f172a;
		line-height: 1.4;
		margin-bottom: 8px;
	}

	.bs-comparison {
		display: flex;
		flex-direction: column;
		gap: 4px;
		font-size: 11px;
	}

	.bs-bad { color: #e11d48; }
	.bs-good { color: #0d9488; font-weight: 500; }

	@media (max-width: 900px) {
		.blindspot-feed {
			grid-template-columns: 1fr;
		}
		.profile-meta-row {
			grid-template-columns: 1fr;
		}
		.header-caption {
			text-align: left;
		}
	}
</style>
