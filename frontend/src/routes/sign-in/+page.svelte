<script lang="ts">
	// CAPSTONE_FRONTEND_AUTH_V1 sign-in. The BACKEND (/product/v1/system) decides the mode.
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { getProductStore } from '$lib/product/state.svelte';
	import type { AuthIdentity } from '$lib/product/types';

	const store = getProductStore();
	let host = $state<HTMLDivElement | null>(null);
	let preview = $state<AuthIdentity | null>(null);
	let entering = $state(false);
	let unmount: (() => void) | null = null;
	const auth = $derived(store.authState);

	onMount(() => {
		void (async () => {
			const state = await store.auth.bootstrap();
			if (state.phase === 'AUTHENTICATED') { await goto('/app'); return; }
			if (state.mode === 'DEMO') { try { preview = await store.api.me(); } catch { preview = null; } }
		})();
		return () => unmount?.();
	});

	$effect(() => {
		if (auth.mode === 'CLERK' && auth.phase === 'SIGN_IN_REQUIRED' && host && !unmount) unmount = store.auth.mountClerkSignIn(host);
		if (auth.phase === 'AUTHENTICATED') void goto('/app');
	});

	async function enterDemo() {
		entering = true;
		const state = await store.auth.enterDemo();
		entering = false;
		if (state.phase === 'AUTHENTICATED') await goto('/app');
	}
</script>

<svelte:head><title>Sign in | NHM</title></svelte:head>

<main class="signin">
	<a class="brand" href="/" aria-label="NHM home"><span>N</span>NHM</a>
	<section class="card" aria-labelledby="si-title">
		<div class="eyebrow">NHM / FEDERATED PHYSIOLOGICAL MONITORING RESEARCH PLATFORM</div>

		{#if auth.phase === 'LOADING'}
			<h1 id="si-title">Checking the local product system…</h1>
			<p role="status">Reading the authentication mode from the product backend.</p>
		{:else if auth.phase === 'BACKEND_UNREACHABLE'}
			<h1 id="si-title">Product backend unavailable</h1>
			<p class="err" role="alert">{auth.error}</p>
			<p>Start the local product API and the SOFTWARE_SYSTEM_V2 service, then reload:</p>
			<pre>python -m scripts.run_nhm_default
python -m scripts.run_capstone_product</pre>
		{:else if auth.phase === 'AUTHENTICATION_UNAVAILABLE'}
			<h1 id="si-title">AUTHENTICATION UNAVAILABLE</h1>
			<p class="err" role="alert">{auth.error}</p>
			<p>The backend requires Clerk sign-in. The product does <b>not</b> fall back to the offline demo identity.</p>
		{:else if auth.mode === 'DEMO'}
			<h1 id="si-title">NHM OFFLINE FACULTY DEMO</h1>
			<p class="lede">This workspace uses an explicit offline demo identity supplied by the local product backend. There is no password and no external sign-in service.</p>
			<dl>
				<dt>IDENTITY</dt><dd>{preview?.user_id ?? 'demo identity (verified on entry)'}</dd>
				<dt>AUTH PROVIDER</dt><dd>DEMO - NOT CLERK</dd>
				<dt>HARDWARE</dt><dd>SIMULATED ONLY - no physical wearable</dd>
				<dt>MODEL</dt><dd>{auth.system?.model_id} via {auth.system?.software_system} (server-side)</dd>
			</dl>
			<p class="disclose">Research prototype. Not diagnostic. Simulated device. Monitoring states are research outputs, not health assessments.</p>
			<button class="cta" onclick={enterDemo} disabled={entering}>{entering ? 'VERIFYING…' : 'ENTER DEMO WORKSPACE'}</button>
			{#if auth.error}<p class="err" role="alert">{auth.error}</p>{/if}
		{:else}
			<h1 id="si-title">Sign in to NHM</h1>
			<div bind:this={host} class="clerk" data-testid="clerk-mount"></div>
			{#if auth.error}<p class="err" role="alert">{auth.error}</p>{/if}
		{/if}
	</section>
</main>

<style>
	.signin { min-height: 100vh; display: grid; place-items: center; align-content: center; gap: 28px; padding: 24px 16px; background: radial-gradient(900px 500px at 70% -10%, rgba(43,184,176,.12), transparent), #030712; color: #eef7f6; font-family: Inter, sans-serif; }
	.brand { display: flex; align-items: center; gap: 10px; color: inherit; text-decoration: none; font: 600 15px 'Space Grotesk', sans-serif; letter-spacing: .18em; } .brand span { display: grid; place-items: center; width: 30px; height: 30px; border: 1px solid #2bb8b0; color: #2bb8b0; letter-spacing: 0; }
	.card { width: min(100%, 620px); box-sizing: border-box; padding: clamp(22px, 4vw, 40px); border: 1px solid var(--nhm-border); background: rgba(8,14,29,.85); }
	.eyebrow { color: #2bb8b0; font: 10px/1.5 'JetBrains Mono', monospace; letter-spacing: .14em; }
	h1 { margin: 18px 0 12px; font: 500 clamp(26px, 5vw, 38px)/1.1 'Space Grotesk', sans-serif; }
	p { color: #94a3b8; line-height: 1.7; } .lede { font-size: 16px; } .disclose { padding: 12px 14px; border-left: 2px solid #fbbf24; background: rgba(251,191,36,.07); color: #fde68a; font-size: 13px; }
	dl { display: grid; grid-template-columns: max-content 1fr; gap: 8px 18px; margin: 20px 0; font: 12px 'JetBrains Mono', monospace; } dt { color: #71829a; letter-spacing: .1em; } dd { margin: 0; color: #e2e8f0; overflow-wrap: anywhere; }
	.cta { width: 100%; margin-top: 8px; padding: 15px 20px; border: 0; background: #2bb8b0; color: #03110f; font: 700 13px 'JetBrains Mono', monospace; letter-spacing: .14em; cursor: pointer; } .cta:hover:not(:disabled) { background: #5fd8d0; } .cta:disabled { opacity: .6; cursor: progress; }
	.err { color: #fecdd3; padding: 10px 12px; border: 1px solid rgba(251,113,133,.4); background: rgba(127,29,29,.2); overflow-wrap: anywhere; }
	pre { overflow-x: auto; padding: 12px; background: #050a15; border: 1px solid var(--nhm-border); color: #9fe7e1; font: 12px 'JetBrains Mono', monospace; }
	.clerk { min-height: 120px; display: flex; justify-content: center; }
	@media (max-width: 520px) { dl { grid-template-columns: 1fr; gap: 2px; } dd { margin-bottom: 10px; } }
</style>
