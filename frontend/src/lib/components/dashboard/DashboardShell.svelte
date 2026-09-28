<script lang="ts">
	import { page } from '$app/state';
	import { onMount } from 'svelte';
	import type { Snippet } from 'svelte';
	import { Activity, Radio, Network, FlaskConical, Menu, X, ArrowUpRight } from '@lucide/svelte';
	import { api } from '$lib/services/api';
	const NAV = [
		{ label: 'OBSERVE', detail: 'Signals', path: '/overview', icon: Activity },
		{ label: 'MONITOR', detail: 'Central stream', path: '/monitoring', icon: Radio },
		{ label: 'DEFERRED', detail: 'Federated / hardware', path: '/fl/overview', icon: Network },
		{ label: 'LAB', detail: 'Evidence', path: '/research/analytics', icon: FlaskConical }
	];
	const GROUPS: Record<string, string> = {
		'/overview': '/overview', '/monitoring': '/monitoring', '/monitor': '/monitoring', '/signals': '/monitoring',
		'/fl': '/fl/overview', '/research': '/research/analytics', '/system': '/overview'
	};
	let { children }: { children?: Snippet } = $props();
	let mobileOpen = $state(false); let apiStatus = $state('SYNCING');
	const currentPath = $derived(page.url.pathname);
	const activePath = $derived(Object.entries(GROUPS).find(([prefix]) => currentPath.startsWith(prefix))?.[1] ?? '/overview');
	const current = $derived(NAV.find((item) => item.path === activePath) ?? NAV[0]);
	onMount(async () => { try { apiStatus = (await api.health()).status.toUpperCase(); } catch { apiStatus = 'OFFLINE'; } });
