<script lang="ts">
	// Plain-language question -> short answer -> one-line reason. The answer and reason stay visible; exact evidence goes in the children snippet (use TechnicalEvidence).
	import type { Snippet } from 'svelte';
	let { n, question, answer, tone = 'neutral', reason, testid = undefined, children = undefined }: { n: string; question: string; answer: string; tone?: 'yes' | 'no' | 'neutral'; reason: string; testid?: string; children?: Snippet } = $props();
</script>
<section class={`q q-${tone}`} data-testid={testid}>
	<p class="k">QUESTION {n}</p><h3>{question}</h3>
	<p class="a"><span aria-hidden="true">{tone === 'yes' ? '✓' : tone === 'no' ? '✕' : '•'}</span> <b>{answer}</b></p>
	<p class="r">{reason}</p>
	{#if children}{@render children()}{/if}
</section>
<style>
	.q { border: 1px solid rgba(148,163,184,.25); padding: 14px 16px; display: grid; gap: 6px; min-width: 0; } .k { margin: 0; font: 10px 'JetBrains Mono', monospace; letter-spacing: .14em; color: #71829a; } h3 { margin: 0; font: 500 16px 'Space Grotesk', sans-serif; line-height: 1.35; }
	.a { margin: 4px 0 0; font: 600 20px 'Space Grotesk', sans-serif; overflow-wrap: anywhere; } .r { margin: 0; color: #a7b8c9; font-size: 13px; line-height: 1.6; }
	.q-yes { border-color: rgba(43,184,176,.55); } .q-yes .a { color: #2bb8b0; } .q-no { border-color: rgba(251,191,36,.55); } .q-no .a { color: #fbbf24; }
</style>
