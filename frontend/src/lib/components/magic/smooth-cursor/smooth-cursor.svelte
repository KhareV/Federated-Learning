<script lang="ts">
	// The site's arrow cursor. It follows the mouse INSTANTLY, exactly like the system pointer: the position is written straight to the element on every
	// pointer event (no spring, no frame throttling, no rotation or scale easing), and the arrow's tip is the hotspot.
	import { onMount } from "svelte";
	import type { Snippet } from "svelte";

	let { cursor }: { cursor?: Snippet } = $props();

	let el = $state<HTMLDivElement>();
	let visible = $state(false);

	// The default arrow is drawn 50x54 and shown at half scale about its centre, which puts its tip 25px right and ~15.75px down from the element's corner.
	const TIP_X = 25;
	const TIP_Y = 15.75;

	onMount(() => {
		const place = (e: MouseEvent | PointerEvent) => {
			if (el) el.style.transform = `translate3d(${e.clientX - TIP_X}px, ${e.clientY - TIP_Y}px, 0)`;
			if (!visible) visible = true;
		};
		const leave = () => { visible = false; };
		document.body.style.cursor = "none";
		window.addEventListener("pointermove", place, { passive: true });
		window.addEventListener("mousemove", place, { passive: true });
		document.documentElement.addEventListener("mouseleave", leave);
		return () => {
			window.removeEventListener("pointermove", place);
			window.removeEventListener("mousemove", place);
			document.documentElement.removeEventListener("mouseleave", leave);
			document.body.style.cursor = "auto";
		};
	});
</script>

<div
	bind:this={el}
	data-testid="site-cursor"
	style="position: fixed; left: 0; top: 0; z-index: 100; pointer-events: none; will-change: transform; opacity: {visible ? 1 : 0};"
>
	{#if cursor}
		{@render cursor()}
	{:else}
		<svg
			xmlns="http://www.w3.org/2000/svg"
			width={50}
			height={54}
			viewBox="0 0 50 54"
			fill="none"
			style="scale: 0.5"
		>
			<g filter="url(#filter0_d_91_7928)">
				<path
					d="M42.6817 41.1495L27.5103 6.79925C26.7269 5.02557 24.2082 5.02558 23.3927 6.79925L7.59814 41.1495C6.75833 42.9759 8.52712 44.8902 10.4125 44.1954L24.3757 39.0496C24.8829 38.8627 25.4385 38.8627 25.9422 39.0496L39.8121 44.1954C41.6849 44.8902 43.4884 42.9759 42.6817 41.1495Z"
					fill="black"
				/>
				<path
					d="M43.7146 40.6933L28.5431 6.34306C27.3556 3.65428 23.5772 3.69516 22.3668 6.32755L6.57226 40.6778C5.3134 43.4156 7.97238 46.298 10.803 45.2549L24.7662 40.109C25.0221 40.0147 25.2999 40.0156 25.5494 40.1082L39.4193 45.254C42.2261 46.2953 44.9254 43.4347 43.7146 40.6933Z"
					stroke="white"
					stroke-width={2.25825}
				/>
			</g>
			<defs>
				<filter
					id="filter0_d_91_7928"
					x={0.602397}
					y={0.952444}
					width={49.0584}
					height={52.428}
					filterUnits="userSpaceOnUse"
					color-interpolation-filters="sRGB"
				>
					<feFlood flood-opacity={0} result="BackgroundImageFix" />
					<feColorMatrix
						in="SourceAlpha"
						type="matrix"
						values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 127 0"
						result="hardAlpha"
					/>
					<feOffset dy={2.25825} />
					<feGaussianBlur stdDeviation={2.25825} />
					<feComposite in2="hardAlpha" operator="out" />
					<feColorMatrix
						type="matrix"
						values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0.08 0"
					/>
					<feBlend
						mode="normal"
						in2="BackgroundImageFix"
						result="effect1_dropShadow_91_7928"
					/>
					<feBlend
						mode="normal"
						in="SourceGraphic"
						in2="effect1_dropShadow_91_7928"
						result="shape"
					/>
				</filter>
			</defs>
		</svg>
	{/if}
</div>
