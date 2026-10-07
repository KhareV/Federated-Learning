<script lang="ts">
	// One navigation system for the product. The backend remains the auth authority.
	import { page } from '$app/state';
	import type { Snippet } from 'svelte';
	import { LayoutDashboard, Watch, Activity, History, Network, Boxes, FlaskConical, Server, Info, LogOut, Menu, X } from '@lucide/svelte';
	import DemoBanner from './DemoBanner.svelte';
	import { getProductStore } from '$lib/product/state.svelte';

	let { children }: { children?: Snippet } = $props();
	const store = getProductStore();
	let open = $state(false);
	let menuButton: HTMLButtonElement;

	const NAV = [
		{ label: 'Overview', href: '/app', icon: LayoutDashboard, exact: true },
		{ label: 'Device', href: '/app/device', icon: Watch },
		{ label: 'Monitor', href: '/app/monitoring', icon: Activity },
		{ label: 'History', href: '/app/history', icon: History },
		{ label: 'Federation', href: '/app/federation', icon: Network, children: [
			{ label: 'Clients', href: '/app/federation/clients' }, { label: 'Rounds', href: '/app/federation/rounds' },
			{ label: 'Live', href: '/app/federation/live' }, { label: 'Privacy', href: '/app/federation/privacy' }] },
		{ label: 'Models', href: '/app/models', icon: Boxes },
		{ label: 'Research', href: '/app/research/ml', icon: FlaskConical, children: [
			{ label: 'ML evidence', href: '/app/research/ml' }, { label: 'FL evidence', href: '/app/research/fl' }] },
		{ label: 'System', href: '/app/system', icon: Server },
		{ label: 'About', href: '/app/about', icon: Info }
	];
	const path = $derived(page.url.pathname.replace(/\/$/, '') || '/');
	const section = (item: { href: string; exact?: boolean }) => (item.exact ? path === item.href : path === item.href || path.startsWith(item.href + '/') || (item.href === '/app/research/ml' && path.startsWith('/app/research')));
	const identity = $derived(store.authState.identity);
	const system = $derived(store.authState.system);
	async function signOut() { await store.auth.signOut(); location.assign('/sign-in'); }
	function onKeydown(event: KeyboardEvent) {
		if (event.key === 'Escape' && open) { open = false; menuButton?.focus(); }
	}
</script>

