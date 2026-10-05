import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { fileURLToPath } from 'node:url';
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
// NHM_API_PORT lets scripts/run_e2e_dashboard_demo_c034.py point both `vite dev` and
// `vite preview` at whatever ephemeral port it actually started the backend on.
const nhmApiPort = process.env.NHM_API_PORT ?? '8001';
const nhmApiProxy: ProxyOptions = {
	target: `http://localhost:${nhmApiPort}`,
	changeOrigin: true
};

// CAPSTONE_UI_V1: the CAP-004 product API (scripts/run_capstone_product.py, default port 8002) is reached
// same-origin at /product (HTTP + WebSocket). It is SEPARATE from the /v1 research-runtime proxy above,
// which is not repointed. NHM_PRODUCT_API_PORT lets the canonical E2E use an ephemeral port.
const productApiPort = process.env.NHM_PRODUCT_API_PORT ?? '8002';
const productProxy: ProxyOptions = {
	target: `http://127.0.0.1:${productApiPort}`,
	changeOrigin: true,
	ws: true
};

// The official ClerkJS browser SDK lives in the additive frontend/clerk-sdk package (exact pin; the
// frozen V2-014 lock binds frontend/package.json). It is imported lazily, in CLERK mode only.
const clerkJs = fileURLToPath(new URL('./clerk-sdk/node_modules/@clerk/clerk-js', import.meta.url));

export default defineConfig({
	plugins: [tailwindcss(), sveltekit()],
	resolve: { alias: { '@clerk/clerk-js': clerkJs } },
	server: { proxy: { '/api': apiProxy, '/ws': websocketProxy, '/v1': nhmApiProxy, '/product': productProxy } },
	preview: { proxy: { '/api': apiProxy, '/ws': websocketProxy, '/v1': nhmApiProxy, '/product': productProxy } }
});
