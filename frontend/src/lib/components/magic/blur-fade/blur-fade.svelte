<script lang="ts">
	export let inView = false;
	export let direction: 'up' | 'down' | 'left' | 'right' = 'up';
	export let offset = 0;
	export let delay = 0;
	export let blur = '0px';
	export let duration = 0;
	export let once = false;
</script>

<div class={`blur-fade blur-fade--${direction}`} data-in-view={inView} data-once={once} style={`--blur:${blur}; --offset:${offset}px; --delay:${delay}s; --duration:${duration}s`}>
	<slot />
</div>
