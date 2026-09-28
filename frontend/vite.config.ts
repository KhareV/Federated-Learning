import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig, type ProxyOptions } from 'vite';

const apiProxy: ProxyOptions = {
	target: 'http://localhost:8000',
	changeOrigin: true,
	rewrite: (path) => path.replace(/^\/api/, '')
};

const websocketProxy: ProxyOptions = {
	target: 'ws://localhost:8000',
	ws: true,
	changeOrigin: true
};

export default defineConfig({
	plugins: [tailwindcss(), sveltekit()],
	server: { proxy: { '/api': apiProxy, '/ws': websocketProxy } }
});
