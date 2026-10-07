<script lang="ts">
	import Panel from '$lib/components/dashboard/Panel.svelte';
</script>
<svelte:head><title>About | NHM</title></svelte:head>
<div class="eyebrow">NHM / ABOUT</div><h1>About this prototype</h1>
<p class="lead">A research monitoring prototype and a separate federated-development demonstration. These are engineering and scientific evidence boundaries, not medical claims.</p>
<div class="cards">
	<Panel eyebrow="01 / SCOPE" title="What NHM is"><ul>
		<li>NHM is a <b>research prototype</b> for physiological monitoring and federated model development. It is <b>not diagnostic</b> and not a medical device.</li>
		<li>Monitoring states are research outputs, not health assessments.</li>
	</ul></Panel>
	<Panel eyebrow="02 / MONITORING" title="What runs today"><ul>
		<li>Hardware today is <b>SIMULATED ONLY</b> (virtual wearable, WEARABLE_SIM_V1). No physical wearable is connected. A real wearable is a future source adapter that requires verification.</li>
		<li>Inference is server-side: MODEL_V2_FINAL in SOFTWARE_SYSTEM_V2. Nothing runs on a sensor.</li>
		<li>The waveform is a simulated source ECG. A PPG waveform is unavailable in the current simulator; SpO2/PPG-derived context is shown where the backend emits it.</li>
	</ul></Panel>
	<Panel eyebrow="03 / DEVELOPMENT" title="Federated development"><ul>
		<li>The <b>engineering federation runtime is enabled</b>. It runs eight logical, synthetic research clients (not hospitals or institutions) on one demonstration machine; each performs genuine local optimization and the coordinator receives model updates rather than local examples.</li>
		<li>In a connected (Clerk) live run only, one existing synthetic client, SIM_FL_SITE_00, is shown as <b>MY EDGE CLIENT</b> - a presentation binding to the signed-in owner. Its training data is still synthetic engineering data: your physiology does not train any model, no personal or personalized model exists, and monitoring sessions are never federation data.</li>
	</ul></Panel>
	<Panel eyebrow="04 / BOUNDARY" title="What NHM does not claim"><ul>
		<li>A federation run produces an engineering candidate that stays in a sandbox. It is never automatically deployed and does not replace the released MODEL_V2_FINAL.</li>
		<li>No physical wearable validation, personalized model, or hospital deployment is established. NHM is not diagnostic.</li>
	</ul></Panel>
</div>
<style>.eyebrow{color:#2bb8b0;font:10px 'JetBrains Mono',monospace;letter-spacing:.14em}h1{margin:10px 0 12px;font:500 clamp(26px,4vw,40px) 'Space Grotesk',sans-serif}.lead{max-width:740px;color:#a7b8c9;font-size:14px;line-height:1.6}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,380px),1fr));gap:12px;align-items:start}ul{margin:0;padding-left:18px;display:grid;gap:10px;color:#cbd5e1;line-height:1.7;font-size:13px}li{overflow-wrap:anywhere}</style>
