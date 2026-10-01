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

// NHM_API_RUNTIME_V1: the frozen T032 FastAPI service (uvicorn api.app:app), dev-run on a
// distinct port from the legacy /api backend above. Same-origin in production via reverse
// proxy; override with VITE_NHM_API_BASE_URL for a non-same-origin research setup.
const nhmApiProxy: ProxyOptions = {
	target: 'http://localhost:8001',
	changeOrigin: true
};

export default defineConfig({
	plugins: [tailwindcss(), sveltekit()],
	server: { proxy: { '/api': apiProxy, '/ws': websocketProxy, '/v1': nhmApiProxy } }
});
