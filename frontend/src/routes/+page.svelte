<script lang="ts">
	import { onMount } from 'svelte';

	import { TypingAnimation } from '$lib/components/magic/typing-animation';
	import { AnimatedGridPattern } from '$lib/components/magic/animated-grid-pattern';
	import { AnimatedList } from '$lib/components/magic/animated-list';
	import { DottedMap } from '$lib/components/magic/dotted-map';
	import { Lens } from '$lib/components/magic/lens';
	import { Marquee } from '$lib/components/magic/marquee';
	import { ProgressiveBlur } from '$lib/components/magic/progressive-blur';
	import { AnimatedBeam } from '$lib/components/magic/animated-beam';
	import { DiaTextReveal } from '$lib/components/magic/dia-text-reveal';
	import { LineShadowText } from '$lib/components/magic/line-shadow-text';
	import { MorphingText } from '$lib/components/magic/morphing-text';
	import { ArcTimeline } from '$lib/components/magic/arc-timeline';
	import { PixelImage } from '$lib/components/magic/pixel-image';
	import { Globe } from '$lib/components/magic/globe';
	import BlurFade from '$lib/components/magic/blur-fade/blur-fade.svelte';
	import NumberTicker from '$lib/components/magic/number-ticker/number-ticker.svelte';
	
	// Import the Signature component you provided
	import { Signature } from "$lib/components/spell/signature";

	import WatchScene from '$lib/components/landing/WatchScene.svelte';
	import PhysiologicalWaveform from '$lib/components/landing/PhysiologicalWaveform.svelte';
	import NeuralGraph from '$lib/components/landing/NeuralGraph.svelte';
	import HardwareStudio from '$lib/components/hardware/HardwareStudio.svelte';
	import MultimodalStudio from '$lib/components/signals/MultimodalStudio.svelte';
	import SystemArchitecture from '$lib/components/landing/SystemArchitecture.svelte';
	import ProductWorkstation from '$lib/components/landing/ProductWorkstation.svelte';

	let ready = false;
	let preloaderMounted = true;

	let beamContainer: HTMLDivElement | null = null;
	let beamFrom: HTMLDivElement | null = null;
	let beamTo: HTMLDivElement | null = null;

	const setupLines = [
		'SENSOR ARRAY / READY',
		'ECG STREAM / CONNECTED',
		'PPG STREAM / CONNECTED',
		'EDGE PROCESSING / READY',
		'PRIVACY LAYER / READY'
	];

	const signalItems = [
		{ id: 'ecg', label: 'ECG', value: 'Electrical cardiac signal', meta: 'AD8232' },
		{ id: 'ppg', label: 'PPG', value: 'Optical pulse waveform', meta: 'MAX30102' },
		{ id: 'spo2', label: 'SpO₂', value: 'Blood oxygen estimation', meta: 'MAX30102' },
		{ id: 'edge', label: 'EDGE', value: 'Local feature processing', meta: 'ESP32' }
	];

	const timelineData = [
		{ time: '01', steps: [{ icon: 'S', content: 'Wearable physiological sensing' }, { icon: 'I', content: 'Connected IoMT monitoring' }] },
		{ time: '02', steps: [{ icon: 'A', content: 'AI / machine learning on health signals' }, { icon: 'F', content: 'Federated learning for collaborative training' }] },
		{ time: '03', steps: [{ icon: 'P', content: 'Privacy-preserving healthcare intelligence' }, { icon: 'N', content: 'NHM: a practical wearable architecture' }] }
	];

	const federationMarkers = [
		{ lat: 28.61, lng: 77.21, size: 0.70 }, { lat: 19.07, lng: 72.88, size: 0.70 },
		{ lat: 13.08, lng: 80.27, size: 0.70 }, { lat: 12.97, lng: 77.59, size: 0.70 },
		{ lat: 1.35, lng: 103.82, size: 0.55 }, { lat: 35.68, lng: 139.65, size: 0.55 },
		{ lat: 51.51, lng: -0.13, size: 0.55 }, { lat: 40.71, lng: -74.01, size: 0.55 },
		{ lat: 37.77, lng: -122.42, size: 0.55 }
	];

	onMount(() => {
		const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
		const seen = sessionStorage.getItem('nhm-preloader-seen');

		if (seen === '1' || reducedMotion) {
			preloaderMounted = false;
			ready = true;
			return;
		}

		const timer = window.setTimeout(() => {
			ready = true;
			sessionStorage.setItem('nhm-preloader-seen', '1');
			window.setTimeout(() => {
				preloaderMounted = false;
			}, 950);
		}, 4300);

		return () => window.clearTimeout(timer);
	});
</script>

<svelte:head>
	<title>NHM — Non-Invasive Health Monitor</title>
	<meta name="description" content="Continuous physiological monitoring with edge intelligence and privacy-preserving federated learning." />
	<meta name="theme-color" content="#030712" />
	
	<!-- High-end typography -->
	<link rel="preconnect" href="https://fonts.googleapis.com">
	<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="anonymous">
	<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=JetBrains+Mono:wght@100..800&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">
</svelte:head>

<!-- =========================================================
	 PRELOADER
========================================================= -->

