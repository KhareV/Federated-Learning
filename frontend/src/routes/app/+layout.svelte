<script lang="ts">
	// UX-only route guard: the FastAPI backend remains the authorization authority for every call.
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import type { Snippet } from 'svelte';
	import ProductShell from '$lib/components/product/ProductShell.svelte';
	import { getProductStore } from '$lib/product/state.svelte';

	let { children }: { children?: Snippet } = $props();
	const store = getProductStore();
	let checked = $state(false);
	const auth = $derived(store.authState);

	onMount(() => {
		void (async () => {
			if (store.authState.phase !== 'AUTHENTICATED') await store.init();
			checked = true;
			if (store.authState.phase === 'SIGN_IN_REQUIRED' || store.authState.phase === 'BACKEND_UNREACHABLE' || store.authState.phase === 'AUTHENTICATION_UNAVAILABLE') {
				await goto('/sign-in');
			}
		})();
	});
</script>

<svelte:head><meta name="robots" content="noindex" /></svelte:head>

{#if checked && auth.phase === 'AUTHENTICATED'}
	<ProductShell>{@render children?.()}</ProductShell>
{:else}
	<main class="boot"><div role="status"><h1>Opening the NHM workspace…</h1></div></main>
{/if}

<style>
	.boot { min-height: 100vh; display: grid; place-items: center; background: #030712; color: #94a3b8; font: 12px 'JetBrains Mono', monospace; letter-spacing: .1em; }
	.boot h1 { margin: 0; font: inherit; letter-spacing: inherit; color: inherit; }
</style>
