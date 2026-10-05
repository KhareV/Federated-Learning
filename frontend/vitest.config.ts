import { sveltekit } from '@sveltejs/kit/vite';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vitest/config';

// Minimal vitest config (Section 43): this project tree has no prior unit-test framework.
// Reuses the project's own SvelteKit/Vite plugin pipeline (for $lib resolution AND so Svelte 5
// rune syntax in .svelte.ts modules like dashboard/session.svelte.ts compiles correctly)
// rather than hand-rolling a separate alias/transform setup.
//
// C034: resolve.conditions: ['browser'] makes `svelte` resolve to its CLIENT build under
// Vitest (default is the server/SSR build, which has no `mount()`) -- required only for the
// one rendered-component test (page.render.test.ts, environment: jsdom via an inline
// `// @vitest-environment jsdom` directive); it does not affect the actual app build, which
// uses the separate top-level vite.config.ts.
export default defineConfig({
	plugins: [sveltekit()],
	resolve: {
		conditions: ['browser'],
		alias: { '@clerk/clerk-js': fileURLToPath(new URL('./clerk-sdk/node_modules/@clerk/clerk-js', import.meta.url)) }
	},
	test: {
		environment: 'node',
		include: ['src/**/__tests__/**/*.test.ts']
	}
});