{#if preloaderMounted}
	<div class:preloader--closing={ready} class="preloader" aria-label="Initializing NHM">
		<div class="preloader__orb"></div>
		<div class="preloader__grid"></div>

		<div class="preloader__inner">
			<div class="preloader__topline">
				<span>NHM</span>
				<span>SYSTEM / 01</span>
			</div>

			<div class="preloader__identity">
				<div class="preloader__mini">NON-INVASIVE HEALTH MONITOR</div>

				<div class="preloader__quote">
					<div class="preloader__quote-text">
						<TypingAnimation
							words={['Measure what matters.', 'Know your baseline.', 'Health is a continuous signal.', 'Understand the pattern.', 'Better sensing. Better understanding.']}
							typeSpeed={40} deleteSpeed={15} pauseDelay={850} loop={true} startOnView={false} showCursor={true} cursorStyle="line"
						/>
					</div>

					<div class="mt-6">
						<Signature once={false} inView class="dark:invert-100" text="Rich Harris" fontSize={16} color="#1D1D1F" />
					</div>
				</div>
			</div>

			<div class="preloader__systems">
				{#each setupLines as item, index}
					<div class="preloader__system" style={`--delay:${700 + index * 230}ms`}>
						<span class="preloader__system-index">0{index + 1}</span>
						<span class="preloader__system-name">{item.split(' / ')[0]}</span>
						<span class="preloader__system-state">{item.split(' / ')[1]}</span>
						<span class="preloader__system-ok">●</span>
					</div>
				{/each}
			</div>

			<div class="preloader__bottom">
				<div class="preloader__progress"><span></span></div>
				<div class="preloader__progress-meta">
					<span>INITIALIZING SYSTEM</span>
					<span>LOCAL-FIRST ARCHITECTURE</span>
				</div>
			</div>
		</div>

		<div class="preloader__ready">READY</div>
	</div>
{/if}

<div class="site-shell">

	<!-- =========================================================
		 NAVIGATION
	========================================================= -->
	<nav class="nav">
		<a class="brand" href="#top" aria-label="NHM home">
			<span class="brand__mark">N</span>
			<span class="brand__name">NHM</span>
		</a>

		<div class="nav__links">
			<a href="#technology">Technology</a>
			<a href="#signals">Signals</a>
			<a href="#privacy">Privacy</a>
			<a href="#research">Research</a>
		</div>

		<a class="nav__cta button--glass" href="/monitor">
			<span>Open Monitor</span>
			<span class="arrow">↗</span>
		</a>
	</nav>

	<main id="top">
		<!-- =====================================================
			 01 — HERO
		====================================================== -->
		<section class="hero section-dark">
			<div class="hero__grid">
				<AnimatedGridPattern width={52} height={52} numSquares={18} maxOpacity={0.1} duration={7} repeatDelay={1.8} />
			</div>

			<div class="hero__technical">
				<span>NHM / 01</span>
				<span>CONTINUOUS MONITORING</span>
				<span>ECG · PPG · SpO₂</span>
			</div>

			<div class="hero__content-wrapper">
				<div class="hero__content">
					<div class="hero__copy-container">
						<BlurFade inView={true} direction="up" offset={18} blur="10px" duration={0.85}>
							<div class="hero__copy">
							<div class="eyebrow eyebrow--teal">NON-INVASIVE · CONTINUOUS · PRIVATE</div>
							<h1>
								Your health.<br />
								<span class="text-gradient">Continuously</span><br />
								<span>understood.</span>
							</h1>
							<p class="hero__lede">
								A wearable monitoring system that captures physiological signals, processes them at the edge, and learns collaboratively without treating raw health data as centralized training data.
							</p>
							<div class="hero__actions">
								<a class="button button--light" href="#technology">
									<span>Explore the system</span><span>↓</span>
								</a>
								<a class="text-link" href="/monitor">Open monitoring environment<span>↗</span></a>
							</div>
							</div>
						</BlurFade>
					</div>

					<div class="hero__device">
						<WatchScene />
					</div>
				</div>
			</div>

			<div class="hero__signal">
				<div class="complex-wave">
					<div class="complex-wave__grid"></div>
					<PhysiologicalWaveform mode="ecg" speed={0.65} amplitude={0.72} />
					<div class="complex-wave__layer">
						<PhysiologicalWaveform mode="ecg" speed={0.45} amplitude={0.4} />
					</div>
					<div class="complex-wave__scanline"></div>
				</div>
				<div class="hero__signal-meta">
					<span>ECG SIGNAL</span>
					<span>LOCAL / LIVE</span>
					<span>QUALITY / EXCELLENT</span>
				</div>
			</div>
		</section>

		<!-- =====================================================
			 02 — PROBLEM
		====================================================== -->
		<section class="problem section-light">
			<div class="container relative z-10">
				<div class="section-kicker">02 / THE SAMPLING DILEMMA</div>
				<div class="problem__heading">
					<div class="problem__title-wrap">
						<BlurFade inView={true} direction="up" offset={24} blur="8px" duration={0.8}>
							<h2>Healthcare often sees<br /><span>snapshots.</span> <em class="text-slate-400">Disease lives in the gaps.</em></h2>
						</BlurFade>
						
						<!-- Signature component integrated cleanly here -->
						<div class="mt-6 hidden md:block">
							<Signature once={false} inView text="Context is everything." fontSize={26} color="#64748b" />
						</div>
					</div>

					<div class="problem__intro-copy">
						<BlurFade inView={true} direction="up" offset={18} delay={0.12} blur="6px" duration={0.7}>
							<p>Standard episodic clinical visits capture isolated 15-minute readings months apart, leaving 99.8% of cardiac and respiratory variations completely unobserved. NHM bridges this discontinuous void with an on-device neural knowledge graph that correlates multi-modal biopotentials continuously in real time.</p>
						</BlurFade>
					</div>
				</div>

				<!-- Intricate Neural Graph & Snapshot Comparator Component -->
				<div class="problem__neural-stage">
					<NeuralGraph />
				</div>
			</div>
		</section>

		<!-- =====================================================
			 03 — RESEARCH
		====================================================== -->
		<section id="research" class="research section-light section-tight">
			<div class="container">
				<div class="section-kicker">03 / RESEARCH EVOLUTION</div>
				<div class="research__heading">
					<BlurFade inView={true} direction="up" offset={18} blur="8px">
						<h2>From sensing to<br /><span>privacy-preserving intelligence.</span></h2>
					</BlurFade>
					<BlurFade inView={true} direction="up" offset={18} delay={0.12} blur="6px">
						<p>NHM brings together the progression identified in the project literature review rather than treating each technique as an isolated feature.</p>
					</BlurFade>
				</div>
				<div class="research__timeline">
					<ArcTimeline data={timelineData} arcConfig={{ circleWidth: 3000, angleBetweenMinorSteps: 0.52, lineCountFillBetweenSteps: 7, boundaryPlaceholderLinesCount: 28 }} />
				</div>
			</div>
		</section>

		<!-- =====================================================
			 04 — HARDWARE
		====================================================== -->
		<section id="technology" class="hardware section-dark">
			<div class="section-bg">
				<img src="https://images.unsplash.com/photo-1507413245164-6160d8298b31?q=80&w=2070" alt="Hardware Engineering Lab" />
				<div class="section-bg__overlay section-bg__overlay--heavy"></div>
			</div>

			<div class="container relative z-10">
				<div class="section-kicker section-kicker--dark">04 / THE WEARABLE HARDWARE LAB</div>
				<div class="hardware__heading">
					<div class="hardware__title">
						<DiaTextReveal text="The body becomes the signal." textColor="#eef7f6" colors={['#2bb8b0', '#89d7d0', '#d5f0ed']} duration={1.65} triggerOnView={true} once={true} />
					</div>
					<p>An integrated hardware suite uniting biopotential ECG acquisition, dual-wavelength optical PPG, and dual-core edge machine learning within a titanium unibody enclosure.</p>
				</div>

				<!-- State-of-the-art Interactive Hardware Studio Component -->
				<div class="hardware__studio-wrap">
					<HardwareStudio />
				</div>
			</div>

			<div class="technical-marquee">
				<Marquee repeat={4} pauseOnHover={true}>
					<div class="marquee-item">
						<span>MAX30102 PPG</span><i>•</i><span>AD8232 ECG</span><i>•</i><span>ESP32-S3 EDGE</span><i>•</i><span>BLE 5.0 MESH</span><i>•</i><span>LOCAL 24-BIT ADC</span><i>•</i><span>360Hz SAMPLING</span><i>•</i><span>AES-256 ENCRYPTED</span>
					</div>
				</Marquee>
				<ProgressiveBlur position="both" height="100%" class="marquee-blur" />
			</div>
		</section>

		<!-- =====================================================
			 05 — SIGNALS
		====================================================== -->
		<section id="signals" class="signals section-light">
			<div class="container">
				<div class="section-kicker">05 / MULTIMODAL SENSING</div>

				<div class="signals__heading">
					<BlurFade inView={true} direction="up" offset={20} blur="8px">
						<h2>One device.<br /><span>Synchronized signals.</span></h2>
					</BlurFade>
					
					<div class="signals__morph-container">
						<div class="signals__morph">
							<MorphingText texts={['SENSE', 'SYNCHRONIZE', 'UNDERSTAND']} />
						</div>
					</div>
				</div>

				<div class="signals__studio-wrap">
					<MultimodalStudio />
				</div>
			</div>
		</section>

		<!-- =====================================================
			 06 — EDGE INTELLIGENCE
		====================================================== -->
		<section class="edge section-dark">
			<div class="section-bg">
				<img src="https://images.unsplash.com/photo-1518770660439-4636190af475?q=80&w=2070" alt="Hardware Intelligence" />
				<div class="section-bg__overlay"></div>
			</div>
			
			<div class="edge__grid"></div>
			<div class="container relative z-10">
				<div class="section-kicker section-kicker--dark">06 / EDGE INTELLIGENCE</div>
				<div class="edge__heading">
					<h2>The intelligence<br /><span>stays close.</span></h2>
					<p>Signals move from sensing to local processing before any collaborative learning step. The architecture keeps the first layer of interpretation close to the device.</p>
				</div>

				<div class="edge__flow" bind:this={beamContainer}>
					<div class="flow-node glass-panel" bind:this={beamFrom}>
						<span class="flow-node__index">01</span>
						<strong>SENSORS</strong>
						<span>ECG · PPG · SpO₂</span>
					</div>
					<div class="flow-node glass-panel flow-node--active">
						<span class="flow-node__index">02</span>
						<strong>ESP32</strong>
						<span>EDGE PROCESSING</span>
					</div>
					<div class="flow-node glass-panel" bind:this={beamTo}>
						<span class="flow-node__index">03</span>
						<strong>LOCAL MODEL</strong>
						<span>FEATURES · INFERENCE</span>
					</div>

					{#if beamContainer && beamFrom && beamTo}
						<AnimatedBeam containerRef={beamContainer} fromRef={beamFrom} toRef={beamTo} curvature={18} duration={5.4} delay={0.7} pathColor="rgba(255,255,255,0.08)" pathWidth={2} pathOpacity={0.7} gradientStartColor="#2bb8b0" gradientStopColor="#38bdf8" />
					{/if}
				</div>

				<div class="edge__quote">
					<div class="edge__line-shadow">
						<LineShadowText content="PROCESS LOCALLY" shadowColor="#2bb8b0" as="div" />
					</div>
				</div>
			</div>
		</section>

		<!-- =====================================================
			 07 — FEDERATED LEARNING
		====================================================== -->
		<section id="privacy" class="federation section-dark">
			<div class="section-bg">
				<img src="https://images.unsplash.com/photo-1451187580459-43490279c0fa?q=80&w=2072" alt="Global Network" />
				<div class="section-bg__overlay section-bg__overlay--heavy"></div>
			</div>

			<div class="container relative z-10">
				<div class="section-kicker section-kicker--dark">07 / PRIVACY-PRESERVING LEARNING</div>
				<div class="federation__heading">
					<h2>Learn together.<br /><em>Share less.</em></h2>
					<p>Federated learning lets participating clients contribute model updates while keeping raw physiological recordings at the local side of the architecture.</p>
				</div>

				<div class="federation__stage">
					<div class="federation__map">
						<DottedMap width={150} height={75} mapSamples={4200} markers={federationMarkers} dotColor="#64748b" markerColor="#2dd4bf" dotRadius={0.35} />
					</div>
					
					<div class="federation__path">
						<div class="federation-node federation-node--left">
							<span>LOCAL CLIENTS</span>
							<strong>MODEL UPDATES</strong>
						</div>
						<div class="federation-path-line"><span></span><span></span><span></span></div>
						<div class="federation-node federation-node--right">
							<span>FEDERATED SERVER</span>
							<strong>AGGREGATION</strong>
						</div>
					</div>

					<div class="federation__rule glass-panel">
						<div class="federation__rule-col">
							<span class="rule-bad">RAW DATA</span>
							<strong>STAYS LOCAL</strong>
						</div>
						<div class="federation__rule-divider"></div>
						<div class="federation__rule-col">
							<span class="rule-good">LEARNING</span>
							<strong>HAPPENS COLLABORATIVELY</strong>
						</div>
					</div>
				</div>
			</div>
		</section>

		<!-- =====================================================
			 08 — SYSTEM ARCHITECTURE
		====================================================== -->
		<section class="system section-dark">
			<div class="container relative z-10">
				<div class="section-kicker section-kicker--dark">08 / SYSTEM ARCHITECTURE</div>
				<div class="system__intro">
					<h2>Under the interface is<br /><span>a layered system.</span></h2>
					<p>From analog microvolt transduction and on-device SIMD feature extraction to differential privacy accounting and global federated consensus.</p>
				</div>

				<div class="system__matrix-wrap">
					<SystemArchitecture />
				</div>
			</div>
		</section>

		<!-- =====================================================
			 09 — PRODUCT PREVIEW
		====================================================== -->
		<section class="product section-light">
			<div class="container">
				<div class="section-kicker">09 / THE PRODUCT</div>
				<div class="product__heading">
					<h2>See the system<br /><span>in action.</span></h2>
					<p>An interactive preview of the continuous health telemetry environment: live multilead signals, arrhythmia detection, and privacy-preserving insights.</p>
				</div>

				<div class="product__workstation-wrap">
					<ProductWorkstation />
				</div>
			</div>
		</section>

		<!-- =====================================================
			 10 — FINAL
		====================================================== -->
		<section class="final section-dark">
			<!-- Aesthetic Background Layer -->
			<div class="section-bg">
				<img src="https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?q=80&w=2070" alt="Cyber matrix code" />
				<div class="section-bg__overlay section-bg__overlay--heavy"></div>
			</div>

			<div class="final__grid"></div>
			<div class="container relative z-10 text-center flex flex-col items-center">
				<div class="eyebrow eyebrow--teal glow-text mb-6">NHM / 10</div>
				
				<!-- Fixed seeping out of screen by splitting the large text and containing width -->
				<div class="final__headline">
					<LineShadowText content="Continuous health" shadowColor="#2bb8b0" as="div" />
					<LineShadowText content="intelligence." shadowColor="#2bb8b0" as="div" />
				</div>
				
				<p class="final__p">Continuous sensing. Local intelligence. Privacy-preserving learning.</p>
				<a href="/monitor" class="button button--light button--glow">
					<span>Enter the monitoring environment</span><span>↗</span>
				</a>
			</div>

			<div class="final__wave">
				<div class="complex-wave" style="opacity: 0.5;">
					<PhysiologicalWaveform mode="ecg" speed={0.32} amplitude={0.72} />
					<div class="complex-wave__layer complex-wave__layer--offset">
						<PhysiologicalWaveform mode="ecg" speed={0.25} amplitude={0.4} />
					</div>
				</div>
			</div>
		</section>
	</main>

	<!-- =========================================================
		 FOOTER
	========================================================= -->
	<footer class="footer">
		<div class="footer__brand">
			<div class="brand"><span class="brand__mark">N</span><span class="brand__name">NHM</span></div>
			<p>Non-Invasive Health Monitor</p>
		</div>
		<div class="footer__links">
			<a href="#technology">Technology</a>
			<a href="#privacy">Privacy</a>
			<a href="#research">Research</a>
			<a href="/monitor">Monitor</a>
		</div>
		<div class="footer__meta">
			<span>B.TECH FINAL YEAR PROJECT</span>
			<span>VIT CHENNAI</span>
		</div>
	</footer>
</div>

<style>
	/* =========================================================
	   TOKENS & BASE CSS
	========================================================= */
	.site-shell {
		--bg-dark: #030712;
		--bg-light: #f8fafc;
		--accent: #2bb8b0;
		--accent-glow: rgba(43,184,176,0.4);
		--text-main: #f8fafc;
		--text-muted: #94a3b8;
		--border-dark: rgba(255,255,255,0.06);
		--border-light: rgba(15,23,42,0.08);
		
		--font-sans: 'Space Grotesk', system-ui, sans-serif;
		--font-body: 'Inter', system-ui, sans-serif;
		--font-mono: 'JetBrains Mono', monospace;
	}

	.site-shell { position: relative; overflow: clip; background: var(--bg-dark); color: var(--text-main); font-family: var(--font-body); }
	.site-shell, .site-shell :global(*) { box-sizing: border-box; }
	.site-shell :global(a) { color: inherit; text-decoration: none; }
	
	/* High-end grain texture overlay */
	.site-shell::after {
		content: ""; position: fixed; inset: 0; z-index: 90; pointer-events: none; opacity: 0.04;
		background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
		mix-blend-mode: soft-light;
	}

	.section-dark { position: relative; background: var(--bg-dark); color: var(--text-main); }
	.section-light { position: relative; background: var(--bg-light); color: #0f172a; }

	.container { width: 100%; max-width: 1400px; margin: 0 auto; padding: 0 clamp(24px, 5vw, 64px); }

	/* Aesthetic Backgrounds for dark sections */
	.section-bg { position: absolute; inset: 0; z-index: 0; overflow: hidden; pointer-events: none; }
	.section-bg img { width: 100%; height: 100%; object-fit: cover; opacity: 0.12; mix-blend-mode: screen; filter: grayscale(100%) contrast(120%); }
	.section-bg__overlay { position: absolute; inset: 0; background: linear-gradient(to bottom, var(--bg-dark) 0%, transparent 30%, transparent 70%, var(--bg-dark) 100%); }
	.section-bg__overlay--heavy { background: radial-gradient(circle at center, transparent 0%, var(--bg-dark) 85%); }

	/* Complex Graph Layering Styling */
	.complex-wave { position: relative; width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; }
	.complex-wave__grid { position: absolute; inset: 0; background: linear-gradient(rgba(43, 184, 176, 0.15) 1px, transparent 1px), linear-gradient(90deg, rgba(43, 184, 176, 0.15) 1px, transparent 1px); background-size: 24px 24px; opacity: 0.4; mask-image: radial-gradient(circle at center, black, transparent 80%); pointer-events: none; }
	.complex-wave__layer { position: absolute; inset: 0; opacity: 0.3; filter: blur(1px); transform: scaleY(0.75); pointer-events: none; display: flex; align-items: center; justify-content: center; width: 100%; height: 100%; }
	.complex-wave__layer :global(svg) { width: 100%; height: 100%; }
	.complex-wave__layer--offset { opacity: 0.15; transform: scaleY(0.4) translateY(40px); filter: blur(2px); color: #38bdf8; }
	.complex-wave__scanline { position: absolute; inset: 0; background: linear-gradient(to bottom, transparent 50%, rgba(0, 0, 0, 0.15) 51%); background-size: 100% 4px; opacity: 0.6; pointer-events: none; }
	
	/* Typography */
	h1, h2, h3, .brand__name, .hardware__title { font-family: var(--font-sans); margin: 0; }
	.text-gradient { background: linear-gradient(135deg, #ffffff 0%, var(--accent) 100%); background-clip: text; -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
	.glow-text { text-shadow: 0 0 20px var(--accent-glow); }

	.eyebrow { font-family: var(--font-mono); font-size: 11px; font-weight: 600; letter-spacing: 0.2em; text-transform: uppercase; color: var(--text-muted); }
	.eyebrow--teal { color: var(--accent); }
	
	.section-kicker { display: flex; align-items: center; gap: 16px; margin-bottom: 48px; color: #64748b; font-family: var(--font-mono); font-size: 11px; font-weight: 600; letter-spacing: 0.2em; }
	.section-kicker::before { content: ""; width: 32px; height: 1px; background: currentColor; }
	.section-kicker--dark { color: var(--accent); }

	/* Glassmorphism & Cards */
	.glass-panel { background: rgba(255,255,255,0.02); backdrop-filter: blur(24px); -webkit-backdrop-filter: blur(24px); border: 1px solid var(--border-dark); border-radius: 32px; box-shadow: 0 40px 80px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.05); }
	.glass-panel-sm { background: rgba(255,255,255,0.02); backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px); border: 1px solid var(--border-dark); border-radius: 20px; }
	.card-light { background: #ffffff; border: 1px solid var(--border-light); border-radius: 24px; box-shadow: 0 20px 40px rgba(15,23,42,0.04); }

	/* Buttons */
	.button { display: inline-flex; align-items: center; justify-content: space-between; gap: 32px; padding: 16px 28px; border-radius: 999px; font-family: var(--font-mono); font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.1em; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); border: 1px solid transparent; }
	.button:hover { transform: translateY(-2px); }
	.button--light { background: #f8fafc !important; color: #030712 !important; border-color: #f8fafc; }
	.button--light:hover { background: transparent !important; color: #f8fafc !important; border-color: rgba(255,255,255,0.55); }
	.section-light .button--light { background: #030712 !important; color: #f8fafc !important; border-color: #030712; }
	.section-light .button--light:hover { background: transparent !important; color: #030712 !important; border-color: rgba(3,7,18,.4); }
	.button--dark { background: var(--bg-dark); color: var(--text-main); }
	.button--dark:hover { background: transparent; color: var(--bg-dark); border-color: var(--bg-dark); }
	.button--glow { box-shadow: 0 0 30px var(--accent-glow); }
	.button--glass { background: rgba(255,255,255,0.05); backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px); border: 1px solid var(--border-dark); color: var(--text-main); font-family: var(--font-mono); font-size: 11px; text-transform: uppercase; letter-spacing: 0.1em; padding: 12px 20px; border-radius: 999px; display: inline-flex; align-items: center; gap: 12px; transition: all 0.3s; }
	.button--glass:hover { background: var(--text-main); color: var(--bg-dark); transform: translateY(-1px); }

	.text-link { color: var(--text-muted); font-family: var(--font-mono); font-size: 11px; text-transform: uppercase; letter-spacing: 0.1em; transition: color 0.3s; }
	.text-link span { display: inline-block; margin-left: 6px; transition: transform 0.3s; }
	.text-link:hover { color: var(--text-main); }
	.text-link:hover span { transform: translate(3px, -3px); }

	/* =========================================================
	   NAVIGATION
	========================================================= */
	.nav { position: absolute; top: 0; right: 0; left: 0; z-index: 50; display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; width: 100%; max-width: 1400px; margin: 0 auto; padding: 32px clamp(24px, 5vw, 64px); color: var(--text-main); }
	.brand { display: inline-flex; align-items: center; gap: 12px; font-weight: 700; letter-spacing: -0.02em; }
	.brand__mark { display: grid; width: 32px; height: 32px; place-items: center; border: 1px solid var(--accent); border-radius: 50%; color: var(--accent); font-family: var(--font-mono); font-size: 12px; }
	.brand__name { font-size: 20px; }
	.nav__links { display: flex; gap: 40px; font-family: var(--font-mono); font-size: 12px; text-transform: uppercase; letter-spacing: 0.1em; color: var(--text-muted); }
	.nav__links a:hover { color: var(--text-main); }
	.nav__cta { justify-self: end; }

	/* =========================================================
	   PRELOADER
	========================================================= */
	.preloader { position: fixed; inset: 0; z-index: 9999; display: grid; place-items: center; background: radial-gradient(circle at 50% 50%, #061021 0%, #030712 60%); color: var(--text-main); overflow: hidden; transition: opacity 0.9s cubic-bezier(0.7,0,0.2,1), transform 1.1s cubic-bezier(0.7,0,0.2,1); }
	.preloader--closing { opacity: 0; transform: scale(1.03); pointer-events: none; }
	.preloader__grid { position: absolute; inset: 0; background: linear-gradient(rgba(43,184,176,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(43,184,176,0.03) 1px, transparent 1px); background-size: 48px 48px; mask-image: radial-gradient(circle at center, black, transparent 70%); }
	.preloader__orb { position: absolute; width: min(80vw,800px); height: min(80vw,800px); border-radius: 50%; background: radial-gradient(circle, rgba(43,184,176,0.1), transparent 60%); filter: blur(30px); }
	
	.preloader__inner { position: relative; z-index: 2; width: min(900px, 85vw); }
	.preloader__topline { display: flex; justify-content: space-between; color: var(--text-muted); font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.2em; }
	.preloader__identity { margin-top: 12vh; }
	.preloader__mini { color: var(--accent); font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.2em; margin-bottom: 24px; }
	.preloader__quote-text { display: block; color: var(--text-main); font-family: var(--font-sans); font-size: clamp(32px, 5vw, 64px); font-weight: 400; line-height: 1.1; letter-spacing: -0.04em; }
	
	.preloader__systems { display: grid; margin-top: 10vh; border-top: 1px solid var(--border-dark); }
	.preloader__system { display: grid; grid-template-columns: 40px 1fr auto 20px; gap: 16px; align-items: center; padding: 16px 0; border-bottom: 1px solid var(--border-dark); opacity: 0; transform: translateY(10px); animation: preloaderSystemIn 500ms var(--delay) cubic-bezier(0.2,0.8,0.2,1) forwards; font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.1em; color: var(--text-muted); }
	.preloader__system-index { color: var(--accent); }
	.preloader__system-ok { color: var(--accent); font-size: 8px; text-align: right; }
	
	.preloader__bottom { margin-top: 40px; }
	.preloader__progress { height: 1px; background: rgba(255,255,255,0.1); overflow: hidden; }
	.preloader__progress span { display: block; width: 0%; height: 100%; background: linear-gradient(90deg, transparent, var(--accent)); animation: preloaderProgress 4s cubic-bezier(0.2,0.8,0.2,1) forwards; }
	.preloader__progress-meta { display: flex; justify-content: space-between; margin-top: 12px; color: var(--text-muted); font-family: var(--font-mono); font-size: 8px; letter-spacing: 0.15em; }
	
	.preloader__ready { position: absolute; z-index: 0; color: rgba(255,255,255,0.02); font-family: var(--font-sans); font-size: clamp(100px, 20vw, 300px); font-weight: 700; letter-spacing: -0.05em; pointer-events: none; }

	@keyframes preloaderSystemIn { to { opacity: 1; transform: translateY(0); } }
	@keyframes preloaderProgress { to { width: 100%; } }

	/* =========================================================
	   HERO
	========================================================= */
	.hero { min-height: max(850px, 100svh); padding-top: 96px; padding-bottom: 40px; display: flex; flex-direction: column; overflow: visible; }
	.hero__grid { position: absolute; inset: 0; opacity: 0.6; mask-image: linear-gradient(to bottom, black 0%, rgba(0,0,0,0.6) 50%, transparent 95%); }
	
	.hero__technical { position: absolute; top: 110px; right: clamp(24px, 5vw, 64px); left: clamp(24px, 5vw, 64px); display: flex; justify-content: space-between; color: rgba(255,255,255,0.3); font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.2em; z-index: 10; max-width: 1400px; margin: 0 auto; }
	
	.hero__content-wrapper { flex: 1; display: flex; align-items: center; width: 100%; max-width: 1400px; margin: 0 auto; padding: 0 clamp(24px, 5vw, 64px); z-index: 20; position: relative; transform: translateY(-46px); }
	
	/* Fixed Hero Layout */
	.hero__content { display: grid; grid-template-columns: 1fr 1fr; align-items: center; gap: clamp(40px, 6vw, 100px); width: 100%; }
	
	.hero__copy-container { width: 100%; }
	.hero__copy { max-width: 650px; }
	.hero h1 { font-size: clamp(56px, 6vw, 110px); font-weight: 500; line-height: 0.9; letter-spacing: -0.05em; margin: 24px 0 32px; }
	.hero__lede { font-size: clamp(16px, 1.2vw, 18px); color: var(--text-muted); line-height: 1.7; margin-bottom: 48px; max-width: 540px; }
	.hero__actions { display: flex; align-items: center; flex-wrap: wrap; gap: 32px; }
	
	/* Fixed 3D Canvas wrapper */
	.hero__device { position: relative; width: 100%; height: 700px; overflow: visible; z-index: 30; }
	
	.hero__device-label { position: absolute; z-index: 12; display: inline-flex; align-items: center; gap: 10px; padding: 10px 16px; font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.1em; color: var(--text-main); }
	.hero__device-label--one { top: 20%; left: 0%; }
	.hero__device-label--two { top: 50%; right: -5%; }
	.hero__device-label--three { bottom: 15%; left: 20%; }
	
	.signal-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--accent); box-shadow: 0 0 16px var(--accent); }
	.neon-blue { background: #38bdf8; box-shadow: 0 0 16px #38bdf8; }

	.hero__signal { position: absolute; right: 0; bottom: 0; left: 0; z-index: 5; padding: 0 clamp(24px, 5vw, 64px) 24px; pointer-events: none; max-width: 1400px; margin: 0 auto; width: 100%; }
	.hero__signal::before { content: ""; position: absolute; right: clamp(24px, 5vw, 64px); bottom: 44px; left: clamp(24px, 5vw, 64px); height: 1px; background: linear-gradient(90deg, transparent, rgba(43,184,176,0.2), transparent); }
	.hero__signal > .complex-wave { width: 100%; height: 130px; margin-bottom: 10px; overflow: hidden; }
	.hero__signal > .complex-wave :global(svg) { transform: scale(1.02); }
	
	.hero__signal-meta { position: relative; z-index: 3; display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; color: var(--text-muted); font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.15em; margin-top: 8px; }
	.hero__signal-meta span:last-child { text-align: right; }

	/* =========================================================
	   SECTIONS Layouts
	========================================================= */
	.problem, .research, .signals, .federation, .product { padding: 140px 0; }
	.section-tight { padding-top: 100px; padding-bottom: 100px; }

	/* Section 02 - Problem Styling */
	.problem {
		position: relative;
		background: var(--bg-light);
		color: #0f172a;
	}
	.problem__heading {
		display: grid;
		grid-template-columns: 1.2fr 0.8fr;
		gap: clamp(40px, 6vw, 100px);
		align-items: end;
		margin-bottom: 50px;
	}
	.problem h2, .research h2, .signals h2, .federation h2, .system h2, .product h2 {
		font-size: clamp(44px, 5.5vw, 84px);
		font-weight: 450;
		line-height: 0.95;
		letter-spacing: -0.05em;
	}
	.problem h2 span { color: #0f172a; }
	.problem h2 em, .federation h2 em { color: var(--text-muted); font-style: normal; }
	.problem__intro-copy p {
		color: #475569;
		font-size: 16px;
		line-height: 1.7;
		margin: 0;
	}
	.problem__neural-stage {
		margin-top: 20px;
		width: 100%;
	}

	.research__heading { display: grid; grid-template-columns: 1.2fr 0.8fr; gap: clamp(60px, 8vw, 120px); align-items: end; margin-bottom: 80px; }
	.research__heading h2 span { color: #64748b; display: block; }
	.research__heading p, .hardware__heading p, .edge__heading p, .federation__heading p, .system__intro p, .product__heading p { max-width: 480px; color: #64748b; font-size: 16px; line-height: 1.7; margin: 0; }
	.research__timeline { width: 100%; min-height: 500px; overflow: hidden; padding: 20px 0; }

	/* =========================================================
	   HARDWARE
	========================================================= */
	.hardware { padding: 140px 0 100px; overflow: hidden; }
	.hardware__heading { display: grid; grid-template-columns: 1.2fr 0.8fr; gap: clamp(60px, 8vw, 120px); align-items: end; margin-bottom: 50px; }
	.hardware__title { font-size: clamp(52px, 6.5vw, 100px); line-height: 0.9; letter-spacing: -0.05em; }
	.hardware__heading p { color: var(--text-muted); }
	.hardware__studio-wrap { width: 100%; margin-top: 20px; }

	.technical-marquee { margin-top: 80px; border-top: 1px solid var(--border-dark); border-bottom: 1px solid var(--border-dark); padding: 24px 0; position: relative; overflow: hidden; }
	.marquee-item { display: inline-flex; align-items: center; gap: 40px; color: var(--text-muted); font-family: var(--font-mono); font-size: 12px; letter-spacing: 0.2em; white-space: nowrap; }
	.marquee-item i { color: var(--accent); font-style: normal; }

	/* =========================================================
	   SIGNALS
	========================================================= */
	/* Fixed the morphing text overlap issue */
	.signals__heading { display: grid; grid-template-columns: 1fr 1fr; align-items: end; gap: 40px; margin-bottom: 104px; }
	.signals h2 span { color: #94a3b8; display: block; }
	
	.signals__morph-container { display: flex; justify-content: flex-end; width: 100%; min-width: 0; overflow: visible; }
	.signals__morph { width: 100%; max-width: none; min-width: 0; text-align: right; color: #0f172a; font-size: clamp(32px, 4.2vw, 68px); text-transform: uppercase; font-family: var(--font-sans); font-weight: 600; letter-spacing: -0.045em; overflow: visible; }
	
	.signals__grid { display: grid; grid-template-columns: 1.3fr 0.7fr; gap: 40px; margin-top: 80px; }
	.signal-main { padding: 40px; }
	.signal-main__header { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; }
	.signal-label { color: #64748b; font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.15em; }
	.signal-main h3 { margin: 12px 0 0; font-size: 28px; font-weight: 600; letter-spacing: -0.03em; }
	
	.live-pill { display: inline-flex; align-items: center; gap: 8px; padding: 8px 16px; border-radius: 999px; border: 1px solid #e2e8f0; background: #f8fafc; color: #0f766e; font-family: var(--font-mono); font-size: 10px; font-weight: 600; letter-spacing: 0.1em; }
	
	.signal-main__wave { height: 320px; margin: 40px 0; overflow: hidden; border-radius: 20px; border: 1px solid rgba(15,23,42,0.05); }
	
	.signal-main__footer { display: flex; justify-content: space-between; border-top: 1px solid #e2e8f0; padding-top: 24px; color: #64748b; font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.15em; }
	
	.signal-stack { padding: 20px 40px; }
	.signal-list-item { display: grid; grid-template-columns: 40px 1fr auto; align-items: center; gap: 20px; padding: 24px 0; border-bottom: 1px solid #e2e8f0; }
	.signal-list-item:last-child { border-bottom: none; }
	.signal-list-item__number { color: #94a3b8; font-family: var(--font-mono); font-size: 12px; }
	.signal-list-item__copy strong { display: block; font-size: 18px; font-weight: 600; margin-bottom: 4px; }
	.signal-list-item__copy span { display: block; color: #64748b; font-size: 14px; }
	.signal-list-item code { background: #f1f5f9; padding: 6px 10px; border-radius: 6px; color: #64748b; font-family: var(--font-mono); font-size: 10px; }

	/* =========================================================
	   EDGE
	========================================================= */
	.edge { padding: 160px 0; overflow: hidden; }
	.edge__grid { position: absolute; inset: 0; background: linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px); background-size: 64px 64px; mask-image: linear-gradient(to bottom, transparent, black 20%, black 75%, transparent); }
	.edge__heading { position: relative; z-index: 2; display: grid; grid-template-columns: 1fr 0.7fr; gap: 8vw; align-items: end; }
	.edge__heading h2 span { color: var(--accent); display: block; }
	.edge__heading p { color: var(--text-muted); }
	
	.edge__flow { position: relative; z-index: 3; display: grid; grid-template-columns: repeat(3, 1fr); gap: clamp(40px, 6vw, 100px); margin: 120px 0 0; }
	.flow-node { display: flex; flex-direction: column; gap: 12px; padding: 40px 32px; text-align: center; }
	.flow-node__index { color: var(--accent); font-family: var(--font-mono); font-size: 12px; }
	.flow-node strong { font-size: 24px; font-weight: 600; }
	.flow-node span:last-child { color: var(--text-muted); font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.15em; }
	.flow-node--active { border-color: rgba(43,184,176,0.4); box-shadow: 0 0 40px rgba(43,184,176,0.1); }
	
	.edge__quote { position: relative; z-index: 2; margin: 160px auto 0; text-align: center; }
	.edge__line-shadow { font-size: clamp(50px, 8vw, 120px); font-weight: 750; letter-spacing: -0.05em; }

	/* =========================================================
	   FEDERATION
	========================================================= */
	/* Re-styled as dark section for better contrast on Map glowing dots */
	.federation { padding: 160px 0; overflow: hidden; }
	.federation__heading { display: grid; grid-template-columns: 1fr 0.6fr; gap: 8vw; align-items: end; }
	.federation__heading p { color: var(--text-muted); }
	
	.federation__stage { position: relative; min-height: 650px; margin-top: 100px; }
	.federation__map { position: absolute; inset: 45px 0 auto; z-index: 1; display: grid; height: 500px; place-items: center; opacity: 0.95; pointer-events: none; mask-image: linear-gradient(to bottom, transparent, black 16%, black 77%, transparent); }
	
	.federation__path { position: relative; z-index: 4; display: grid; grid-template-columns: 1fr 1.5fr 1fr; align-items: center; gap: 40px; min-height: 500px; }
	.federation-node { display: flex; flex-direction: column; gap: 12px; }
	.federation-node span { color: var(--text-muted); font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.15em; }
	.federation-node strong { font-size: 28px; font-weight: 600; letter-spacing: -0.03em; }
	.federation-node--right { text-align: right; }
	
	.federation-path-line { position: relative; display: flex; align-items: center; justify-content: center; gap: 12px; height: 2px; }
	.federation-path-line::before { content: ""; position: absolute; width: 100%; height: 2px; background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent); }
	.federation-path-line span { position: relative; z-index: 2; width: 8px; height: 8px; border-radius: 50%; background: #2dd4bf; box-shadow: 0 0 20px rgba(45,212,191,0.8); animation: packet 2.5s cubic-bezier(0.4,0,0.2,1) infinite; }
	.federation-path-line span:nth-child(2) { animation-delay: 0.4s; }
	.federation-path-line span:nth-child(3) { animation-delay: 0.8s; }
	@keyframes packet { 0%, 100% { transform: translateX(-80px); opacity: 0; } 50% { transform: translateX(0px); opacity: 1; } }

	.federation__rule { position: relative; z-index: 5; display: grid; grid-template-columns: 1fr 1px 1fr; align-items: center; max-width: 900px; margin: 20px auto 0; padding: 40px; }
	.federation__rule-col { display: flex; flex-direction: column; gap: 12px; text-align: center; }
	.federation__rule-col span { font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.15em; font-weight: 600; }
	.federation__rule-col strong { font-size: 18px; font-weight: 600; }
	.rule-bad { color: #ef4444; }
	.rule-good { color: #0ea5e9; }
	.federation__rule-divider { width: 1px; height: 60px; background: var(--border-dark); }

	/* =========================================================
	   SYSTEM
	========================================================= */
	.system { padding: 160px 0; overflow: hidden; }
	.system__intro { display: grid; grid-template-columns: 1fr 0.6fr; gap: 8vw; align-items: end; }
	.system__intro h2 span { color: var(--accent); display: block; }
	.system__intro h2 { margin-bottom: 30px; }
	.system__intro p { color: var(--text-muted); }
	.system__matrix-wrap { margin-top: 76px; }
	
	.system__architecture { display: grid; grid-template-columns: repeat(9, 1fr); align-items: center; width: 100%; margin-top: 100px; }
	.system-layer { display: flex; flex-direction: column; justify-content: center; gap: 12px; height: 200px; padding: 24px; text-align: center; }
	.system-layer > span { color: var(--accent); font-family: var(--font-mono); font-size: 10px; }
	.system-layer strong { font-size: 14px; font-weight: 600; }
	.system-layer small { color: var(--text-muted); font-family: var(--font-mono); font-size: 8px; line-height: 1.6; letter-spacing: 0.1em; }
	.system-layer--accent { border-color: rgba(43,184,176,0.4); background: rgba(43,184,176,0.08); }
	.system-layer--terminal { background: rgba(14,165,233,0.08); border-color: rgba(14,165,233,0.3); }
	.system-connector { height: 1px; background: linear-gradient(90deg, rgba(255,255,255,0.1), rgba(43,184,176,0.5)); }

	.system__globe { position: relative; display: grid; grid-template-columns: 0.8fr 1.2fr; align-items: center; min-height: 650px; margin-top: 80px; padding: 60px; overflow: hidden; }
	.system__globe-copy { position: relative; z-index: 5; }
	.system__globe-copy span { color: var(--accent); font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.2em; }
	.system__globe-copy h3 { margin: 20px 0 0; font-size: clamp(40px, 5vw, 70px); font-weight: 500; line-height: 1; }
	.globe { position: absolute !important; right: -5%; top: 50%; transform: translateY(-50%); width: min(100%, 750px); height: min(100%, 750px); }

	/* =========================================================
	   PRODUCT
	========================================================= */
	.product { padding: 160px 0; }
	.product__heading { display: grid; grid-template-columns: 1fr 0.6fr; gap: 8vw; align-items: end; }
	.product__heading h2 span { color: #94a3b8; display: block; }
	
	.product__preview { margin-top: 80px; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 24px; box-shadow: 0 40px 100px rgba(15,23,42,0.08); overflow: hidden; }
	.product__chrome { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; height: 50px; padding: 0 24px; border-bottom: 1px solid #e2e8f0; background: #f8fafc; color: #64748b; font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.15em; }
	.product__chrome > span:last-child { justify-self: end; }
	.chrome-dots { display: flex; gap: 8px; }
	.chrome-dots span { width: 10px; height: 10px; border-radius: 50%; background: #cbd5e1; }
	.chrome-dots span:nth-child(1) { background: #fca5a5; }
	.chrome-dots span:nth-child(2) { background: #fcd34d; }
	.chrome-dots span:nth-child(3) { background: #86efac; }
	
	.live-indicator { display: flex; align-items: center; gap: 8px; font-weight: 600; color: #0f766e; }
	
	.product__screen { padding: clamp(40px, 6vw, 80px); background: #ffffff; }
	.monitor-copy span { color: #0d9488; font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.15em; font-weight: 600; }
	.monitor-copy h3 { max-width: 800px; margin: 16px 0; font-size: clamp(40px, 5vw, 64px); font-weight: 500; line-height: 1; letter-spacing: -0.04em; }
	.monitor-copy p { max-width: 500px; margin: 0; color: #64748b; font-size: 18px; line-height: 1.6; }
	
	.monitor-vitals { display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 24px; max-width: 700px; margin-top: 60px; }
	.vital-card { padding: 40px; }
	.vital-card span { display: block; color: #64748b; font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.15em; }
	.ticker-value { display: flex !important; align-items: baseline; gap: 8px; margin-top: 16px; }
	.ticker-value :global(span) { color: #0f172a; font-family: var(--font-sans); font-size: clamp(60px, 6vw, 90px); font-weight: 500; line-height: 1; letter-spacing: -0.05em; }
	.ticker-value small { color: #94a3b8; font-family: var(--font-sans); font-size: 18px; font-weight: 400; }
	
	.monitor-wave { height: 220px; margin-top: 60px; padding: 20px; overflow: hidden; border-radius: 12px; border: 1px solid rgba(15,23,42,0.05); }
	.product__cta { display: flex; justify-content: flex-end; margin-top: 40px; }

	/* =========================================================
	   FINAL
	========================================================= */
	.final { min-height: 85vh; display: grid; place-items: center; padding: 160px 0; overflow: hidden; }
	.final__grid { position: absolute; inset: 0; background: linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px); background-size: 64px 64px; mask-image: radial-gradient(circle at center, black, transparent 75%); pointer-events: none; }
	
	.final__headline { display: flex; flex-direction: column; align-items: center; gap: 12px; font-size: clamp(45px, 7vw, 100px); line-height: 1.1; letter-spacing: -0.04em; margin-bottom: 40px; width: 100%; word-break: keep-all; }
	.final__p { max-width: 600px; margin: 0 0 50px; color: var(--text-muted); font-size: 20px; line-height: 1.6; }
	
	.final__wave { position: absolute; right: 0; bottom: 0; left: 0; z-index: 1; opacity: 0.6; mask-image: linear-gradient(to top, black, transparent); height: 280px; overflow: hidden; pointer-events: none; }

	/* =========================================================
	   FOOTER
	========================================================= */
	.footer { display: grid; grid-template-columns: 1fr auto 1fr; align-items: end; gap: 40px; padding: 60px clamp(24px, 5vw, 64px); border-top: 1px solid var(--border-dark); background: var(--bg-dark); color: var(--text-muted); }
	.footer__brand p { margin: 12px 0 0; font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.15em; }
	.footer__links { display: flex; gap: 40px; font-family: var(--font-mono); font-size: 12px; letter-spacing: 0.1em; text-transform: uppercase; }
	.footer__links a:hover { color: var(--text-main); }
	.footer__meta { justify-self: end; display: flex; flex-direction: column; gap: 8px; font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.15em; text-align: right; margin: 0; }

	/* =========================================================
	   RESPONSIVE
	========================================================= */
	@media (max-width: 1050px) {
		.nav { grid-template-columns: 1fr auto; }
		.nav__links { display: none; }
		
		.hero__content { grid-template-columns: 1fr; text-align: center; gap: 40px; }
		.hero__copy { max-width: 100%; margin: 0 auto; display: flex; flex-direction: column; align-items: center; }
		.hero__actions { justify-content: center; }
		.hero__device { height: 500px; margin-top: 40px; overflow: visible; }
		.hero__content-wrapper { transform: translateY(-24px); }
		
		.problem__heading, .research__heading, .hardware__heading, .signals__heading, .edge__heading, .federation__heading, .system__intro, .product__heading { grid-template-columns: 1fr; text-align: center; }
		.problem__intro-copy p, .research__heading p, .hardware__heading p, .edge__heading p, .federation__heading p, .system__intro p, .product__heading p { max-width: 600px; margin: 20px auto 0; }
		.signals__morph-container { justify-content: center; }
		.signals__morph { text-align: center; }
		.signals__heading { margin-bottom: 76px; }
		
		.signals__grid { grid-template-columns: 1fr; }
		.system__architecture { grid-template-columns: 1fr; gap: 20px; }
		.system-connector { width: 2px; height: 30px; margin: 0 auto; background: linear-gradient(to bottom, rgba(255,255,255,0.1), rgba(43,184,176,0.5)); }
		
		.system__globe { grid-template-columns: 1fr; text-align: center; padding: 40px; }
		.globe { position: relative !important; top: auto; right: auto; transform: none; margin: 40px auto 0; height: 400px; }
		
		.federation__path { grid-template-columns: 1fr; gap: 40px; text-align: center; }
		.federation-node--right { text-align: center; }
		.federation-path-line { transform: rotate(90deg); margin: 40px 0; }
		
		.footer { grid-template-columns: 1fr auto; }
		.footer__meta { grid-column: 2; }
	}

	@media (max-width: 700px) {
		.nav { padding: 20px; }
		.nav__cta span:first-child { display: none; }
		
		.hero { padding: 120px 0 40px; min-height: auto; }
		.hero__technical { display: none; }
		.hero h1 { font-size: clamp(50px, 14vw, 80px); }
		.hero__device { height: 400px; overflow: visible; }
		.hero__content-wrapper { transform: translateY(-12px); }
		.hero__signal { padding: 0 20px 20px; }
		.hero__signal-meta span:nth-child(2) { display: none; }
		.signals__heading { margin-bottom: 56px; }
		
		.problem, .research, .signals, .federation, .product, .hardware, .edge, .system, .final { padding: 80px 0; }
		
		.signal-main { padding: 24px; }
		.signal-main__header { flex-direction: column; gap: 16px; }
		.signal-main__footer { flex-direction: column; gap: 12px; }
		.signal-stack { padding: 20px; }
		
		.edge__flow { grid-template-columns: 1fr; gap: 24px; }
		
		.federation__map { display: none; }
		.federation__rule { grid-template-columns: 1fr; gap: 24px; padding: 32px 20px; }
		.federation__rule-divider { width: 100%; height: 1px; }
		
		.product__screen { padding: 24px; }
		.monitor-vitals { grid-template-columns: 1fr; }
		.monitor-wave { height: 160px; }
		
		.footer { grid-template-columns: 1fr; text-align: left; align-items: flex-start; gap: 32px; padding: 40px 20px; }
		.footer__links { flex-direction: column; gap: 20px; }
		.footer__meta { justify-self: start; text-align: left; }

		.preloader__inner { width: 90vw; }
		.preloader__quote-text { font-size: 28px; }
		.preloader__ready { font-size: 20vw; }
		
		.final__headline { font-size: clamp(35px, 8vw, 55px); }
	}

	@media (prefers-reduced-motion: reduce) {
		.site-shell, .site-shell :global(*) { animation-duration: 0.001ms !important; animation-iteration-count: 1 !important; transition-duration: 0.001ms !important; }
		.preloader, .preloader__orb, .preloader__system, .preloader__progress span, .preloader__ready { animation: none !important; }
	}
</style>
