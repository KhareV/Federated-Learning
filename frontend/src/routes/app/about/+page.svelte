<script lang="ts">
	import Panel from '$lib/components/dashboard/Panel.svelte';
</script>
<svelte:head><title>About | NHM</title></svelte:head>
<div class="eyebrow">NHM / ABOUT</div><h1>About this prototype</h1>
<Panel eyebrow="01 / SCOPE" title="What this is - and is not">
	<ul>
		<li>NHM is a <b>research prototype</b> for physiological monitoring and federated model development. It is <b>not diagnostic</b> and not a medical device.</li>
		<li>Hardware today is <b>SIMULATED ONLY</b> (virtual wearable, WEARABLE_SIM_V1). No physical wearable is connected. A real wearable is a future source adapter that requires verification.</li>
		<li>Inference is server-side: MODEL_V2_FINAL in SOFTWARE_SYSTEM_V2. Nothing runs on a sensor.</li>
		<li>The waveform is a simulated source ECG. A PPG waveform is unavailable in the current simulator; SpO2/PPG-derived context is shown where the backend emits it.</li>
		<li>Federated-learning client sites are synthetic research partitions, not institutions. The federation product runtime is not yet enabled.</li>
		<li>Monitoring states are research outputs, not health assessments.</li>
	</ul>
</Panel>
<style>.eyebrow{color:#2bb8b0;font:10px 'JetBrains Mono',monospace;letter-spacing:.14em}h1{margin:10px 0 18px;font:500 clamp(26px,4vw,40px) 'Space Grotesk',sans-serif}ul{margin:0;padding-left:18px;display:grid;gap:10px;color:#cbd5e1;line-height:1.7;font-size:14px}</style>
