import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vitest/config';

// Minimal vitest config (Section 43): this project tree has no prior unit-test framework.
// Reuses the project's own SvelteKit/Vite plugin pipeline (for $lib resolution AND so Svelte 5
// rune syntax in .svelte.ts modules like dashboard/session.svelte.ts compiles correctly)
// rather than hand-rolling a separate alias/transform setup.
export default defineConfig({
	plugins: [sveltekit()],
	test: {
		environment: 'node',
		include: ['src/**/__tests__/**/*.test.ts']
	}
});
