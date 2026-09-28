<script lang="ts">
	import { Canvas, T } from '@threlte/core';
	import { GLTF } from '@threlte/extras';
	import { onMount } from 'svelte';

	// Gentle, continuous rotation for an ultra-premium feel
	let rotY = 0;
	let rotX = 0.15;
	
	onMount(() => {
		let animationId: number;
		const animate = () => {
			rotY -= 0.002; // Smooth slow rotation
			rotX = 0.15 + Math.sin(Date.now() * 0.001) * 0.05; // Gentle float
			animationId = requestAnimationFrame(animate);
		};
		animate();
		return () => cancelAnimationFrame(animationId);
	});
</script>

<div class="watch-scene">
	<Canvas dpr={[1, 2]}>
		<!-- Camera positioned so the full watch unibody and straps fit gracefully -->
		<T.PerspectiveCamera makeDefault position={[0, 0.2, 9.8]} fov={32} />

		<!-- Premium Studio Lighting Setup -->
		<T.AmbientLight intensity={1.4} color="#ffffff" />
		<T.DirectionalLight position={[5, 6, 5]} intensity={4.5} color="#14b8a6" />
		<T.DirectionalLight position={[-5, 4, -2]} intensity={3} color="#38bdf8" />
		<T.SpotLight position={[0, 8, 2]} intensity={7} color="#ffffff" angle={0.6} penumbra={1} />
		<T.PointLight position={[0, -3, 3]} intensity={2.5} color="#2dd4bf" />

		<!-- Centered and scaled model -->
		<T.Group rotation={[rotX, rotY, -0.05]} scale={0.50} position={[0, 0, 0]}>
			<GLTF url="/models/nhm-watch.glb" />
		</T.Group>
	</Canvas>
</div>

<style>
	.watch-scene {
		position: absolute;
		/* Let the watch breathe beyond the device column. The canvas is
		   intentionally oversized so the straps can cross the surrounding
		   grid and labels like a physical object in front of the page. */
		top: -5%;
		left: -20%;
		width: 160%;
		height: 110%;
		z-index: 30;
		transform: translateY(-4%);
		pointer-events: none;
		overflow: visible;
	}

	.watch-scene :global(canvas) {
		display: block;
		width: 100% !important;
		height: 100% !important;
		outline: none;
		background: transparent !important;
	}

	@media (max-width: 1050px) {
		.watch-scene { left: -5%; width: 110%; height: 104%; }
	}
</style>
