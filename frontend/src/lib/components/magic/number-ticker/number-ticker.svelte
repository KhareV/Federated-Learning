<script lang="ts">
	import { onMount } from 'svelte';

	export let value = 0;
	export let startValue = 0;
	export let delay = 0;
	export let duration = 0.6;
	export let decimalPlaces = 0;
	export let once = false;
	export let className = '';
	export { className as class };

	let currentValue = startValue;

	onMount(() => {
		const timeout = window.setTimeout(() => {
			currentValue = value;
		}, delay * 1000);

		return () => {
			window.clearTimeout(timeout);
		};
	});

	$: displayedValue = Number(currentValue).toFixed(decimalPlaces);
</script>

<span class={className} data-once={once} style={`--duration:${duration}s`}>
	{displayedValue}
</span>