</script>
<div class:mobile-open={mobileOpen} class="dashboard-shell">
	<button class="scrim" aria-label="Close navigation" aria-hidden={!mobileOpen} onclick={() => (mobileOpen = false)}></button>
	<aside class="sidebar" aria-label="Primary workspaces">
		<a class="brand" href="/" onclick={() => (mobileOpen = false)} aria-label="NHM home"><strong>NHM</strong></a>
		<div class="nav-caption">NAVIGATION</div>
		<nav aria-label="Dashboard navigation">
			{#each NAV as item, index}
				{@const Icon = item.icon}
				<a class="nav-item" class:active={activePath === item.path} aria-current={activePath === item.path ? 'page' : undefined} href={item.path} onclick={() => (mobileOpen = false)}><span class="nav-icon"><Icon size={17} strokeWidth={1.6} /></span><span class="nav-copy"><b>{item.label}</b><small>{item.detail}</small></span><span class="nav-index">0{index + 1}</span></a>
			{/each}
		</nav>
		<div class="sidebar-footer"><span class:offline={apiStatus === 'OFFLINE'} class="sys-dot"></span><span>CORE / {apiStatus}</span><a href="/system/health" aria-label="System health"><ArrowUpRight size={13} /></a></div>
	</aside>
	<section class="dashboard-main"><header class="dashboard-header"><button class="menu-button" aria-label="Open navigation" aria-expanded={mobileOpen} onclick={() => (mobileOpen = !mobileOpen)}>{#if mobileOpen}<X size={19} />{:else}<Menu size={19} />{/if}</button><div class="header-route"><span>{current.label}</span></div><div class="header-readouts"><span class:offline={apiStatus === 'OFFLINE'} class="online"><i></i>{apiStatus}</span></div></header><div class="dashboard-body">{@render children?.()}</div></section>
</div>
<style>
	.dashboard-shell{min-height:100vh;display:flex;background:var(--nhm-bg);color:var(--nhm-text);font-family:Inter,sans-serif}.sidebar{position:sticky;top:0;z-index:30;width:224px;height:100vh;flex:0 0 224px;box-sizing:border-box;border-right:1px solid var(--nhm-border);background:linear-gradient(180deg,#050a14,#040812);display:flex;flex-direction:column}.brand{display:flex;align-items:center;gap:12px;height:76px;box-sizing:border-box;padding:16px 18px;border-bottom:1px solid var(--nhm-border);color:inherit;text-decoration:none}.brand-mark{position:relative;display:grid;place-items:center;width:34px;height:34px;border:1px solid rgba(50,214,201,.45);background:rgba(43,184,176,.07)}.brand-mark:before,.brand-mark:after{content:"";position:absolute;background:#2bb8b0}.brand-mark:before{width:12px;height:1px;left:-6px;top:16px}.brand-mark:after{height:12px;width:1px;left:16px;top:-6px}.brand-mark i{position:absolute;inset:5px;border:1px solid rgba(43,184,176,.2)}.brand-mark b{font:600 13px 'Space Grotesk',sans-serif;color:#82e9e1}.brand-copy{display:grid;gap:3px}.brand-copy strong{font:600 14px 'Space Grotesk',sans-serif;letter-spacing:.18em}.brand-copy small,.nav-caption{color:#53647b;font:7px 'JetBrains Mono',monospace;letter-spacing:.14em}.nav-caption{display:flex;justify-content:space-between;padding:22px 18px 9px}.nav-caption span{color:#2bb8b0}nav{padding:0 10px}.nav-item{position:relative;display:grid;grid-template-columns:34px 1fr auto;align-items:center;gap:10px;min-height:64px;padding:8px;color:#71829a;border:1px solid transparent;text-decoration:none;transition:.18s ease}.nav-item:hover{color:#dce9e8;background:rgba(43,184,176,.04)}.nav-item.active{color:#eef7f6;border-color:rgba(43,184,176,.18);background:linear-gradient(90deg,rgba(43,184,176,.12),rgba(43,184,176,.025))}.nav-item.active:before{content:"";position:absolute;left:-11px;top:12px;bottom:12px;width:2px;background:#2bb8b0;box-shadow:0 0 12px #2bb8b0}.nav-icon{display:grid;place-items:center;width:32px;height:32px;border:1px solid rgba(148,163,184,.12)}.active .nav-icon{color:#54d6cc;border-color:rgba(43,184,176,.35);background:rgba(43,184,176,.08)}.nav-copy{display:grid;gap:5px}.nav-copy b{font:500 9px 'JetBrains Mono',monospace;letter-spacing:.09em}.nav-copy small{font:9px Inter,sans-serif;color:#53647b}.nav-index{font:7px 'JetBrains Mono',monospace;color:#405067}.edge-card{margin:auto 12px 12px;padding:13px;border:1px solid rgba(148,163,184,.13);background:#070d19}.edge-head,.edge-vitals{display:flex;justify-content:space-between;align-items:center}.edge-head span,.edge-vitals{color:#53647b;font:7px 'JetBrains Mono',monospace;letter-spacing:.1em}.edge-head b{color:#a7b8c9;font:8px 'JetBrains Mono',monospace}.edge-card svg{width:100%;height:30px;margin:7px 0 2px}.edge-card polyline{fill:none;stroke:#fb7185;stroke-width:1.2;vector-effect:non-scaling-stroke;filter:drop-shadow(0 0 3px #fb718570)}.edge-vitals i{display:inline-block;width:5px;height:5px;margin-right:5px;border-radius:50%;background:#2bb8b0;box-shadow:0 0 7px #2bb8b0}.sidebar-footer{display:flex;align-items:center;gap:8px;padding:15px 18px;border-top:1px solid var(--nhm-border);color:#53647b;font:7px 'JetBrains Mono',monospace;letter-spacing:.11em}.sidebar-footer a{margin-left:auto;color:#71829a}.sys-dot{width:6px;height:6px;border-radius:50%;background:#2bb8b0;box-shadow:0 0 8px #2bb8b0}.sys-dot.offline{background:#fb7185;box-shadow:0 0 8px #fb7185}.dashboard-main{min-width:0;flex:1}.dashboard-header{position:sticky;top:0;z-index:20;display:flex;align-items:center;justify-content:space-between;height:58px;box-sizing:border-box;padding:0 clamp(18px,3vw,42px);border-bottom:1px solid var(--nhm-border);background:rgba(3,7,18,.88);backdrop-filter:blur(16px)}.header-route{display:flex;align-items:center;gap:11px;color:#71829a;font:8px 'JetBrains Mono',monospace;letter-spacing:.12em}.header-route i{width:24px;height:1px;background:#334155}.header-route b{color:#2bb8b0;font-weight:500}.header-readouts{display:flex;align-items:center;gap:24px}.header-readouts>span{color:#dbe7e7;font:500 11px 'Space Grotesk',sans-serif}.header-readouts small{margin-left:4px;color:#53647b;font:7px 'JetBrains Mono',monospace}.online{display:flex;align-items:center;color:#2bb8b0!important;font:7px 'JetBrains Mono',monospace!important;letter-spacing:.1em}.online i{width:6px;height:6px;margin-right:6px;border-radius:50%;background:#2bb8b0;box-shadow:0 0 8px #2bb8b0}.online.offline{color:#fb7185!important}.online.offline i{background:#fb7185}.dashboard-body{padding:clamp(20px,3vw,42px)}.menu-button,.scrim{display:none}@media(max-width:760px){.sidebar{position:fixed;transform:translateX(-102%);transition:transform .25s}.mobile-open .sidebar{transform:translateX(0)}.mobile-open .scrim{display:block;position:fixed;z-index:25;inset:0;border:0;background:rgba(0,0,0,.65)}.menu-button{display:grid;place-items:center;border:0;color:#b7c6d4;background:transparent}.header-route i,.header-route b,.header-readouts>span:not(.online){display:none}.dashboard-header{padding:0 14px}.dashboard-body{padding:18px 14px 36px}}
</style>