<svelte:window onkeydown={onKeydown} />
<a class="skip" href="#main-content">Skip to content</a>
{#if system?.demo_mode}<DemoBanner />{/if}
<div class="shell" class:open>
	<button class="scrim" aria-label="Close navigation" tabindex="-1" onclick={() => (open = false)}></button>
	<aside id="product-navigation" class="side" aria-label="Product navigation">
		<a class="brand" href="/" aria-label="NHM home"><span>N</span>NHM</a>
		<nav aria-label="Product sections">
			{#each NAV as item}
				{@const Icon = item.icon}
				<a class="item" class:active={section(item)} aria-current={path === item.href ? 'page' : undefined} href={item.href} onclick={() => (open = false)}><Icon size={16} strokeWidth={1.7} aria-hidden="true" /><span>{item.label}</span></a>
				{#if item.children && section(item)}
					<div class="sub">{#each item.children as child}<a class:active={path === child.href} aria-current={path === child.href ? 'page' : undefined} href={child.href} onclick={() => (open = false)}>{child.label}</a>{/each}</div>
				{/if}
			{/each}
		</nav>
		<div class="foot"><span class="tag">SIMULATED ONLY</span><span class="tag">RESEARCH / NOT DIAGNOSTIC</span></div>
	</aside>
	<div class="main">
		<header>
			<button bind:this={menuButton} class="menu" aria-label={open ? 'Close navigation' : 'Open navigation'} aria-expanded={open} aria-controls="product-navigation" onclick={() => (open = !open)}>{#if open}<X size={19} />{:else}<Menu size={19} />{/if}</button>
			<div class="who" data-testid="identity-chip">
				{#if identity}<span class="mode">{identity.auth_provider}</span><strong>{identity.user_id}</strong>{:else}<span class="mode">NOT SIGNED IN</span>{/if}
			</div>
			<button class="out" onclick={signOut} aria-label="Sign out"><LogOut size={15} aria-hidden="true" /><span>Sign out</span></button>
		</header>
		<main id="main-content" tabindex="-1">{@render children?.()}</main>
	</div>
</div>

<style>
	.skip { position: absolute; left: -999px; top: 0; z-index: 100; padding: 10px 14px; background: #2bb8b0; color: #030712; } .skip:focus { left: 8px; top: 8px; }
	.shell { min-height: 100vh; display: flex; background: var(--nhm-bg); color: var(--nhm-text); font-family: Inter, sans-serif; }
	.side { position: sticky; top: 0; align-self: flex-start; width: 232px; flex: 0 0 232px; height: 100vh; box-sizing: border-box; display: flex; flex-direction: column; border-right: 1px solid var(--nhm-border); background: linear-gradient(180deg,#050a14,#040812); overflow-y: auto; }
	.brand { display: flex; align-items: center; gap: 10px; height: 68px; padding: 0 18px; border-bottom: 1px solid var(--nhm-border); color: inherit; text-decoration: none; font: 600 14px 'Space Grotesk', sans-serif; letter-spacing: .18em; }
	.brand span { display: grid; place-items: center; width: 28px; height: 28px; border: 1px solid #2bb8b0; color: #2bb8b0; letter-spacing: 0; }
	nav { display: grid; gap: 2px; padding: 14px 10px; }
	.item { display: flex; align-items: center; gap: 12px; padding: 11px 12px; border: 1px solid transparent; color: #94a3b8; text-decoration: none; font: 500 13px 'Space Grotesk', sans-serif; letter-spacing: .04em; }
	.item:hover { color: #eef7f6; background: rgba(43,184,176,.05); } .item.active { color: #eef7f6; border-color: rgba(43,184,176,.3); background: rgba(43,184,176,.1); }
	.sub { display: grid; margin: 0 0 4px 26px; border-left: 1px solid var(--nhm-border); } .sub a { padding: 7px 14px; color: #71829a; text-decoration: none; font: 11px 'JetBrains Mono', monospace; letter-spacing: .08em; } .sub a.active, .sub a:hover { color: #2bb8b0; }
	.foot { margin-top: auto; display: grid; gap: 6px; padding: 14px 18px; border-top: 1px solid var(--nhm-border); } .tag { color: #71829a; font: 10px 'JetBrains Mono', monospace; letter-spacing: .1em; }
	.main { flex: 1; min-width: 0; display: flex; flex-direction: column; }
	header { position: sticky; top: 0; z-index: 20; display: flex; align-items: center; justify-content: space-between; gap: 12px; min-height: 58px; padding: 0 clamp(14px, 3vw, 40px); border-bottom: 1px solid var(--nhm-border); background: rgba(3,7,18,.92); backdrop-filter: blur(14px); }
	.who { display: flex; align-items: center; gap: 10px; min-width: 0; } .who strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font: 500 13px 'Space Grotesk', sans-serif; }
	.mode { padding: 3px 8px; border: 1px solid rgba(43,184,176,.5); color: #2bb8b0; font: 10px 'JetBrains Mono', monospace; letter-spacing: .1em; }
	.out, .menu { display: inline-flex; align-items: center; gap: 8px; padding: 8px 12px; border: 1px solid var(--nhm-border); background: transparent; color: #cbd5e1; font: 12px 'JetBrains Mono', monospace; cursor: pointer; } .out:hover, .menu:hover { color: #2bb8b0; border-color: #2bb8b0; }
	.menu, .scrim { display: none; }
	main { padding: clamp(16px, 3vw, 40px); min-width: 0; } main:focus { outline: none; }
	@media (max-width: 860px) {
		.side { position: fixed; z-index: 40; left: 0; top: 0; transform: translateX(-102%); transition: transform .2s; } .open .side { transform: none; }
		.open .scrim { display: block; position: fixed; z-index: 35; inset: 0; border: 0; background: rgba(0,0,0,.65); }
		.menu { display: inline-flex; } .out span { display: none; } .out { padding: 8px 10px; }
	}
	@media (prefers-reduced-motion: reduce) { .side { transition: none; } }
	.who{max-width:min(60vw,600px)}.who strong{min-width:0}.out:focus-visible,.menu:focus-visible,.brand:focus-visible,.item:focus-visible,.sub a:focus-visible{outline:2px solid #fbbf24;outline-offset:2px}
	@media(max-width:390px){.who{max-width:calc(100vw - 165px)}.who .mode{flex-shrink:0}.out,.menu{min-width:36px;justify-content:center}}
</style>
