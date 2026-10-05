<script lang="ts">
	// Navigation shell for destinations that later capstone phases own. It shows NO data.
	let { title, owner, note = '', links = [] }: { title: string; owner: string; note?: string; links?: { href: string; label: string }[] } = $props();
</script>

<section class="future" data-testid="future-phase">
	<div class="tag">NOT YET ENABLED IN THIS PHASE</div>
	<h1>{title}</h1>
	<p>{note || 'This product surface is planned for a later capstone phase. Nothing here is live.'}</p>
	<dl><dt>OWNER PHASE</dt><dd>{owner}</dd><dt>STATUS</dt><dd>No runtime, no data, no placeholder metrics</dd></dl>
	{#if links.length}<ul>{#each links as link}<li><a href={link.href}>{link.label} →</a></li>{/each}</ul>{/if}
</section>

<style>
	.future { max-width: 760px; padding: clamp(18px, 3vw, 32px); border: 1px dashed rgba(148,163,184,.35); background: rgba(8,14,29,.6); }
	.tag { color: #fbbf24; font: 11px 'JetBrains Mono', monospace; letter-spacing: .14em; }
	h1 { margin: 14px 0 10px; font: 500 clamp(26px, 4vw, 40px)/1.1 'Space Grotesk', sans-serif; }
	p { margin: 0 0 18px; color: #94a3b8; font-size: 15px; line-height: 1.7; }
	dl { display: grid; grid-template-columns: max-content 1fr; gap: 6px 18px; margin: 0 0 18px; font: 12px 'JetBrains Mono', monospace; }
	dt { color: #71829a; letter-spacing: .1em; } dd { margin: 0; color: #cbd5e1; }
	ul { margin: 0; padding: 0; list-style: none; display: grid; gap: 8px; } a { color: #2bb8b0; font: 12px 'JetBrains Mono', monospace; letter-spacing: .08em; text-decoration: none; } a:hover { text-decoration: underline; }
</style>
